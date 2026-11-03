"""Resumo financeiro sem dupla contagem, snapshot único e autorização no SQL."""

import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import event, update

from test_payable_http import PayableHttpFixture
from app.modules.finance.models import Payable, PayableMovement
from app.modules.finance.movements import PayableMovementService
from app.modules.finance.summary import PayableSummaryService


class PayableSummaryHttpTests(PayableHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        calendar = patch.object(PayableMovementService,"_today",return_value=date(2026,11,5))
        calendar.start()
        self.addCleanup(calendar.stop)

    async def report(self, *, actor=None, company=None, org=None, **params):
        return await self.client.get(self.path(company=company,org=org)+"/summary",headers=self.headers[actor or self.owner.id],
            params={"period_start":"2026-11-01","period_end":"2026-11-30",**params})

    async def seed(self, *, due="2026-11-10", amount="100.00", status="OPEN", company=None, movements=()):
        company = company or self.a
        async with self.factory() as writer, writer.begin():
            title = Payable(organization_id=company.organization_id,company_id=company.id,description="Texto financeiro privado",
                amount=Decimal(amount),issue_date=date(2026,10,1),due_date=date.fromisoformat(due),
                status=status,created_by_user_id=self.owner.id)
            writer.add(title)
            await writer.flush()
            source_id = None
            for kind,value,day in movements:
                movement = PayableMovement(organization_id=company.organization_id,company_id=company.id,payable_id=title.id,
                    actor_user_id=self.owner.id,kind=kind,amount=Decimal(value),occurred_on=date.fromisoformat(day),
                    reverses_id=source_id if kind=="REVERSAL" else None,
                    reversal_reason="Motivo financeiro privado" if kind=="REVERSAL" else None)
                writer.add(movement)
                await writer.flush()
                if kind=="PAYMENT":
                    source_id=movement.id
            return title.id

    async def test_empty_company_returns_exact_zero_and_complete_days(self):
        response = await self.report()
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual(result["current"]["outstanding_amount"],"0.00")
        self.assertEqual(result["period"]["net_paid_amount"],"0.00")
        self.assertEqual(len(result["days"]),30)
        self.assertEqual(result["as_of"],"2026-11-05")
        self.assertEqual(result["balance_basis"],"CURRENT")

    async def test_multiple_movements_do_not_multiply_original_or_outstanding(self):
        await self.seed(movements=(("PAYMENT","10.00","2026-11-01"),("PAYMENT","20.00","2026-11-02"),("REVERSAL","20.00","2026-11-03")))
        response=await self.report()
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual(result["current"]["original_amount"],"100.00")
        self.assertEqual(result["current"]["paid_amount"],"10.00")
        self.assertEqual(result["current"]["outstanding_amount"],"90.00")
        self.assertEqual(result["period"]["payments_amount"],"30.00")
        self.assertEqual(result["period"]["reversals_amount"],"20.00")
        self.assertEqual(result["period"]["net_paid_amount"],"10.00")

    async def test_overdue_today_upcoming_and_later_partition_current_balance(self):
        for due,value in (("2026-11-04","1.00"),("2026-11-05","2.00"),("2026-11-06","3.00"),("2026-11-12","4.00"),("2026-11-13","5.00")):
            await self.seed(due=due,amount=value)
        current=(await self.report()).json()["current"]
        self.assertEqual([current[k] for k in ("overdue_amount","due_today_amount","upcoming_amount","later_amount")], ["1.00","2.00","7.00","5.00"])
        self.assertEqual(current["outstanding_amount"],"15.00")
        self.assertEqual(current["unpaid_title_count"],5)
        window=(await self.report(upcoming_days=1)).json()["current"]
        self.assertEqual((window["upcoming_amount"],window["later_amount"]),("3.00","9.00"))

    async def test_due_period_and_payment_period_have_distinct_bases(self):
        await self.seed(due="2026-12-10",movements=(("PAYMENT","40.00","2026-11-02"),))
        await self.seed(due="2026-11-05",amount="50.00",movements=(("PAYMENT","10.00","2026-10-31"),))
        period=(await self.report()).json()["period"]
        self.assertEqual(period["original_due_amount"],"50.00")
        self.assertEqual(period["outstanding_due_amount"],"40.00")
        self.assertEqual(period["payments_amount"],"40.00")
        self.assertEqual(period["overdue_due_amount"],"0.00")

    async def test_reversal_of_previous_period_can_make_net_negative(self):
        await self.seed(movements=(("PAYMENT","70.00","2026-10-31"),("REVERSAL","70.00","2026-11-02")))
        period=(await self.report()).json()["period"]
        self.assertEqual((period["payments_amount"],period["reversals_amount"],period["net_paid_amount"]),("0.00","70.00","-70.00"))

    async def test_cancelled_titles_excluded_from_balance_but_preserve_period_flows(self):
        await self.seed(status="CANCELLED",movements=(("PAYMENT","20.00","2026-11-01"),("REVERSAL","20.00","2026-11-02")))
        result=(await self.report()).json()
        self.assertEqual((result["current"]["original_amount"],result["current"]["outstanding_amount"]),("0.00","0.00"))
        self.assertEqual(result["current"]["cancelled_title_count"],1)
        self.assertEqual(result["period"]["payments_amount"],"20.00")
        self.assertEqual(result["period"]["reversals_amount"],"20.00")

    async def test_paid_and_partial_title_counts_and_remaining_values(self):
        await self.seed(movements=(("PAYMENT","100.00","2026-11-01"),))
        await self.seed(movements=(("PAYMENT","40.00","2026-11-01"),))
        current=(await self.report()).json()["current"]
        self.assertEqual((current["paid_title_count"],current["partial_title_count"]),(1,1))
        self.assertEqual(current["outstanding_amount"],"60.00")

    async def test_daily_series_totals_match_period_and_have_no_sensitive_fields(self):
        await self.seed(due="2026-11-02",amount="0.30",movements=(("PAYMENT","0.10","2026-11-01"),("PAYMENT","0.20","2026-11-02")))
        response=await self.report()
        result=response.json()
        for field in ("payments_amount","reversals_amount","net_paid_amount","original_due_amount","outstanding_due_amount"):
            self.assertEqual(sum(Decimal(day[field]) for day in result["days"]),Decimal(result["period"][field]))
        self.assertEqual(result["days"][1]["payments_amount"],"0.20")
        for private in ("Texto financeiro privado","Motivo financeiro privado","actor_user_id","token","description"):
            self.assertNotIn(private,response.text)

    async def test_large_aggregates_exceed_individual_limit_without_float_loss(self):
        for _ in range(2):
            await self.seed(amount="9999999999999999.99")
        current=(await self.report()).json()["current"]
        self.assertEqual(current["outstanding_amount"],"19999999999999999.98")

    async def test_company_and_tenant_isolation_before_aggregation(self):
        await self.seed(amount="1.00")
        await self.seed(amount="999.99",company=self.b)
        await self.seed(amount="888.88",company=self.foreign)
        self.assertEqual((await self.report()).json()["current"]["outstanding_amount"],"1.00")
        self.assertEqual((await self.report(company=self.foreign,org=self.org.id)).status_code,404)

    async def test_only_financial_read_permits_summary_and_revoke_is_immediate(self):
        await self.seed()
        self.assertEqual((await self.report(actor=self.member.id)).status_code,404)
        for key in ("payables.manage","payables.settle","payables.reverse"):
            await self.grant(key)
        self.assertEqual((await self.report(actor=self.member.id)).status_code,404)
        await self.grant("payables.read")
        self.assertEqual((await self.report(actor=self.member.id)).status_code,200)
        await self.grant("payables.read",status="INACTIVE",revision=1)
        self.assertEqual((await self.report(actor=self.member.id)).status_code,404)

    async def test_platform_flag_and_inactive_company_do_not_grant_access(self):
        self.assertEqual((await self.report(actor=self.operator.id)).status_code,404)
        self.assertEqual((await self._update_company(status="INACTIVE",revision=1)).status_code,200)
        self.assertEqual((await self.report()).status_code,404)

    async def test_invalid_ranges_historical_override_and_duplicates_rejected(self):
        for params in ({"period_start":"2026-12-01","period_end":"2026-11-01"},
                       {"period_start":"2025-01-01","period_end":"2026-01-02"},
                       {"period_start":"20261101"}, {"period_end":"2026-02-30"},
                       {"upcoming_days":0},{"upcoming_days":91},{"as_of":"2020-01-01"}):
            self.assertEqual((await self.report(**params)).status_code,422)
        response=await self.client.get(self.path()+"/summary?period_start=2026-11-01&period_start=2026-11-02&period_end=2026-11-30",headers=self.headers[self.owner.id])
        self.assertEqual(response.status_code,422)

    async def test_inclusive_endpoints_single_day_and_leap_year(self):
        await self.seed(due="2026-11-02",movements=(("PAYMENT","10.00","2026-11-02"),))
        result=(await self.report(period_start="2026-11-02",period_end="2026-11-02")).json()
        self.assertEqual(len(result["days"]),1)
        self.assertEqual(result["period"]["payments_amount"],"10.00")
        leap=await self.report(period_start="2024-01-01",period_end="2024-12-31")
        self.assertEqual(leap.status_code,200)
        self.assertEqual(len(leap.json()["days"]),366)
        self.assertEqual(leap.json()["current"]["outstanding_amount"],"90.00")

    async def test_invalid_ledger_is_not_silently_totalled(self):
        title=await self.seed(movements=(("PAYMENT","100.01","2026-11-02"),))
        response=await self.report()
        self.assertEqual(response.status_code,409)
        self.assertNotIn("100.01",response.text)

    async def test_future_movements_and_invalid_reversal_amount_are_detected(self):
        await self.seed(movements=(("PAYMENT","50.00","2026-11-06"),))
        self.assertEqual((await self.report()).status_code,409)
        # Outro escopo continua utilizável, sem compartilhar o erro ou os dados.
        await self.seed(company=self.b,movements=(("PAYMENT","50.00","2026-11-01"),("REVERSAL","20.00","2026-11-02")))
        self.assertEqual((await self.report(company=self.b)).status_code,409)

    async def test_one_sql_data_snapshot_and_no_financial_writes(self):
        await self.seed()
        statements=[]
        def capture(connection,cursor,statement,parameters,context,executemany):
            statements.append(statement)
        event.listen(self.engine.sync_engine,"before_cursor_execute",capture)
        try:
            async with self.factory() as reader:
                result=await PayableSummaryService(reader).summary(self.org.id,self.a.id,self.owner.id,date(2026,11,1),date(2026,11,30))
            self.assertEqual(result.current.outstanding_amount,Decimal("100.00"))
        finally:
            event.remove(self.engine.sync_engine,"before_cursor_execute",capture)
        self.assertEqual(len([sql for sql in statements if sql.lstrip().startswith("WITH")]),1)
        self.assertFalse(any(sql.lstrip().startswith(("UPDATE","INSERT","DELETE")) for sql in statements))

    async def test_no_session_https_and_safe_headers(self):
        path=self.path()+"/summary?period_start=2026-11-01&period_end=2026-11-30"
        self.assertEqual((await self.client.get(path)).status_code,401)
        response=await self.report()
        self.assertEqual(response.headers["cache-control"],"no-store")
        self.assertIn("x-request-id",response.headers)
        self.app.state.settings=self.config.model_copy(update={"app_environment":"production"})
        self.assertEqual((await self.report()).status_code,503)
