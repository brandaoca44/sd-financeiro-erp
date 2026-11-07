"""Correções e cancelamentos mantêm despesa, título e histórico consistentes."""
import asyncio
from uuid import uuid4

from test_payable_http import PayableHttpFixture


class ExpenseChangeTests(PayableHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.base = self.path().removesuffix("/payables") + "/expenses"
        self.owner_headers = self.headers[self.owner.id]

    def expense_data(self, **changes):
        return dict(description="Cobrança sintética", category="INTERNET", supplier="Fornecedor de teste",
                    amount="100.00", competence="2026-11-01", issue_date="2026-11-01", due_date="2026-11-10", **changes)

    async def create_expense(self, **changes):
        data = self.expense_data()
        data.update(changes)
        response = await self.client.post(self.base, json=data,
            headers={**self.owner_headers, "Idempotency-Key": str(uuid4())})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"], data

    async def row(self, expense):
        response = await self.client.get(self.base, params={"expense_id": expense}, headers=self.owner_headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()[0]

    async def change(self, expense, original, **changes):
        row = await self.row(expense)
        return await self.client.put(self.base + "/" + expense, headers=self.owner_headers, json={
            **original, "expected_revision": row["revision"], "expected_payable_revision": row["payable_revision"], **changes})

    async def test_partial_payments_stale_revisions_and_cancel_after_reversal(self):
        expense, data = await self.create_expense()
        updated = await self.change(expense, data, amount="150.00")
        self.assertEqual(updated.status_code, 200, updated.text)
        data["amount"] = "150.00"
        row = await self.row(expense)
        title_id = row["payable_id"]
        payment = await self.client.post(self.path(title_id) + "/payments",
            headers={**self.owner_headers, "Idempotency-Key": str(uuid4())},
            json={"expected_revision": 2, "amount": "30.00", "occurred_on": "2026-11-02"})
        self.assertEqual(payment.status_code, 201, payment.text)
        stale = await self.client.put(self.base + "/" + expense, headers=self.owner_headers,
            json={**data, "amount": "160.00", "expected_revision": 2, "expected_payable_revision": 2})
        self.assertEqual(stale.status_code, 409, stale.text)
        cancel = await self.client.post(self.base + "/" + expense + "/cancel", headers=self.owner_headers,
            json={"expected_revision": 2, "expected_payable_revision": 3})
        self.assertEqual(cancel.status_code, 409, cancel.text)
        too_small = await self.change(expense, data, amount="20.00")
        self.assertEqual(too_small.status_code, 409)
        valid = await self.change(expense, data, amount="120.00")
        self.assertEqual(valid.status_code, 200, valid.text)
        title = await self.get(title_id)
        self.assertEqual(title.json()["amount"], "120.00")
        reversal = await self.client.post(self.path(title_id) + "/payments/" + payment.json()["movement_id"] + "/reverse",
            headers={**self.owner_headers, "Idempotency-Key": str(uuid4())},
            json={"expected_revision": 4, "occurred_on": "2026-11-03", "reason": "Correção sintética"})
        self.assertEqual(reversal.status_code, 201, reversal.text)
        row = await self.row(expense)
        cancel = await self.client.post(self.base + "/" + expense + "/cancel", headers=self.owner_headers,
            json={"expected_revision": row["revision"], "expected_payable_revision": row["payable_revision"]})
        self.assertEqual(cancel.status_code, 200, cancel.text)
        self.assertEqual((await self.row(expense))["status"], "CANCELLED")
        self.assertEqual((await self.get(title_id)).json()["status"], "CANCELLED")
        history = await self.client.get(self.base + "/" + expense + "/history", headers=self.owner_headers)
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(len(history.json()), 4)

    async def test_no_title_edit_adds_one_title_and_concurrent_writes_conflict(self):
        expense, data = await self.create_expense(due_date=None)
        payload = {**data, "due_date": "2026-11-10", "expected_revision": 1, "expected_payable_revision": None}
        replies = await asyncio.gather(*[
            self.client.put(self.base + "/" + expense, headers=self.owner_headers, json=payload) for _ in range(2)])
        self.assertEqual(sorted(reply.status_code for reply in replies), [200, 409])
        row = await self.row(expense)
        self.assertIsNotNone(row["payable_id"])
        self.assertEqual(row["revision"], 2)
        response = await self.change(expense, {**data, "due_date": "2026-11-10"}, due_date=None)
        self.assertEqual(response.status_code, 409)

    async def test_cancel_without_title_and_legacy_title_routes_sync_source(self):
        expense, _ = await self.create_expense(due_date=None)
        cancelled = await self.client.post(self.base + "/" + expense + "/cancel", headers=self.owner_headers,
            json={"expected_revision": 1})
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        result = await self.client.get(self.base.replace("/expenses", "/results") + "?month=2026-11", headers=self.owner_headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["expense_count"], 0)
        expense, _ = await self.create_expense()
        row = await self.row(expense)
        changed = await self.edit(row["payable_id"], amount="150.00")
        self.assertEqual(changed.status_code, 200, changed.text)
        row = await self.row(expense)
        self.assertEqual(row["amount"], "150.00")
        self.assertEqual(row["revision"], 2)
        cancelled = await self.cancel(row["payable_id"], revision=2)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual((await self.row(expense))["status"], "CANCELLED")

    async def test_read_only_and_foreign_supplier_do_not_change_source(self):
        expense, data = await self.create_expense()
        await self.grant("payables.read")
        denied = await self.client.put(self.base + "/" + expense, headers=self.headers[self.member.id],
            json={**data, "expected_revision": 1, "expected_payable_revision": 1})
        self.assertEqual(denied.status_code, 404)
        foreign_base = self.path(company=self.b).removesuffix("/payables")
        supplier = await self.client.post(foreign_base + "/suppliers", headers=self.owner_headers, json={"name": "Fornecedor B"})
        bad = {**data, "supplier": None, "supplier_id": supplier.json()["id"], "amount": "170.00",
               "expected_revision": 1, "expected_payable_revision": 1}
        denied = await self.client.put(self.base + "/" + expense, headers=self.owner_headers, json=bad)
        self.assertEqual(denied.status_code, 404)
        row = await self.row(expense)
        self.assertEqual(row["amount"], "100.00")
        self.assertEqual(row["payable_revision"], 1)
