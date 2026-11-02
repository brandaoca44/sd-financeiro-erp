"""Contratos exatos, FKs de escopo, atomicidade e migration financeira."""

import asyncio
from datetime import date, datetime
from decimal import Decimal
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from database_support import DatabaseTestCase
from app.modules.finance.models import Payable, PayableChange, PayableMovement
from app.modules.finance.repository import PayableRepository
from app.modules.finance.schemas import PayableCreate
from app.modules.identity.models import User, OrganizationMembership
from app.modules.organizations.models import Organization, Company


def data(**changes):
    return PayableCreate(**(dict(description="Despesa sintética", amount="123.45", issue_date="2026-11-01", due_date="2026-11-10") | changes))


class PayableContractTests(unittest.TestCase):
    def test_amount_decimal_exact_and_maximum(self):
        for amount in ("0.01", "0.10", "123.45", "9999999999999999.99", Decimal("3.20")):
            self.assertEqual(data(amount=amount).amount, Decimal(amount))
        self.assertEqual(json.loads(data(amount="0.10").model_dump_json())["amount"], "0.10")

    def test_float_boolean_integer_nonfinite_and_precision_are_rejected(self):
        for amount in (0.1, True, 2, "0", "-1", "1.001", "1.000", "1e2", "NaN", "Infinity", "10000000000000000", "1,25", " 1.25", Decimal("NaN"), Decimal("1.001")):
            with self.subTest(amount=repr(amount)), self.assertRaises(ValidationError):
                data(amount=amount)

    def test_dates_are_calendar_dates_and_ordered(self):
        self.assertEqual(data().issue_date, date(2026, 11, 1))
        for changes in ({"issue_date": "2026-02-30"}, {"due_date": "2026-10-31"},
                        {"issue_date": datetime(2026, 11, 1)}, {"due_date": "20261110"}, {"issue_date": 123}):
            with self.assertRaises(ValidationError):
                data(**changes)

    def test_client_cannot_choose_scope_actor_currency_status_or_revision(self):
        for extra in ({"organization_id": uuid4()}, {"company_id": uuid4()}, {"created_by_user_id": uuid4()}, {"currency": "USD"}, {"status": "PAID"}, {"revision": 10}):
            with self.assertRaises(ValidationError):
                data(**extra)

    def test_description_limits_and_errors_do_not_reflect_input(self):
        self.assertEqual(data(description="  Despesa  ").description, "Despesa")
        for description in (" ", "private-description" * 50):
            with self.assertRaises(ValidationError) as error:
                data(description=description)
            self.assertNotIn("private-description", str(error.exception))


class PayablePersistenceTests(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.org = Organization(name="Tenant sintético")
        self.other_org = Organization(name="Outro tenant")
        self.actor = User(name="Pessoa", email=uuid4().hex + "@example.invalid", status="ACTIVE")
        self.session.add_all([self.org, self.other_org, self.actor])
        await self.session.flush()
        self.company = Company(organization_id=self.org.id, legal_name="Empresa", tax_id="11222333000181")
        self.sibling = Company(organization_id=self.org.id, legal_name="Outra empresa", tax_id="12ABC34501DE35")
        self.foreign = Company(organization_id=self.other_org.id, legal_name="Outro tenant", tax_id="11222333000181")
        self.session.add_all([self.company, self.sibling, self.foreign,
            OrganizationMembership(user_id=self.actor.id, organization_id=self.org.id, status="ACTIVE")])
        await self.session.flush()
        self.repo = PayableRepository(self.session)

    async def title(self, **changes):
        return await self.repo.create(self.org.id, self.company.id, self.actor.id, data(**changes))

    def movement(self, title, **changes):
        values = dict(organization_id=self.org.id, company_id=self.company.id, payable_id=title.id,
                      kind="PAYMENT", amount=Decimal("1.25"), occurred_on=date(2026, 11, 2), actor_user_id=self.actor.id)
        return PayableMovement(**(values | changes))

    async def test_create_and_minimal_audit_are_in_same_transaction(self):
        title = await self.title()
        self.assertEqual(title.amount, Decimal("123.45"))
        self.assertEqual((title.currency, title.status, title.revision), ("BRL", "OPEN", 1))
        audit = await self.session.scalar(select(PayableChange).where(PayableChange.payable_id == title.id))
        self.assertEqual(audit.after_state["amount"], "123.45")
        self.assertNotIn("Despesa", json.dumps(audit.after_state))
        title_id = title.id
        await self.session.rollback()
        self.assertIsNone(await self.session.get(Payable, title_id))

    async def test_get_and_list_require_both_scope_identifiers(self):
        title = await self.title()
        for org, company in ((self.org.id, self.sibling.id), (self.other_org.id, self.company.id), (self.other_org.id, self.foreign.id)):
            self.assertIsNone(await self.repo.get(org, company, title.id))
            self.assertEqual(await self.repo.list(org, company), [])
        self.assertEqual((await self.repo.list(self.org.id, self.company.id))[0].id, title.id)
        self.assertEqual(await self.repo.list(self.org.id, self.company.id, after_id=title.id), [])
        for limit in (True, 0, 101):
            with self.assertRaises(ValueError):
                await self.repo.list(self.org.id, self.company.id, limit=limit)

    async def test_sql_rejects_rounding_nonfinite_values_and_overflow(self):
        title = await self.title()
        for amount in ("0", "-1", "1.001", "1.000", "NaN", "Infinity", "10000000000000000"):
            with self.subTest(amount=amount), self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    await self.session.execute(text("UPDATE payables SET amount=CAST(:value AS numeric) WHERE id=:id"), {"value": amount, "id": title.id})
        self.assertEqual((await self.repo.get(self.org.id, self.company.id, title.id)).amount, Decimal("123.45"))

    async def test_database_rejects_forged_company_actor_dates_and_status(self):
        title = await self.title()
        statements = (("organization_id=:value", self.other_org.id), ("company_id=:value", self.foreign.id),
                      ("created_by_user_id=:value", uuid4()), ("revision=:value", 0), ("currency=:value", "USD"),
                      ("status=:value", "PAID"), ("description=:value", " "), ("due_date=:value", date(2026, 10, 1)))
        for expression, value in statements:
            with self.subTest(expression=expression), self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    await self.session.execute(text(f"UPDATE payables SET {expression} WHERE id=:id"), {"value": value, "id": title.id})

    async def test_movements_keep_title_scope_and_one_reversal(self):
        title = await self.title()
        payment = self.movement(title)
        self.session.add(payment)
        await self.session.flush()
        for changes in ({"company_id": self.sibling.id}, {"organization_id": self.other_org.id},
                        {"kind": "UNKNOWN"}, {"kind": "REVERSAL"}, {"amount": Decimal("1.001")}):
            with self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    self.session.add(self.movement(title, **changes))
                    await self.session.flush()
        reversal = self.movement(title, kind="REVERSAL", reverses_id=payment.id)
        self.session.add(reversal)
        await self.session.flush()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(self.movement(title, kind="REVERSAL", reverses_id=payment.id))
                await self.session.flush()

    async def test_reversal_cannot_reference_payment_of_another_title(self):
        first, second = await self.title(), await self.title()
        payment = self.movement(first)
        self.session.add(payment)
        await self.session.flush()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(self.movement(second, kind="REVERSAL", reverses_id=payment.id))
                await self.session.flush()

    async def test_history_prevents_deletion_of_title(self):
        title = await self.title()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                await self.session.delete(title)
                await self.session.flush()

    async def test_audit_failure_does_not_commit_title(self):
        await self.session.commit()
        original = self.session.flush
        calls = 0
        async def failing_flush(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Falha sintética no histórico")
            return await original(*args, **kwargs)
        with self.assertRaises(RuntimeError):
            async with self.session.begin():
                with patch.object(self.session, "flush", side_effect=failing_flush):
                    await self.title()
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(Payable)), 0)


class PayableMigrationTests(DatabaseTestCase):
    async def test_empty_roundtrip_schema_check_and_populated_downgrade_block(self):
        await self.session.close()
        await self.engine.dispose()
        await asyncio.to_thread(self.run_migration, "downgrade", "e96b2130ad74")
        await asyncio.to_thread(self.run_migration, "upgrade", "head")
        await asyncio.to_thread(self.run_migration, "check")
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(Payable)), 0)
        org = Organization(name="Tenant")
        actor = User(name="Pessoa", email=uuid4().hex + "@example.invalid")
        self.session.add_all([org, actor])
        await self.session.flush()
        company = Company(organization_id=org.id, legal_name="Empresa", tax_id="11222333000181")
        self.session.add_all([company, OrganizationMembership(user_id=actor.id, organization_id=org.id)])
        await self.session.flush()
        await PayableRepository(self.session).create(org.id, company.id, actor.id, data())
        await self.session.commit()
        await self.session.close()
        await self.engine.dispose()
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.run_migration, "downgrade", "e96b2130ad74")
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(Payable)), 1)
