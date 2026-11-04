"""Vínculos de clientes no faturamento e isolamento por empresa."""
from uuid import uuid4

from test_payable_http import PayableHttpFixture


class CustomerBillingTests(PayableHttpFixture):
    async def test_customer_binding_replay_and_legacy_billing(self):
        base = self.path().removesuffix("/payables")
        headers = {**self.headers[self.owner.id], "Idempotency-Key": str(uuid4())}
        created = await self.client.post(base + "/customers", headers=headers, json={"name": "Cliente sintético"})
        self.assertEqual(created.status_code, 201, created.text)
        customer_id = created.json()["id"]
        replay = await self.client.post(base + "/customers", headers=headers, json={"name": "Cliente sintético"})
        self.assertEqual(replay.json(), created.json())
        customers = await self.client.get(base + "/customers", headers=headers)
        self.assertEqual(len(customers.json()), 1)

        data = dict(customer_id=customer_id, service="Consultoria", competence="2026-11-01",
                    issue_date="2026-11-01", due_date="2026-11-10", amount="200.00")
        headers["Idempotency-Key"] = str(uuid4())
        billing = await self.client.post(base + "/billing", headers=headers, json=data)
        self.assertEqual(billing.status_code, 201, billing.text)
        self.assertEqual(billing.json()["customer"], "Cliente sintético")
        self.assertEqual(billing.json()["customer_id"], customer_id)
        replay = await self.client.post(base + "/billing", headers=headers, json=data)
        self.assertEqual(replay.json(), billing.json())

        foreign = self.path(company=self.b).removesuffix("/payables")
        denied = await self.client.post(foreign + "/billing", headers=headers, json=data)
        self.assertEqual(denied.status_code, 404, denied.text)

        headers["Idempotency-Key"] = str(uuid4())
        legacy = {**data, "customer": "Cliente anterior"}
        legacy.pop("customer_id")
        response = await self.client.post(base + "/billing", headers=headers, json=legacy)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIsNone(response.json()["customer_id"])
