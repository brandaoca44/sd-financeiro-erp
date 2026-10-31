"""Valida perfis, teto de delegação, origem da autoridade e compatibilidade de acesso."""

import asyncio
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
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database_support import DatabaseTestCase
from app.core.config import Settings
from app.main import create_app
from app.modules.identity.access_models import OrganizationOwnership, OrganizationRole, OrganizationRoleAssignment, RoleStatus
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.models import (
    MembershipStatus, OrganizationMembership, User, UserPasswordCredential, UserSession, UserStatus,
)
from app.modules.identity.passwords import hash_password
from app.modules.identity.permission_models import (
    OrganizationAccessChange, OrganizationAccessDelegation, OrganizationDelegationPermission, OrganizationRolePermission,
)
from app.modules.identity.permissions import PermissionKey, ROLE_PERMISSIONS
from app.modules.identity.rate_limit import LoginRateLimiter, LoginRateLimitPolicy
from app.modules.identity.role_schemas import AssignmentRequest, DelegationRequest, RoleCreateRequest
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Organization

READ, ROLES = "organizations.read", "identity.roles.read"


class RoleSchemaTests(unittest.TestCase):
    def test_permissions_are_closed_and_administrative_keys_cannot_be_in_roles(self):
        for key in ("*", "fiscal.documents.read", "platform.admin", "identity.roles.manage", "identity.assignments.manage"):
            with self.assertRaises(ValidationError):
                RoleCreateRequest(name="Perfil", permissions=[key], password="segredo")

    def test_no_company_scope_duplicate_permissions_or_actor_override(self):
        for extras in ({"company_id": str(uuid4())}, {"actor_user_id": str(uuid4())}, {"permissions": [READ, READ]}):
            with self.assertRaises(ValidationError):
                RoleCreateRequest(name="Perfil", password="segredo", **extras)

    def test_active_delegation_requires_ceiling_and_revisions_are_strict(self):
        with self.assertRaises(ValidationError):
            DelegationRequest(status="ACTIVE", permissions=[], expected_revision=0, password="segredo")
        with self.assertRaises(ValidationError):
            AssignmentRequest(status="ACTIVE", expected_revision=True, expected_role_revision=1, password="segredo")


@unittest.skipUnless(os.environ.get("SD_RUN_DATABASE_TESTS") == "1" and os.environ.get("SD_RUN_REDIS_TESTS") == "1",
                     "Defina SD_RUN_DATABASE_TESTS=1 e SD_RUN_REDIS_TESTS=1.")
class RoleHttpTests(DatabaseTestCase):
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
        self.password = "Senha ficticia para teste de perfis @123"
        self.owner, self.delegate, self.target, self.other_delegate, self.operator = [
            User(name=name, email=uuid4().hex+"@example.com", status=UserStatus.ACTIVE,
                 can_provision_organizations=(name == "Operador")) for name in ("Master", "Delegado", "Alvo", "Outro delegado", "Operador")]
        self.org, self.other = Organization(name="Empresa"), Organization(name="Outra empresa")
        self.session.add_all([self.owner, self.delegate, self.target, self.other_delegate, self.operator, self.org, self.other])
        await self.session.flush()
        hashed = (await hash_password(SecretStr(self.password))).get_secret_value()
        for user in (self.owner, self.delegate, self.target, self.other_delegate, self.operator):
            self.session.add(UserPasswordCredential(user_id=user.id, password_hash=hashed))
        for user in (self.owner, self.delegate, self.target, self.other_delegate):
            self.session.add(OrganizationMembership(user_id=user.id, organization_id=self.org.id, status=MembershipStatus.ACTIVE))
        await self.session.flush()
        self.session.add(OrganizationOwnership(organization_id=self.org.id, user_id=self.owner.id))
        await self.session.commit()
        self.headers = {}
        for user in (self.owner, self.delegate, self.target, self.other_delegate, self.operator):
            issued = await SessionService(self.session).issue_for_authenticated_user(user.id)
            self.headers[user.id] = {"Authorization": "Bearer "+issued.token.get_secret_value()}
        self.base = f"/api/v1/organizations/{self.org.id}"

    async def _clear_redis(self):
        keys = [key async for key in self.redis.scan_iter(match="{"+self.namespace+":*")]
        if keys:
            await self.redis.delete(*keys)

    def _wide_limit(self):
        self.app.state.access_manage_limiter = LoginRateLimiter(self.redis, key_secret=self.config.auth_rate_limit_key,
            namespace=self.namespace, operation="access_manage", policy=LoginRateLimitPolicy(account_limit=100))

    async def _create(self, *, actor=None, org=None, **changes):
        return await self.client.post(f"/api/v1/organizations/{org or self.org.id}/roles", headers=self.headers[actor or self.owner.id],
            json={"name": "Perfil "+uuid4().hex[:8], "status": "ACTIVE", "permissions": [READ], "password": self.password, **changes})

    async def _role(self, **kwargs):
        response = await self._create(**kwargs)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def _update(self, role, *, actor=None, **changes):
        return await self.client.put(self.base+"/roles/"+role["id"], headers=self.headers[actor or self.owner.id], json={
            "name": role["name"], "category": role["category"], "status": role["status"], "permissions": role["permissions"],
            "expected_revision": role["revision"], "password": self.password, **changes})

    async def _assign(self, role, *, actor=None, target=None, org=None, **changes):
        return await self.client.put(f"/api/v1/organizations/{org or self.org.id}/members/{target or self.target.id}/roles/{role['id']}",
            headers=self.headers[actor or self.owner.id], json={"status": "ACTIVE", "expected_revision": 0,
                "expected_role_revision": role["revision"], "password": self.password, **changes})

    async def _delegation(self, *, target=None, actor=None, **changes):
        return await self.client.put(self.base+f"/members/{target or self.delegate.id}/delegation", headers=self.headers[actor or self.owner.id],
            json={"status": "ACTIVE", "permissions": [READ], "expected_revision": 0, "password": self.password, **changes})

    async def _can(self, user=None, permission=READ):
        async with self.factory() as reader:
            return await OrganizationAccessPolicy(reader).has_permission(user or self.target.id, self.org.id, permission)

    async def _transfer(self, actor, target):
        response = await self.client.post(self.base+"/ownership/transfer", headers=self.headers[actor],
            json={"new_owner_id": str(target), "password": self.password})
        self.assertEqual(response.status_code, 204, response.text)

    async def test_catalog_requires_session_and_lists_only_implemented_keys(self):
        self.assertEqual((await self.client.get("/api/v1/auth/permissions")).status_code, 401)
        response = await self.client.get("/api/v1/auth/permissions", headers=self.headers[self.target.id])
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["key"] for item in response.json()}, {key.value for key in PermissionKey})
        self.assertNotIn(self.target.email, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_role_and_assignment_grant_read_and_revoke_on_next_query(self):
        role = await self._role()
        self.assertFalse(await self._can())
        assigned = await self._assign(role)
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertTrue(await self._can())
        response = await self.client.get(self.base, headers=self.headers[self.target.id])
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self._assign(role, status="INACTIVE", expected_revision=1)).status_code, 200)
        self.assertFalse(await self._can())

    async def test_inactive_defaults_and_ceo_title_never_grant_access(self):
        response = await self.client.post(self.base+"/roles", headers=self.headers[self.owner.id],
            json={"name": "CEO", "category": "CEO", "password": self.password})
        self.assertEqual(response.status_code, 201)
        role = response.json()
        self.assertEqual(role["status"], "INACTIVE")
        self.assertEqual(role["permissions"], [])
        self.assertEqual((await self._assign(role)).status_code, 404)
        role = (await self._update(role, status="ACTIVE")).json()
        self.assertEqual((await self._assign(role)).status_code, 200)
        self.assertFalse(await self._can())
        self.assertFalse(await self._can(permission="identity.roles.manage"))

    async def test_legacy_read_is_preserved_after_role_revocation(self):
        await self.session.execute(update(OrganizationMembership).where(
            OrganizationMembership.user_id == self.target.id).values(can_read_organization=True))
        await self.session.commit()
        role = await self._role()
        await self._assign(role)
        await self._assign(role, status="INACTIVE", expected_revision=1)
        self.assertTrue(await self._can())

    async def test_operator_and_ordinary_member_cannot_manage_profiles(self):
        responses = [await self._create(actor=self.operator.id), await self._create(actor=self.target.id),
                     await self._create(org=self.other.id)]
        self.assertTrue(all(response.status_code == 404 for response in responses))
        self.assertEqual(len({r.text for r in responses}), 1)

    async def test_case_insensitive_role_name_uniqueness_is_per_tenant(self):
        await self._role(name="Cadastro")
        self.assertEqual((await self._create(name="CADASTRO")).status_code, 409)
        self.session.add(OrganizationMembership(user_id=self.owner.id, organization_id=self.other.id, status=MembershipStatus.ACTIVE))
        await self.session.flush()
        self.session.add(OrganizationOwnership(organization_id=self.other.id, user_id=self.owner.id))
        await self.session.commit()
        self.assertEqual((await self._create(name="Cadastro", org=self.other.id)).status_code, 201)

    async def test_cross_tenant_role_and_membership_are_never_accepted(self):
        role = await self._role()
        self.assertEqual((await self._assign(role, org=self.other.id)).status_code, 404)
        self.assertEqual((await self._assign(role, target=self.operator.id)).status_code, 404)
        self.assertFalse(await self._can())

    async def test_read_requires_active_user_membership_role_and_assignment(self):
        role = await self._role()
        await self._assign(role)
        for model, clause in ((User, User.id == self.target.id),
                              (OrganizationMembership, OrganizationMembership.user_id == self.target.id),
                              (OrganizationRole, OrganizationRole.id == role["id"]),
                              (OrganizationRoleAssignment, OrganizationRoleAssignment.user_id == self.target.id)):
            await self.session.execute(update(model).where(clause).values(status="INACTIVE"))
            await self.session.commit()
            self.assertFalse(await self._can())
            await self.session.execute(update(model).where(clause).values(status="ACTIVE"))
            await self.session.commit()
            self.assertTrue(await self._can())

    async def test_wrong_password_does_not_mutate_or_renew_session(self):
        before = await self.session.scalar(select(UserSession.expires_at).where(UserSession.user_id == self.owner.id))
        response = await self._create(password="incorreta")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(OrganizationAccessChange).where(
            OrganizationAccessChange.organization_id == self.org.id)), 0)
        self.assertEqual(await self.session.scalar(select(UserSession.expires_at).where(UserSession.user_id == self.owner.id)), before)

    async def test_concurrent_role_updates_have_one_winner_and_one_revision_conflict(self):
        role = await self._role()
        responses = await asyncio.gather(self._update(role, name="Primeiro"), self._update(role, name="Segundo"))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])

    async def test_assignment_rechecks_both_assignment_and_role_revision(self):
        role = await self._role()
        updated = (await self._update(role, name="Novo nome")).json()
        self.assertEqual((await self._assign(role)).status_code, 409)
        self.assertEqual((await self._assign(updated)).status_code, 200)
        self.assertEqual((await self._assign(updated)).status_code, 409)

    async def test_delegate_can_assign_only_within_explicit_ceiling(self):
        small = await self._role(permissions=[READ])
        large = await self._role(permissions=[READ, ROLES])
        self.assertEqual((await self._delegation()).status_code, 200)
        self.assertEqual((await self._assign(large, actor=self.delegate.id)).status_code, 404)
        self.assertEqual((await self._assign(small, actor=self.delegate.id)).status_code, 200)
        self.assertTrue(await self._can())
        self.assertFalse(await self._can(permission=ROLES))

    async def test_delegate_cannot_promote_self_owner_other_admin_or_redelegate(self):
        self._wide_limit()
        role = await self._role()
        await self._delegation()
        await self._delegation(target=self.other_delegate.id)
        for user in (self.owner, self.delegate, self.other_delegate):
            self.assertEqual((await self._assign(role, actor=self.delegate.id, target=user.id)).status_code, 404)
        self.assertEqual((await self._delegation(actor=self.delegate.id, target=self.target.id)).status_code, 404)
        self.assertEqual((await self._create(actor=self.delegate.id)).status_code, 404)
        self.assertEqual((await self._update(role, actor=self.delegate.id)).status_code, 404)

    async def test_combining_operational_profiles_does_not_create_administrative_authority(self):
        first, second = await self._role(permissions=[READ]), await self._role(permissions=[ROLES])
        await self._assign(first, target=self.delegate.id)
        await self._assign(second, target=self.delegate.id)
        self.assertTrue(await self._can(self.delegate.id, READ))
        self.assertTrue(await self._can(self.delegate.id, ROLES))
        self.assertFalse(await self._can(self.delegate.id, PermissionKey.ASSIGNMENTS_MANAGE))
        self.assertEqual((await self._assign(first, actor=self.delegate.id)).status_code, 404)

    async def test_own_operational_permissions_cannot_expand_delegation_ceiling(self):
        self._wide_limit()
        broad = await self._role(permissions=[READ, ROLES])
        await self._assign(broad, target=self.delegate.id)
        await self._delegation(permissions=[READ])
        self.assertEqual((await self._assign(broad, actor=self.delegate.id)).status_code, 404)

    async def test_revocation_and_reactivation_do_not_revive_old_delegated_assignments(self):
        role = await self._role()
        await self._delegation()
        await self._assign(role, actor=self.delegate.id)
        self.assertTrue(await self._can())
        await self._delegation(status="INACTIVE", expected_revision=1)
        self.assertFalse(await self._can())
        await self._delegation(status="ACTIVE", expected_revision=2)
        self.assertFalse(await self._can())
        self.assertEqual((await self._assign(role, actor=self.delegate.id, expected_revision=1)).status_code, 200)
        self.assertTrue(await self._can())

    async def test_owner_transfer_and_return_do_not_revive_old_delegations(self):
        role = await self._role()
        await self._delegation()
        await self._assign(role, actor=self.delegate.id)
        await self._transfer(self.owner.id, self.other_delegate.id)
        self.assertFalse(await self._can())
        await self._transfer(self.other_delegate.id, self.owner.id)
        self.assertFalse(await self._can())
        response = await self.client.get(self.base+f"/members/{self.delegate.id}/delegation", headers=self.headers[self.owner.id])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["effective"])
        self.assertEqual(response.json()["status"], "ACTIVE")

    async def test_delegated_source_requires_current_owner_and_delegate_to_remain_active(self):
        role = await self._role()
        await self._delegation()
        await self._assign(role, actor=self.delegate.id)
        for model, clause in ((User, User.id == self.owner.id), (User, User.id == self.delegate.id),
                              (OrganizationMembership, OrganizationMembership.user_id == self.owner.id),
                              (OrganizationMembership, OrganizationMembership.user_id == self.delegate.id)):
            await self.session.execute(update(model).where(clause).values(status="INACTIVE"))
            await self.session.commit()
            self.assertFalse(await self._can())
            await self.session.execute(update(model).where(clause).values(status="ACTIVE"))
            await self.session.commit()

    async def test_owner_can_adopt_assignment_without_delegated_source(self):
        role = await self._role()
        await self._delegation()
        await self._assign(role, actor=self.delegate.id)
        self.assertEqual((await self._assign(role, expected_revision=1)).status_code, 200)
        await self._delegation(status="INACTIVE", expected_revision=1)
        self.assertTrue(await self._can())

    async def test_role_expansion_never_exceeds_ceiling_of_existing_delegated_source(self):
        role = await self._role()
        await self._delegation()
        await self._assign(role, actor=self.delegate.id)
        updated = (await self._update(role, permissions=[READ, ROLES])).json()
        self.assertTrue(await self._can())
        self.assertFalse(await self._can(permission=ROLES))
        self.assertEqual((await self._assign(updated, actor=self.delegate.id, expected_revision=1)).status_code, 404)
        self.assertEqual((await self._assign(updated, expected_revision=1)).status_code, 200)
        self.assertTrue(await self._can(permission=ROLES))

    async def test_owner_does_not_receive_implicit_read_but_can_grant_own_operational_role(self):
        self.assertFalse(await self._can(self.owner.id))
        role = await self._role()
        self.assertEqual((await self._assign(role, target=self.owner.id)).status_code, 200)
        self.assertTrue(await self._can(self.owner.id))
        self.assertFalse(await self._can(permission="unknown.permission"))

    async def test_inactive_target_cannot_receive_active_assignment_but_can_be_revoked(self):
        role = await self._role()
        await self._assign(role)
        await self.session.execute(update(User).where(User.id == self.target.id).values(status=UserStatus.INACTIVE))
        await self.session.commit()
        self.assertEqual((await self._assign(role, expected_revision=1)).status_code, 404)
        self.assertEqual((await self._assign(role, expected_revision=1, status="INACTIVE")).status_code, 200)

    async def test_members_directory_is_owner_only_minimal_and_paginated(self):
        self.assertEqual((await self.client.get(self.base+"/members", headers=self.headers[self.delegate.id])).status_code, 404)
        response = await self.client.get(self.base+"/members?limit=2", headers=self.headers[self.owner.id])
        self.assertEqual(response.status_code, 200)
        page = response.json()
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(set(page["items"][0]), {"user_id", "name", "email", "status", "legacy_read", "revision"})
        self.assertNotIn(self.operator.email, response.text)
        self.assertNotIn(self.password, response.text)
        next_page = await self.client.get(self.base+"/members?limit=2&cursor="+page["next_cursor"], headers=self.headers[self.owner.id])
        self.assertEqual(len(next_page.json()["items"]), 2)
        self.assertFalse({r["user_id"] for r in page["items"]} & {r["user_id"] for r in next_page.json()["items"]})

    async def test_roles_read_grants_only_paginated_profile_metadata(self):
        role = await self._role(permissions=[ROLES])
        await self._role()
        await self._assign(role)
        response = await self.client.get(self.base+"/roles?limit=1", headers=self.headers[self.target.id])
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()["next_cursor"])
        self.assertEqual(set(response.json()["items"][0]), {"id", "name", "category", "status", "revision", "permissions"})
        self.assertEqual((await self.client.get(self.base+"/members", headers=self.headers[self.target.id])).status_code, 404)
        self.assertEqual((await self.client.get(self.base+f"/members/{self.target.id}/roles", headers=self.headers[self.target.id])).status_code, 404)

    async def test_rate_limit_is_shared_across_management_endpoints_and_sessions(self):
        for _ in range(5):
            self.assertEqual((await self._create(password="incorreta")).status_code, 404)
        issued = await SessionService(self.session).issue_for_authenticated_user(self.owner.id)
        self.headers[self.owner.id] = {"Authorization": "Bearer "+issued.token.get_secret_value(), "X-Forwarded-For": "198.51.100.1"}
        with patch("app.modules.identity.roles.verify_password", new_callable=AsyncMock) as verifier:
            response = await self._delegation()
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers["retry-after"]), 0)
        verifier.assert_not_awaited()

    async def test_redis_failure_blocks_mutation_and_logout_remains_available(self):
        with patch.object(self.redis, "eval", side_effect=ConnectionError("segredo_redis")):
            response = await self._create()
            logout = await self.client.post("/api/v1/auth/logout", headers=self.headers[self.owner.id])
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("segredo_redis", response.text)
        self.assertEqual(logout.status_code, 204)

    async def test_cancellation_keeps_shared_hash_slot_and_rolls_back_role_creation(self):
        self.app.state.auth_hash_slots = asyncio.Semaphore(1)
        entered, finish = asyncio.Event(), asyncio.Event()

        async def delayed(*args):
            entered.set()
            await finish.wait()
            return True, None

        with patch("app.modules.identity.roles.verify_password", delayed):
            first = asyncio.create_task(self._create())
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                first.cancel()
                self.assertEqual((await self._create()).status_code, 503)
            finally:
                finish.set()
                await asyncio.gather(first, return_exceptions=True)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(OrganizationRole).where(
            OrganizationRole.organization_id == self.org.id)), 0)

    async def test_audit_failure_rolls_back_role_permissions_and_revision(self):
        role = await self._role()
        real_flush = AsyncSession.flush

        async def fail_after_audit(session, *args, **kwargs):
            if any(isinstance(row, OrganizationAccessChange) for row in session.new):
                await real_flush(session, *args, **kwargs)
                raise SQLAlchemyError("falha simulada")
            return await real_flush(session, *args, **kwargs)

        with patch.object(AsyncSession, "flush", fail_after_audit):
            result = await self._update(role, permissions=[ROLES])
        self.assertEqual(result.status_code, 503)
        async with self.factory() as reader:
            stored = await reader.get(OrganizationRole, role["id"])
            self.assertEqual(stored.revision, 1)
            self.assertEqual((await reader.scalars(select(OrganizationRolePermission.permission_key).where(
                OrganizationRolePermission.role_id == role["id"]))).all(), [READ])

    async def test_validation_put_body_limits_and_no_sensitive_error_echo(self):
        role = await self._role()
        response = await self._create(permissions=["identity.roles.manage"])
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(self.password, response.text)
        response = await self.client.put(self.base+"/roles/"+role["id"], content="x"*4097,
            headers={**self.headers[self.owner.id], "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.headers["cache-control"], "no-store")
        wrong_type = await self.client.put(self.base+"/roles/"+role["id"], content="segredo",
            headers={**self.headers[self.owner.id], "Content-Type": "text/plain"})
        self.assertEqual(wrong_type.status_code, 415)
        invalid = await self.client.get(self.base+"/roles?limit=101", headers=self.headers[self.owner.id])
        self.assertEqual(invalid.status_code, 422)

    async def test_database_and_unexpected_errors_do_not_escape_debug_responses(self):
        for error, code in ((SQLAlchemyError("segredo_sql"), 503), (RuntimeError("segredo_app"), 500)):
            with patch("app.api.v1.roles.RoleService.create", side_effect=error):
                response = await self._create()
            self.assertEqual(response.status_code, code)
            self.assertNotIn("segredo", response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_catalog_and_writes_reject_http_in_production(self):
        self.app.state.settings = self.config.model_copy(update={"app_environment": "production"})
        self.assertEqual((await self._create()).status_code, 503)
        self.assertEqual((await self.client.get("/api/v1/auth/permissions", headers=self.headers[self.owner.id])).status_code, 503)

    async def test_database_rejects_unknown_cross_tenant_and_partial_source_grants(self):
        role = await self._role()
        for grant in (OrganizationRolePermission(organization_id=self.org.id, role_id=role["id"], permission_key="platform.admin"),
                      OrganizationRolePermission(organization_id=self.other.id, role_id=role["id"], permission_key=READ)):
            with self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    self.session.add(grant)
                    await self.session.flush()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(OrganizationRoleAssignment(organization_id=self.org.id, user_id=self.target.id, role_id=role["id"],
                    delegated_by_user_id=self.delegate.id, delegation_revision=None))
                await self.session.flush()

    async def test_migration_round_trip_preserves_flags_and_does_not_seed_new_access(self):
        role = await self._role()
        await self._delegation()
        await self._assign(role, actor=self.delegate.id)
        await self.session.execute(update(OrganizationMembership).where(
            OrganizationMembership.user_id == self.other_delegate.id).values(can_read_organization=True))
        await self.session.commit()
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration, "downgrade", "f3a82c17d905")
        finally:
            await asyncio.to_thread(self.run_migration, "upgrade", "head")
        async with self.factory() as reader:
            self.assertTrue((await reader.get(OrganizationMembership, (self.other_delegate.id, self.org.id))).can_read_organization)
            self.assertTrue((await reader.get(User, self.operator.id)).can_provision_organizations)
            self.assertEqual(await reader.scalar(select(func.count()).select_from(OrganizationRolePermission)), 0)
            assignment = await reader.get(OrganizationRoleAssignment, (self.org.id, self.target.id, role["id"]))
            self.assertEqual(assignment.status, "INACTIVE")
            self.assertIsNone(assignment.delegated_by_user_id)
            self.assertEqual((await reader.get(OrganizationRole, role["id"])).revision, 1)
        await asyncio.to_thread(self.run_migration, "check")

    async def test_owner_reads_paginated_assignments_and_absent_delegation_without_secrets(self):
        first, second = await self._role(), await self._role()
        await self._assign(first)
        await self._assign(second)
        response = await self.client.get(self.base+f"/members/{self.target.id}/roles?limit=1", headers=self.headers[self.owner.id])
        self.assertEqual(response.status_code, 200)
        page = response.json()
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(set(page["items"][0]), {"user_id", "role_id", "status", "revision"})
        self.assertIsNotNone(page["next_cursor"])
        self.assertNotIn(self.password, response.text)
        self.assertNotIn(self.target.email, response.text)
        empty = await self.client.get(self.base+f"/members/{self.target.id}/delegation", headers=self.headers[self.owner.id])
        self.assertEqual(empty.status_code, 200)
        self.assertIsNone(empty.json())

    async def test_revocation_racing_assignment_never_leaves_effective_delegated_access(self):
        role = await self._role()
        await self._delegation()
        assigned, revoked = await asyncio.gather(self._assign(role, actor=self.delegate.id),
                                               self._delegation(status="INACTIVE", expected_revision=1))
        self.assertIn(assigned.status_code, (200, 404))
        self.assertEqual(revoked.status_code, 200)
        self.assertFalse(await self._can())

    async def test_audit_snapshots_are_minimal_and_bound_to_actor_tenant_and_target(self):
        role = await self._role()
        await self._assign(role)
        rows = (await self.session.scalars(select(OrganizationAccessChange).where(
            OrganizationAccessChange.organization_id == self.org.id).order_by(OrganizationAccessChange.created_at))).all()
        self.assertEqual([row.action for row in rows], ["ROLE_CREATED", "ASSIGNMENT_SET"])
        self.assertTrue(all(row.actor_user_id == self.owner.id and str(row.role_id) == role["id"] for row in rows))
        self.assertEqual(rows[1].target_user_id, self.target.id)
        payload = str([(row.before_state, row.after_state) for row in rows])
        self.assertNotIn(self.password, payload)
        self.assertNotIn(self.owner.email, payload)
        self.assertNotIn("password_hash", payload)
        self.assertNotIn("token", payload)

    async def test_delegate_can_inspect_only_assignments_within_ceiling_for_known_non_admin_target(self):
        self._wide_limit()
        small, broad = await self._role(permissions=[READ]), await self._role(permissions=[READ, ROLES])
        await self._assign(small)
        await self._assign(broad)
        await self._delegation()
        response = await self.client.get(self.base+f"/members/{self.target.id}/roles", headers=self.headers[self.delegate.id])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["role_id"] for item in response.json()["items"]], [small["id"]])
        for path in (self.base+"/members", self.base+f"/members/{self.owner.id}/roles",
                     self.base+f"/members/{self.delegate.id}/roles", self.base+f"/members/{self.target.id}/delegation"):
            self.assertEqual((await self.client.get(path, headers=self.headers[self.delegate.id])).status_code, 404)
