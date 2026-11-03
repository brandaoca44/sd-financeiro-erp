"""Baixas/estornos reais em banco temporário, com replay e corridas."""

import asyncio
import unittest
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from redis.exceptions import ConnectionError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database_support import DatabaseTestCase
from test_payable_http import PayableHttpFixture
from app.modules.finance.models import Payable, PayableMovement, PayableMovementRequest, PayableChange
from app.modules.finance.movements import PayableMovementService
from app.modules.finance.schemas import PayablePayment, PayableReversal
from app.modules.identity.models import UserSession
from app.modules.identity.sessions import SessionService


class MovementContractTests(unittest.TestCase):
    def test_payment_and_reversal_contracts_reject_privilege_and_amount_overrides(self):
        for changes in ({"amount":0.1}, {"amount":"1.001"}, {"actor_user_id":str(uuid4())}, {"kind":"REVERSAL"}, {"expected_revision":True}):
            with self.assertRaises(ValidationError):
                PayablePayment(**({"amount":"1.00", "occurred_on":"2026-11-02", "expected_revision":1} | changes))
        for extra in ({"amount":"1.00"}, {"reason":" "}, {"reverses_id":str(uuid4())}):
            with self.assertRaises(ValidationError):
                PayableReversal(**({"reason":"Correção", "occurred_on":"2026-11-03", "expected_revision":2} | extra))


class PayableMovementHttpTests(PayableHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        calendar = patch.object(PayableMovementService, "_today", return_value=date(2026,11,5))
        calendar.start()
        self.addCleanup(calendar.stop)

    async def pay(self, title, *, key=None, actor=None, company=None, **changes):
        return await self.client.post(self.path(title, company)+"/payments",
            headers={**self.headers[actor or self.owner.id], "Idempotency-Key":str(key or uuid4())},
            json={"amount":"40.00", "occurred_on":"2026-11-02", "expected_revision":1, **changes})

    async def reverse(self, title, payment, *, key=None, actor=None, company=None, **changes):
        return await self.client.post(self.path(title, company)+f"/payments/{payment}/reverse",
            headers={**self.headers[actor or self.owner.id], "Idempotency-Key":str(key or uuid4())},
            json={"occurred_on":"2026-11-03", "expected_revision":2, "reason":"Correção sintética privada", **changes})

    async def position(self, title, *, actor=None, company=None):
        return await self.client.get(self.path(title, company)+"/position", headers=self.headers[actor or self.owner.id])

    async def test_partial_full_payment_and_reversal_positions_are_exact(self):
        title = await self.title_id()
        first = await self.pay(title, amount="0.10")
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(set(first.json()), {"payable_id", "movement_id", "revision", "kind"})
        self.assertEqual((await self.position(title)).json()["paid_amount"], "0.10")
        self.assertEqual((await self.position(title)).json()["settlement_status"], "PARTIALLY_PAID")
        second = await self.pay(title, amount="123.35", expected_revision=2)
        self.assertEqual(second.status_code, 201)
        self.assertEqual((await self.position(title)).json()["outstanding_amount"], "0.00")
        self.assertEqual((await self.position(title)).json()["settlement_status"], "PAID")
        self.assertEqual((await self.reverse(title, second.json()["movement_id"], expected_revision=3)).status_code, 201)
        self.assertEqual((await self.position(title)).json()["paid_amount"], "0.10")

    async def test_exact_replay_returns_original_receipt_without_new_revision(self):
        title, key = await self.title_id(), uuid4()
        first, second = await self.pay(title,key=key), await self.pay(title,key=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.json(), first.json())
        self.assertEqual((await self.position(title)).json()["revision"], 2)
        async with self.factory() as reader:
            self.assertEqual(await reader.scalar(select(func.count()).select_from(PayableMovementRequest).where(
                PayableMovementRequest.organization_id==self.org.id)), 1)

    async def test_normalized_decimal_payload_replays_but_changed_payload_conflicts(self):
        title, key = await self.title_id(), uuid4()
        self.assertEqual((await self.pay(title,key=key,amount="40")).status_code, 201)
        self.assertEqual((await self.pay(title,key=key,amount="40.00")).status_code, 201)
        for changes in ({"amount":"41.00"}, {"expected_revision":2}, {"occurred_on":"2026-11-03"}):
            self.assertEqual((await self.pay(title,key=key,**changes)).status_code, 409)
        other = await self.title_id()
        self.assertEqual((await self.pay(other,key=key)).status_code, 409)

    async def test_concurrent_identical_requests_only_apply_once(self):
        title, key = await self.title_id(), uuid4()
        responses = await asyncio.gather(self.pay(title,key=key), self.pay(title,key=key))
        self.assertEqual([r.status_code for r in responses], [201,201])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual((await self.position(title)).json()["paid_amount"], "40.00")

    async def test_concurrent_different_keys_do_not_overpay(self):
        title = await self.title_id()
        responses = await asyncio.gather(self.pay(title,amount="100.00"), self.pay(title,amount="100.00"))
        self.assertEqual(sorted(r.status_code for r in responses), [201,409])
        self.assertEqual((await self.pay(title,amount="24.00",expected_revision=2)).status_code, 409)
        self.assertEqual((await self.position(title)).json()["paid_amount"], "100.00")

    async def test_reverse_once_and_replay_even_after_title_cancelled(self):
        title, key = await self.title_id(), uuid4()
        payment = await self.pay(title)
        reversal = await self.reverse(title,payment.json()["movement_id"],key=key)
        self.assertEqual(reversal.status_code, 201)
        self.assertEqual((await self.reverse(title,payment.json()["movement_id"],expected_revision=3)).status_code, 409)
        self.assertEqual((await self.cancel(title,revision=3)).status_code, 200)
        self.assertEqual((await self.reverse(title,payment.json()["movement_id"],key=key)).json(), reversal.json())
        position = (await self.position(title)).json()
        self.assertEqual((position["settlement_status"],position["outstanding_amount"]), ("CANCELLED","0.00"))

    async def test_reversal_cannot_reverse_another_reversal_or_other_title(self):
        title, other = await self.title_id(), await self.title_id()
        payment = await self.pay(title)
        self.assertEqual((await self.reverse(other,payment.json()["movement_id"],expected_revision=1)).status_code, 404)
        reversal = await self.reverse(title,payment.json()["movement_id"])
        self.assertEqual((await self.reverse(title,reversal.json()["movement_id"],expected_revision=3)).status_code, 404)

    async def test_concurrent_reversals_have_one_winner(self):
        title = await self.title_id()
        payment = await self.pay(title)
        results = await asyncio.gather(self.reverse(title,payment.json()["movement_id"]), self.reverse(title,payment.json()["movement_id"]))
        self.assertEqual(sorted(r.status_code for r in results), [201,409])
        self.assertEqual((await self.position(title)).json()["paid_amount"], "0.00")

    async def test_dates_and_cancelled_titles_cannot_receive_payments(self):
        title = await self.title_id()
        for day in ("2026-10-31", "2026-11-06"):
            self.assertEqual((await self.pay(title,occurred_on=day)).status_code, 409)
        payment = await self.pay(title)
        for day in ("2026-11-01", "2026-11-06"):
            self.assertEqual((await self.reverse(title,payment.json()["movement_id"],occurred_on=day)).status_code, 409)
        other = await self.title_id()
        await self.cancel(other)
        self.assertEqual((await self.pay(other,expected_revision=2)).status_code, 409)

    async def test_settle_permission_is_independent_and_minimal(self):
        title = await self.title_id()
        await self.grant("payables.settle")
        payment = await self.pay(title,actor=self.member.id)
        self.assertEqual(payment.status_code, 201)
        self.assertNotIn("amount",payment.json())
        self.assertEqual((await self.position(title,actor=self.member.id)).status_code, 404)
        self.assertEqual((await self.reverse(title,payment.json()["movement_id"],actor=self.member.id)).status_code, 404)
        self.assertEqual((await self.create(actor=self.member.id)).status_code, 404)

    async def test_reverse_only_permission_does_not_pay_or_read(self):
        title = await self.title_id()
        payment = await self.pay(title)
        await self.grant("payables.reverse")
        self.assertEqual((await self.reverse(title,payment.json()["movement_id"],actor=self.member.id)).status_code, 201)
        self.assertEqual((await self.pay(title,actor=self.member.id,expected_revision=3)).status_code, 404)
        self.assertEqual((await self.position(title,actor=self.member.id)).status_code, 404)

    async def test_read_and_manage_do_not_pay(self):
        title = await self.title_id()
        for key in ("payables.read","payables.manage"):
            await self.grant(key)
        self.assertEqual((await self.pay(title,actor=self.member.id)).status_code, 404)
        self.assertEqual((await self.position(title,actor=self.member.id)).status_code, 200)

    async def test_replay_after_revocation_is_not_an_authorization_bypass(self):
        title, key = await self.title_id(), uuid4()
        await self.grant("payables.settle")
        self.assertEqual((await self.pay(title,key=key,actor=self.member.id)).status_code, 201)
        await self.grant("payables.settle",status="INACTIVE",revision=1)
        self.assertEqual((await self.pay(title,key=key,actor=self.member.id)).status_code, 404)

    async def test_key_scope_includes_actor_and_operation(self):
        title, key = await self.title_id(), uuid4()
        first = await self.pay(title,key=key,amount="10.00")
        await self.grant("payables.settle")
        second = await self.pay(title,key=key,actor=self.member.id,amount="20.00",expected_revision=2)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.json()["movement_id"],second.json()["movement_id"])
        self.assertEqual((await self.reverse(title,first.json()["movement_id"],key=key,expected_revision=3)).status_code, 201)

    async def test_cross_company_references_cannot_pay_reverse_or_read(self):
        title, key = await self.title_id(), uuid4()
        payment = await self.pay(title,key=key)
        for company in (self.b,self.foreign):
            self.assertEqual((await self.pay(title,key=key,company=company)).status_code, 404)
            self.assertEqual((await self.reverse(title,payment.json()["movement_id"],company=company)).status_code, 404)
            self.assertEqual((await self.position(title,company=company)).status_code, 404)

    async def test_movement_listing_is_read_protected_paginated_and_exact(self):
        title = await self.title_id()
        payment = await self.pay(title)
        await self.reverse(title,payment.json()["movement_id"])
        path = self.path(title)+"/movements"
        denied = await self.client.get(path,headers=self.headers[self.member.id])
        self.assertEqual(denied.status_code,404)
        first = await self.client.get(path,headers=self.headers[self.owner.id],params={"limit":1})
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()["items"][0]["amount"],"40.00")
        second = await self.client.get(path,headers=self.headers[self.owner.id],params={"limit":1,"cursor":first.json()["next_cursor"]})
        self.assertIsNone(second.json()["next_cursor"])
        self.assertNotEqual(first.json()["items"][0]["id"],second.json()["items"][0]["id"])

    async def test_failed_audit_or_idempotency_save_rolls_back_everything(self):
        title, key = await self.title_id(), uuid4()
        original = AsyncSession.flush
        for model in (PayableChange,PayableMovementRequest):
            async def fail(session,*args,**kwargs):
                if any(isinstance(row,model) for row in session.new):
                    raise RuntimeError("segredo de infraestrutura")
                return await original(session,*args,**kwargs)
            with patch.object(AsyncSession,"flush",fail):
                response = await self.pay(title,key=key)
                self.assertEqual(response.status_code,500)
                self.assertNotIn("segredo",response.text)
            self.assertEqual((await self.position(title)).json()["revision"],1)
        self.assertEqual((await self.pay(title,key=key)).status_code,201)
        self.assertEqual((await self.position(title)).json()["paid_amount"],"40.00")

    async def test_required_uuid_header_and_request_limits(self):
        title = await self.title_id()
        path = self.path(title)+"/payments"
        for headers in (self.headers[self.owner.id], {**self.headers[self.owner.id],"Idempotency-Key":"private-invalid"}):
            response = await self.client.post(path,headers=headers,json={"amount":"10.00","occurred_on":"2026-11-02","expected_revision":1})
            self.assertEqual(response.status_code,422)
            self.assertNotIn("private-invalid",response.text)
        response = await self.client.post(path,headers={**self.headers[self.owner.id],"content-type":"application/json","Idempotency-Key":str(uuid4())},content="x"*4097)
        self.assertEqual(response.status_code,413)
        self.assertEqual(response.headers["cache-control"],"no-store")

    async def test_redis_outage_and_revoked_session_block_replay(self):
        title,key = await self.title_id(),uuid4()
        self.assertEqual((await self.pay(title,key=key)).status_code,201)
        with patch.object(self.redis,"eval",side_effect=ConnectionError("segredo")):
            self.assertEqual((await self.pay(title,key=key)).status_code,503)
        await self.client.post("/api/v1/auth/logout",headers=self.headers[self.owner.id])
        self.assertEqual((await self.pay(title,key=key)).status_code,401)

    async def test_session_revoked_between_resolution_and_movement_is_rejected(self):
        title = await self.title_id()
        original = PayableMovementService._authorize_write
        async def revoke(service, organization_id, company_id, token, **kwargs):
            async with self.factory() as writer:
                await SessionService(writer).revoke(token)
            return await original(service,organization_id,company_id,token,**kwargs)
        with patch.object(PayableMovementService,"_authorize_write",revoke):
            self.assertEqual((await self.pay(title)).status_code,404)

    async def test_company_inactivity_blocks_replay_and_read(self):
        title,key = await self.title_id(),uuid4()
        self.assertEqual((await self.pay(title,key=key)).status_code,201)
        self.assertEqual((await self._update_company(status="INACTIVE",revision=1)).status_code,200)
        self.assertEqual((await self.pay(title,key=key)).status_code,404)
        self.assertEqual((await self.position(title)).status_code,404)

    async def test_database_rejects_cross_company_result_and_invalid_metadata(self):
        title,key = await self.title_id(),uuid4()
        self.assertEqual((await self.pay(title,key=key)).status_code,201)
        async with self.factory() as writer, writer.begin():
            for changes in ({"company_id":self.b.id}, {"payable_id":uuid4()},
                            {"operation":"OTHER"}, {"payload_hash":"invalid"}, {"title_revision":0}):
                with self.assertRaises(IntegrityError):
                    async with writer.begin_nested():
                        await writer.execute(update(PayableMovementRequest).where(
                            PayableMovementRequest.organization_id==self.org.id,
                            PayableMovementRequest.request_key==key).values(**changes))

    async def test_downgrade_preserves_movements_and_idempotency_results(self):
        title = await self.title_id()
        self.assertEqual((await self.pay(title)).status_code,201)
        await self.session.close()
        await self.engine.dispose()
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.run_migration,"downgrade","a18d5320cf97")
        await asyncio.to_thread(self.run_migration,"check")
        self.assertEqual((await self.position(title)).json()["paid_amount"],"40.00")


class MovementMigrationTests(DatabaseTestCase):
    async def test_empty_roundtrip_and_schema_alignment(self):
        await self.session.close()
        await self.engine.dispose()
        await asyncio.to_thread(self.run_migration,"downgrade","a18d5320cf97")
        await asyncio.to_thread(self.run_migration,"upgrade","head")
        await asyncio.to_thread(self.run_migration,"check")
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(PayableMovementRequest)),0)
