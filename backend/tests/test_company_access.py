"""Valida autorização exata por empresa, revogação e ausência de concessões futuras."""

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
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database_support import DatabaseTestCase
from app.core.config import Settings
from app.main import create_app
from app.modules.identity.access_models import OrganizationOwnership
from app.modules.identity.company_access_models import CompanyPermissionChange, CompanyPermissionGrant
from app.modules.identity.company_access_schemas import CompanyReadGrantRequest
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.models import OrganizationMembership, User, UserPasswordCredential, UserSession
from app.modules.identity.passwords import hash_password
from app.modules.identity.permission_models import OrganizationAccessDelegation, OrganizationDelegationPermission
from app.modules.identity.rate_limit import LoginRateLimiter, LoginRateLimitPolicy
from app.modules.identity.role_schemas import RoleCreateRequest
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Company, CompanyChange, Organization


class CompanyGrantSchemaTests(unittest.TestCase):
    def test_requires_positive_parent_revisions_and_zero_or_positive_grant_revision(self):
        base = dict(status="ACTIVE", expected_revision=0, expected_company_revision=1, expected_membership_revision=1, password="segredo")
        for extra in ({"expected_revision":-1}, {"expected_company_revision":0}, {"expected_membership_revision":True}, {"status":"ALL"}):
            with self.assertRaises(ValidationError):
                CompanyReadGrantRequest(**{**base, **extra})

    def test_rejects_wildcard_scope_actor_and_other_permission_overrides(self):
        for extra in ({"company_id":"*"}, {"organization_id":str(uuid4())}, {"actor_user_id":str(uuid4())},
                      {"permission_key":"companies.manage"}, {"all_companies":True}):
            with self.assertRaises(ValidationError):
                CompanyReadGrantRequest(status="ACTIVE", expected_revision=0, expected_company_revision=1,
                                       expected_membership_revision=1, password="segredo", **extra)

    def test_company_permission_cannot_be_put_into_organization_role(self):
        with self.assertRaises(ValidationError):
            RoleCreateRequest(name="CEO", permissions=["companies.read"], password="segredo")


@unittest.skipUnless(os.environ.get("SD_RUN_DATABASE_TESTS") == "1" and os.environ.get("SD_RUN_REDIS_TESTS") == "1",
                     "Defina SD_RUN_DATABASE_TESTS=1 e SD_RUN_REDIS_TESTS=1.")
class CompanyGrantHttpFixture(DatabaseTestCase):
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
            app=self.app, client=("127.0.0.1",12345), raise_app_exceptions=False), base_url="http://testserver")
        self.addAsyncCleanup(self.client.aclose)
        self.password = "Senha ficticia de acesso por empresa @123"
        self.owner, self.member, self.colleague, self.operator = [User(name=name,email=uuid4().hex+"@example.com",status="ACTIVE",
            can_provision_organizations=(name=="Operador")) for name in ("Master","Membro","Outro tenant","Operador")]
        self.org, self.other = Organization(name="Organização"), Organization(name="Outra organização")
        self.session.add_all([self.owner,self.member,self.colleague,self.operator,self.org,self.other])
        await self.session.flush()
        hashed = (await hash_password(SecretStr(self.password))).get_secret_value()
        for user in (self.owner,self.member,self.colleague,self.operator):
            self.session.add(UserPasswordCredential(user_id=user.id,password_hash=hashed))
        for org in (self.org,self.other):
            self.session.add(OrganizationMembership(user_id=self.owner.id,organization_id=org.id,status="ACTIVE"))
            self.session.add(OrganizationMembership(user_id=self.member.id,organization_id=org.id,status="ACTIVE",can_read_organization=True))
        self.session.add(OrganizationMembership(user_id=self.colleague.id,organization_id=self.other.id,status="ACTIVE"))
        await self.session.flush()
        self.session.add_all([OrganizationOwnership(organization_id=org.id,user_id=self.owner.id) for org in (self.org,self.other)])
        self.a = Company(organization_id=self.org.id,legal_name="Empresa A",tax_id="11222333000181")
        self.b = Company(organization_id=self.org.id,legal_name="Empresa B",tax_id="12ABC34501DE35")
        self.d = Company(organization_id=self.org.id,legal_name="Empresa D",tax_id="00000000E08G12")
        self.foreign = Company(organization_id=self.other.id,legal_name="Mesmo CNPJ, outro tenant",tax_id="11222333000181")
        self.session.add_all([self.a,self.b,self.d,self.foreign])
        await self.session.commit()
        self.headers = {}
        for user in (self.owner,self.member,self.colleague,self.operator):
            issued = await SessionService(self.session).issue_for_authenticated_user(user.id)
            self.headers[user.id] = {"Authorization":"Bearer "+issued.token.get_secret_value()}
        self.base = f"/api/v1/organizations/{self.org.id}"

    async def enable_business_contracts(self):
        from datetime import datetime, timedelta, timezone
        from app.modules.commercial.catalog import CATALOG_VERSION
        from app.modules.commercial.models import BusinessCompanyActivation, BusinessContract

        now = datetime.now(timezone.utc)
        self.session.add_all([
            BusinessContract(organization_id=org.id, plan="PROFESSIONAL", catalog_version=CATALOG_VERSION,
                status="ACTIVE", valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1))
            for org in (self.org, self.other)
        ])
        await self.session.flush()
        self.session.add_all([
            BusinessCompanyActivation(organization_id=company.organization_id, company_id=company.id)
            for company in (self.a, self.b, self.d, self.foreign)
        ])
        await self.session.commit()

    async def _clear_redis(self):
        keys = [key async for key in self.redis.scan_iter(match="{"+self.namespace+":*")]
        if keys:
            await self.redis.delete(*keys)

    def _wide_limit(self):
        self.app.state.access_manage_limiter = LoginRateLimiter(self.redis,key_secret=self.config.auth_rate_limit_key,
            namespace=self.namespace,operation="access_manage",policy=LoginRateLimitPolicy(account_limit=100))

    def _grant_path(self, company=None, user=None, org=None):
        company = company or self.a
        return f"/api/v1/organizations/{org or company.organization_id}/companies/{company.id}/members/{user or self.member.id}/read-access"

    async def _set(self, *, actor=None, company=None, user=None, org=None, **changes):
        return await self.client.put(self._grant_path(company,user,org),headers=self.headers[actor or self.owner.id],
            json={"status":"ACTIVE","expected_revision":0,"expected_company_revision":1,
                  "expected_membership_revision":1,"password":self.password,**changes})

    async def _get(self, company=None, *, actor=None, org=None):
        company = company or self.a
        return await self.client.get(f"/api/v1/organizations/{org or company.organization_id}/companies/{company.id}",
            headers=self.headers[actor or self.member.id])

    async def _update_company(self, company=None, *, status, revision):
        company = company or self.a
        return await self.client.put(f"/api/v1/organizations/{company.organization_id}/companies/{company.id}",headers=self.headers[self.owner.id],
            json={"legal_name":company.legal_name,"trade_name":None,"status":status,"expected_revision":revision,"password":self.password})

    async def _member_status(self, status, revision):
        return await self.client.put(self.base+f"/members/{self.member.id}/status",headers=self.headers[self.owner.id],
            json={"status":status,"expected_revision":revision,"password":self.password})

class CompanyGrantHttpTests(CompanyGrantHttpFixture):
    async def test_no_implicit_company_access_from_tenant_read_or_platform_flag(self):
        self.assertEqual((await self._get()).status_code,404)
        for user in (self.member,self.operator):
            response = await self.client.get(self.base+"/companies",headers=self.headers[user.id])
            self.assertEqual(response.status_code,404)

    async def test_visibility_expression_enforces_tenant_without_repository_filter(self):
        async with self.factory() as reader:
            policy = CompanyAccessPolicy(reader)
            ids = set((await reader.scalars(select(Company.id).where(policy.visibility(self.owner.id,self.org.id)))).all())
            self.assertEqual(ids,{self.a.id,self.b.id,self.d.id})
            self.assertNotIn(self.foreign.id,ids)

    async def test_grant_reads_only_selected_company_and_not_new_companies(self):
        response = await self._set()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["permission_key"],"companies.read")
        self.assertTrue(response.json()["effective"])
        self.assertEqual((await self._get()).status_code,200)
        self.assertEqual((await self._get(self.b)).status_code,404)
        self.assertEqual((await self._get(self.foreign)).status_code,404)
        created = await self.client.post(self.base+"/companies",headers=self.headers[self.owner.id],
            json={"legal_name":"Empresa posterior","tax_id":"00000000000191","password":self.password})
        self.assertEqual(created.status_code,201,created.text)
        self.assertEqual((await self.client.get(self.base+"/companies/"+created.json()["id"],headers=self.headers[self.member.id])).status_code,404)
        page = await self.client.get(self.base+"/companies",headers=self.headers[self.member.id])
        self.assertEqual([item["id"] for item in page.json()["items"]],[str(self.a.id)])

    async def test_visibility_is_filtered_before_pagination(self):
        hidden, first, second = sorted([self.a,self.b,self.d],key=lambda company:company.id)
        await self._set(company=first)
        await self._set(company=second)
        response = await self.client.get(self.base+"/companies?limit=1",headers=self.headers[self.member.id])
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["items"][0]["id"],str(first.id))
        cursor = response.json()["next_cursor"]
        page = await self.client.get(self.base+"/companies?limit=1&cursor="+cursor,headers=self.headers[self.member.id])
        self.assertEqual(page.json()["items"][0]["id"],str(second.id))
        self.assertIsNone(page.json()["next_cursor"])
        self.assertEqual((await self._get(hidden)).status_code,404)
        tail = await self.client.get(self.base+"/companies?cursor="+str(second.id),headers=self.headers[self.member.id])
        self.assertEqual(tail.json()["items"],[])

    async def test_company_grant_does_not_grant_tenant_read_or_company_edit(self):
        await self.session.execute(update(OrganizationMembership).where(OrganizationMembership.user_id==self.member.id).values(can_read_organization=False))
        await self.session.commit()
        await self._set()
        self.assertEqual((await self._get()).status_code,200)
        self.assertEqual((await self.client.get(self.base,headers=self.headers[self.member.id])).status_code,404)
        response = await self.client.put(self.base+f"/companies/{self.a.id}",headers=self.headers[self.member.id],
            json={"legal_name":"Não alterar","status":"ACTIVE","expected_revision":1,"password":self.password})
        self.assertEqual(response.status_code,404)

    async def test_member_delegate_and_operator_cannot_grant_or_inspect_concessions(self):
        self.session.add(OrganizationAccessDelegation(organization_id=self.org.id,user_id=self.member.id,
            granted_by_user_id=self.owner.id,owner_revision=1,status="ACTIVE"))
        await self.session.flush()
        self.session.add(OrganizationDelegationPermission(organization_id=self.org.id,user_id=self.member.id,permission_key="organizations.read"))
        await self.session.commit()
        for user in (self.member,self.operator):
            self.assertEqual((await self._set(actor=user.id)).status_code,404)
            self.assertEqual((await self.client.get(self._grant_path(),headers=self.headers[user.id])).status_code,404)

    async def test_owner_reads_null_or_minimal_grant_and_cannot_modify_own_owner_rights(self):
        before = await self.client.get(self._grant_path(),headers=self.headers[self.owner.id])
        self.assertEqual(before.status_code,200)
        self.assertIsNone(before.json())
        await self._set()
        after = await self.client.get(self._grant_path(),headers=self.headers[self.owner.id])
        self.assertEqual(set(after.json()),{"company_id","user_id","permission_key","status","revision","company_revision","membership_revision","effective"})
        self.assertNotIn(self.member.email,after.text)
        self.assertNotIn(self.a.tax_id,after.text)
        self.assertEqual((await self._set(user=self.owner.id)).status_code,404)

    async def test_revocation_removes_only_selected_scope_and_preserves_session(self):
        await self._set()
        await self._set(company=self.b)
        response = await self._set(status="INACTIVE",expected_revision=1)
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json()["effective"])
        self.assertEqual((await self._get()).status_code,404)
        self.assertEqual((await self._get(self.b)).status_code,200)
        self.assertEqual((await self.client.get("/api/v1/auth/permissions",headers=self.headers[self.member.id])).status_code,200)

    async def test_deactivated_membership_clears_grants_without_restoring_on_reactivation(self):
        self._wide_limit()
        await self._set()
        await self._set(company=self.b)
        await self._set(company=self.foreign)
        self.assertEqual((await self._member_status("INACTIVE",1)).status_code,200)
        self.assertEqual((await self._get()).status_code,404)
        self.assertEqual((await self._get(self.foreign)).status_code,200)
        self.assertEqual((await self._member_status("ACTIVE",2)).status_code,200)
        self.assertEqual((await self._get()).status_code,404)
        proof = await self.client.get(self._grant_path(),headers=self.headers[self.owner.id])
        self.assertEqual(proof.json()["revision"],3)
        self.assertEqual(proof.json()["status"],"INACTIVE")
        self.assertEqual((await self._set(expected_revision=1)).status_code,409)
        current = await self._set(expected_revision=3,expected_membership_revision=3)
        self.assertEqual(current.status_code,200,current.text)
        self.assertEqual((await self._get()).status_code,200)
        self.assertEqual((await self._get(self.b)).status_code,404)

    async def test_deactivated_company_revokes_grants_and_reactivation_requires_new_consent(self):
        self._wide_limit()
        await self._set()
        await self._set(company=self.b)
        self.assertEqual((await self._update_company(status="INACTIVE",revision=1)).status_code,200)
        self.assertEqual((await self._get()).status_code,404)
        self.assertEqual((await self._get(actor=self.owner.id)).status_code,200)
        self.assertEqual((await self._get(self.b)).status_code,200)
        self.assertEqual((await self._update_company(status="ACTIVE",revision=2)).status_code,200)
        self.assertEqual((await self._get()).status_code,404)
        proof = await self.client.get(self._grant_path(),headers=self.headers[self.owner.id])
        self.assertEqual(proof.json()["revision"],3)
        self.assertFalse(proof.json()["effective"])
        self.assertEqual((await self._set(expected_revision=3,expected_company_revision=3)).status_code,200)
        self.assertEqual((await self._get()).status_code,200)

    async def test_inactive_user_member_company_or_organization_is_denied(self):
        await self._set()
        for model,clause in ((User,User.id==self.member.id),
                             (OrganizationMembership,(OrganizationMembership.user_id==self.member.id)&(OrganizationMembership.organization_id==self.org.id)),
                             (Company,Company.id==self.a.id),(Organization,Organization.id==self.org.id)):
            await self.session.execute(update(model).where(clause).values(status="INACTIVE"))
            await self.session.commit()
            async with self.factory() as reader:
                self.assertFalse(await CompanyAccessPolicy(reader).can_read(self.member.id,self.org.id,self.a.id))
            await self.session.execute(update(model).where(clause).values(status="ACTIVE"))
            await self.session.commit()

    async def test_active_grant_requires_active_target_and_company_but_revocation_is_allowed(self):
        await self._set()
        await self.session.execute(update(OrganizationMembership).where(
            OrganizationMembership.user_id==self.member.id,OrganizationMembership.organization_id==self.org.id).values(status="INACTIVE"))
        await self.session.commit()
        self.assertEqual((await self._set(expected_revision=1)).status_code,404)
        self.assertEqual((await self._set(status="INACTIVE",expected_revision=1)).status_code,200)

    async def test_foreign_company_member_and_tenant_cannot_be_combined(self):
        responses = [await self._set(company=self.foreign,org=self.org.id), await self._set(user=self.colleague.id),
                     await self._set(org=uuid4())]
        self.assertTrue(all(response.status_code==404 for response in responses))
        self.assertEqual(len({response.text for response in responses}),1)
        await self._set()
        self.assertEqual((await self._get(self.foreign)).status_code,404)

    async def test_expected_company_member_and_grant_revisions_are_checked(self):
        self.assertEqual((await self._set(expected_company_revision=2)).status_code,409)
        self.assertEqual((await self._set(expected_membership_revision=2)).status_code,409)
        self.assertEqual((await self._set(expected_revision=1)).status_code,409)
        self.assertEqual((await self._set()).status_code,200)
        self.assertEqual((await self._set()).status_code,409)

    async def test_concurrent_updates_do_not_overwrite_and_revocation_is_immediate(self):
        await self._set()
        first,second = await asyncio.gather(self._set(expected_revision=1,status="INACTIVE"),self._set(expected_revision=1,status="INACTIVE"))
        self.assertEqual(sorted([first.status_code,second.status_code]),[200,409])
        self.assertEqual((await self._get()).status_code,404)

    async def test_deactivation_racing_grant_cannot_leave_effective_access(self):
        granted,deactivated = await asyncio.gather(self._set(),self._member_status("INACTIVE",1))
        self.assertIn(granted.status_code,(200,409))
        self.assertEqual(deactivated.status_code,200)
        self.assertEqual((await self._get()).status_code,404)
        self.assertEqual((await self._member_status("ACTIVE",2)).status_code,200)
        self.assertEqual((await self._get()).status_code,404)

    async def test_company_deactivation_racing_grant_cannot_restore_access(self):
        granted,deactivated = await asyncio.gather(self._set(),self._update_company(status="INACTIVE",revision=1))
        self.assertIn(granted.status_code,(200,409))
        self.assertEqual(deactivated.status_code,200)
        self.assertEqual((await self._get()).status_code,404)
        self.assertEqual((await self._update_company(status="ACTIVE",revision=2)).status_code,200)
        self.assertEqual((await self._get()).status_code,404)

    async def test_owner_transfer_preserves_direct_grants_but_changes_administrator(self):
        await self._set()
        self.session.add(OrganizationMembership(user_id=self.colleague.id,organization_id=self.org.id,status="ACTIVE"))
        await self.session.commit()
        transferred = await self.client.post(self.base+"/ownership/transfer",headers=self.headers[self.owner.id],
            json={"new_owner_id":str(self.colleague.id),"password":self.password})
        self.assertEqual(transferred.status_code,204)
        self.assertEqual((await self._get()).status_code,200)
        self.assertEqual((await self._set(expected_revision=1)).status_code,404)
        self.assertEqual((await self._set(actor=self.colleague.id,status="INACTIVE",expected_revision=1)).status_code,200)
        self.assertEqual((await self._get()).status_code,404)

    async def test_audit_failure_rolls_back_grant_or_revocation(self):
        real_flush = AsyncSession.flush

        async def fail_after_audit(session,*args,**kwargs):
            if any(isinstance(row,CompanyPermissionChange) for row in session.new):
                await real_flush(session,*args,**kwargs)
                raise SQLAlchemyError("falha simulada")
            return await real_flush(session,*args,**kwargs)

        with patch.object(AsyncSession,"flush",fail_after_audit):
            self.assertEqual((await self._set()).status_code,503)
        self.assertEqual((await self._get()).status_code,404)
        self.assertEqual((await self._set()).status_code,200)
        with patch.object(AsyncSession,"flush",fail_after_audit):
            self.assertEqual((await self._set(status="INACTIVE",expected_revision=1)).status_code,503)
        self.assertEqual((await self._get()).status_code,200)

    async def test_parent_audit_failure_rolls_back_automatic_company_grant_reset(self):
        await self._set()
        real_flush = AsyncSession.flush

        async def fail_after_audit(session,*args,**kwargs):
            if any(isinstance(row,CompanyChange) for row in session.new):
                await real_flush(session,*args,**kwargs)
                raise SQLAlchemyError("falha simulada")
            return await real_flush(session,*args,**kwargs)

        with patch.object(AsyncSession,"flush",fail_after_audit):
            self.assertEqual((await self._update_company(status="INACTIVE",revision=1)).status_code,503)
        self.assertEqual((await self._get()).status_code,200)
        async with self.factory() as reader:
            grant = await reader.get(CompanyPermissionGrant,(self.org.id,self.a.id,self.member.id,"companies.read"))
            self.assertEqual(grant.revision,1)

    async def test_audit_snapshot_contains_only_scope_state_and_revisions(self):
        await self._set()
        async with self.factory() as reader:
            audit = await reader.scalar(select(CompanyPermissionChange).where(CompanyPermissionChange.organization_id==self.org.id))
            self.assertEqual(audit.actor_user_id,self.owner.id)
            self.assertEqual(audit.company_id,self.a.id)
            self.assertEqual(audit.user_id,self.member.id)
            self.assertEqual(audit.after_state["membership_revision"],1)
            for value in (self.password,self.member.email,self.a.tax_id,self.a.legal_name):
                self.assertNotIn(value,str(audit.after_state))

    async def test_wrong_password_does_not_grant_or_renew_session(self):
        deadline = await self.session.scalar(select(UserSession.expires_at).where(UserSession.user_id==self.owner.id))
        self.assertEqual((await self._set(password="incorreta")).status_code,404)
        self.assertEqual(await self.session.scalar(select(UserSession.expires_at).where(UserSession.user_id==self.owner.id)),deadline)
        self.assertEqual((await self._get()).status_code,404)

    async def test_rate_limit_and_capacity_precede_password_work(self):
        for _ in range(5):
            self.assertEqual((await self._set(password="incorreta")).status_code,404)
        with patch("app.modules.identity.access_security.verify_password",new_callable=AsyncMock) as verifier:
            result = await self._set(company=self.b)
        self.assertEqual(result.status_code,429)
        verifier.assert_not_awaited()

    async def test_cancellation_keeps_hash_slot_and_leaves_no_grant(self):
        self.app.state.auth_hash_slots = asyncio.Semaphore(1)
        entered,finish = asyncio.Event(),asyncio.Event()

        async def delayed(*args):
            entered.set()
            await finish.wait()
            return True,None

        with patch("app.modules.identity.access_security.verify_password",delayed):
            first = asyncio.create_task(self._set())
            try:
                await asyncio.wait_for(entered.wait(),timeout=5)
                first.cancel()
                self.assertEqual((await self._set()).status_code,503)
            finally:
                finish.set()
                await asyncio.gather(first,return_exceptions=True)
        self.assertEqual((await self._get()).status_code,404)

    async def test_redis_failure_blocks_grant_but_not_logout(self):
        with patch.object(self.redis,"eval",side_effect=ConnectionError("segredo_redis")):
            response = await self._set()
            logout = await self.client.post("/api/v1/auth/logout",headers=self.headers[self.owner.id])
        self.assertEqual(response.status_code,503)
        self.assertNotIn("segredo_redis",response.text)
        self.assertEqual(logout.status_code,204)

    async def test_body_validation_debug_sanitization_and_https_are_enforced(self):
        self.assertEqual((await self._set(permission_key="companies.manage")).status_code,422)
        body = await self.client.put(self._grant_path(),content="x"*4097,
            headers={**self.headers[self.owner.id],"Content-Type":"application/json"})
        self.assertEqual(body.status_code,413)
        self.assertEqual(body.headers["cache-control"],"no-store")
        with patch("app.api.v1.company_access.CompanyGrantService.set_read",side_effect=RuntimeError("segredo_app")):
            response = await self._set()
        self.assertEqual(response.status_code,500)
        self.assertNotIn("segredo_app",response.text)
        self.assertEqual((await self.client.get(self._grant_path())).status_code,401)
        self.app.state.settings = self.config.model_copy(update={"app_environment":"production"})
        self.assertEqual((await self._set()).status_code,503)

    async def test_database_rejects_cross_tenant_unknown_permission_and_duplicate_scope(self):
        for company_id,user_id,permission in ((self.foreign.id,self.member.id,"companies.read"),
                                              (self.a.id,self.colleague.id,"companies.read"),(self.a.id,self.member.id,"companies.manage")):
            with self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    self.session.add(CompanyPermissionGrant(organization_id=self.org.id,company_id=company_id,user_id=user_id,
                        permission_key=permission,updated_by_user_id=self.owner.id))
                    await self.session.flush()
        self.assertEqual((await self._set()).status_code,200)
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(CompanyPermissionGrant(organization_id=self.org.id,company_id=self.a.id,user_id=self.member.id,
                    permission_key="companies.read",updated_by_user_id=self.owner.id))
                await self.session.flush()


class CompanyGrantMigrationTests(DatabaseTestCase):
    async def test_round_trip_does_not_seed_grants_and_downgrade_preserves_new_history(self):
        user = User(name="Pessoa",email=uuid4().hex+"@example.com",status="ACTIVE")
        org = Organization(name="Empresa")
        self.session.add_all([user,org])
        await self.session.flush()
        company = Company(organization_id=org.id,legal_name="Cadastro",tax_id="11222333000181")
        self.session.add_all([company,OrganizationMembership(user_id=user.id,organization_id=org.id,status="ACTIVE")])
        await self.session.commit()
        user_id,org_id,company_id = user.id,org.id,company.id
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration,"downgrade","d85fa1049ce3")
        finally:
            await asyncio.to_thread(self.run_migration,"upgrade","head")
        self.assertIsNotNone(await self.session.get(Company,company_id))
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(CompanyPermissionGrant)),0)
        grant = CompanyPermissionGrant(organization_id=org_id,company_id=company_id,user_id=user_id,updated_by_user_id=user_id)
        self.session.add(grant)
        await self.session.commit()
        self.assertEqual(grant.status,"INACTIVE")
        await self.session.close()
        await self.engine.dispose()
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.run_migration,"downgrade","d85fa1049ce3")
        self.session.add(CompanyPermissionChange(organization_id=org_id,company_id=company_id,user_id=user_id,
            permission_key="companies.read",actor_user_id=user_id,action="COMPANY_READ_SET",before_state={},after_state={"revision":1}))
        await self.session.commit()
        await self.session.close()
        await self.engine.dispose()
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.run_migration,"downgrade","d85fa1049ce3")
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(CompanyPermissionChange)),1)
        await self.session.close()
        await asyncio.to_thread(self.run_migration,"check")
