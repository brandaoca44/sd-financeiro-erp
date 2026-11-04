"""Resultado por competência com valores exatos e autorização por empresa."""
from uuid import uuid4

from test_payable_http import PayableHttpFixture


class CompetenceResultTests(PayableHttpFixture):
    async def test_competence_is_independent_of_payment_and_cancellation(self):
        base = self.path().removesuffix("/payables")
        headers = self.headers[self.owner.id]

        async def post(path, data):
            response = await self.client.post(base + path,
                headers={**headers, "Idempotency-Key": str(uuid4())}, json=data)
            self.assertEqual(response.status_code, 201, response.text)
            return response.json()

        billing = await post("/billing", dict(customer="Cliente", service="Consultoria",
            competence="2026-11-01", issue_date="2026-12-01", due_date="2026-12-10", amount="1000.10"))
        expense = await post("/expenses", dict(description="Internet", category="INTERNET", supplier="Fornecedor",
            competence="2026-11-01", issue_date="2026-12-01", due_date="2026-12-10", amount="200.05"))
        await post("/expenses", dict(description="Legado", category="AGUA", supplier="Fornecedor",
            issue_date="2026-11-01", amount="10.00"))
        await post("/billing", dict(customer="Outro cliente", service="Serviço em dezembro",
            competence="2026-12-01", issue_date="2026-11-01", amount="500.00"))
        await self.title_id()

        async def result(month="2026-11"):
            response = await self.client.get(base + "/results", params={"month": month}, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()

        report = await result()
        self.assertEqual(report["revenue"], "1000.10")
        self.assertEqual(report["expenses"], "200.05")
        self.assertEqual(report["result"], "800.05")
        self.assertEqual(report["status"], "PROFIT")
        self.assertTrue(report["partial"])
        self.assertEqual(report["unassigned_expenses"], 1)
        self.assertEqual(report["unlinked_payables"], 1)

        await post("/billing/" + billing["id"] + "/receipts", dict(amount="100.00", received_on="2026-12-02"))
        self.assertEqual((await result())["result"], "800.05")
        cancelled = await self.cancel(expense["payable_id"])
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual((await result())["expenses"], "0")
        self.assertEqual((await result("2026-10"))["status"], "NO_ACTIVITY")

    async def test_company_scope_permissions_and_negative_result(self):
        base = self.path().removesuffix("/payables")
        headers = self.headers[self.owner.id]
        response = await self.client.post(base + "/expenses",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json=dict(description="Aluguel", category="ALUGUEL", supplier="Fornecedor",
                      competence="2026-11-01", issue_date="2026-11-01", amount="350.55"))
        self.assertEqual(response.status_code, 201, response.text)
        report = await self.client.get(base + "/results?month=2026-11", headers=headers)
        self.assertEqual(report.status_code, 200, report.text)
        self.assertEqual(report.json()["result"], "-350.55")
        self.assertEqual(report.json()["status"], "LOSS")
        foreign = self.path(company=self.b).removesuffix("/payables")
        report = await self.client.get(foreign + "/results?month=2026-11", headers=headers)
        self.assertEqual(report.status_code, 200, report.text)
        self.assertEqual(report.json()["expense_count"], 0)
        denied = await self.client.get(base + "/results?month=2026-11", headers=self.headers[self.member.id])
        self.assertEqual(denied.status_code, 404, denied.text)
        malformed = await self.client.get(base + "/results?month=2026-13", headers=headers)
        self.assertEqual(malformed.status_code, 422)
