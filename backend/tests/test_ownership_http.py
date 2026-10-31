"""Testa contratos HTTP de propriedade com PostgreSQL e Redis exclusivos."""

import asyncio
import os
import secrets
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from pydantic import SecretStr
from redis.asyncio import Redis
from redis.exceptions import ConnectionError
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from database_support import DatabaseTestCase
from app.core.config import Settings
from app.main import create_app
from app.modules.identity.access_models import OrganizationOwnership, OwnershipChange
from app.modules.identity.models import (
    MembershipStatus, OrganizationMembership, User, UserPasswordCredential, UserSession, UserStatus,
)
from app.modules.identity.passwords import hash_password
from app.modules.identity.rate_limit import LoginRateLimiter, LoginRateLimitPolicy
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Organization


@unittest.skipUnless(os.environ.get("SD_RUN_DATABASE_TESTS") == "1" and os.environ.get("SD_RUN_REDIS_TESTS") == "1",
                     "Defina SD_RUN_DATABASE_TESTS=1 e SD_RUN_REDIS_TESTS=1.")
class OwnershipHttpTests(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.redis = Redis(host="127.0.0.1", port=6379, db=15, socket_timeout=2, socket_connect_timeout=2)
        self.addAsyncCleanup(self.redis.aclose)
        self.namespace = "sd-financeiro:test:" + uuid4().hex
        self.addAsyncCleanup(self._clear_redis)
        self.config = Settings(_env_file=None, database_password="ficticia", app_environment="test", app_debug=True,
                               auth_rate_limit_key=SecretStr(secrets.token_urlsafe(32)))
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        self.app = create_app(self.config, session_factory=self.factory, redis_client=self.redis,
                              rate_limit_namespace=self.namespace)
        context = self.app.router.lifespan_context(self.app)
        await context.__aenter__()
        self.addAsyncCleanup(context.__aexit__, None, None, None)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(
            app=self.app, client=("127.0.0.1", 12345), raise_app_exceptions=False), base_url="http://testserver")
        self.addAsyncCleanup(self.client.aclose)
        self.password = "Senha ficticia de testes @123"
        hashed = (await hash_password(SecretStr(self.password))).get_secret_value()
        self.operator = User(name="Operador", email=uuid4().hex + "@example.com", status=UserStatus.ACTIVE,
                             can_provision_organizations=True)
        self.owner = User(name="Proprietário", email=uuid4().hex + "@example.com", status=UserStatus.ACTIVE)
        self.target = User(name="Destinatário", email=uuid4().hex + "@example.com", status=UserStatus.ACTIVE)
        self.org = Organization(name="Empresa de teste")
        self.other = Organization(name="Outra empresa")
        self.session.add_all([self.operator, self.owner, self.target, self.org, self.other])
        await self.session.flush()
        for user in (self.operator, self.owner, self.target):
            self.session.add(UserPasswordCredential(user_id=user.id, password_hash=hashed))
        for user in (self.owner, self.target):
            self.session.add(OrganizationMembership(user_id=user.id, organization_id=self.org.id,
                                                    status=MembershipStatus.ACTIVE))
        await self.session.commit()
        self.tokens = {}
        for user in (self.operator, self.owner, self.target):
            self.tokens[user.id] = (await SessionService(self.session).issue_for_authenticated_user(user.id)).token

    async def _clear_redis(self):
        keys = [key async for key in self.redis.scan_iter(match="{" + self.namespace + ":*")]
        if keys:
            await self.redis.delete(*keys)

    async def _post(self, *, initial=False, actor=None, org=None, target=None, password=None, headers=None, **kwargs):
        operation = "designate" if initial else "transfer"
        return await self.client.post(f"/api/v1/organizations/{org or self.org.id}/ownership/{operation}",
            headers=headers if headers is not None else {"Authorization": "Bearer " + self.tokens[actor or self.owner.id].get_secret_value()},
            json={"new_owner_id": str(target or (self.owner.id if initial else self.target.id)),
                  "password": password or self.password}, **kwargs)

    async def _designate(self):
        result = await self._post(initial=True, actor=self.operator.id)
        self.assertEqual(result.status_code, 204, result.text)

    async def _owner(self):
        async with self.factory() as reader:
            return await reader.scalar(select(OrganizationOwnership.user_id).where(
                OrganizationOwnership.organization_id == self.org.id))

    async def test_designate_transfer_return_empty_no_store_and_atomic_history(self):
        await self._designate()
        response = await self._post()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(await self._owner(), self.target.id)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(OwnershipChange).where(
            OwnershipChange.organization_id == self.org.id)), 2)
        denied = await self._post()
        self.assertEqual(denied.status_code, 404)

    async def test_missing_malformed_revoked_and_expired_bearer_are_unauthorized(self):
        for headers in ({}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer invalido"},
                        {"Cookie": "access_token=falso"}):
            self.assertEqual((await self._post(headers=headers)).status_code, 401)
        await SessionService(self.session).revoke(self.tokens[self.owner.id])
        self.assertEqual((await self._post()).status_code, 401)
        now = datetime.now(timezone.utc)
        await self.session.execute(update(UserSession).where(UserSession.user_id == self.operator.id).values(
            created_at=now-timedelta(hours=2), expires_at=now-timedelta(hours=1)))
        await self.session.commit()
        self.assertEqual((await self._post(initial=True, actor=self.operator.id)).status_code, 401)

    async def test_unknown_foreign_tenant_and_wrong_password_have_same_minimal_denial(self):
        await self._designate()
        results = [await self._post(org=uuid4()), await self._post(org=self.other.id),
                   await self._post(password="incorreta"), await self._post(target=self.operator.id),
                   await self._post(actor=self.target.id)]
        self.assertTrue(all(r.status_code == 404 for r in results))
        self.assertEqual(len({r.text for r in results}), 1)
        for r in results:
            self.assertNotIn(self.password, r.text)
            self.assertNotIn(str(self.owner.id), r.text)
            self.assertEqual(r.headers["cache-control"], "no-store")

    async def test_platform_operator_cannot_replace_owner(self):
        await self._designate()
        for initial in (True, False):
            self.assertEqual((await self._post(initial=initial, actor=self.operator.id)).status_code, 404)
        self.assertEqual(await self._owner(), self.owner.id)

    async def test_rate_limit_precedes_password_and_ignores_destination_session_and_forwarded_headers(self):
        await self._designate()
        for _ in range(5):
            self.assertEqual((await self._post(password="incorreta")).status_code, 404)
        token = (await SessionService(self.session).issue_for_authenticated_user(self.owner.id)).token
        with patch("app.modules.identity.ownership.verify_password", new_callable=AsyncMock) as verifier:
            response = await self._post(initial=True, target=self.operator.id, headers={
                "Authorization": "Bearer " + token.get_secret_value(), "X-Forwarded-For": "198.51.100.8"})
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers["retry-after"]), 0)
        verifier.assert_not_awaited()
        login = await self.client.post("/api/v1/auth/login", json={"email": self.owner.email, "password": self.password})
        self.assertEqual(login.status_code, 200)
        self.assertEqual((await self.client.post("/api/v1/auth/logout", headers={
            "Authorization": "Bearer " + token.get_secret_value()})).status_code, 204)

    async def test_redis_failure_denies_change_without_password_work(self):
        with patch.object(self.redis, "eval", side_effect=ConnectionError("segredo_interno")), patch(
            "app.modules.identity.ownership.verify_password", new_callable=AsyncMock) as verifier:
            response = await self._post(initial=True, actor=self.operator.id)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("segredo_interno", response.text)
        verifier.assert_not_awaited()
        self.assertIsNone(await self._owner())

    async def test_hash_capacity_is_shared_with_login_and_rejects_without_password_work(self):
        self.assertIs(self.app.state.auth_hash_slots, self.app.state.authentication._hash_slots)
        slots = self.app.state.auth_hash_slots
        await slots.acquire()
        await slots.acquire()
        try:
            with patch("app.modules.identity.ownership.verify_password", new_callable=AsyncMock) as verifier:
                response = await self._post(initial=True, actor=self.operator.id)
            self.assertEqual(response.status_code, 503)
            verifier.assert_not_awaited()
        finally:
            slots.release()
            slots.release()

    async def test_validation_rejects_privilege_fields_and_does_not_echo_secret(self):
        url = f"/api/v1/organizations/{self.org.id}/ownership/designate"
        headers = {"Authorization": "Bearer " + self.tokens[self.operator.id].get_secret_value()}
        for data in ({"new_owner_id": str(self.owner.id), "password": self.password, "actor_user_id": str(self.operator.id)},
                     {"new_owner_id": "invalido", "password": self.password},
                     {"new_owner_id": str(self.owner.id), "password": "x"*129}):
            response = await self.client.post(url, json=data, headers=headers)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json(), {"detail": "Dados de entrada inválidos."})
        for content, content_type, expected in (("x"*4097, "application/json", 413),
                                                ("segredo", "text/plain", 415)):
            response = await self.client.post(url, content=content, headers={**headers, "Content-Type": content_type})
            self.assertEqual(response.status_code, expected)
            self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_sql_and_unexpected_failures_are_sanitized_even_in_debug(self):
        for error, status in ((SQLAlchemyError("segredo_sql"), 503), (RuntimeError("segredo_app"), 500)):
            with patch("app.api.v1.ownership.OrganizationOwnershipService.designate", side_effect=error):
                response = await self._post(initial=True, actor=self.operator.id)
            self.assertEqual(response.status_code, status)
            self.assertNotIn("segredo", response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_concurrent_transfers_have_one_success(self):
        await self._designate()
        responses = await asyncio.gather(self._post(), self._post())
        self.assertEqual(sorted(r.status_code for r in responses), [204, 404])
        self.assertEqual(await self._owner(), self.target.id)

    async def test_success_renews_idle_deadline_but_denial_does_not(self):
        now = datetime.now(timezone.utc)
        await self.session.execute(update(UserSession).where(UserSession.user_id == self.operator.id).values(
            expires_at=now+timedelta(seconds=60)))
        await self.session.commit()
        await self._designate()
        async with self.factory() as reader:
            deadline = await reader.scalar(select(UserSession.expires_at).where(UserSession.user_id == self.operator.id))
        self.assertGreater(deadline, now+timedelta(minutes=29))
        await self._post(initial=True, actor=self.operator.id)
        async with self.factory() as reader:
            self.assertEqual(await reader.scalar(select(UserSession.expires_at).where(
                UserSession.user_id == self.operator.id)), deadline)

    async def test_production_http_is_denied_before_change(self):
        self.app.state.settings = self.config.model_copy(update={"app_environment": "production"})
        self.assertEqual((await self._post(initial=True, actor=self.operator.id)).status_code, 503)
        self.assertIsNone(await self._owner())

    async def test_origin_limit_cannot_be_bypassed_by_changing_actor(self):
        self.app.state.ownership_limiter = LoginRateLimiter(self.redis,
            key_secret=self.config.auth_rate_limit_key, namespace=self.namespace, operation="ownership",
            policy=LoginRateLimitPolicy(origin_limit=1))
        self.assertEqual((await self._post()).status_code, 404)
        response = await self._post(initial=True, actor=self.operator.id,
                                    headers={"Authorization": "Bearer " + self.tokens[self.operator.id].get_secret_value(),
                                             "X-Forwarded-For": "198.51.100.9"})
        self.assertEqual(response.status_code, 429)
        self.assertIsNone(await self._owner())

    async def test_global_limit_applies_to_different_origins_and_actors(self):
        limiter = LoginRateLimiter(self.redis, key_secret=self.config.auth_rate_limit_key,
            namespace=self.namespace, operation="ownership", policy=LoginRateLimitPolicy(global_limit=1))
        self.app.state.ownership_limiter = limiter
        await limiter.check(account_identifier=str(uuid4()), origin_ip="198.51.100.3")
        self.assertEqual((await self._post(initial=True, actor=self.operator.id)).status_code, 429)

    async def test_missing_ownership_limiter_fails_closed(self):
        self.app.state.ownership_limiter = None
        self.assertEqual((await self._post(initial=True, actor=self.operator.id)).status_code, 503)
        self.assertIsNone(await self._owner())

    async def test_cancellation_keeps_hash_slot_until_verification_finishes_and_rolls_back(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        self.app.state.auth_hash_slots = asyncio.Semaphore(1)

        async def delayed_verification(*args):
            entered.set()
            await finish.wait()
            return True, None

        with patch("app.modules.identity.ownership.verify_password", delayed_verification):
            first = asyncio.create_task(self._post(initial=True, actor=self.operator.id))
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                first.cancel()
                response = await self._post(initial=True, actor=self.operator.id)
                self.assertEqual(response.status_code, 503)
            finally:
                finish.set()
                await asyncio.gather(first, return_exceptions=True)
        self.assertIsNone(await self._owner())
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(OwnershipChange).where(
            OwnershipChange.organization_id == self.org.id)), 0)
