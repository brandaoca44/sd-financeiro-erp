"""Alertas financeiros por saldo, empresa e permissão."""
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select

from app.modules.finance.recurring import generate_due_expenses
from app.modules.identity.models import UserSession
from test_payable_http import PayableHttpFixture


class FinancialAlertsTests(PayableHttpFixture):
    async def get_alerts(self, headers=None, company=None):
        base = self.path(company=company).removesuffix("/payables")
        with patch("app.modules.finance.alerts.PayableMovementService._today", return_value=date(2026, 11, 6)):
            return await self.client.get(base + "/alerts", headers=headers or self.headers[self.owner.id])

    async def test_balances_dates_and_review_drafts(self):
        async def title(description, amount, due):
            response = await self.create(description=description, amount=amount, due_date=due)
            self.assertEqual(response.status_code, 201, response.text)
            return response.json()["id"]
        overdue = await title("Vencida", "100.00", "2026-11-05")
        response = await self.client.post(self.path(overdue) + "/payments",
            headers={**self.headers[self.owner.id], "Idempotency-Key": str(uuid4())},
            json=dict(amount="40.00", occurred_on="2026-11-06", expected_revision=1))
        self.assertEqual(response.status_code, 201, response.text)
        await title("Hoje", "50.00", "2026-11-06")
        await title("Próximos sete dias", "70.00", "2026-11-13")
        await title("Depois da janela", "80.00", "2026-11-14")
        paid = await title("Paga", "25.00", "2026-11-01")
        response = await self.client.post(self.path(paid) + "/payments",
            headers={**self.headers[self.owner.id], "Idempotency-Key": str(uuid4())},
            json=dict(amount="25.00", occurred_on="2026-11-06", expected_revision=1))
        self.assertEqual(response.status_code, 201, response.text)
        cancelled = await title("Cancelada", "30.00", "2026-11-01")
        self.assertEqual((await self.cancel(cancelled)).status_code, 200)
        base = self.path().removesuffix("/payables")
        supplier = await self.client.post(base + "/suppliers", headers=self.headers[self.owner.id], json={"name": "Fornecedor teste"})
        with patch("app.modules.finance.expenses.PayableMovementService._today", return_value=date(2026, 11, 6)):
            rule = await self.client.post(base + "/expenses/rules",
                headers={**self.headers[self.owner.id], "Idempotency-Key": str(uuid4())},
                json=dict(description="Conta variável", category="ENERGIA", supplier_id=supplier.json()["id"], due_day=10))
        self.assertEqual(rule.status_code, 201, rule.text)
        await generate_due_expenses(self.factory, today=date(2026, 11, 6))
        response = await self.get_alerts()
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertEqual([report[key] for key in ("total", "overdue", "today", "upcoming", "review")], [4, 1, 1, 1, 1])
        self.assertEqual(report["items"][0]["amount"], "60.00")
        self.assertEqual([row["kind"] for row in report["items"]], ["OVERDUE", "TODAY", "REVIEW", "UPCOMING"])
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_permission_scope_and_no_idle_renewal(self):
        await self.title_id()
        async with self.factory() as session:
            before = list((await session.execute(select(UserSession.id, UserSession.expires_at).where(
                UserSession.user_id == self.owner.id))).all())
        report = await self.get_alerts()
        self.assertEqual(report.status_code, 200, report.text)
        async with self.factory() as session:
            after = list((await session.execute(select(UserSession.id, UserSession.expires_at).where(
                UserSession.user_id == self.owner.id))).all())
        self.assertEqual(before, after)
        foreign = await self.get_alerts(company=self.b)
        self.assertEqual(foreign.json()["total"], 0)
        denied = await self.get_alerts(headers=self.headers[self.member.id])
        self.assertEqual(denied.status_code, 404)
        await self.grant("payables.read")
        allowed = await self.get_alerts(headers=self.headers[self.member.id])
        self.assertEqual(allowed.status_code, 200, allowed.text)
        denied = await self.get_alerts(headers=self.headers[self.member.id], company=self.b)
        self.assertEqual(denied.status_code, 404)
        await self.grant("payables.read", status="INACTIVE", revision=1)
        denied = await self.get_alerts(headers=self.headers[self.member.id])
        self.assertEqual(denied.status_code, 404)
