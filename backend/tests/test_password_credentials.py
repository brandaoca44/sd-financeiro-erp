"""Valida armazenamento de hashes em banco temporário exclusivo."""

import asyncio
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import undefer

from database_support import DatabaseTestCase
from app.modules.identity.models import User, UserPasswordCredential
from app.modules.identity.passwords import hash_password, verify_password


class PasswordCredentialTests(DatabaseTestCase):
    """Exercita constraints, carregamento restrito e reversibilidade da migration."""

    async def _user(self):
        user = User(name="Pessoa fictícia", email=f"{uuid4().hex}@example.invalid")
        self.session.add(user)
        await self.session.flush()
        return user

    async def test_stores_hash_and_requires_explicit_loading(self):
        user = await self._user()
        password = SecretStr("senha somente para teste")
        hashed = await hash_password(password)
        self.session.add(UserPasswordCredential(user_id=user.id, password_hash=hashed.get_secret_value()))
        await self.session.flush()
        self.session.expunge_all()
        credential = await self.session.get(UserPasswordCredential, user.id)
        self.assertIn("password_hash", inspect(credential).unloaded)
        credential = await self.session.scalar(select(UserPasswordCredential).options(
            undefer(UserPasswordCredential.password_hash)
        ).where(UserPasswordCredential.user_id == user.id))
        self.assertTrue((await verify_password(password, credential.password_hash))[0])
        self.assertNotEqual(credential.password_hash, password.get_secret_value())

    async def test_database_rejects_plaintext_and_missing_user(self):
        user = await self._user()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(UserPasswordCredential(user_id=user.id, password_hash="senha em texto puro"))
                await self.session.flush()
        hashed = await hash_password(SecretStr("senha ficticia sem usuario"))
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(UserPasswordCredential(user_id=uuid4(), password_hash=hashed.get_secret_value()))
                await self.session.flush()

    async def test_one_credential_per_user_and_restricted_deletion(self):
        user = await self._user()
        hashed = await hash_password(SecretStr("senha ficticia com vinculo"))
        credential = UserPasswordCredential(user_id=user.id, password_hash=hashed.get_secret_value())
        self.session.add(credential)
        await self.session.flush()
        self.session.expunge(credential)
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(UserPasswordCredential(user_id=user.id, password_hash=hashed.get_secret_value()))
                await self.session.flush()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                await self.session.execute(delete(User).where(User.id == user.id))

    async def test_migration_round_trip_preserves_users(self):
        user = await self._user()
        await self.session.commit()
        user_id = user.id
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration, "downgrade", "4db0f645bda1")
            table = await self.session.scalar(text("SELECT to_regclass('public.user_password_credentials')"))
            self.assertIsNone(table)
            self.assertIsNotNone(await self.session.get(User, user_id))
        finally:
            await self.session.close()
            await self.engine.dispose()
            await asyncio.to_thread(self.run_migration, "upgrade", "head")
        await asyncio.to_thread(self.run_migration, "check")
