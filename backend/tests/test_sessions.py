"""Valida emissão, resolução e revogação de sessões sem expor autenticação HTTP."""

import asyncio
import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database_support import DatabaseTestCase
from app.modules.identity.models import User, UserPasswordCredential, UserSession, UserStatus
from app.modules.identity.passwords import hash_password
from app.modules.identity.sessions import SessionIssueDeniedError, SessionService


class SessionConfigurationTests(unittest.TestCase):
    """Rejeita configuração insegura e relógio sem fuso antes de consultar o banco."""

    def test_rejects_invalid_idle_timeouts(self):
        for idle_timeout in (None, 1800, timedelta(0), timedelta(seconds=-1), timedelta(days=2)):
            with self.subTest(idle_timeout=idle_timeout), self.assertRaises(ValueError):
                SessionService(MagicMock(), idle_timeout=idle_timeout)

    def test_rejects_naive_clock(self):
        service = SessionService(MagicMock(), clock=lambda: datetime(2026, 10, 31))
        with self.assertRaises(ValueError):
            service._now()


class SessionTests(DatabaseTestCase):
    """Usa banco e relógio controlados para testar o ciclo completo das sessões."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        self.service = SessionService(self.session, clock=lambda: self.now)

    async def _user(self, *, active=True):
        user = User(
            name="Pessoa de teste", email=f"{uuid4().hex}@example.invalid",
            status=UserStatus.ACTIVE if active else UserStatus.INACTIVE,
        )
        self.session.add(user)
        await self.session.commit()
        return user

    async def _revoke(self, token):
        async with AsyncSession(self.engine) as writer:
            await SessionService(writer, clock=lambda: self.now).revoke(token)

    async def test_issue_persists_only_hash_and_resolves_identity(self):
        user = await self._user()
        issued = await self.service.issue_for_authenticated_user(user.id)
        self.assertEqual(issued.expires_at, self.now + timedelta(minutes=30))
        self.assertNotIn(issued.token.get_secret_value(), repr(issued))
        async with AsyncSession(self.engine) as reader:
            row = (await reader.execute(select(
                UserSession.id, UserSession.user_id, UserSession.token_hash,
            ).where(UserSession.id == issued.id))).one()
            self.assertEqual(row.user_id, user.id)
            self.assertEqual(row.token_hash, hashlib.sha256(
                issued.token.get_secret_value().encode("ascii")
            ).hexdigest())
            self.assertNotEqual(row.token_hash, issued.token.get_secret_value())
        resolved = await self.service.resolve(issued.token)
        self.assertEqual(resolved.id, issued.id)
        self.assertEqual(resolved.user_id, user.id)
        self.assertFalse(hasattr(resolved, "token"))

    async def test_issue_requires_active_existing_user(self):
        inactive = await self._user(active=False)
        inactive_id = inactive.id
        for user_id in (inactive_id, uuid4(), None, "id-invalido"):
            with self.subTest(user_id=user_id), self.assertRaises(SessionIssueDeniedError):
                await self.service.issue_for_authenticated_user(user_id)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(UserSession).where(
            UserSession.user_id == inactive_id,
        )), 0)

    async def test_unknown_malformed_and_non_secret_tokens_are_rejected(self):
        for token in (None, "A" * 43, SecretStr(""), SecretStr("a" * 42),
                      SecretStr("a" * 44), SecretStr("á" * 43), SecretStr("A" * 43)):
            with self.subTest(token_type=type(token).__name__):
                self.assertIsNone(await self.service.resolve(token))

    async def test_modified_token_is_rejected(self):
        user = await self._user()
        issued = await self.service.issue_for_authenticated_user(user.id)
        original = issued.token.get_secret_value()
        changed = ("A" if original[0] != "A" else "B") + original[1:]
        self.assertIsNone(await self.service.resolve(SecretStr(changed)))

    async def test_idle_deadline_is_exclusive_without_activity(self):
        user = await self._user()
        issued = await self.service.issue_for_authenticated_user(user.id)
        self.now = issued.expires_at - timedelta(microseconds=1)
        self.assertIsNotNone(await self.service.resolve(issued.token))
        self.now = issued.expires_at
        self.assertIsNone(await self.service.resolve(issued.token))
        self.now += timedelta(seconds=1)
        self.assertIsNone(await self.service.resolve(issued.token))

    async def test_future_session_is_not_resolved(self):
        user = await self._user()
        issued = await self.service.issue_for_authenticated_user(user.id)
        self.now -= timedelta(seconds=1)
        self.assertIsNone(await self.service.resolve(issued.token))

    async def test_inactive_user_is_rejected_even_with_previously_valid_session(self):
        user = await self._user()
        issued = await self.service.issue_for_authenticated_user(user.id)
        self.assertIsNotNone(await self.service.resolve(issued.token))
        async with AsyncSession(self.engine) as writer:
            async with writer.begin():
                await writer.execute(update(User).where(User.id == user.id).values(status=UserStatus.INACTIVE))
        self.assertIsNone(await self.service.resolve(issued.token))

    async def test_logout_revokes_immediately_for_existing_reader(self):
        user = await self._user()
        issued = await self.service.issue_for_authenticated_user(user.id)
        self.assertIsNotNone(await self.service.resolve(issued.token))
        await self._revoke(issued.token)
        self.assertIsNone(await self.service.resolve(issued.token))

    async def test_revocation_is_idempotent_and_accepts_unknown_token(self):
        user = await self._user()
        issued = await self.service.issue_for_authenticated_user(user.id)
        await self._revoke(issued.token)
        self.now += timedelta(minutes=1)
        await self._revoke(issued.token)
        await self._revoke(SecretStr("A" * 43))
        await self._revoke(SecretStr("invalido"))
        revoked_at = await self.session.scalar(select(UserSession.revoked_at).where(UserSession.id == issued.id))
        self.assertEqual(revoked_at, self.now - timedelta(minutes=1))

    async def test_logout_of_one_session_does_not_revoke_other_sessions(self):
        user = await self._user()
        other_user = await self._user()
        first = await self.service.issue_for_authenticated_user(user.id)
        second = await self.service.issue_for_authenticated_user(user.id)
        third = await self.service.issue_for_authenticated_user(other_user.id)
        self.assertEqual(len({s.token.get_secret_value() for s in (first, second, third)}), 3)
        await self._revoke(first.token)
        self.assertIsNone(await self.service.resolve(first.token))
        self.assertIsNotNone(await self.service.resolve(second.token))
        self.assertEqual((await self.service.resolve(third.token)).user_id, other_user.id)

    async def test_collision_rolls_back_issuance(self):
        user = await self._user()
        user_id = user.id
        with patch("app.modules.identity.sessions.secrets.token_urlsafe", return_value="B" * 43):
            await self.service.issue_for_authenticated_user(user_id)
            with self.assertRaises(IntegrityError):
                await self.service.issue_for_authenticated_user(user_id)
        self.assertFalse(self.session.in_transaction())
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(UserSession).where(
            UserSession.user_id == user_id,
        )), 1)

    async def test_database_failure_never_resolves_identity(self):
        with patch.object(self.session, "execute", side_effect=SQLAlchemyError("falha simulada")):
            with self.assertRaises(SQLAlchemyError):
                await self.service.resolve(SecretStr("A" * 43))

    async def test_database_constraints_reject_invalid_session_rows(self):
        user = await self._user()
        for values in (
            dict(user_id=uuid4()), dict(token_hash="token em texto puro"),
            dict(expires_at=self.now), dict(revoked_at=self.now - timedelta(seconds=1)),
        ):
            with self.subTest(fields=list(values)), self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    data = dict(user_id=user.id, token_hash="a" * 64,
                                created_at=self.now, expires_at=self.now + timedelta(minutes=30))
                    self.session.add(UserSession(**{**data, **values}))
                    await self.session.flush()

    async def test_migration_round_trip_preserves_identity_and_credentials(self):
        user = await self._user()
        user_id = user.id
        hashed = await hash_password(SecretStr("senha ficticia da migration"))
        self.session.add(UserPasswordCredential(user_id=user_id, password_hash=hashed.get_secret_value()))
        await self.session.commit()
        await self.service.issue_for_authenticated_user(user_id)
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration, "downgrade", "9e3d7a51c286")
            self.assertIsNone(await self.session.scalar(text("SELECT to_regclass('public.user_sessions')")))
            self.assertIsNotNone(await self.session.get(User, user_id))
            self.assertIsNotNone(await self.session.get(UserPasswordCredential, user_id))
        finally:
            await self.session.close()
            await self.engine.dispose()
            await asyncio.to_thread(self.run_migration, "upgrade", "head")
        await asyncio.to_thread(self.run_migration, "check")

    async def _activity(self, token):
        async with AsyncSession(self.engine) as writer:
            return await SessionService(writer, clock=lambda: self.now).record_activity(token)

    async def test_activity_keeps_session_valid_beyond_one_day(self):
        user = await self._user()
        issued = await self.service.issue_for_authenticated_user(user.id)
        for _ in range(75):
            self.now += timedelta(minutes=20)
            renewed = await self._activity(issued.token)
            self.assertIsNotNone(renewed)
            self.assertEqual(renewed.expires_at, self.now + timedelta(minutes=30))
        self.assertGreater(self.now, issued.expires_at + timedelta(days=1))
        self.assertIsNotNone(await self.service.resolve(issued.token))
        self.now += timedelta(minutes=30)
        self.assertIsNone(await self.service.resolve(issued.token))

    async def test_activity_does_not_revive_expired_or_revoked_session(self):
        user = await self._user()
        expired = await self.service.issue_for_authenticated_user(user.id)
        revoked = await self.service.issue_for_authenticated_user(user.id)
        await self._revoke(revoked.token)
        self.assertIsNone(await self._activity(revoked.token))
        self.now = expired.expires_at
        self.assertIsNone(await self._activity(expired.token))
        self.assertIsNone(await self.service.resolve(expired.token))

    async def test_activity_rejects_inactive_user_unknown_and_invalid_token(self):
        user = await self._user()
        issued = await self.service.issue_for_authenticated_user(user.id)
        async with AsyncSession(self.engine) as writer:
            async with writer.begin():
                await writer.execute(update(User).where(User.id == user.id).values(status=UserStatus.INACTIVE))
        for token in (issued.token, SecretStr("A" * 43), SecretStr("invalido"), None):
            self.assertIsNone(await self._activity(token))

    async def test_resolution_does_not_renew_background_requests(self):
        user = await self._user()
        issued = await self.service.issue_for_authenticated_user(user.id)
        self.now += timedelta(minutes=20)
        self.assertEqual((await self.service.resolve(issued.token)).expires_at, issued.expires_at)
        self.now = issued.expires_at
        self.assertIsNone(await self.service.resolve(issued.token))

    async def test_older_activity_cannot_shorten_persisted_deadline(self):
        user = await self._user()
        issued = await self.service.issue_for_authenticated_user(user.id)
        self.now += timedelta(minutes=20)
        first = await self._activity(issued.token)
        self.now -= timedelta(minutes=5)
        delayed = await self._activity(issued.token)
        self.assertEqual(delayed.expires_at, first.expires_at)

    async def test_activity_renews_only_presented_session(self):
        user = await self._user()
        first = await self.service.issue_for_authenticated_user(user.id)
        second = await self.service.issue_for_authenticated_user(user.id)
        self.now += timedelta(minutes=20)
        await self._activity(first.token)
        self.now = second.expires_at
        self.assertIsNotNone(await self.service.resolve(first.token))
        self.assertIsNone(await self.service.resolve(second.token))
