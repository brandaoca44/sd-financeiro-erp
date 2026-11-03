"""Concessões financeiras fechadas e independentes no escopo exato da empresa."""

import asyncio
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from redis.exceptions import ConnectionError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database_support import DatabaseTestCase
from test_company_access import CompanyGrantHttpFixture
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.company_access_models import CompanyPermissionGrant, CompanyPermissionChange
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.models import OrganizationMembership, User
from app.modules.identity.permissions import FinancialPermissionKey, FINANCIAL_PERMISSIONS
from app.modules.identity.role_schemas import RoleCreateRequest
from app.modules.organizations.models import Company, Organization


class FinancialPermissionSchemaTests(unittest.TestCase):
    def test_closed_keys_and_no_organization_role_grants(self):
        self.assertEqual(set(FINANCIAL_PERMISSIONS), {"payables.read", "payables.manage", "payables.settle", "payables.reverse"})
        for key in FINANCIAL_PERMISSIONS:
            with self.assertRaises(ValidationError):
                RoleCreateRequest(name="CEO", permissions=[key], password="segredo")
        for key in ("*", "payables.*", "companies.read", "identity.roles.manage"):
            with self.assertRaises(ValueError):
                FinancialPermissionKey(key)


class FinancialPermissionHttpTests(CompanyGrantHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.enable_business_contracts()
        self.original_limiter = self.app.state.access_manage_limiter
        self._wide_limit()

    def path(self, key="payables.read", company=None, user=None, org=None):
        company = company or self.a
        return f"/api/v1/organizations/{org or company.organization_id}/companies/{company.id}/members/{user or self.member.id}/permissions/{key}"

    async def grant(self, key="payables.read", *, company=None, actor=None, user=None, org=None, **changes):
        return await self.client.put(self.path(key, company, user, org), headers=self.headers[actor or self.owner.id],
            json={"status": "ACTIVE", "expected_revision": 0, "expected_company_revision": 1,
                  "expected_membership_revision": 1, "password": self.password, **changes})

    async def allowed(self, key, *, user=None, company=None, org=None):
        company = company or self.a
        async with self.factory() as reader:
            return await CompanyAccessPolicy(reader).has_financial_permission(user or self.member.id,
                org or company.organization_id, company.id, key)

    async def test_no_implicit_grants_from_tenant_flags_platform_or_company_read(self):
        self.assertEqual((await self._set()).status_code, 200)
        for key in FINANCIAL_PERMISSIONS:
            self.assertFalse(await self.allowed(key))
            self.assertFalse(await self.allowed(key, user=self.operator.id))

    async def test_four_independent_permissions_and_no_company_read_escalation(self):
        for key in FINANCIAL_PERMISSIONS:
            response = await self.grant(key)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["permission_key"], key)
            self.assertTrue(response.json()["effective"])
            self.assertTrue(await self.allowed(key))
            self.assertFalse(await self.allowed(key, company=self.b))
        self.assertEqual((await self._get()).status_code, 404)

    async def test_settle_does_not_imply_read_manage_or_reverse(self):
        self.assertEqual((await self.grant("payables.settle")).status_code, 200)
        for key in FINANCIAL_PERMISSIONS:
            self.assertEqual(await self.allowed(key), key == "payables.settle")

    async def test_only_master_manages_and_target_master_is_rejected(self):
        for user in (self.member, self.operator):
            self.assertEqual((await self.grant(actor=user.id)).status_code, 404)
            response = await self.client.get(self.path(), headers=self.headers[user.id])
            self.assertEqual(response.status_code, 404)
        self.assertEqual((await self.grant(user=self.owner.id)).status_code, 404)

    async def test_owner_authority_requires_exact_active_company(self):
        for key in FINANCIAL_PERMISSIONS:
            self.assertTrue(await self.allowed(key, user=self.owner.id))
            async with self.factory() as reader:
                self.assertFalse(await OrganizationAccessPolicy(reader).has_permission(self.owner.id, self.org.id, key))
        self.assertFalse(await self.allowed("payables.read", user=self.owner.id, company=self.foreign, org=self.org.id))
        self.assertEqual((await self._update_company(status="INACTIVE", revision=1)).status_code, 200)
        self.assertFalse(await self.allowed("payables.read", user=self.owner.id))

    async def test_read_configuration_and_unknown_keys_are_minimal(self):
        response = await self.client.get(self.path(), headers=self.headers[self.owner.id])
        self.assertIsNone(response.json())
        self.assertEqual((await self.grant()).status_code, 200)
        response = await self.client.get(self.path(), headers=self.headers[self.owner.id])
        self.assertEqual(set(response.json()), {"company_id", "user_id", "permission_key", "status", "revision", "company_revision", "membership_revision", "effective"})
        self.assertEqual(response.headers["cache-control"], "no-store")
        for key in ("payables.all", "companies.manage", "identity.roles.manage"):
            self.assertEqual((await self.grant(key)).status_code, 422)

    async def test_cross_tenant_and_cross_member_references_denied(self):
        self.assertEqual((await self.grant(company=self.foreign, org=self.org.id)).status_code, 404)
        self.assertEqual((await self.grant(user=self.colleague.id)).status_code, 404)
        self.assertFalse(await self.allowed("payables.read", company=self.foreign, org=self.org.id))

    async def test_all_three_revisions_and_wrong_password_fail_without_grant(self):
        for change, code in (({"expected_revision": 1}, 409), ({"expected_company_revision": 2}, 409),
                             ({"expected_membership_revision": 2}, 409), ({"password": "errada"}, 404)):
            self.assertEqual((await self.grant(**change)).status_code, code)
        self.assertFalse(await self.allowed("payables.read"))

    async def test_concurrent_grants_have_one_winner(self):
        results = await asyncio.gather(self.grant(), self.grant())
        self.assertEqual(sorted(r.status_code for r in results), [200, 409])

    async def test_selective_revocation_preserves_other_permission_and_company(self):
        for key, company in (("payables.read", self.a), ("payables.settle", self.a), ("payables.read", self.b)):
            self.assertEqual((await self.grant(key, company=company)).status_code, 200)
        self.assertEqual((await self.grant(status="INACTIVE", expected_revision=1)).status_code, 200)
        self.assertFalse(await self.allowed("payables.read"))
        self.assertTrue(await self.allowed("payables.settle"))
        self.assertTrue(await self.allowed("payables.read", company=self.b))

    async def test_company_reactivation_does_not_restore_financial_grants(self):
        for key in FINANCIAL_PERMISSIONS:
            self.assertEqual((await self.grant(key)).status_code, 200)
        self.assertEqual((await self._update_company(status="INACTIVE", revision=1)).status_code, 200)
        self.assertEqual((await self._update_company(status="ACTIVE", revision=2)).status_code, 200)
        for key in FINANCIAL_PERMISSIONS:
            self.assertFalse(await self.allowed(key))

    async def test_membership_reactivation_does_not_restore_financial_grants(self):
        self.assertEqual((await self.grant()).status_code, 200)
        self.assertEqual((await self._member_status("INACTIVE", 1)).status_code, 200)
        self.assertEqual((await self._member_status("ACTIVE", 2)).status_code, 200)
        self.assertFalse(await self.allowed("payables.read"))

    async def test_inactive_user_and_organization_block_effective_access(self):
        self.assertEqual((await self.grant()).status_code, 200)
        async with self.factory() as writer, writer.begin():
            await writer.execute(update(User).where(User.id == self.member.id).values(status="INACTIVE"))
        self.assertFalse(await self.allowed("payables.read"))
        async with self.factory() as writer, writer.begin():
            await writer.execute(update(User).where(User.id == self.member.id).values(status="ACTIVE"))
            await writer.execute(update(Organization).where(Organization.id == self.org.id).values(status="INACTIVE"))
        self.assertFalse(await self.allowed("payables.read"))
        self.assertFalse(await self.allowed("payables.read", user=self.owner.id))

    async def test_financial_visibility_enforces_tenant_without_extra_filter(self):
        async with self.factory() as reader:
            ids = set((await reader.scalars(select(Company.id).where(
                CompanyAccessPolicy(reader).financial_visibility(self.owner.id, self.org.id, "payables.read")))).all())
            self.assertEqual(ids, {self.a.id, self.b.id, self.d.id})
            self.assertFalse(await CompanyAccessPolicy(reader).has_financial_permission(self.owner.id, self.org.id, self.a.id, "*"))

    async def test_audit_is_atomic_and_minimal(self):
        original = AsyncSession.flush
        async def broken(session, *args, **kwargs):
            if any(isinstance(row, CompanyPermissionChange) for row in session.new):
                raise RuntimeError("detalhe privado")
            return await original(session, *args, **kwargs)
        with patch.object(AsyncSession, "flush", broken):
            self.assertEqual((await self.grant()).status_code, 500)
        self.assertFalse(await self.allowed("payables.read"))
        self.assertEqual((await self.grant()).status_code, 200)
        async with self.factory() as reader:
            audit = await reader.scalar(select(CompanyPermissionChange).where(CompanyPermissionChange.permission_key == "payables.read"))
            self.assertEqual(audit.action, "COMPANY_PERMISSION_SET")
            self.assertEqual(set(audit.after_state), {"status", "revision", "company_revision", "membership_revision"})

    async def test_rate_limit_and_unauthenticated_access_are_preserved(self):
        self.app.state.access_manage_limiter = self.original_limiter
        response = await self.client.put(self.path(), json={})
        self.assertEqual(response.status_code, 401)
        for _ in range(5):
            self.assertEqual((await self.grant(password="errada")).status_code, 404)
        response = await self.grant()
        self.assertEqual(response.status_code, 429)
        self.assertIn("retry-after", response.headers)

    async def test_database_rejects_mismatched_audit_action(self):
        self.assertEqual((await self.grant()).status_code, 200)
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(CompanyPermissionChange(organization_id=self.org.id, company_id=self.a.id,
                    user_id=self.member.id, permission_key="payables.read", actor_user_id=self.owner.id,
                    action="COMPANY_READ_SET", before_state={}, after_state={}))
                await self.session.flush()

    async def test_owner_transfer_preserves_grants_and_changes_authority(self):
        self.assertEqual((await self.grant()).status_code, 200)
        self.session.add(OrganizationMembership(user_id=self.colleague.id, organization_id=self.org.id, status="ACTIVE"))
        await self.session.commit()
        response = await self.client.post(self.base + "/ownership/transfer", headers=self.headers[self.owner.id],
            json={"new_owner_id": str(self.colleague.id), "password": self.password})
        self.assertEqual(response.status_code, 204)
        self.assertTrue(await self.allowed("payables.read"))
        self.assertFalse(await self.allowed("payables.read", user=self.owner.id))
        self.assertEqual((await self.grant(expected_revision=1)).status_code, 404)
        self.assertEqual((await self.grant(actor=self.colleague.id, status="INACTIVE", expected_revision=1)).status_code, 200)
        self.assertFalse(await self.allowed("payables.read"))

    async def test_redis_failure_blocks_grant(self):
        with patch.object(self.redis, "eval", side_effect=ConnectionError("detalhe privado")):
            response = await self.grant()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("detalhe privado", response.text)
        self.assertFalse(await self.allowed("payables.read"))

    async def test_request_cannot_override_key_actor_or_scope(self):
        for changes in ({"permission_key": "payables.reverse"}, {"actor_user_id": str(self.owner.id)},
                        {"all_companies": True}, {"company_id": str(self.b.id)}):
            self.assertEqual((await self.grant(**changes)).status_code, 422)
        self.assertFalse(await self.allowed("payables.read"))

    async def test_https_required_and_request_body_bounded(self):
        response = await self.client.put(self.path(), headers={**self.headers[self.owner.id], "content-type":"application/json"}, content="x" * 4097)
        self.assertEqual(response.status_code, 413)
        self.app.state.settings = self.config.model_copy(update={"app_environment":"production"})
        self.assertEqual((await self.grant()).status_code, 503)

    async def test_grant_racing_deactivation_cannot_leave_effective_access(self):
        granted, deactivated = await asyncio.gather(self.grant(), self._member_status("INACTIVE", 1))
        self.assertEqual(deactivated.status_code, 200)
        self.assertIn(granted.status_code, (200, 404, 409))
        self.assertFalse(await self.allowed("payables.read"))


class FinancialPermissionMigrationTests(CompanyGrantHttpFixture):
    async def test_migration_preserves_legacy_grants_and_blocks_financial_downgrade(self):
        self.assertEqual((await self._set()).status_code, 200)
        await self.session.close()
        await self.engine.dispose()
        await asyncio.to_thread(self.run_migration, "downgrade", "f07c4219be86")
        await asyncio.to_thread(self.run_migration, "upgrade", "head")
        async with self.factory() as reader:
            rows = list((await reader.scalars(select(CompanyPermissionGrant).where(CompanyPermissionGrant.organization_id == self.org.id))).all())
            self.assertEqual([(row.permission_key, row.status, row.revision) for row in rows], [("companies.read", "ACTIVE", 1)])
        path = self._grant_path().replace("read-access", "permissions/payables.read")
        response = await self.client.put(path, headers=self.headers[self.owner.id], json={"status":"INACTIVE", "expected_revision":0,
            "expected_company_revision":1, "expected_membership_revision":1, "password":self.password})
        self.assertEqual(response.status_code, 200)
        await self.session.close()
        await self.engine.dispose()
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.run_migration, "downgrade", "f07c4219be86")
        await asyncio.to_thread(self.run_migration, "check")
