"""Valida ciclo do vínculo, proteção do Master e revogação sem efeitos entre tenants."""

import asyncio
import hashlib
import os
import secrets
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from pydantic import SecretStr, ValidationError
from redis.asyncio import Redis
from redis.exceptions import ConnectionError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from database_support import DatabaseTestCase
from app.core.config import Settings
from app.main import create_app
from app.modules.identity.access_models import OrganizationOwnership, OrganizationRole, OrganizationRoleAssignment, RoleStatus
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.invitation_models import OrganizationInvitation
from app.modules.identity.membership_schemas import MembershipStatusRequest
from app.modules.identity.models import (
    MembershipStatus, OrganizationMembership, User, UserPasswordCredential, UserSession, UserStatus,
)
from app.modules.identity.passwords import hash_password
from app.modules.identity.permission_models import OrganizationAccessChange, OrganizationAccessDelegation, OrganizationDelegationPermission, OrganizationRolePermission
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Organization


class MembershipSchemaTests(unittest.TestCase):
    def test_rejects_identity_overrides_privileges_and_extra_scope(self):
        for extras in ({"user_status": "ACTIVE"}, {"can_read_organization": True}, {"actor_user_id": str(uuid4())}, {"company_id": str(uuid4())}):
            with self.assertRaises(ValidationError):
                MembershipStatusRequest(status="INACTIVE", expected_revision=1, password="segredo", **extras)

    def test_requires_explicit_status_and_positive_strict_revision(self):
        for changes in ({"status": "DELETED"}, {"expected_revision": 0}, {"expected_revision": True}, {"expected_revision": "1"}):
            with self.assertRaises(ValidationError):
                MembershipStatusRequest(**{"status": "ACTIVE", "expected_revision": 1, "password": "segredo", **changes})

    def test_password_is_masked_and_keeps_symbols(self):
        data = MembershipStatusRequest(status="INACTIVE", expected_revision=1, password=" teste @ ")
        self.assertNotIn(" teste @ ", repr(data))
        self.assertEqual(data.password.get_secret_value(), " teste @ ")


@unittest.skipUnless(os.environ.get("SD_RUN_DATABASE_TESTS") == "1" and os.environ.get("SD_RUN_REDIS_TESTS") == "1",
                     "Defina SD_RUN_DATABASE_TESTS=1 e SD_RUN_REDIS_TESTS=1.")
class MembershipHttpTests(DatabaseTestCase):
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
        self.password = "Senha ficticia de ciclo de vinculos @123"
        self.owner, self.target, self.delegate, self.operator = [User(name=name, email=uuid4().hex+"@example.com",
            status=UserStatus.ACTIVE, can_provision_organizations=(name == "Operador")) for name in ("Master", "Alvo", "Delegado", "Operador")]
        self.org, self.other = Organization(name="Empresa"), Organization(name="Outra empresa")
        self.session.add_all([self.owner, self.target, self.delegate, self.operator, self.org, self.other])
        await self.session.flush()
        hashed = (await hash_password(SecretStr(self.password))).get_secret_value()
        for user in (self.owner, self.target, self.delegate, self.operator):
            self.session.add(UserPasswordCredential(user_id=user.id, password_hash=hashed))
        for organization in (self.org, self.other):
            for user in (self.owner, self.target):
                self.session.add(OrganizationMembership(user_id=user.id, organization_id=organization.id,
                    status=MembershipStatus.ACTIVE, can_read_organization=True))
        self.session.add(OrganizationMembership(user_id=self.delegate.id, organization_id=self.org.id, status=MembershipStatus.ACTIVE))
        await self.session.flush()
        self.session.add_all([OrganizationOwnership(organization_id=org.id, user_id=self.owner.id) for org in (self.org, self.other)])
        self.role = OrganizationRole(organization_id=self.org.id, name="Leitura", status=RoleStatus.ACTIVE)
        self.session.add(self.role)
        await self.session.flush()
        self.session.add_all([OrganizationRolePermission(organization_id=self.org.id, role_id=self.role.id, permission_key="organizations.read"),
            OrganizationRoleAssignment(organization_id=self.org.id, user_id=self.target.id, role_id=self.role.id, status="ACTIVE")])
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

    async def _set(self, *, actor=None, target=None, org=None, **changes):
        return await self.client.put(f"/api/v1/organizations/{org or self.org.id}/members/{target or self.target.id}/status",
            headers=self.headers[actor or self.owner.id], json={"status": "INACTIVE", "expected_revision": 1,
                "password": self.password, **changes})

    async def _member(self, user=None, org=None):
        async with self.factory() as reader:
            return await reader.get(OrganizationMembership, (user or self.target.id, org or self.org.id))

    async def _delegate(self):
        self.session.add(OrganizationAccessDelegation(organization_id=self.org.id, user_id=self.delegate.id,
            granted_by_user_id=self.owner.id, owner_revision=1, status="ACTIVE"))
        await self.session.flush()
        self.session.add(OrganizationDelegationPermission(organization_id=self.org.id, user_id=self.delegate.id,
                                                         permission_key="organizations.read"))
        await self.session.commit()

    async def _pending_invite(self, *, org=None, issued_by=None, email=None):
        invitation = OrganizationInvitation(organization_id=org or self.org.id,
            email=email or uuid4().hex+"@example.com", kind="MEMBER", can_read_organization=False,
            token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
            issued_by_user_id=issued_by or self.owner.id, expires_at=datetime.now(timezone.utc)+timedelta(hours=24))
        self.session.add(invitation)
        await self.session.commit()
        return invitation.id

    async def test_owner_reads_minimal_status_and_revision(self):
        response = await self.client.get(self.base+f"/members/{self.target.id}/status", headers=self.headers[self.owner.id])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user_id": str(self.target.id), "status": "ACTIVE", "revision": 1})
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn(self.target.email, response.text)

    async def test_deactivation_removes_legacy_read_and_inactivates_role_assignments(self):
        response = await self._set()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"user_id": str(self.target.id), "status": "INACTIVE", "revision": 2})
        member = await self._member()
        self.assertFalse(member.can_read_organization)
        async with self.factory() as reader:
            assignment = await reader.get(OrganizationRoleAssignment, (self.org.id, self.target.id, self.role.id))
            self.assertEqual(assignment.status, "INACTIVE")
            self.assertEqual(assignment.revision, 2)
        self.assertEqual((await self.client.get(self.base, headers=self.headers[self.target.id])).status_code, 404)

    async def test_reactivation_does_not_restore_old_grants_but_allows_explicit_new_assignment(self):
        await self._set()
        self.assertEqual((await self._set(status="ACTIVE", expected_revision=2)).status_code, 200)
        self.assertEqual((await self._member()).status, "ACTIVE")
        self.assertEqual((await self.client.get(self.base, headers=self.headers[self.target.id])).status_code, 404)
        response = await self.client.put(self.base+f"/members/{self.target.id}/roles/{self.role.id}", headers=self.headers[self.owner.id],
            json={"status":"ACTIVE", "expected_revision":3, "expected_role_revision":1, "password":self.password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.client.get(self.base, headers=self.headers[self.target.id])).status_code, 200)
        self.assertFalse((await self._member()).can_read_organization)

    async def test_current_owner_cannot_be_changed_or_deactivated_by_status_flow(self):
        for status in ("INACTIVE", "ACTIVE"):
            self.assertEqual((await self._set(target=self.owner.id, status=status)).status_code, 404)
        self.assertEqual((await self._member(self.owner.id)).status, "ACTIVE")
        self.assertEqual((await self._member(self.owner.id)).revision, 1)

    async def test_after_transfer_new_owner_can_deactivate_previous_owner(self):
        response = await self.client.post(self.base+"/ownership/transfer", headers=self.headers[self.owner.id],
            json={"new_owner_id":str(self.target.id), "password":self.password})
        self.assertEqual(response.status_code, 204)
        self.assertEqual((await self._set(actor=self.target.id, target=self.owner.id)).status_code, 200)
        self.assertEqual((await self._member(self.target.id)).status, "ACTIVE")

    async def test_tenant_deactivation_preserves_global_identity_sessions_and_other_tenant_access(self):
        await self._set()
        async with self.factory() as reader:
            user = await reader.get(User, self.target.id)
            self.assertEqual(user.status, "ACTIVE")
            self.assertFalse(user.can_provision_organizations)
            self.assertEqual(await reader.scalar(select(func.count()).select_from(UserSession).where(
                UserSession.user_id == self.target.id, UserSession.revoked_at.is_not(None))), 0)
        self.assertEqual((await self._member(org=self.other.id)).status, "ACTIVE")
        self.assertTrue((await self._member(org=self.other.id)).can_read_organization)
        other = await self.client.get(f"/api/v1/organizations/{self.other.id}", headers=self.headers[self.target.id])
        self.assertEqual(other.status_code, 200)
        self.assertEqual((await self.client.get("/api/v1/auth/permissions", headers=self.headers[self.target.id])).status_code, 200)

    async def test_delegate_and_platform_operator_cannot_manage_or_read_status(self):
        await self._delegate()
        for user in (self.delegate, self.operator, self.target):
            self.assertEqual((await self._set(actor=user.id)).status_code, 404)
            self.assertEqual((await self.client.get(self.base+f"/members/{self.target.id}/status", headers=self.headers[user.id])).status_code, 404)

    async def test_cross_tenant_or_missing_membership_has_same_denial(self):
        responses = [await self._set(target=uuid4()), await self._set(target=self.delegate.id, org=self.other.id), await self._set(org=uuid4())]
        self.assertTrue(all(response.status_code == 404 for response in responses))
        self.assertEqual(len({response.text for response in responses}), 1)

    async def test_deactivating_delegate_invalidates_derived_grants_and_reactivation_does_not_restore_them(self):
        await self._delegate()
        await self.session.execute(update(OrganizationMembership).where(
            OrganizationMembership.user_id == self.target.id, OrganizationMembership.organization_id == self.org.id).values(can_read_organization=False))
        await self.session.execute(update(OrganizationRoleAssignment).where(OrganizationRoleAssignment.organization_id == self.org.id).values(
            delegated_by_user_id=self.delegate.id, delegation_revision=1))
        await self.session.commit()
        self.assertEqual((await self.client.get(self.base, headers=self.headers[self.target.id])).status_code, 200)
        self.assertEqual((await self._set(target=self.delegate.id)).status_code, 200)
        self.assertEqual((await self.client.get(self.base, headers=self.headers[self.target.id])).status_code, 404)
        self.assertEqual((await self._set(target=self.delegate.id, status="ACTIVE", expected_revision=2)).status_code, 200)
        async with self.factory() as reader:
            delegation = await reader.get(OrganizationAccessDelegation, (self.org.id, self.delegate.id))
            assignment = await reader.get(OrganizationRoleAssignment, (self.org.id, self.target.id, self.role.id))
            self.assertEqual(delegation.status, "INACTIVE")
            self.assertEqual(delegation.revision, 3)
            self.assertEqual(assignment.status, "INACTIVE")

    async def test_pending_invitations_to_or_from_target_are_revoked_only_in_same_tenant(self):
        to_target = await self._pending_invite(email=self.target.email)
        from_target = await self._pending_invite(issued_by=self.target.id)
        other = await self._pending_invite(org=self.other.id, email=self.target.email)
        await self._set()
        async with self.factory() as reader:
            for invitation_id in (to_target, from_target):
                invitation = await reader.get(OrganizationInvitation, invitation_id)
                self.assertIsNotNone(invitation.revoked_at)
                self.assertEqual(invitation.revoked_by_user_id, self.owner.id)
            self.assertIsNone((await reader.get(OrganizationInvitation, other)).revoked_at)

    async def test_activation_of_globally_inactive_user_is_denied(self):
        await self._set()
        await self.session.execute(update(User).where(User.id == self.target.id).values(status="INACTIVE"))
        await self.session.commit()
        self.assertEqual((await self._set(status="ACTIVE", expected_revision=2)).status_code, 404)
        self.assertEqual((await self._member()).status, "INACTIVE")

    async def test_wrong_password_does_not_mutate_audit_or_renew_actor_session(self):
        before = await self.session.scalar(select(UserSession.expires_at).where(UserSession.user_id == self.owner.id))
        self.assertEqual((await self._set(password="incorreta")).status_code, 404)
        self.assertEqual((await self._member()).revision, 1)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(OrganizationAccessChange).where(
            OrganizationAccessChange.organization_id == self.org.id)), 0)
        self.assertEqual(await self.session.scalar(select(UserSession.expires_at).where(UserSession.user_id == self.owner.id)), before)

    async def test_stale_and_concurrent_revisions_do_not_overwrite_each_other(self):
        responses = await asyncio.gather(self._set(), self._set())
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
        self.assertEqual((await self._member()).revision, 2)
        self.assertEqual((await self._set(status="ACTIVE", expected_revision=1)).status_code, 409)

    async def test_transfer_racing_deactivation_never_leaves_owner_inactive(self):
        deactivate, transfer = await asyncio.gather(self._set(), self.client.post(self.base+"/ownership/transfer",
            headers=self.headers[self.owner.id], json={"new_owner_id":str(self.target.id), "password":self.password}))
        self.assertIn((deactivate.status_code, transfer.status_code), ((200, 404), (404, 204)))
        async with self.factory() as reader:
            owner = await reader.get(OrganizationOwnership, self.org.id)
            self.assertEqual((await reader.get(OrganizationMembership, (owner.user_id, self.org.id))).status, "ACTIVE")

    async def test_audit_failure_rolls_back_status_legacy_roles_delegation_and_invites(self):
        await self._delegate()
        invitation_id = await self._pending_invite(email=self.delegate.email)
        real_flush = AsyncSession.flush

        async def fail_after_audit(session, *args, **kwargs):
            if any(isinstance(row, OrganizationAccessChange) for row in session.new):
                await real_flush(session, *args, **kwargs)
                raise SQLAlchemyError("falha simulada")
            return await real_flush(session, *args, **kwargs)

        with patch.object(AsyncSession, "flush", fail_after_audit):
            result = await self._set(target=self.delegate.id)
        self.assertEqual(result.status_code, 503)
        self.assertEqual((await self._member(self.delegate.id)).status, "ACTIVE")
        self.assertEqual((await self._member(self.delegate.id)).revision, 1)
        async with self.factory() as reader:
            self.assertEqual((await reader.get(OrganizationAccessDelegation, (self.org.id, self.delegate.id))).status, "ACTIVE")
            self.assertIsNone((await reader.get(OrganizationInvitation, invitation_id)).revoked_at)

    async def test_audit_has_only_minimal_snapshots_and_cleanup_counts(self):
        await self._set()
        async with self.factory() as reader:
            audit = await reader.scalar(select(OrganizationAccessChange).where(
                OrganizationAccessChange.organization_id == self.org.id, OrganizationAccessChange.action == "MEMBERSHIP_SET"))
            self.assertEqual(audit.actor_user_id, self.owner.id)
            self.assertEqual(audit.target_user_id, self.target.id)
            self.assertEqual(audit.before_state["legacy_read"], True)
            self.assertEqual(audit.after_state["assignments_reset"], 1)
            self.assertEqual(audit.after_state["revision"], 2)
            self.assertNotIn(self.password, str(audit.after_state))
            self.assertNotIn(self.target.email, str(audit.after_state))

    async def test_rate_limit_is_shared_with_other_access_management_and_precedes_password_work(self):
        for _ in range(5):
            self.assertEqual((await self._set(password="incorreta")).status_code, 404)
        with patch("app.modules.identity.roles.verify_password", new_callable=AsyncMock) as verifier:
            response = await self.client.post(self.base+"/roles", headers={**self.headers[self.owner.id], "X-Forwarded-For":"198.51.100.9"},
                json={"name":"Teste", "password":self.password})
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers["retry-after"]), 0)
        verifier.assert_not_awaited()

    async def test_redis_failure_blocks_status_change_without_preventing_logout(self):
        with patch.object(self.redis, "eval", side_effect=ConnectionError("segredo_redis")):
            response = await self._set()
            logout = await self.client.post("/api/v1/auth/logout", headers=self.headers[self.owner.id])
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("segredo_redis", response.text)
        self.assertEqual(logout.status_code, 204)

    async def test_request_validation_and_body_limits_do_not_echo_sensitive_input(self):
        response = await self._set(can_read_organization=True)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail":"Dados de entrada inválidos."})
        url = self.base+f"/members/{self.target.id}/status"
        for content, content_type, status in (("x"*4097,"application/json",413), ("segredo","text/plain",415)):
            response = await self.client.put(url, content=content, headers={**self.headers[self.owner.id],"Content-Type":content_type})
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_missing_revoked_session_and_http_production_are_denied(self):
        url = self.base+f"/members/{self.target.id}/status"
        self.assertEqual((await self.client.get(url)).status_code, 401)
        await self.client.post("/api/v1/auth/logout", headers=self.headers[self.owner.id])
        self.assertEqual((await self._set()).status_code, 401)
        self.app.state.settings = self.config.model_copy(update={"app_environment":"production"})
        self.assertEqual((await self.client.get(url,headers=self.headers[self.target.id])).status_code, 503)

    async def test_unexpected_error_is_sanitized_even_in_debug(self):
        with patch("app.api.v1.memberships.MembershipService.set_status", side_effect=RuntimeError("segredo_interno")):
            response = await self._set()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("segredo",response.text)
        self.assertEqual(response.headers["cache-control"],"no-store")

    async def test_cancelled_password_work_keeps_slot_and_does_not_change_status(self):
        self.app.state.auth_hash_slots = asyncio.Semaphore(1)
        entered, finish = asyncio.Event(), asyncio.Event()

        async def delayed(*args):
            entered.set()
            await finish.wait()
            return True,None

        with patch("app.modules.identity.roles.verify_password",delayed):
            first = asyncio.create_task(self._set())
            try:
                await asyncio.wait_for(entered.wait(),timeout=5)
                first.cancel()
                self.assertEqual((await self._set()).status_code,503)
            finally:
                finish.set()
                await asyncio.gather(first,return_exceptions=True)
        self.assertEqual((await self._member()).status,"ACTIVE")


class MembershipMigrationTests(DatabaseTestCase):
    async def test_round_trip_preserves_data_and_downgrade_refuses_to_erase_new_history(self):
        user = User(name="Pessoa",email=uuid4().hex+"@example.com",status=UserStatus.ACTIVE)
        org = Organization(name="Empresa")
        self.session.add_all([user,org])
        await self.session.flush()
        self.session.add(OrganizationMembership(user_id=user.id,organization_id=org.id,status="ACTIVE",can_read_organization=True))
        await self.session.commit()
        user_id,org_id=user.id,org.id
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration,"downgrade","a81e73c405bf")
        finally:
            await asyncio.to_thread(self.run_migration,"upgrade","head")
        member=await self.session.get(OrganizationMembership,(user_id,org_id))
        self.assertEqual(member.revision,1)
        self.assertTrue(member.can_read_organization)
        self.assertEqual(member.status,"ACTIVE")
        self.session.add(OrganizationAccessChange(organization_id=org_id,actor_user_id=user_id,target_user_id=user_id,
            action="MEMBERSHIP_SET",before_state={"revision":1},after_state={"revision":2}))
        await self.session.commit()
        await self.session.close()
        await self.engine.dispose()
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.run_migration,"downgrade","a81e73c405bf")
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(OrganizationAccessChange)),1)
        await self.session.close()
        await asyncio.to_thread(self.run_migration,"check")
