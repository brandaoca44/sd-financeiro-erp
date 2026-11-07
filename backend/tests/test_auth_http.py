"""Exercita login, logout e acesso a tenants via HTTP com infraestrutura real isolada."""

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
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from database_support import DatabaseTestCase
from app.core.config import Settings
from app.main import create_app
from app.modules.identity.models import (
    MembershipStatus, OrganizationMembership, User, UserPasswordCredential, UserSession, UserStatus,
)
from app.modules.identity.passwords import hash_password, verify_password
from app.modules.organizations.models import Organization


@unittest.skipUnless(
    os.environ.get("SD_RUN_DATABASE_TESTS") == "1" and os.environ.get("SD_RUN_REDIS_TESTS") == "1",
    "Defina SD_RUN_DATABASE_TESTS=1 e SD_RUN_REDIS_TESTS=1 para testes HTTP reais.",
)
class AuthenticationHttpTests(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.redis = Redis(host="127.0.0.1", port=6379, db=15, socket_timeout=2, socket_connect_timeout=2)
        self.addAsyncCleanup(self.redis.aclose)
        self.namespace = "sd-financeiro:test:" + uuid4().hex
        self.addAsyncCleanup(self._clear_redis)
        self.config = Settings(
            _env_file=None, database_password="ficticia", app_environment="test", app_debug=True,
            auth_rate_limit_key=SecretStr(secrets.token_urlsafe(32)),
            auth_account_limit=50, auth_origin_limit=100, auth_global_limit=200,
        )
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        self.app = create_app(self.config, session_factory=self.factory, redis_client=self.redis,
                              rate_limit_namespace=self.namespace)
        context = self.app.router.lifespan_context(self.app)
        await context.__aenter__()
        self.addAsyncCleanup(context.__aexit__, None, None, None)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, client=("127.0.0.1", 12345), raise_app_exceptions=False),
            base_url="http://testserver",
        )
        self.addAsyncCleanup(self.client.aclose)
        self.password = "frase ficticia exclusiva de teste"

    async def _clear_redis(self):
        keys = [key async for key in self.redis.scan_iter(match="{" + self.namespace + ":login:v1}:*")]
        if keys:
            await self.redis.delete(*keys)

    async def _user(self, *, active=True, provision=False, credential=True):
        user = User(name="Pessoa de teste", email=uuid4().hex + "@example.com",
                    status=UserStatus.ACTIVE if active else UserStatus.INACTIVE,
                    can_provision_organizations=provision)
        self.session.add(user)
        await self.session.flush()
        if credential:
            hashed = await hash_password(SecretStr(self.password))
            self.session.add(UserPasswordCredential(user_id=user.id, password_hash=hashed.get_secret_value()))
        await self.session.commit()
        return user

    async def _login(self, user, *, password=None, headers=None):
        return await self.client.post("/api/v1/auth/login", json={
            "email": user.email, "password": password or self.password,
        }, headers=headers)

    async def _token(self, user):
        response = await self._login(user)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["access_token"]

    async def test_login_returns_only_token_type_and_idle_deadline_without_persistent_cookie(self):
        user = await self._user()
        response = await self._login(user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"access_token", "token_type", "expires_at"})
        self.assertEqual(response.json()["token_type"], "bearer")
        self.assertEqual(len(response.json()["access_token"]), 43)
        self.assertEqual(response.headers["cache-control"], "no-store")
        # Login clears any remembered session; it never persists the new bearer token.
        cookie = response.headers.get("set-cookie", "")
        self.assertIn('sdf_remember_session=""', cookie)
        self.assertIn("Max-Age=0", cookie)
        self.assertNotIn(response.json()["access_token"], cookie)
        self.assertNotIn(self.password, response.text)
        self.assertNotIn(user.email, response.text)

    async def test_wrong_unknown_inactive_and_missing_credential_have_same_error(self):
        active = await self._user()
        inactive = await self._user(active=False)
        missing = await self._user(credential=False)
        results = [await self._login(active, password="incorreta"), await self._login(inactive),
                   await self._login(missing), await self.client.post("/api/v1/auth/login", json={
                       "email": "nao-existe@example.com", "password": self.password,
                   })]
        self.assertTrue(all(r.status_code == 401 for r in results))
        self.assertEqual(len({r.text for r in results}), 1)
        for user in (active, inactive, missing):
            self.assertEqual(await self.session.scalar(select(func.count()).select_from(UserSession).where(
                UserSession.user_id == user.id,
            )), 0)

    async def test_rate_limit_precedes_password_work_and_ignores_forwarded_headers(self):
        user = await self._user()
        for _ in range(50):
            await self.app.state.authentication._limiter.check(account_identifier=user.email, origin_ip="127.0.0.1")
        with patch("app.modules.identity.authentication.verify_password", new_callable=AsyncMock) as verifier:
            response = await self._login(user, headers={"X-Forwarded-For": "198.51.100.1", "Forwarded": "for=198.51.100.1"})
        self.assertEqual(response.status_code, 429)
        self.assertGreaterEqual(int(response.headers["retry-after"]), 1)
        verifier.assert_not_awaited()

    async def test_redis_failure_blocks_login_but_not_logout(self):
        user = await self._user()
        token = await self._token(user)
        with patch.object(self.redis, "eval", side_effect=ConnectionError("segredo_privado")):
            response = await self._login(user)
            logout = await self.client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer " + token})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("segredo_privado", response.text)
        self.assertEqual(logout.status_code, 204)

    async def test_logout_revokes_and_is_idempotent(self):
        user = await self._user(provision=True)
        token = await self._token(user)
        headers = {"Authorization": "Bearer " + token}
        for _ in range(2):
            self.assertEqual((await self.client.post("/api/v1/auth/logout", headers=headers)).status_code, 204)
        response = await self.client.post("/api/v1/organizations", json={"name": "Bloqueada"}, headers=headers)
        self.assertEqual(response.status_code, 401)

    async def test_organization_routes_require_valid_bearer_not_cookie_or_query(self):
        for headers in ({}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer invalido"},
                        {"Cookie": "access_token=falso"}):
            response = await self.client.get(f"/api/v1/organizations/{uuid4()}?access_token=falso", headers=headers)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_only_provisioner_can_create_and_receives_no_tenant_read_access(self):
        ordinary = await self._user()
        operator = await self._user(provision=True)
        ordinary_token, operator_token = await self._token(ordinary), await self._token(operator)
        denied = await self.client.post("/api/v1/organizations", json={"name": "Negada"},
                                        headers={"Authorization": "Bearer " + ordinary_token})
        self.assertEqual(denied.status_code, 403)
        created = await self.client.post("/api/v1/organizations", json={"name": "  Nova  "},
                                         headers={"Authorization": "Bearer " + operator_token})
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["name"], "Nova")
        self.assertEqual(set(created.json()), {"id", "name", "status", "created_at", "updated_at"})
        self.assertEqual(created.headers["location"], "/api/v1/organizations/" + created.json()["id"])
        self.assertEqual((await self.client.get(created.headers["location"],
                         headers={"Authorization": "Bearer " + operator_token})).status_code, 404)

    async def test_tenant_isolation_matches_nonexistent_response_and_revocation_is_seen(self):
        user = await self._user()
        own, other = Organization(name="Permitida"), Organization(name="Confidencial de outro tenant")
        self.session.add_all([own, other])
        await self.session.flush()
        self.session.add(OrganizationMembership(user_id=user.id, organization_id=own.id,
                          status=MembershipStatus.ACTIVE, can_read_organization=True))
        await self.session.commit()
        headers = {"Authorization": "Bearer " + await self._token(user)}
        allowed = await self.client.get(f"/api/v1/organizations/{own.id}", headers=headers)
        self.assertEqual(allowed.status_code, 200)
        denied = await self.client.get(f"/api/v1/organizations/{other.id}", headers=headers)
        absent = await self.client.get(f"/api/v1/organizations/{uuid4()}", headers=headers)
        self.assertEqual((denied.status_code, denied.text), (absent.status_code, absent.text))
        self.assertNotIn(other.name, denied.text)
        async with self.session.begin():
            await self.session.execute(update(OrganizationMembership).where(
                OrganizationMembership.user_id == user.id, OrganizationMembership.organization_id == own.id,
            ).values(can_read_organization=False))
        self.assertEqual((await self.client.get(f"/api/v1/organizations/{own.id}", headers=headers)).status_code, 404)

    async def test_validation_and_unexpected_errors_do_not_reflect_secrets_even_in_debug(self):
        invalid = await self.client.post("/api/v1/auth/login", json={
            "email": "email_privado_invalido", "password": "senha_privada", "admin": True,
        })
        self.assertEqual(invalid.status_code, 422)
        for value in ("email_privado_invalido", "senha_privada", "input", "ctx"):
            self.assertNotIn(value, invalid.text)
        user = await self._user()
        with patch.object(self.app.state.authentication, "login", side_effect=RuntimeError("segredo_SQL_traceback")):
            failed = await self._login(user)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(failed.json(), {"detail": "Erro interno."})
        self.assertEqual(failed.headers["cache-control"], "no-store")

    async def test_login_body_size_and_content_type_are_bounded(self):
        oversized = await self.client.post("/api/v1/auth/login", content=b"x" * 4097,
                                            headers={"Content-Type": "application/json"})
        self.assertEqual(oversized.status_code, 413)
        form = await self.client.post("/api/v1/auth/login", content="password=segredo",
                                      headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(form.status_code, 415)

    async def test_database_outage_does_not_issue_token_or_expose_sql(self):
        user = await self._user()
        with patch.object(self.app.state.authentication, "_factory", side_effect=SQLAlchemyError("SQL_privado")):
            response = await self._login(user)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("SQL_privado", response.text)
        self.assertNotIn("access_token", response.text)

    async def test_rehash_is_persisted_together_with_session(self):
        user = await self._user()
        old_hash = PasswordHash((Argon2Hasher(time_cost=2),)).hash(self.password)
        async with self.session.begin():
            await self.session.execute(update(UserPasswordCredential).where(
                UserPasswordCredential.user_id == user.id,
            ).values(password_hash=old_hash))
        response = await self._login(user)
        self.assertEqual(response.status_code, 200)
        stored = await self.session.scalar(select(UserPasswordCredential.password_hash).where(
            UserPasswordCredential.user_id == user.id,
        ))
        self.assertNotEqual(stored, old_hash)
        self.assertEqual(await verify_password(SecretStr(self.password), stored), (True, None))

    async def test_public_health_returns_only_status(self):
        with patch("app.api.v1.health.is_database_available", AsyncMock(return_value=True)):
            response = await self.client.get("/api/v1/health")
        self.assertEqual(response.json(), {"status": "healthy"})

    async def test_missing_configuration_and_production_http_fail_closed(self):
        self.app.state.authentication = None
        response = await self.client.post("/api/v1/auth/login", json={"email": "pessoa@example.com", "password": "ficticia"})
        self.assertEqual(response.status_code, 503)
        self.app.state.settings = self.config.model_copy(update={"app_environment": "production"})
        self.assertEqual((await self.client.post("/api/v1/auth/logout",
                          headers={"Authorization": "Bearer " + "A" * 43})).status_code, 503)

    async def test_password_changed_after_verification_prevents_session_issuance(self):
        user = await self._user()
        replacement = await hash_password(SecretStr("nova frase ficticia de teste"))

        async def change_after_verification(password, stored_hash):
            result = await verify_password(password, stored_hash)
            async with self.factory() as writer:
                async with writer.begin():
                    await writer.execute(update(UserPasswordCredential).where(
                        UserPasswordCredential.user_id == user.id,
                    ).values(password_hash=replacement.get_secret_value()))
            return result

        with patch("app.modules.identity.authentication.verify_password", side_effect=change_after_verification):
            response = await self._login(user)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(UserSession).where(
            UserSession.user_id == user.id,
        )), 0)

    async def test_inactive_or_expired_session_cannot_access_protected_routes(self):
        user = await self._user(provision=True)
        token = await self._token(user)
        now = datetime.now(timezone.utc)
        async with self.session.begin():
            await self.session.execute(update(UserSession).where(UserSession.user_id == user.id).values(
                created_at=now - timedelta(hours=2), expires_at=now - timedelta(hours=1),
            ))
        self.assertEqual((await self.client.post("/api/v1/organizations", json={"name": "Negada"},
                          headers={"Authorization": "Bearer " + token})).status_code, 401)
        token = await self._token(user)
        async with self.session.begin():
            await self.session.execute(update(User).where(User.id == user.id).values(status=UserStatus.INACTIVE))
        self.assertEqual((await self.client.get(f"/api/v1/organizations/{uuid4()}",
                          headers={"Authorization": "Bearer " + token})).status_code, 401)
