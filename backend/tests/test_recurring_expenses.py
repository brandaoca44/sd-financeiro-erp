"""Recorrências mensais, recuperação após falhas e revisão sem duplicidade."""
import asyncio
from datetime import date
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.modules.finance.expenses import Expense, ExpenseRule
from app.modules.finance.models import Payable
from app.modules.finance.recurring import ExpenseOccurrence, generate_due_expenses
from app.modules.organizations.models import Company
from test_payable_http import PayableHttpFixture


class RecurringExpenseTests(PayableHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.base = self.path().removesuffix("/payables")
        self.owner_headers = self.headers[self.owner.id]
        response = await self.client.post(self.base + "/suppliers",
            headers=self.owner_headers, json={"name": "Fornecedor sintético"})
        self.assertEqual(response.status_code, 201, response.text)
        self.supplier_id = response.json()["id"]

    async def create_rule(self, amount="99.90"):
        body = dict(description="Serviço mensal", category="INTERNET", supplier_id=self.supplier_id,
                    due_day=30, fixed_amount=amount)
        with patch("app.modules.finance.expenses.PayableMovementService._today", return_value=date(2026, 1, 15)):
            response = await self.client.post(self.base + "/expenses/rules",
                headers={**self.owner_headers, "Idempotency-Key": str(uuid4())}, json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"], body

    async def occurrences(self):
        response = await self.client.get(self.base + "/expense-occurrences", headers=self.owner_headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_fixed_concurrent_generation_catches_up_and_clamps_february(self):
        rule, _ = await self.create_rule()
        await asyncio.gather(*[generate_due_expenses(self.factory, today=date(2026, 2, 10)) for _ in range(2)])
        rows = await self.occurrences()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["status"] == "GENERATED" for row in rows))
        self.assertEqual({row["due_date"] for row in rows}, {"2026-01-30", "2026-02-28"})
        async with self.factory() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Payable).where(Payable.company_id == self.a.id)), 2)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Expense).where(Expense.company_id == self.a.id)), 2)
            scheduled = await session.get(ExpenseRule, (self.org.id, self.a.id, UUID(rule)))
            self.assertEqual(scheduled.next_month, date(2026, 3, 1))
        self.assertEqual(await generate_due_expenses(self.factory, today=date(2026, 2, 10)), 0)

    async def test_variable_review_replays_and_cancel_stops_future(self):
        rule, _ = await self.create_rule(None)
        await generate_due_expenses(self.factory, today=date(2026, 1, 15))
        row = (await self.occurrences())[0]
        self.assertEqual(row["status"], "PENDING")
        async with self.factory() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Payable).where(Payable.company_id == self.a.id)), 0)
        path = self.base + "/expense-occurrences/" + row["id"] + "/confirm"
        data = dict(amount="175.45", due_date="2026-01-25", document_type="BOLETO", document_reference="FATURA-TESTE")
        first = await self.client.post(path, headers=self.owner_headers, json=data)
        self.assertEqual(first.status_code, 200, first.text)
        again = await self.client.post(path, headers=self.owner_headers, json=data)
        self.assertEqual(first.json(), again.json())
        changed = await self.client.post(path, headers=self.owner_headers, json={**data, "amount": "190.00"})
        self.assertEqual(changed.status_code, 409)
        response = await self.client.post(self.base + "/expenses/rules/" + rule + "/cancel", headers=self.owner_headers, json={})
        self.assertEqual(response.status_code, 204, response.text)
        await generate_due_expenses(self.factory, today=date(2026, 3, 1))
        self.assertEqual(len(await self.occurrences()), 1)

    async def test_cancelled_draft_scope_and_unauthorized_actor(self):
        rule, _ = await self.create_rule(None)
        await generate_due_expenses(self.factory, today=date(2026, 1, 15))
        row = (await self.occurrences())[0]
        foreign = self.path(company=self.b).removesuffix("/payables")
        denied = await self.client.post(foreign + "/expense-occurrences/" + row["id"] + "/confirm",
            headers=self.owner_headers, json={"amount": "20.00", "due_date": "2026-01-30"})
        self.assertEqual(denied.status_code, 404)
        await self.client.post(self.base + "/expenses/rules/" + rule + "/cancel", headers=self.owner_headers, json={})
        denied = await self.client.post(self.base + "/expense-occurrences/" + row["id"] + "/confirm",
            headers=self.owner_headers, json={"amount": "20.00", "due_date": "2026-01-30"})
        self.assertEqual(denied.status_code, 409)
        self.assertEqual((await self.occurrences())[0]["status"], "CANCELLED")
        _, _ = await self.create_rule()
        async with self.factory() as session, session.begin():
            company = await session.get(Company, self.a.id)
            company.status = "INACTIVE"
        self.assertEqual(await generate_due_expenses(self.factory, today=date(2026, 1, 15)), 0)

    async def test_legacy_rule_requires_activation_and_starts_in_activation_month(self):
        rule, data = await self.create_rule()
        async with self.factory() as session, session.begin():
            scheduled = await session.get(ExpenseRule, (self.org.id, self.a.id, UUID(rule)))
            scheduled.authorized_by_user_id = None
        await generate_due_expenses(self.factory, today=date(2026, 3, 1))
        self.assertEqual(await self.occurrences(), [])
        with patch("app.modules.finance.expenses.PayableMovementService._today", return_value=date(2026, 3, 15)):
            response = await self.client.put(self.base + "/expenses/rules/" + rule, headers=self.owner_headers, json=data)
        self.assertEqual(response.status_code, 204, response.text)
        await generate_due_expenses(self.factory, today=date(2026, 3, 15))
        self.assertEqual([row["competence"] for row in await self.occurrences()], ["2026-03-01"])

    async def test_revoked_permission_blocks_authorized_schedule(self):
        rule, _ = await self.create_rule()
        await self.grant("payables.manage")
        async with self.factory() as session, session.begin():
            scheduled = await session.get(ExpenseRule, (self.org.id, self.a.id, UUID(rule)))
            scheduled.authorized_by_user_id = self.member.id
        await self.grant("payables.manage", status="INACTIVE", revision=1)
        await generate_due_expenses(self.factory, today=date(2026, 1, 15))
        self.assertEqual(await self.occurrences(), [])

    async def test_failure_rolls_back_then_retry_generates_and_edit_only_affects_next_month(self):
        rule, data = await self.create_rule()
        with patch("app.modules.finance.recurring.materialize", side_effect=SQLAlchemyError()):
            self.assertEqual(await generate_due_expenses(self.factory, today=date(2026, 1, 15)), 0)
        self.assertEqual(await self.occurrences(), [])
        await generate_due_expenses(self.factory, today=date(2026, 1, 15))
        response = await self.client.put(self.base + "/expenses/rules/" + rule,
            headers=self.owner_headers, json={**data, "fixed_amount": "120.00", "due_day": 5})
        self.assertEqual(response.status_code, 204, response.text)
        await generate_due_expenses(self.factory, today=date(2026, 2, 1))
        rows = await self.occurrences()
        self.assertEqual([(row["amount"], row["due_date"]) for row in rows],
                         [("120.00", "2026-02-05"), ("99.90", "2026-01-30")])
