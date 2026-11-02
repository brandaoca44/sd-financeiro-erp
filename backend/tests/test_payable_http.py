"""HTTP financeiro com transações reais isoladas, sem pagamentos bancários."""

import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from redis.exceptions import ConnectionError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from test_company_access import CompanyGrantHttpFixture
from app.modules.finance.models import Payable, PayableChange, PayableMovement
from app.modules.finance.service import PayableService
from app.modules.identity.rate_limit import LoginRateLimiter, LoginRateLimitPolicy
from app.modules.identity.sessions import SessionService


class PayableHttpTests(CompanyGrantHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self._wide_limit()

    def path(self, title=None, company=None, org=None):
        company = company or self.a
        base = f"/api/v1/organizations/{org or company.organization_id}/companies/{company.id}/payables"
        return base if title is None else base + "/" + str(title)

    def data(self, **changes):
        return {"description":"Despesa sintética privada", "amount":"123.45", "issue_date":"2026-11-01", "due_date":"2026-11-10", **changes}

    async def grant(self, key, *, status="ACTIVE", revision=0):
        response = await self.client.put(self._grant_path().replace("read-access", "permissions/" + key),
            headers=self.headers[self.owner.id], json={"status":status, "expected_revision":revision,
                "expected_company_revision":1, "expected_membership_revision":1, "password":self.password})
        self.assertEqual(response.status_code, 200, response.text)

    async def create(self, *, actor=None, company=None, org=None, **changes):
        return await self.client.post(self.path(company=company, org=org), headers=self.headers[actor or self.owner.id], json=self.data(**changes))

    async def title_id(self):
        response = await self.create()
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    async def edit(self, title, *, actor=None, company=None, **changes):
        return await self.client.put(self.path(title, company), headers=self.headers[actor or self.owner.id],
            json=self.data(**{"expected_revision":1, **changes}))

    async def cancel(self, title, *, actor=None, company=None, revision=1):
        return await self.client.post(self.path(title, company)+"/cancel", headers=self.headers[actor or self.owner.id], json={"expected_revision":revision})

    async def get(self, title, *, actor=None, company=None, org=None):
        return await self.client.get(self.path(title, company, org), headers=self.headers[actor or self.owner.id])

    async def test_owner_full_title_flow_without_payment_operations(self):
        response = await self.create(amount="0.10")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), {"id", "revision", "status"})
        title = response.json()["id"]
        self.assertTrue(response.headers["location"].endswith(title))
        self.assertEqual((await self.get(title)).json()["amount"], "0.10")
        self.assertEqual((await self.edit(title, amount="0.20")).status_code, 200)
        self.assertEqual((await self.cancel(title, revision=2)).status_code, 200)
        self.assertEqual((await self.get(title)).json()["status"], "CANCELLED")
        self.assertEqual((await self.cancel(title, revision=3)).status_code, 409)
        self.assertEqual((await self.edit(title, expected_revision=3)).status_code, 409)
        self.assertEqual((await self.client.post(self.path(title)+"/payments", headers=self.headers[self.owner.id], json={})).status_code, 404)

    async def test_manage_only_does_not_read_or_receive_financial_fields(self):
        await self.grant("payables.manage")
        response = await self.create(actor=self.member.id)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(set(response.json()), {"id", "revision", "status"})
        self.assertEqual((await self.get(response.json()["id"], actor=self.member.id)).status_code, 404)
        self.assertEqual((await self.client.get(self.path(), headers=self.headers[self.member.id])).status_code, 404)
        self.assertEqual((await self.edit(response.json()["id"], actor=self.member.id)).status_code, 200)

    async def test_read_only_cannot_write(self):
        title = await self.title_id()
        await self.grant("payables.read")
        self.assertEqual((await self.get(title, actor=self.member.id)).status_code, 200)
        for response in (await self.create(actor=self.member.id), await self.edit(title, actor=self.member.id), await self.cancel(title, actor=self.member.id)):
            self.assertEqual(response.status_code, 404)

    async def test_settle_reverse_and_company_read_do_not_manage_titles(self):
        self.assertEqual((await self._set()).status_code, 200)
        for key in ("payables.settle", "payables.reverse"):
            await self.grant(key)
        title = await self.title_id()
        self.assertEqual((await self.create(actor=self.member.id)).status_code, 404)
        self.assertEqual((await self.get(title, actor=self.member.id)).status_code, 404)
        self.assertEqual((await self.edit(title, actor=self.operator.id)).status_code, 404)

    async def test_input_cannot_override_scope_actor_status_or_use_float(self):
        for changes in ({"amount":0.10}, {"amount":"1.001"}, {"amount":"NaN"}, {"currency":"USD"},
                        {"company_id":str(self.b.id)}, {"organization_id":str(self.other.id)},
                        {"created_by_user_id":str(self.member.id)}, {"status":"CANCELLED"}, {"issue_date":"20261101"}):
            response = await self.create(**changes)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("Despesa sintética privada", response.text)

    async def test_all_title_operations_require_same_company_and_tenant(self):
        title = await self.title_id()
        for company in (self.b, self.foreign):
            self.assertEqual((await self.get(title, company=company)).status_code, 404)
            self.assertEqual((await self.edit(title, company=company)).status_code, 404)
            self.assertEqual((await self.cancel(title, company=company)).status_code, 404)
        self.assertEqual((await self.create(company=self.foreign, org=self.org.id)).status_code, 404)
        self.assertEqual((await self.get(title)).json()["revision"], 1)

    async def test_list_is_paginated_and_filters_dates_and_status(self):
        first, second = await self.title_id(), await self.title_id()
        await self.create(company=self.b)
        response = await self.client.get(self.path(), headers=self.headers[self.owner.id], params={"limit":1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 1)
        cursor = response.json()["next_cursor"]
        self.assertIsNotNone(cursor)
        next_page = await self.client.get(self.path(), headers=self.headers[self.owner.id], params={"limit":1, "cursor":cursor})
        self.assertIsNone(next_page.json()["next_cursor"])
        self.assertNotEqual(next_page.json()["items"][0]["id"], response.json()["items"][0]["id"])
        self.assertEqual((await self.client.get(self.path(), headers=self.headers[self.owner.id], params={"due_from":"2026-11-11"})).json()["items"], [])
        self.assertEqual((await self.client.get(self.path(), headers=self.headers[self.owner.id], params={"due_from":"2026-12-01", "due_to":"2026-11-01"})).status_code, 422)
        self.assertEqual((await self.client.get(self.path(), headers=self.headers[self.owner.id], params={"limit":101})).status_code, 422)

    async def test_revocation_and_company_inactivity_block_titles(self):
        title = await self.title_id()
        await self.grant("payables.read")
        self.assertEqual((await self.get(title, actor=self.member.id)).status_code, 200)
        await self.grant("payables.read", status="INACTIVE", revision=1)
        self.assertEqual((await self.get(title, actor=self.member.id)).status_code, 404)
        self.assertEqual((await self._update_company(status="INACTIVE", revision=1)).status_code, 200)
        self.assertEqual((await self.get(title)).status_code, 404)
        self.assertEqual((await self.create()).status_code, 404)

    async def test_concurrent_updates_have_one_winner_and_no_lost_revision(self):
        title = await self.title_id()
        responses = await asyncio.gather(self.edit(title, amount="100.00"), self.edit(title, amount="101.00"))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        self.assertEqual((await self.get(title)).json()["revision"], 2)

    async def test_cancel_racing_edit_has_one_winner(self):
        title = await self.title_id()
        responses = await asyncio.gather(self.cancel(title), self.edit(title))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])

    async def test_existing_movements_prevent_inconsistent_edit_or_cancel(self):
        title = await self.title_id()
        async with self.factory() as writer, writer.begin():
            writer.add(PayableMovement(organization_id=self.org.id, company_id=self.a.id, payable_id=title,
                actor_user_id=self.owner.id, kind="PAYMENT", amount=Decimal("100.00"), occurred_on=date(2026,11,2)))
        self.assertEqual((await self.cancel(title)).status_code, 409)
        self.assertEqual((await self.edit(title, amount="99.99")).status_code, 409)
        self.assertEqual((await self.edit(title, issue_date="2026-11-03")).status_code, 409)
        self.assertEqual((await self.edit(title, amount="100.00")).status_code, 200)

    async def test_audit_failure_rolls_back_title_and_update(self):
        title = await self.title_id()
        original = AsyncSession.flush
        async def fail(session, *args, **kwargs):
            if any(isinstance(row, PayableChange) for row in session.new):
                raise RuntimeError("detalhe privado de auditoria")
            return await original(session, *args, **kwargs)
        with patch.object(AsyncSession, "flush", fail):
            for response in (await self.create(), await self.edit(title), await self.cancel(title)):
                self.assertEqual(response.status_code, 500)
                self.assertNotIn("detalhe privado", response.text)
        self.assertEqual((await self.get(title)).json()["revision"], 1)
        async with self.factory() as reader:
            self.assertEqual(await reader.scalar(select(func.count()).select_from(Payable).where(Payable.organization_id==self.org.id)), 1)

    async def test_session_revoked_between_http_resolution_and_write_is_denied(self):
        original = PayableService._authorize_write
        async def revoke(service, organization_id, company_id, token):
            async with self.factory() as writer:
                await SessionService(writer).revoke(token)
            return await original(service, organization_id, company_id, token)
        with patch.object(PayableService, "_authorize_write", revoke):
            self.assertEqual((await self.create()).status_code, 404)

    async def test_rate_limit_and_redis_failure_block_writes(self):
        self.app.state.payables_manage_limiter = LoginRateLimiter(self.redis, key_secret=self.config.auth_rate_limit_key,
            namespace=self.namespace, operation="payables_manage", policy=LoginRateLimitPolicy(account_limit=1))
        self.assertEqual((await self.create()).status_code, 201)
        response = await self.create()
        self.assertEqual(response.status_code, 429)
        self.assertIn("retry-after", response.headers)
        with patch.object(self.redis, "eval", side_effect=ConnectionError("privado")):
            response = await self.create()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("privado", response.text)

    async def test_https_authentication_body_limit_and_safe_headers(self):
        response = await self.client.post(self.path(), json=self.data())
        self.assertEqual(response.status_code, 401)
        response = await self.client.post(self.path(), headers={**self.headers[self.owner.id], "content-type":"application/json"}, content="x"*4097)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("x-request-id", response.headers)
        self.app.state.settings = self.config.model_copy(update={"app_environment":"production"})
        self.assertEqual((await self.create()).status_code, 503)
