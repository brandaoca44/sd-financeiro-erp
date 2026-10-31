"""Valida revisão da origem e conversão sem ampliar permissões do tenant."""

import asyncio
import os
import secrets
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from pydantic import SecretStr, ValidationError
from redis.asyncio import Redis
from redis.exceptions import ConnectionError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database_support import DatabaseTestCase
from app.core.config import Settings
from app.main import create_app
from app.modules.identity.access_models import OrganizationOwnership, OrganizationRole, OrganizationRoleAssignment
from app.modules.identity.legacy_access_schemas import LegacyReadConvertRequest, LegacyReadRevokeRequest
from app.modules.identity.models import OrganizationMembership, User, UserPasswordCredential, UserSession
from app.modules.identity.passwords import hash_password
from app.modules.identity.permission_models import (
    OrganizationAccessChange, OrganizationAccessDelegation, OrganizationDelegationPermission, OrganizationRolePermission,
)
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Organization

READ, ROLES = "organizations.read", "identity.roles.read"


class LegacyReadSchemaTests(unittest.TestCase):
    def test_rejects_actor_privilege_and_scope_overrides(self):
        for extra in ({"can_read_organization": True}, {"actor_user_id": str(uuid4())}, {"company_id": str(uuid4())}, {"permissions": [READ]}):
            with self.assertRaises(ValidationError):
                LegacyReadRevokeRequest(expected_revision=1, password="segredo", **extra)

    def test_requires_strict_revisions_and_existing_role_identifier(self):
        base = dict(expected_revision=1, role_id=uuid4(), expected_role_revision=1, expected_assignment_revision=0, password="segredo")
        for change in ({"expected_revision": 0}, {"expected_assignment_revision": -1}, {"expected_role_revision": True}, {"role_id": "invalido"}):
            with self.assertRaises(ValidationError):
                LegacyReadConvertRequest(**{**base, **change})

    def test_password_is_masked_without_removing_symbols(self):
        data = LegacyReadRevokeRequest(expected_revision=1, password=" teste @ ")
        self.assertEqual(data.password.get_secret_value(), " teste @ ")
        self.assertNotIn(" teste @ ", repr(data))


@unittest.skipUnless(os.environ.get("SD_RUN_DATABASE_TESTS") == "1" and os.environ.get("SD_RUN_REDIS_TESTS") == "1",
                     "Defina SD_RUN_DATABASE_TESTS=1 e SD_RUN_REDIS_TESTS=1.")
class LegacyReadHttpTests(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.redis = Redis(host="127.0.0.1", port=6379, db=15, socket_timeout=2, socket_connect_timeout=2)
        self.addAsyncCleanup(self.redis.aclose)
        self.namespace = "sd-financeiro:test:" + uuid4().hex
        self.addAsyncCleanup(self._clear_redis)
        self.config = Settings(_env_file=None, database_password="ficticia", app_environment="test", app_debug=True,
                               auth_rate_limit_key=SecretStr(secrets.token_urlsafe(32)))
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        self.app = create_app(self.config, session_factory=self.factory, redis_client=self.redis, rate_limit_namespace=self.namespace)
        context = self.app.router.lifespan_context(self.app)
        await context.__aenter__()
        self.addAsyncCleanup(context.__aexit__, None, None, None)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(
            app=self.app, client=("127.0.0.1", 12345), raise_app_exceptions=False), base_url="http://testserver")
        self.addAsyncCleanup(self.client.aclose)
        self.password = "Senha ficticia de revisao de acesso @123"
        self.owner, self.target, self.delegate, self.operator = [User(name=name, email=uuid4().hex+"@example.com", status="ACTIVE",
            can_provision_organizations=(name == "Operador")) for name in ("Master", "Alvo", "Delegado", "Operador")]
        self.org, self.other = Organization(name="Empresa"), Organization(name="Outra empresa")
        self.session.add_all([self.owner, self.target, self.delegate, self.operator, self.org, self.other])
        await self.session.flush()
        hashed = (await hash_password(SecretStr(self.password))).get_secret_value()
        for user in (self.owner, self.target, self.delegate, self.operator):
            self.session.add(UserPasswordCredential(user_id=user.id, password_hash=hashed))
        for org in (self.org, self.other):
            for user in (self.owner, self.target):
                self.session.add(OrganizationMembership(user_id=user.id, organization_id=org.id, status="ACTIVE", can_read_organization=True))
        self.session.add(OrganizationMembership(user_id=self.delegate.id, organization_id=self.org.id, status="ACTIVE"))
        await self.session.flush()
        for org in (self.org, self.other):
            self.session.add(OrganizationOwnership(organization_id=org.id, user_id=self.owner.id))
        self.pure = OrganizationRole(organization_id=self.org.id, name="Somente leitura", status="ACTIVE")
        self.broad = OrganizationRole(organization_id=self.org.id, name="Leitura e perfis", status="ACTIVE")
        self.foreign = OrganizationRole(organization_id=self.other.id, name="Outro tenant", status="ACTIVE")
        self.session.add_all([self.pure, self.broad, self.foreign])
        await self.session.flush()
        for role, keys in ((self.pure, [READ]), (self.broad, [READ, ROLES]), (self.foreign, [READ])):
            self.session.add_all([OrganizationRolePermission(organization_id=role.organization_id, role_id=role.id, permission_key=key) for key in keys])
        await self.session.commit()
        self.headers = {}
        for user in (self.owner, self.target, self.delegate, self.operator):
            issued = await SessionService(self.session).issue_for_authenticated_user(user.id)
            self.headers[user.id] = {"Authorization": "Bearer "+issued.token.get_secret_value()}
        self.base = f"/api/v1/organizations/{self.org.id}"

    async def _clear_redis(self):
        keys = [key async for key in self.redis.scan_iter(match="{"+self.namespace+":*")]
        if keys:
            await self.redis.delete(*keys)

    async def _review(self, *, actor=None, target=None, org=None):
        return await self.client.get(f"/api/v1/organizations/{org or self.org.id}/members/{target or self.target.id}/read-access",
            headers=self.headers[actor or self.owner.id])

    async def _convert(self, *, actor=None, target=None, org=None, **changes):
        return await self.client.post(f"/api/v1/organizations/{org or self.org.id}/members/{target or self.target.id}/legacy-read/convert",
            headers=self.headers[actor or self.owner.id], json={"expected_revision": 1, "role_id": str(self.pure.id),
                "expected_role_revision": 1, "expected_assignment_revision": 0, "password": self.password, **changes})

    async def _revoke(self, *, actor=None, target=None, org=None, **changes):
        return await self.client.post(f"/api/v1/organizations/{org or self.org.id}/members/{target or self.target.id}/legacy-read/revoke",
            headers=self.headers[actor or self.owner.id], json={"expected_revision": 1, "password": self.password, **changes})

    async def _assign_fixture(self, role=None, *, delegated=False, status="ACTIVE"):
        role = role or self.pure
        if delegated:
            self.session.add(OrganizationAccessDelegation(organization_id=self.org.id, user_id=self.delegate.id,
                granted_by_user_id=self.owner.id, owner_revision=1, status="ACTIVE"))
            await self.session.flush()
            self.session.add(OrganizationDelegationPermission(organization_id=self.org.id, user_id=self.delegate.id, permission_key=READ))
            await self.session.flush()
        assignment = OrganizationRoleAssignment(organization_id=self.org.id, user_id=self.target.id, role_id=role.id,
            status=status, delegated_by_user_id=self.delegate.id if delegated else None, delegation_revision=1 if delegated else None)
        self.session.add(assignment)
        await self.session.commit()

    async def test_review_separates_configured_legacy_and_effective_profile_access(self):
        response = await self._review()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"user_id", "revision", "membership_status", "user_status", "legacy_read", "legacy_effective", "profile_read", "effective_read"})
        self.assertTrue(response.json()["legacy_read"])
        self.assertTrue(response.json()["legacy_effective"])
        self.assertFalse(response.json()["profile_read"])
        self.assertTrue(response.json()["effective_read"])
        self.assertNotIn(self.target.email, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_conversion_preserves_read_and_creates_only_narrow_direct_assignment(self):
        response = await self._convert()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["legacy_read"])
        self.assertTrue(response.json()["profile_read"])
        self.assertTrue(response.json()["effective_read"])
        self.assertEqual(response.json()["revision"], 2)
        self.assertEqual(response.json()["assignment_revision"], 1)
        self.assertEqual((await self.client.get(self.base, headers=self.headers[self.target.id])).status_code, 200)
        self.assertEqual((await self.client.get(self.base+"/roles", headers=self.headers[self.target.id])).status_code, 404)
        async with self.factory() as reader:
            assignment = await reader.get(OrganizationRoleAssignment, (self.org.id, self.target.id, self.pure.id))
            self.assertIsNone(assignment.delegated_by_user_id)
            self.assertEqual(assignment.status, "ACTIVE")
            self.assertFalse((await reader.get(User, self.target.id)).can_provision_organizations)

    async def test_broad_empty_inactive_and_foreign_profiles_are_rejected_without_clearing_flag(self):
        self.assertEqual((await self._convert(role_id=str(self.broad.id))).status_code, 404)
        self.assertEqual((await self._convert(role_id=str(self.foreign.id))).status_code, 404)
        await self.session.execute(update(OrganizationRole).where(OrganizationRole.id == self.pure.id).values(status="INACTIVE"))
        await self.session.commit()
        self.assertEqual((await self._convert()).status_code, 404)
        await self.session.execute(update(OrganizationRole).where(OrganizationRole.id == self.pure.id).values(status="ACTIVE"))
        await self.session.execute(delete(OrganizationRolePermission).where(OrganizationRolePermission.role_id == self.pure.id))
        await self.session.commit()
        self.assertEqual((await self._convert()).status_code, 404)
        self.assertTrue((await self._review()).json()["legacy_read"])

    async def test_existing_assignment_is_reused_and_revision_is_checked(self):
        await self._assign_fixture(status="INACTIVE")
        self.assertEqual((await self._convert()).status_code, 409)
        response = await self._convert(expected_assignment_revision=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assignment_revision"], 2)
        async with self.factory() as reader:
            self.assertEqual(await reader.scalar(select(func.count()).select_from(OrganizationRoleAssignment).where(
                OrganizationRoleAssignment.organization_id == self.org.id, OrganizationRoleAssignment.user_id == self.target.id)), 1)

    async def test_delegated_assignment_becomes_direct_to_replace_independent_legacy_grant(self):
        await self._assign_fixture(delegated=True)
        self.assertEqual((await self._convert(expected_assignment_revision=1)).status_code, 200)
        async with self.factory() as reader:
            row = await reader.get(OrganizationRoleAssignment, (self.org.id, self.target.id, self.pure.id))
            self.assertIsNone(row.delegated_by_user_id)
            audit = await reader.scalar(select(OrganizationAccessChange).where(
                OrganizationAccessChange.organization_id == self.org.id, OrganizationAccessChange.action == "LEGACY_READ_CONVERTED"))
            self.assertEqual(audit.before_state["assignment"]["delegated_by_user_id"], str(self.delegate.id))
        response = await self.client.put(self.base+f"/members/{self.delegate.id}/status", headers=self.headers[self.owner.id],
            json={"status":"INACTIVE", "expected_revision":1, "password":self.password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.client.get(self.base, headers=self.headers[self.target.id])).status_code, 200)

    async def test_revocation_removes_only_legacy_source_and_reports_other_grants(self):
        await self._assign_fixture(self.broad)
        response = await self._revoke()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["legacy_read"])
        self.assertTrue(response.json()["profile_read"])
        self.assertTrue(response.json()["effective_read"])
        self.assertEqual((await self.client.get(self.base+"/roles", headers=self.headers[self.target.id])).status_code, 200)

    async def test_revocation_without_profile_removes_read_on_next_verification(self):
        response = await self._revoke()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["effective_read"])
        self.assertEqual((await self.client.get(self.base, headers=self.headers[self.target.id])).status_code, 404)
        self.assertEqual((await self._revoke(expected_revision=2)).status_code, 409)

    async def test_inactive_user_or_membership_cannot_be_converted_and_review_is_not_effective(self):
        await self._assign_fixture()
        for model, condition in ((User, User.id == self.target.id),
                                 (OrganizationMembership, (OrganizationMembership.user_id == self.target.id) & (OrganizationMembership.organization_id == self.org.id))):
            await self.session.execute(update(model).where(condition).values(status="INACTIVE"))
            await self.session.commit()
            review = (await self._review()).json()
            self.assertTrue(review["legacy_read"])
            self.assertFalse(review["legacy_effective"])
            self.assertFalse(review["profile_read"])
            self.assertFalse(review["effective_read"])
            self.assertEqual((await self._convert(expected_assignment_revision=1)).status_code, 404)
            await self.session.execute(update(model).where(condition).values(status="ACTIVE"))
            await self.session.commit()

    async def test_revocation_of_inactive_binding_is_cleanup_without_reactivation(self):
        await self.session.execute(update(OrganizationMembership).where(
            OrganizationMembership.user_id == self.target.id, OrganizationMembership.organization_id == self.org.id).values(status="INACTIVE"))
        await self.session.commit()
        response = await self._revoke()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["membership_status"], "INACTIVE")
        self.assertFalse(response.json()["effective_read"])

    async def test_delegate_operator_and_non_owner_cannot_review_convert_or_revoke(self):
        await self._assign_fixture(delegated=True)
        for actor in (self.delegate.id, self.operator.id, self.target.id):
            self.assertEqual((await self._review(actor=actor)).status_code, 404)
            self.assertEqual((await self._convert(actor=actor, expected_assignment_revision=1)).status_code, 404)
            self.assertEqual((await self._revoke(actor=actor)).status_code, 404)

    async def test_cross_tenant_or_absent_target_does_not_change_other_memberships(self):
        for response in (await self._convert(org=uuid4()), await self._revoke(target=self.delegate.id, org=self.other.id),
                         await self._review(target=uuid4())):
            self.assertEqual(response.status_code, 404)
        self.assertEqual((await self._convert()).status_code, 200)
        self.assertTrue((await self._review(org=self.other.id)).json()["legacy_read"])
        self.assertEqual((await self.client.get(f"/api/v1/organizations/{self.other.id}", headers=self.headers[self.target.id])).status_code, 200)

    async def test_master_can_convert_own_read_without_losing_administration(self):
        response = await self._convert(target=self.owner.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["effective_read"])
        self.assertEqual((await self.client.get(self.base+"/members", headers=self.headers[self.owner.id])).status_code, 200)

    async def test_stale_role_or_membership_revision_and_missing_flag_are_conflicts(self):
        self.assertEqual((await self._convert(expected_role_revision=2)).status_code, 409)
        self.assertEqual((await self._convert(expected_revision=2)).status_code, 409)
        self.assertEqual((await self._convert()).status_code, 200)
        self.assertEqual((await self._convert(expected_revision=2, expected_assignment_revision=1)).status_code, 409)

    async def test_concurrent_conversion_and_revocation_have_one_winner(self):
        converted, revoked = await asyncio.gather(self._convert(), self._revoke())
        self.assertEqual(sorted([converted.status_code, revoked.status_code]), [200, 409])
        self.assertFalse((await self._review()).json()["legacy_read"])

    async def test_conversion_racing_deactivation_never_revives_an_inactive_binding(self):
        converted, deactivated = await asyncio.gather(self._convert(), self.client.put(
            self.base+f"/members/{self.target.id}/status", headers=self.headers[self.owner.id],
            json={"status":"INACTIVE", "expected_revision":1, "password":self.password}))
        self.assertEqual(sorted([converted.status_code, deactivated.status_code]), [200, 409])
        review = (await self._review()).json()
        self.assertFalse(review["legacy_read"])
        if review["membership_status"] == "INACTIVE":
            self.assertFalse(review["effective_read"])

    async def test_wrong_password_does_not_change_flag_or_renew_actor_session(self):
        deadline = await self.session.scalar(select(UserSession.expires_at).where(UserSession.user_id == self.owner.id))
        self.assertEqual((await self._convert(password="incorreta")).status_code, 404)
        self.assertEqual(await self.session.scalar(select(UserSession.expires_at).where(UserSession.user_id == self.owner.id)), deadline)
        self.assertEqual((await self._review()).json()["revision"], 1)
        async with self.factory() as reader:
            self.assertIsNone(await reader.get(OrganizationRoleAssignment, (self.org.id, self.target.id, self.pure.id)))

    async def test_revoking_converted_profile_cannot_fall_back_to_old_flag(self):
        self.assertEqual((await self._convert()).status_code, 200)
        response = await self.client.put(self.base+f"/members/{self.target.id}/roles/{self.pure.id}", headers=self.headers[self.owner.id],
            json={"status":"INACTIVE", "expected_revision":1, "expected_role_revision":1, "password":self.password})
        self.assertEqual(response.status_code, 200)
        review = (await self._review()).json()
        self.assertFalse(review["legacy_read"])
        self.assertFalse(review["profile_read"])
        self.assertFalse(review["effective_read"])
        self.assertEqual((await self.client.get(self.base, headers=self.headers[self.target.id])).status_code, 404)

    async def test_audit_failure_rolls_back_flag_assignment_and_revision(self):
        real_flush = AsyncSession.flush

        async def fail_after_audit(session, *args, **kwargs):
            if any(isinstance(row, OrganizationAccessChange) for row in session.new):
                await real_flush(session, *args, **kwargs)
                raise SQLAlchemyError("falha simulada")
            return await real_flush(session, *args, **kwargs)

        with patch.object(AsyncSession, "flush", fail_after_audit):
            response = await self._convert()
        self.assertEqual(response.status_code, 503)
        review = (await self._review()).json()
        self.assertTrue(review["legacy_read"])
        self.assertEqual(review["revision"], 1)
        async with self.factory() as reader:
            self.assertIsNone(await reader.get(OrganizationRoleAssignment, (self.org.id, self.target.id, self.pure.id)))

    async def test_audit_records_only_explicit_conversion_state_and_tenant_target(self):
        await self._convert()
        async with self.factory() as reader:
            audit = await reader.scalar(select(OrganizationAccessChange).where(OrganizationAccessChange.organization_id == self.org.id))
            self.assertEqual(audit.action, "LEGACY_READ_CONVERTED")
            self.assertEqual(audit.role_id, self.pure.id)
            self.assertEqual(audit.actor_user_id, self.owner.id)
            self.assertEqual(audit.target_user_id, self.target.id)
            self.assertEqual(audit.before_state["legacy_read"], True)
            self.assertEqual(audit.after_state["legacy_read"], False)
            self.assertNotIn(self.password, str(audit.after_state))
            self.assertNotIn(self.target.email, str(audit.after_state))

    async def test_rate_limit_shared_between_conversion_and_revocation_precedes_hash(self):
        for _ in range(5):
            self.assertEqual((await self._convert(password="incorreta")).status_code, 404)
        with patch("app.modules.identity.roles.verify_password", new_callable=AsyncMock) as verifier:
            response = await self._revoke()
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers["retry-after"]), 0)
        verifier.assert_not_awaited()

    async def test_redis_failure_and_debug_errors_are_sanitized(self):
        with patch.object(self.redis, "eval", side_effect=ConnectionError("segredo_redis")):
            response = await self._convert()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("segredo_redis", response.text)
        with patch("app.api.v1.legacy_access.LegacyReadService.convert", side_effect=RuntimeError("segredo_app")):
            response = await self._convert()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("segredo_app", response.text)

    async def test_validation_and_body_limits_do_not_echo_credentials(self):
        response = await self._convert(can_read_organization=True)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail":"Dados de entrada inválidos."})
        for content, content_type, status in (("x"*4097,"application/json",413), ("segredo","text/plain",415)):
            response = await self.client.post(self.base+f"/members/{self.target.id}/legacy-read/convert", content=content,
                headers={**self.headers[self.owner.id], "Content-Type":content_type})
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_cancelled_hash_keeps_slot_and_preserves_legacy_flag(self):
        self.app.state.auth_hash_slots = asyncio.Semaphore(1)
        entered, finish = asyncio.Event(), asyncio.Event()

        async def delayed(*args):
            entered.set()
            await finish.wait()
            return True, None

        with patch("app.modules.identity.roles.verify_password", delayed):
            first = asyncio.create_task(self._convert())
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                first.cancel()
                self.assertEqual((await self._revoke()).status_code, 503)
            finally:
                finish.set()
                await asyncio.gather(first, return_exceptions=True)
        self.assertTrue((await self._review()).json()["legacy_read"])

    async def test_bearer_and_production_https_are_required(self):
        path = self.base+f"/members/{self.target.id}/read-access"
        self.assertEqual((await self.client.get(path)).status_code, 401)
        self.app.state.settings = self.config.model_copy(update={"app_environment":"production"})
        self.assertEqual((await self._review()).status_code, 503)
        self.assertEqual((await self._convert()).status_code, 503)


class LegacyReadMigrationTests(DatabaseTestCase):
    async def test_round_trip_preserves_flags_and_blocks_downgrade_that_would_erase_history(self):
        user = User(name="Pessoa", email=uuid4().hex+"@example.com", status="ACTIVE")
        org = Organization(name="Empresa")
        self.session.add_all([user, org])
        await self.session.flush()
        self.session.add(OrganizationMembership(user_id=user.id, organization_id=org.id, status="ACTIVE", can_read_organization=True))
        await self.session.commit()
        user_id, org_id = user.id, org.id
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration, "downgrade", "b92f8d06e4a1")
        finally:
            await asyncio.to_thread(self.run_migration, "upgrade", "head")
        member = await self.session.get(OrganizationMembership, (user_id, org_id))
        self.assertTrue(member.can_read_organization)
        self.assertEqual(member.revision, 1)
        self.session.add(OrganizationAccessChange(organization_id=org_id, actor_user_id=user_id, target_user_id=user_id,
            action="LEGACY_READ_REVOKED", before_state={"legacy_read":True}, after_state={"legacy_read":False}))
        await self.session.commit()
        await self.session.close()
        await self.engine.dispose()
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.run_migration, "downgrade", "b92f8d06e4a1")
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(OrganizationAccessChange)), 1)
        await self.session.close()
        await asyncio.to_thread(self.run_migration, "check")
