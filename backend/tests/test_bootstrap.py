"""Valida bootstrap administrativo sem criar conta no banco de negócio."""

import asyncio
import getpass
import io
import os
import subprocess
import sys
import unittest
import warnings
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from pydantic import SecretStr, ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from database_support import DatabaseTestCase
from app.core.config import Settings
from app.modules.identity import bootstrap_cli
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.bootstrap import (
    BootstrapAccountConflictError, BootstrapAlreadyInitializedError,
    BootstrapOperatorInput, PlatformBootstrapService,
)
from app.modules.identity.models import (
    OrganizationMembership, PlatformBootstrap, User, UserPasswordCredential, UserSession, UserStatus,
)
from app.modules.identity.passwords import verify_password
from app.modules.organizations.models import Organization


def operator_data(**changes):
    return BootstrapOperatorInput(**{
        "name": "Operador de teste", "email": "operador@example.com",
        "password": SecretStr("frase longa exclusiva de teste"), **changes,
    })


class BootstrapInputTests(unittest.TestCase):
    def test_normalizes_name_email_and_masks_password(self):
        data = operator_data(name="  Operador  ", email=" OPERADOR@EXAMPLE.COM ")
        self.assertEqual(data.name, "Operador")
        self.assertEqual(str(data.email), "operador@example.com")
        self.assertNotIn(data.password.get_secret_value(), repr(data))

    def test_rejects_invalid_data_and_privilege_overrides(self):
        for changes in ({"name": " "}, {"email": "invalido"}, {"password": "curta"},
                        {"password": "x" * 129}, {"status": "ACTIVE"},
                        {"can_provision_organizations": True}):
            with self.subTest(fields=list(changes)), self.assertRaises(ValidationError):
                operator_data(**changes)

    def test_rejects_locally_blocked_and_repeated_passwords(self):
        for password in ("Password123456789", "123456789012345", "a" * 20):
            with self.assertRaises(ValidationError):
                operator_data(password=SecretStr(password))


class BootstrapCliTests(unittest.TestCase):
    def _run(self, *, answers=None, passwords=None, create=None, arguments=None, interactive=True):
        output, errors = io.StringIO(), io.StringIO()
        settings = Settings(_env_file=None, database_password="senha_ficticia")
        creator = create or AsyncMock(return_value=uuid4())
        with patch.object(bootstrap_cli.sys.stdin, "isatty", return_value=interactive), \
             patch.object(bootstrap_cli, "Settings", return_value=settings), \
             patch("builtins.input", side_effect=answers or ["CRIAR", "Operador", "operador@example.com"]), \
             patch.object(bootstrap_cli.getpass, "getpass", side_effect=passwords or ["senha ficticia longa", "senha ficticia longa"]), \
             patch.object(bootstrap_cli, "_create_operator", creator), \
             redirect_stdout(output), redirect_stderr(errors):
            code = bootstrap_cli.main(arguments or [])
        return code, output.getvalue() + errors.getvalue(), creator

    def test_success_uses_hidden_confirmed_password_without_printing_it(self):
        code, output, creator = self._run()
        self.assertEqual(code, 0)
        creator.assert_awaited_once()
        self.assertNotIn("senha ficticia longa", output)
        self.assertNotIn("operador@example.com", output)

    def test_rejects_arguments_without_echoing_potential_secret(self):
        code, output, creator = self._run(arguments=["--password", "segredo_ficticio"])
        self.assertEqual(code, 2)
        self.assertNotIn("segredo_ficticio", output)
        creator.assert_not_awaited()

    def test_noninteractive_input_is_rejected(self):
        code, _, creator = self._run(interactive=False)
        self.assertEqual(code, 2)
        creator.assert_not_awaited()

    def test_cancel_or_mismatched_password_does_not_write(self):
        code, _, creator = self._run(answers=["CANCELAR"])
        self.assertEqual(code, 1)
        creator.assert_not_awaited()
        code, output, creator = self._run(passwords=["senha ficticia longa", "diferente"])
        self.assertEqual(code, 2)
        self.assertNotIn("senha ficticia longa", output)
        creator.assert_not_awaited()

    def test_getpass_warning_aborts_instead_of_using_visible_input(self):
        def unsafe_getpass(*args):
            warnings.warn("Terminal sem ocultação", getpass.GetPassWarning)
            self.fail("Não deve continuar após aviso de senha visível.")

        code, _, creator = self._run(passwords=unsafe_getpass)
        self.assertEqual(code, 2)
        creator.assert_not_awaited()

    def test_infrastructure_error_is_sanitized(self):
        code, output, _ = self._run(create=AsyncMock(side_effect=RuntimeError("credencial_privada_ficticia")))
        self.assertEqual(code, 1)
        self.assertNotIn("credencial_privada_ficticia", output)

    def test_invalid_fields_are_identified_without_echoing_entered_values(self):
        for answers, passwords, expected, private in (
            (["CRIAR", " ", "operador@example.com"], None, "Nome:", "operador@example.com"),
            (["CRIAR", "Operador", "email_privado_invalido"], None, "E-mail:", "email_privado_invalido"),
            (None, ["curta@1", "curta@1"], "Senha: use entre 8 e 128", "curta@1"),
            (None, ["a" * 20, "a" * 20], "Senha: escolha uma frase", "a" * 20),
        ):
            with self.subTest(field=expected):
                code, output, creator = self._run(answers=answers, passwords=passwords)
                self.assertEqual(code, 2)
                self.assertIn(expected, output)
                self.assertNotIn(private, output)
                creator.assert_not_awaited()

    def test_special_characters_are_accepted_by_cli(self):
        password = "Ab@12#xy"
        code, output, creator = self._run(passwords=[password, password])
        self.assertEqual(code, 0)
        creator.assert_awaited_once()
        self.assertNotIn(password, output)

    def test_settings_validation_is_not_reported_as_invalid_account_data(self):
        with self.assertRaises(ValidationError) as caught:
            Settings(_env_file=None, database_password="privado_ficticio", database_port="porta_privada")
        message = bootstrap_cli._validation_message(caught.exception)
        self.assertIn("Configuração inválida", message)
        self.assertNotIn("privado_ficticio", message)
        self.assertNotIn("porta_privada", message)


class BootstrapDatabaseTests(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        # Esta classe possui seu próprio banco temporário; serviços confirmam transações.
        self.addAsyncCleanup(self._clear_test_data)

    async def _clear_test_data(self):
        await self.session.rollback()
        for model in (PlatformBootstrap, UserPasswordCredential, OrganizationMembership, UserSession, User, Organization):
            await self.session.execute(delete(model))
        await self.session.commit()

    async def test_creates_active_operator_hash_marker_without_tenant_access_or_session(self):
        data = operator_data()
        settings = self.settings.model_copy(update={"database_name": self.test_database})
        user_id = await bootstrap_cli._create_operator(settings, data)
        user = await self.session.get(User, user_id)
        self.assertEqual(user.status, UserStatus.ACTIVE)
        self.assertTrue(user.can_provision_organizations)
        credential = await self.session.scalar(select(UserPasswordCredential).options(
            undefer(UserPasswordCredential.password_hash)
        ).where(UserPasswordCredential.user_id == user_id))
        self.assertTrue((await verify_password(data.password, credential.password_hash))[0])
        marker = await self.session.get(PlatformBootstrap, 1)
        self.assertEqual(marker.user_id, user_id)
        for model in (OrganizationMembership, UserSession, Organization):
            self.assertEqual(await self.session.scalar(select(func.count()).select_from(model)), 0)
        self.assertFalse(await OrganizationAccessPolicy(self.session).can_read_organization(user_id, uuid4()))

    async def test_repetition_is_denied_even_after_operator_is_demoted(self):
        user_id = await PlatformBootstrapService(self.session).create_operator(operator_data())
        async with self.session.begin():
            await self.session.execute(update(User).where(User.id == user_id).values(
                can_provision_organizations=False, status=UserStatus.INACTIVE,
            ))
        with self.assertRaises(BootstrapAlreadyInitializedError):
            await PlatformBootstrapService(self.session).create_operator(operator_data(email="outro@example.com"))

    async def test_preexisting_operator_blocks_bootstrap_without_marker(self):
        self.session.add(User(name="Existente", email="existente@example.com", can_provision_organizations=True))
        await self.session.commit()
        with self.assertRaises(BootstrapAlreadyInitializedError):
            await PlatformBootstrapService(self.session).create_operator(operator_data())

    async def test_existing_account_is_not_promoted_or_given_password(self):
        user = User(name="Sem privilégios", email="operador@example.com")
        self.session.add(user)
        await self.session.commit()
        user_id = user.id
        with self.assertRaises(BootstrapAccountConflictError):
            await PlatformBootstrapService(self.session).create_operator(operator_data())
        existing = await self.session.get(User, user_id)
        self.assertEqual(existing.status, UserStatus.INACTIVE)
        self.assertFalse(existing.can_provision_organizations)
        self.assertIsNone(await self.session.get(UserPasswordCredential, user_id))

    async def test_persistence_failure_rolls_back_user_and_marker(self):
        service = PlatformBootstrapService(self.session)
        original_flush = self.session.flush
        calls = 0

        async def fail_second_flush(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("falha de teste")
            return await original_flush(*args, **kwargs)

        with patch.object(self.session, "flush", side_effect=fail_second_flush):
            with self.assertRaises(RuntimeError):
                await service.create_operator(operator_data())
        self.assertFalse(self.session.in_transaction())
        for model in (User, UserPasswordCredential, PlatformBootstrap):
            self.assertEqual(await self.session.scalar(select(func.count()).select_from(model)), 0)

    async def test_parallel_initialization_creates_exactly_one_operator(self):
        async def initialize(email):
            async with AsyncSession(self.engine, expire_on_commit=False) as writer:
                return await PlatformBootstrapService(writer).create_operator(operator_data(email=email))

        results = await asyncio.gather(
            initialize("primeiro@example.com"), initialize("segundo@example.com"), return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(result, BootstrapAlreadyInitializedError) for result in results), 1)
        self.assertEqual(sum(not isinstance(result, Exception) for result in results), 1)
        for model in (User, UserPasswordCredential, PlatformBootstrap):
            self.assertEqual(await self.session.scalar(select(func.count()).select_from(model)), 1)

    async def test_cli_helper_creates_from_clean_python_process(self):
        environment = os.environ.copy()
        environment.update(
            DATABASE_NAME=self.test_database, DATABASE_HOST="127.0.0.1", DATABASE_PORT="5433",
            DATABASE_USER=self.settings.database_user,
            DATABASE_PASSWORD=self.settings.database_password.get_secret_value(), DATABASE_ECHO="false",
        )
        code = (
            "import asyncio, selectors; "
            "from app.core.config import Settings; "
            "from app.modules.identity.bootstrap import BootstrapOperatorInput; "
            "from app.modules.identity.bootstrap_cli import _create_operator; "
            "data=BootstrapOperatorInput(name='Operador',email='processo@example.com',"
            "password='frase somente ficticia de teste'); "
            "asyncio.run(_create_operator(Settings(),data),"
            "loop_factory=lambda:asyncio.SelectorEventLoop(selectors.SelectSelector()))"
        )
        result = await asyncio.to_thread(
            subprocess.run, [sys.executable, "-c", code], env=environment,
            cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, "Falha no bootstrap em processo independente.")
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(PlatformBootstrap)), 1)

    async def test_singleton_constraint_rejects_other_marker_ids(self):
        user = User(name="Pessoa", email="pessoa@example.com")
        self.session.add(user)
        await self.session.flush()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(PlatformBootstrap(id=2, user_id=user.id))
                await self.session.flush()

    async def test_migration_round_trip_preserves_operator_credentials_and_blocks_rebootstrap(self):
        user_id = await PlatformBootstrapService(self.session).create_operator(operator_data())
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration, "downgrade", "ba72c81409ef")
            self.assertIsNotNone(await self.session.get(User, user_id))
            self.assertIsNotNone(await self.session.get(UserPasswordCredential, user_id))
        finally:
            await self.session.close()
            await self.engine.dispose()
            await asyncio.to_thread(self.run_migration, "upgrade", "head")
        with self.assertRaises(BootstrapAlreadyInitializedError):
            await PlatformBootstrapService(self.session).create_operator(operator_data(email="outro@example.com"))
        await asyncio.to_thread(self.run_migration, "check")
