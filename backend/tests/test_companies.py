"""Valida cadastro jurídico, CNPJ oficial e isolamento sem consultas globais."""

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
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database_support import DatabaseTestCase
from app.core.config import Settings
from app.main import create_app
from app.modules.identity.access_models import OrganizationOwnership
from app.modules.identity.models import OrganizationMembership, User, UserPasswordCredential, UserSession
from app.modules.identity.passwords import hash_password
from app.modules.identity.permission_models import OrganizationAccessDelegation, OrganizationDelegationPermission
from app.modules.identity.sessions import SessionService
from app.modules.organizations.cnpj import normalize_cnpj
from app.modules.organizations.company_schemas import CompanyCreate, CompanyUpdate
from app.modules.organizations.models import Company, CompanyChange, Organization

# Exemplos públicos de cálculo; não são credenciais ou cadastros reais dos testes.
NUMERIC, ALPHA, FIRST_ALPHA = "11222333000181", "12ABC34501DE35", "00000000E08G12"


class CnpjContractTests(unittest.TestCase):
    def test_numeric_and_official_alphanumeric_examples_normalize(self):
        for raw, expected in (("11.222.333/0001-81", NUMERIC), ("12.ABC.345/01DE-35", ALPHA),
                              (" 12.abc.345/01de-35 ", ALPHA), ("00.000.000/E08G-12", FIRST_ALPHA)):
            self.assertEqual(normalize_cnpj(raw), expected)

    def test_rejects_cpf_invalid_digits_partial_masks_and_repeated_digits(self):
        for value in ("12345678901", "00000000000000", "11111111111111", "12ABC34501DE34", "11222333000182",
                      "11.222333/0001-81", "12ABC34501DE3A", "11222333 000181", 11222333000181):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_cnpj(value)

    def test_non_ascii_lookalikes_and_case_expansion_are_not_normalized_as_ascii(self):
        for value in ("１２ABC34501DE35", "12АBC34501DE35", "12ßC34501DE35", "12ABC34501DE٣٥"):
            with self.assertRaises(ValueError):
                normalize_cnpj(value)

    def test_company_input_normalizes_names_and_masks_confirmation_password(self):
        data = CompanyCreate(legal_name=" Empresa Teste ", trade_name=" ", tax_id="12.abc.345/01de-35", password="segredo")
        self.assertEqual(data.legal_name, "Empresa Teste")
        self.assertIsNone(data.trade_name)
        self.assertEqual(data.tax_id, ALPHA)
        self.assertNotIn("segredo", repr(data))

    def test_creation_does_not_accept_tenant_status_cpf_or_privilege_overrides(self):
        for extra in ({"organization_id":str(uuid4())}, {"status":"ACTIVE"}, {"cpf":"12345678901"}, {"owner_id":str(uuid4())}):
            with self.assertRaises(ValidationError):
                CompanyCreate(legal_name="Empresa", tax_id=NUMERIC, password="segredo", **extra)

    def test_update_cannot_change_cnpj_or_tenant_and_requires_strict_revision(self):
        base = dict(legal_name="Empresa", status="ACTIVE", expected_revision=1, password="segredo")
        for extra in ({"tax_id":ALPHA}, {"organization_id":str(uuid4())}, {"expected_revision":True}, {"legal_name":" "}):
            with self.assertRaises(ValidationError):
                CompanyUpdate(**{**base, **extra})


@unittest.skipUnless(os.environ.get("SD_RUN_DATABASE_TESTS") == "1" and os.environ.get("SD_RUN_REDIS_TESTS") == "1",
                     "Defina SD_RUN_DATABASE_TESTS=1 e SD_RUN_REDIS_TESTS=1.")
class CompanyHttpTests(DatabaseTestCase):
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
        self.password = "Senha ficticia de cadastro empresarial @123"
        self.owner, self.member, self.operator = [User(name=name,email=uuid4().hex+"@example.com",status="ACTIVE",
            can_provision_organizations=(name == "Operador")) for name in ("Master","Colaborador","Operador")]
        self.org, self.other = Organization(name="Empresa"), Organization(name="Outra organização")
        self.session.add_all([self.owner,self.member,self.operator,self.org,self.other])
        await self.session.flush()
        hashed = (await hash_password(SecretStr(self.password))).get_secret_value()
        for user in (self.owner,self.member,self.operator):
            self.session.add(UserPasswordCredential(user_id=user.id,password_hash=hashed))
        for org in (self.org,self.other):
            self.session.add(OrganizationMembership(user_id=self.owner.id,organization_id=org.id,status="ACTIVE"))
        self.session.add(OrganizationMembership(user_id=self.member.id,organization_id=self.org.id,status="ACTIVE",can_read_organization=True))
        await self.session.flush()
        self.session.add_all([OrganizationOwnership(organization_id=org.id,user_id=self.owner.id) for org in (self.org,self.other)])
        await self.session.commit()
        self.headers = {}
        for user in (self.owner,self.member,self.operator):
            issued = await SessionService(self.session).issue_for_authenticated_user(user.id)
            self.headers[user.id] = {"Authorization":"Bearer "+issued.token.get_secret_value()}
        self.base = f"/api/v1/organizations/{self.org.id}/companies"

    async def _clear_redis(self):
        keys = [key async for key in self.redis.scan_iter(match="{"+self.namespace+":*")]
        if keys:
            await self.redis.delete(*keys)

    async def _create(self, *, actor=None, org=None, **changes):
        return await self.client.post(f"/api/v1/organizations/{org or self.org.id}/companies", headers=self.headers[actor or self.owner.id],
            json={"legal_name":"Empresa Teste Ltda", "trade_name":"Teste", "tax_id":NUMERIC, "password":self.password, **changes})

    async def _company(self, **kwargs):
        response = await self._create(**kwargs)
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    async def _update(self, company, *, actor=None, org=None, **changes):
        return await self.client.put(f"/api/v1/organizations/{org or self.org.id}/companies/{company['id']}", headers=self.headers[actor or self.owner.id],
            json={"legal_name":company["legal_name"], "trade_name":company["trade_name"], "status":company["status"],
                  "expected_revision":company["revision"], "password":self.password, **changes})

    async def test_create_returns_only_legal_registration_fields_after_commit(self):
        response = await self._create(tax_id="12.abc.345/01de-35")
        self.assertEqual(response.status_code,201,response.text)
        data = response.json()
        self.assertEqual(set(data),{"id","organization_id","legal_name","trade_name","tax_id","status","revision","created_at","updated_at"})
        self.assertEqual(data["tax_id"],ALPHA)
        self.assertEqual(data["status"],"ACTIVE")
        self.assertEqual(data["revision"],1)
        self.assertEqual(response.headers["location"],self.base+"/"+data["id"])
        self.assertEqual(response.headers["cache-control"],"no-store")
        self.assertNotIn(self.password,response.text)
        async with self.factory() as reader:
            self.assertIsNotNone(await reader.get(Company,data["id"]))

    async def test_only_owner_can_access_even_with_tenant_read_or_platform_permission(self):
        company = await self._company()
        for user in (self.member,self.operator):
            for response in (await self._create(actor=user.id,tax_id=ALPHA),
                             await self.client.get(self.base,headers=self.headers[user.id]),
                             await self.client.get(self.base+"/"+company["id"],headers=self.headers[user.id]),
                             await self._update(company,actor=user.id)):
                self.assertEqual(response.status_code,404)

    async def test_bounded_assignment_delegate_cannot_register_or_read_company(self):
        self.session.add(OrganizationAccessDelegation(organization_id=self.org.id,user_id=self.member.id,
            granted_by_user_id=self.owner.id,owner_revision=1,status="ACTIVE"))
        await self.session.flush()
        self.session.add(OrganizationDelegationPermission(organization_id=self.org.id,user_id=self.member.id,permission_key="organizations.read"))
        await self.session.commit()
        self.assertEqual((await self._create(actor=self.member.id)).status_code,404)
        self.assertEqual((await self.client.get(self.base,headers=self.headers[self.member.id])).status_code,404)

    async def test_cnpj_duplicate_is_rejected_only_within_same_tenant_and_normalized(self):
        await self._company()
        duplicate = await self._create(tax_id="11.222.333/0001-81")
        self.assertEqual(duplicate.status_code,409)
        self.assertNotIn(NUMERIC,duplicate.text)
        other = await self._company(org=self.other.id,legal_name="Cadastro Independente")
        self.assertEqual(other["organization_id"],str(self.other.id))
        self.assertEqual(other["legal_name"],"Cadastro Independente")
        page = await self.client.get(self.base,headers=self.headers[self.owner.id])
        self.assertEqual(len(page.json()["items"]),1)

    async def test_cross_tenant_identifier_and_missing_company_have_same_denial(self):
        company = await self._company()
        foreign_base = f"/api/v1/organizations/{self.other.id}/companies"
        responses = [await self.client.get(foreign_base+"/"+company["id"],headers=self.headers[self.owner.id]),
                     await self.client.get(self.base+"/"+str(uuid4()),headers=self.headers[self.owner.id]),
                     await self._update(company,org=self.other.id)]
        self.assertTrue(all(response.status_code==404 for response in responses))
        self.assertEqual(len({response.text for response in responses}),1)

    async def test_update_preserves_cnpj_and_supports_inactivation_and_reactivation(self):
        company = await self._company()
        inactive = await self._update(company,legal_name="Razão Social Atualizada",trade_name=None,status="INACTIVE")
        self.assertEqual(inactive.status_code,200,inactive.text)
        data = inactive.json()
        self.assertEqual(data["revision"],2)
        self.assertEqual(data["tax_id"],NUMERIC)
        self.assertEqual(data["status"],"INACTIVE")
        self.assertIsNone(data["trade_name"])
        self.assertEqual((await self.client.get(self.base+"/"+company["id"],headers=self.headers[self.owner.id])).status_code,200)
        active = await self._update(data,status="ACTIVE")
        self.assertEqual(active.status_code,200)
        self.assertEqual(active.json()["revision"],3)

    async def test_cnpj_tenant_and_status_creation_overrides_are_rejected_without_echo(self):
        for changes in ({"tax_id":"12345678901"},{"tax_id":"12ABC34501DE34"},{"organization_id":str(self.other.id)},{"status":"INACTIVE"}):
            response = await self._create(**changes)
            self.assertEqual(response.status_code,422)
            self.assertEqual(response.json(),{"detail":"Dados de entrada inválidos."})
        company = await self._company()
        self.assertEqual((await self._update(company,tax_id=ALPHA)).status_code,422)

    async def test_list_is_paginated_and_has_no_cross_tenant_rows(self):
        await self._company()
        await self._company(tax_id=ALPHA)
        await self._company(org=self.other.id,tax_id=FIRST_ALPHA)
        response = await self.client.get(self.base+"?limit=1",headers=self.headers[self.owner.id])
        self.assertEqual(response.status_code,200)
        page = response.json()
        self.assertEqual(len(page["items"]),1)
        self.assertIsNotNone(page["next_cursor"])
        second = await self.client.get(self.base+"?limit=1&cursor="+page["next_cursor"],headers=self.headers[self.owner.id])
        self.assertNotEqual(page["items"][0]["id"],second.json()["items"][0]["id"])
        self.assertIsNone(second.json()["next_cursor"])
        self.assertEqual((await self.client.get(self.base+"?limit=101",headers=self.headers[self.owner.id])).status_code,422)

    async def test_concurrent_creation_has_one_winner_and_one_tenant_conflict(self):
        first,second = await asyncio.gather(self._create(),self._create())
        self.assertEqual(sorted([first.status_code,second.status_code]),[201,409])
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(Company).where(Company.organization_id==self.org.id)),1)

    async def test_concurrent_update_and_stale_revision_do_not_overwrite_changes(self):
        company = await self._company()
        first,second = await asyncio.gather(self._update(company,trade_name="Primeiro"),self._update(company,trade_name="Segundo"))
        self.assertEqual(sorted([first.status_code,second.status_code]),[200,409])

    async def test_current_owner_transfer_revokes_old_owner_company_administration(self):
        company = await self._company()
        response = await self.client.post(f"/api/v1/organizations/{self.org.id}/ownership/transfer",headers=self.headers[self.owner.id],
            json={"new_owner_id":str(self.member.id),"password":self.password})
        self.assertEqual(response.status_code,204)
        self.assertEqual((await self.client.get(self.base,headers=self.headers[self.owner.id])).status_code,404)
        self.assertEqual((await self._update(company)).status_code,404)
        self.assertEqual((await self.client.get(self.base,headers=self.headers[self.member.id])).status_code,200)

    async def test_inactive_owner_membership_and_tenant_are_denied(self):
        for model,clause in ((OrganizationMembership,(OrganizationMembership.user_id==self.owner.id)&(OrganizationMembership.organization_id==self.org.id)),
                             (Organization,Organization.id==self.org.id)):
            await self.session.execute(update(model).where(clause).values(status="INACTIVE"))
            await self.session.commit()
            self.assertEqual((await self._create()).status_code,404)
            self.assertEqual((await self.client.get(self.base,headers=self.headers[self.owner.id])).status_code,404)
            await self.session.execute(update(model).where(clause).values(status="ACTIVE"))
            await self.session.commit()

    async def test_wrong_password_does_not_create_audit_or_renew_actor_session(self):
        deadline = await self.session.scalar(select(UserSession.expires_at).where(UserSession.user_id==self.owner.id))
        self.assertEqual((await self._create(password="incorreta")).status_code,404)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(CompanyChange).where(CompanyChange.organization_id==self.org.id)),0)
        self.assertEqual(await self.session.scalar(select(UserSession.expires_at).where(UserSession.user_id==self.owner.id)),deadline)

    async def test_logout_during_password_verification_prevents_creation(self):
        from app.modules.identity.passwords import verify_password as real_verify

        async def revoke_then_verify(password,stored_hash):
            response = await self.client.post("/api/v1/auth/logout",headers=self.headers[self.owner.id])
            self.assertEqual(response.status_code,204)
            return await real_verify(password,stored_hash)

        with patch("app.modules.identity.access_security.verify_password",revoke_then_verify):
            response = await self._create()
        self.assertEqual(response.status_code,404)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(Company).where(Company.organization_id==self.org.id)),0)

    async def test_audit_failure_rolls_back_company_and_update(self):
        company = await self._company()
        real_flush = AsyncSession.flush

        async def fail_after_audit(session,*args,**kwargs):
            if any(isinstance(row,CompanyChange) for row in session.new):
                await real_flush(session,*args,**kwargs)
                raise SQLAlchemyError("falha simulada")
            return await real_flush(session,*args,**kwargs)

        with patch.object(AsyncSession,"flush",fail_after_audit):
            response = await self._update(company,legal_name="Não persistir")
            created = await self._create(tax_id=ALPHA)
        self.assertEqual(response.status_code,503)
        self.assertEqual(created.status_code,503)
        async with self.factory() as reader:
            stored = await reader.get(Company,company["id"])
            self.assertEqual(stored.legal_name,company["legal_name"])
            self.assertEqual(stored.revision,1)
            self.assertEqual(await reader.scalar(select(func.count()).select_from(Company).where(Company.organization_id==self.org.id)),1)

    async def test_audit_snapshots_are_minimal_and_reference_exact_tenant(self):
        company = await self._company()
        await self._update(company,status="INACTIVE")
        rows = (await self.session.scalars(select(CompanyChange).where(CompanyChange.organization_id==self.org.id).order_by(CompanyChange.created_at))).all()
        self.assertEqual([row.action for row in rows],["CREATED","UPDATED"])
        self.assertTrue(all(row.actor_user_id==self.owner.id and str(row.company_id)==company["id"] for row in rows))
        snapshot = str([(row.before_state,row.after_state) for row in rows])
        for secret in (self.password,NUMERIC,company["legal_name"],self.owner.email):
            self.assertNotIn(secret,snapshot)
        self.assertEqual(rows[1].after_state["changed_fields"],["status"])

    async def test_rate_limit_and_capacity_precede_password_work(self):
        for _ in range(5):
            self.assertEqual((await self._create(password="incorreta")).status_code,404)
        with patch("app.modules.identity.access_security.verify_password",new_callable=AsyncMock) as verifier:
            response = await self._create(tax_id=ALPHA)
        self.assertEqual(response.status_code,429)
        verifier.assert_not_awaited()

    async def test_cancellation_keeps_hash_slot_and_leaves_no_company(self):
        self.app.state.auth_hash_slots = asyncio.Semaphore(1)
        entered,finish = asyncio.Event(),asyncio.Event()

        async def delayed(*args):
            entered.set()
            await finish.wait()
            return True,None

        with patch("app.modules.identity.access_security.verify_password",delayed):
            first = asyncio.create_task(self._create())
            try:
                await asyncio.wait_for(entered.wait(),timeout=5)
                first.cancel()
                self.assertEqual((await self._create()).status_code,503)
            finally:
                finish.set()
                await asyncio.gather(first,return_exceptions=True)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(Company).where(Company.organization_id==self.org.id)),0)

    async def test_redis_and_unexpected_errors_are_sanitized_and_logout_still_works(self):
        with patch.object(self.redis,"eval",side_effect=ConnectionError("segredo_redis")):
            response = await self._create()
            logout = await self.client.post("/api/v1/auth/logout",headers=self.headers[self.owner.id])
        self.assertEqual(response.status_code,503)
        self.assertNotIn("segredo_redis",response.text)
        self.assertEqual(logout.status_code,204)
        with patch("app.modules.organizations.company_service.CompanyService.create",side_effect=RuntimeError("segredo_app")):
            # Outro token válido para não confundir falha inesperada com logout anterior.
            issued = await SessionService(self.session).issue_for_authenticated_user(self.owner.id)
            self.headers[self.owner.id] = {"Authorization":"Bearer "+issued.token.get_secret_value()}
            response = await self._create()
        self.assertEqual(response.status_code,500)
        self.assertNotIn("segredo_app",response.text)

    async def test_json_body_limits_and_missing_session_are_enforced(self):
        for content,content_type,status in (("x"*4097,"application/json",413),("segredo","text/plain",415)):
            response = await self.client.post(self.base,content=content,headers={**self.headers[self.owner.id],"Content-Type":content_type})
            self.assertEqual(response.status_code,status)
            self.assertEqual(response.headers["cache-control"],"no-store")
        self.assertEqual((await self.client.get(self.base)).status_code,401)
        self.app.state.settings = self.config.model_copy(update={"app_environment":"production"})
        self.assertEqual((await self._create()).status_code,503)

    async def test_database_validates_dv_ascii_and_company_audit_tenant_integrity(self):
        for tax_id in ("11222333000182","12ABC34501DE34","00000000000000","12abc34501de35","１２ABC34501DE35"):
            with self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    self.session.add(Company(organization_id=self.org.id,legal_name="Inválida",tax_id=tax_id))
                    await self.session.flush()
        company = await self._company()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(CompanyChange(organization_id=self.other.id,company_id=company["id"],actor_user_id=self.owner.id,
                    action="UPDATED",before_state={},after_state={}))
                await self.session.flush()


class CompanyMigrationTests(DatabaseTestCase):
    async def test_schema_matches_and_postgres_agrees_with_official_cnpj_vectors(self):
        for value in (NUMERIC,ALPHA,FIRST_ALPHA):
            self.assertTrue(await self.session.scalar(text("SELECT sd_is_valid_cnpj(:value)"),{"value":value}))
        self.assertFalse(await self.session.scalar(text("SELECT sd_is_valid_cnpj(:value)"),{"value":"12ABC34501DE34"}))
        await self.session.close()
        await asyncio.to_thread(self.run_migration,"check")


class CompanyMigrationGuardTests(DatabaseTestCase):
    async def test_invalid_legacy_data_blocks_upgrade_and_new_history_blocks_downgrade(self):
        org = Organization(name="Empresa legada")
        user = User(name="Responsável",email=uuid4().hex+"@example.com",status="ACTIVE")
        self.session.add_all([org,user])
        await self.session.flush()
        company = Company(organization_id=org.id,legal_name="Preservada",tax_id=NUMERIC)
        self.session.add(company)
        await self.session.commit()
        org_id,user_id,company_id,bad_id = org.id,user.id,company.id,uuid4()
        await self.session.close()
        await self.engine.dispose()
        await asyncio.to_thread(self.run_migration,"downgrade","c74e901a6bd2")
        try:
            await self.session.execute(text("INSERT INTO companies (id,organization_id,legal_name,tax_id,status) "
                "VALUES (:id,:org,'Cadastro legado sem DV','12345678901','ACTIVE')"),{"id":bad_id,"org":org_id})
            await self.session.commit()
            await self.session.close()
            await self.engine.dispose()
            with self.assertRaises(RuntimeError):
                await asyncio.to_thread(self.run_migration,"upgrade","head")
            self.assertEqual(await self.session.scalar(text("SELECT version_num FROM alembic_version")),"c74e901a6bd2")
        finally:
            await self.session.execute(text("DELETE FROM companies WHERE id = :id"),{"id":bad_id})
            await self.session.commit()
            await self.session.close()
            await self.engine.dispose()
            await asyncio.to_thread(self.run_migration,"upgrade","head")
        self.assertEqual((await self.session.get(Company,company_id)).tax_id,NUMERIC)
        self.session.add(CompanyChange(organization_id=org_id,company_id=company_id,actor_user_id=user_id,
            action="CREATED",before_state={},after_state={"revision":1}))
        await self.session.commit()
        await self.session.close()
        await self.engine.dispose()
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.run_migration,"downgrade","c74e901a6bd2")
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(CompanyChange)),1)
        await self.session.close()
        await asyncio.to_thread(self.run_migration,"check")


class CompanyUniquenessMigrationTests(DatabaseTestCase):
    async def test_round_trip_preserves_rows_and_blocks_global_uniqueness_downgrade(self):
        first,second = Organization(name="Primeiro"),Organization(name="Segundo")
        self.session.add_all([first,second])
        await self.session.flush()
        company = Company(organization_id=first.id,legal_name="Preservada",tax_id=NUMERIC)
        self.session.add(company)
        await self.session.commit()
        company_id,other_id = company.id,second.id
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration,"downgrade","c74e901a6bd2")
        finally:
            await asyncio.to_thread(self.run_migration,"upgrade","head")
        stored = await self.session.get(Company,company_id)
        self.assertEqual(stored.tax_id,NUMERIC)
        self.assertEqual(stored.revision,1)
        self.session.add(Company(organization_id=other_id,legal_name="Independente",tax_id=NUMERIC))
        await self.session.commit()
        await self.session.close()
        await self.engine.dispose()
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.run_migration,"downgrade","c74e901a6bd2")
        self.assertIsNotNone(await self.session.get(Company,company_id))
        await self.session.close()
        await asyncio.to_thread(self.run_migration,"check")
