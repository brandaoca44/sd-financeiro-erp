"""Testes opt-in em banco temporário exclusivo no PostgreSQL local do ERP."""

import asyncio
import os
import selectors
import subprocess
import sys
import unittest
from pathlib import Path
from uuid import UUID, uuid4
from unittest.mock import patch

import psycopg
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.modules.organizations.models import OrganizationStatus
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import OrganizationCreate, OrganizationResponse
from app.modules.organizations.service import OrganizationService


@unittest.skipUnless(
    os.environ.get("SD_RUN_DATABASE_TESTS") == "1",
    "Defina SD_RUN_DATABASE_TESTS=1 para criar um banco temporário exclusivo.",
)
class OrganizationRepositoryTests(unittest.IsolatedAsyncioTestCase):
    """Aplica migrations no banco temporário e o remove ao concluir a suíte."""

    loop_factory = staticmethod(
        lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    )

    @classmethod
    def setUpClass(cls):
        cls.settings = Settings()
        if cls.settings.database_host != "127.0.0.1" or cls.settings.database_port != 5433:
            raise RuntimeError("Os testes exigem o PostgreSQL local do ERP na porta 5433.")
        cls.test_database = "sd_repository_test_" + uuid4().hex
        cls.database_created = False
        cls.addClassCleanup(cls._drop_test_database)
        try:
            with cls._maintenance_connection() as connection:
                connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.test_database))
                )
            cls.database_created = True
        except psycopg.Error:
            raise RuntimeError("Não foi possível criar o banco exclusivo de testes.") from None

        environment = os.environ.copy()
        environment.update(
            DATABASE_NAME=cls.test_database,
            DATABASE_HOST="127.0.0.1",
            DATABASE_PORT="5433",
            DATABASE_USER=cls.settings.database_user,
            DATABASE_PASSWORD=cls.settings.database_password.get_secret_value(),
            DATABASE_ECHO="false",
        )
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=Path(__file__).resolve().parents[1],
            env=environment, capture_output=True, timeout=60,
        )
        if result.returncode:
            raise RuntimeError("Falha ao aplicar migrations no banco exclusivo de testes.")

    @classmethod
    def _maintenance_connection(cls):
        # Conecta ao catálogo administrativo, nunca ao banco de negócio do ERP.
        return psycopg.connect(
            host="127.0.0.1", port=5433, dbname="postgres",
            user=cls.settings.database_user,
            password=cls.settings.database_password.get_secret_value(),
            autocommit=True, connect_timeout=5,
        )

    @classmethod
    def _drop_test_database(cls):
        if not cls.database_created:
            return
        if not cls.test_database.startswith("sd_repository_test_"):
            raise RuntimeError("Nome de banco temporário inválido; remoção bloqueada.")
        UUID(cls.test_database.removeprefix("sd_repository_test_"))
        with cls._maintenance_connection() as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {}").format(sql.Identifier(cls.test_database))
            )

    async def asyncSetUp(self):
        settings = self.settings.model_copy(update={"database_name": self.test_database})
        self.engine = create_async_engine(
            settings.database_url, echo=False, connect_args={"connect_timeout": 5}
        )
        self.addAsyncCleanup(self.engine.dispose)
        self.session = AsyncSession(self.engine, expire_on_commit=False)
        self.addAsyncCleanup(self.session.close)
        self.repository = OrganizationRepository(self.session)

    async def test_create_returns_generated_fields(self):
        organization = await self.repository.create(name="Empresa de teste")
        self.assertIsInstance(organization.id, UUID)
        self.assertEqual(organization.status, OrganizationStatus.ACTIVE)
        self.assertIsNotNone(organization.created_at.tzinfo)
        self.assertIsNotNone(organization.updated_at.tzinfo)
        response = OrganizationResponse.model_validate(organization)
        self.assertEqual(response.name, "Empresa de teste")

    async def test_commit_by_caller_persists_for_another_session(self):
        organization = await self.repository.create(name="Organização persistida")
        await self.session.commit()
        async with AsyncSession(self.engine) as reader:
            found = await OrganizationRepository(reader).get_by_id(organization.id)
            self.assertIsNotNone(found)
            self.assertEqual(found.name, "Organização persistida")

    async def test_create_does_not_commit_and_can_be_rolled_back(self):
        organization = await self.repository.create(name="Organização temporária")
        organization_id = organization.id
        async with AsyncSession(self.engine) as reader:
            self.assertIsNone(
                await OrganizationRepository(reader).get_by_id(organization_id)
            )
        await self.session.rollback()
        self.assertIsNone(await self.repository.get_by_id(organization_id))

    async def test_get_by_id_returns_only_requested_organization(self):
        first = await self.repository.create(name="Primeira")
        second = await self.repository.create(name="Segunda")
        self.session.expunge_all()
        found = await self.repository.get_by_id(first.id)
        self.assertEqual(found.id, first.id)
        self.assertEqual(found.name, "Primeira")
        self.assertNotEqual(found.id, second.id)

    async def test_get_by_id_returns_none_when_missing(self):
        self.assertIsNone(await self.repository.get_by_id(uuid4()))

    async def test_service_create_commits_and_returns_response(self):
        response = await OrganizationService(self.session).create(
            OrganizationCreate(name="  Empresa do service  ")
        )
        self.assertIsInstance(response, OrganizationResponse)
        self.assertEqual(response.name, "Empresa do service")
        self.assertEqual(response.status, OrganizationStatus.ACTIVE)
        async with AsyncSession(self.engine) as reader:
            found = await OrganizationService(reader).get_by_id(response.id)
            self.assertEqual(found, response)

    async def test_service_missing_organization_returns_none(self):
        self.assertIsNone(await OrganizationService(self.session).get_by_id(uuid4()))

    async def test_service_rolls_back_when_response_conversion_fails(self):
        from pydantic import ValidationError

        created_ids = []
        original_create = OrganizationRepository.create

        async def create_invalid_response(repository, *, name):
            organization = await original_create(repository, name=name)
            created_ids.append(organization.id)
            organization.created_at = None
            return organization

        with patch.object(OrganizationRepository, "create", create_invalid_response):
            with self.assertRaises(ValidationError):
                await OrganizationService(self.session).create(OrganizationCreate(name="Reverter"))
        async with AsyncSession(self.engine) as reader:
            self.assertIsNone(
                await OrganizationRepository(reader).get_by_id(created_ids[0])
            )
        self.assertFalse(self.session.in_transaction())

    async def test_service_propagates_persistence_failure_and_releases_transaction(self):
        from sqlalchemy.exc import SQLAlchemyError

        with patch.object(OrganizationRepository, "create", side_effect=SQLAlchemyError("falha simulada")):
            with self.assertRaises(SQLAlchemyError):
                await OrganizationService(self.session).create(OrganizationCreate(name="Reverter"))
        self.assertFalse(self.session.in_transaction())
        response = await OrganizationService(self.session).create(OrganizationCreate(name="Recuperada"))
        self.assertEqual(response.name, "Recuperada")
