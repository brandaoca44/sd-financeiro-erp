"""Resumo exato em um snapshot SQL; autorização antecede qualquer agregação."""

from datetime import timedelta

from sqlalchemy import and_, case, cast, func, literal, or_, select, String, text, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased

from app.modules.finance.models import Payable, PayableMovement
from app.modules.finance.movements import PayableMovementService
from app.modules.finance.schemas import CurrentPayables, PeriodPayables, PayablesDay, PayablesSummary
from app.modules.finance.service import PayableService, PayableConflictError
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Company


class PayableSummaryService(PayableService):
    @staticmethod
    def _today():
        return PayableMovementService._today()

    async def summary(self, organization_id, company_id, actor_id, period_start, period_end, *, upcoming_days=7):
        if period_end < period_start or (period_end-period_start).days > 365:
            raise ValueError("Intervalo limitado a 366 dias inclusivos.")
        if type(upcoming_days) is not int or not 1 <= upcoming_days <= 90:
            raise ValueError("Janela de vencimentos inválida.")
        today = self._today()
        horizon = today + timedelta(days=upcoming_days)
        company = select(Company.id).where(Company.id == company_id,
            CompanyAccessPolicy(self.session).financial_visibility(actor_id, organization_id, PermissionKey.PAYABLES_READ)).cte("authorized_company")
        titles = select(Payable.id, Payable.amount, Payable.issue_date, Payable.due_date, Payable.status).join(
            company, company.c.id == Payable.company_id).where(Payable.organization_id == organization_id,
            Payable.company_id == company_id).cte("authorized_titles")
        source = aliased(PayableMovement)
        invalid_reversal = and_(PayableMovement.kind == "REVERSAL", or_(source.kind != "PAYMENT",
            source.amount != PayableMovement.amount, source.occurred_on > PayableMovement.occurred_on))
        movements = select(PayableMovement.payable_id, PayableMovement.amount, PayableMovement.kind,
            PayableMovement.occurred_on,
            case((or_(PayableMovement.occurred_on < titles.c.issue_date, PayableMovement.occurred_on > today,
                      invalid_reversal), 1), else_=0).label("invalid")
        ).select_from(PayableMovement).join(titles, titles.c.id == PayableMovement.payable_id).outerjoin(source, and_(
            source.id == PayableMovement.reverses_id, source.organization_id == organization_id,
            source.company_id == company_id, source.payable_id == PayableMovement.payable_id)
        ).where(PayableMovement.organization_id == organization_id, PayableMovement.company_id == company_id).cte("authorized_movements")
        net = case((movements.c.kind == "PAYMENT", movements.c.amount), else_=-movements.c.amount)
        by_title = select(movements.c.payable_id, func.sum(net).label("paid"),
            func.sum(movements.c.invalid).label("invalid")).group_by(movements.c.payable_id).cte("movement_totals")
        balances = select(titles, func.coalesce(by_title.c.paid, 0).label("paid"),
            func.coalesce(by_title.c.invalid, 0).label("invalid")).outerjoin(by_title,
                by_title.c.payable_id == titles.c.id).cte("title_balances")
        b = balances.c
        active = b.status == "OPEN"
        remaining = b.amount-b.paid
        in_period = b.due_date.between(period_start, period_end)

        def total(value, condition=true()):
            return func.coalesce(func.sum(case((condition, value), else_=0)), 0)

        metrics = select(
            total(1, active).label("active_title_count"), total(1, b.status == "CANCELLED").label("cancelled_title_count"),
            total(1, and_(active, b.paid == 0)).label("unpaid_title_count"),
            total(1, and_(active, b.paid > 0, b.paid < b.amount)).label("partial_title_count"),
            total(1, and_(active, b.paid == b.amount)).label("paid_title_count"),
            total(b.amount, active).label("original_amount"), total(b.paid, active).label("paid_amount"),
            total(remaining, active).label("outstanding_amount"),
            total(remaining, and_(active, b.due_date < today)).label("overdue_amount"),
            total(remaining, and_(active, b.due_date == today)).label("due_today_amount"),
            total(remaining, and_(active, b.due_date > today, b.due_date <= horizon)).label("upcoming_amount"),
            total(remaining, and_(active, b.due_date > horizon)).label("later_amount"),
            total(b.amount, and_(active, in_period)).label("original_due_amount"),
            total(remaining, and_(active, in_period)).label("outstanding_due_amount"),
            total(remaining, and_(active, in_period, b.due_date < today)).label("overdue_due_amount"),
            total(1, or_(b.invalid > 0, b.paid < 0, b.paid > b.amount,
                         and_(b.status == "CANCELLED", b.paid != 0))).label("invalid_count")
        ).select_from(balances).cte("summary_metrics")
        period_movements = select(movements).where(movements.c.occurred_on.between(period_start, period_end)).cte("period_movements")
        pm = period_movements.c
        payments = total(pm.amount, pm.kind == "PAYMENT")
        reversals = total(pm.amount, pm.kind == "REVERSAL")
        flows = select(payments.label("payments_amount"), reversals.label("reversals_amount"),
            (payments-reversals).label("net_paid_amount")).select_from(period_movements).cte("period_flows")
        daily_flows = select(pm.occurred_on.label("day"), payments.label("payments_amount"),
            reversals.label("reversals_amount"), (payments-reversals).label("net_paid_amount")
        ).group_by(pm.occurred_on).cte("daily_flows")
        daily_due = select(b.due_date.label("day"), total(b.amount, active).label("original_due_amount"),
            total(remaining, active).label("outstanding_due_amount")
        ).where(in_period).group_by(b.due_date).cte("daily_due")

        def days_json(cte, fields):
            # Numeric em JSON vira texto antes de decodificar: nenhum float intermediário.
            obj = func.jsonb_build_object("day", cast(cte.c.day, String),
                *[item for name in fields for item in (name, cast(cte.c[name], String))])
            return select(func.coalesce(func.jsonb_agg(obj), cast(literal("[]"), JSONB))).select_from(cte).scalar_subquery()

        query = select(*metrics.c, *flows.c,
            days_json(daily_flows, ("payments_amount", "reversals_amount", "net_paid_amount")).label("flows_days"),
            days_json(daily_due, ("original_due_amount", "outstanding_due_amount")).label("due_days")
        ).select_from(company).join(metrics, true()).join(flows, true())
        await self.session.execute(text("SET LOCAL statement_timeout = '5s'"))
        row = (await self.session.execute(query)).mappings().one_or_none()
        if row is None:
            self.deny()
        if row["invalid_count"]:
            raise PayableConflictError()
        current = CurrentPayables.model_validate(row)
        period = PeriodPayables.model_validate(row)
        day_values = {value["day"]:value.copy() for value in row["due_days"]}
        for value in row["flows_days"]:
            day_values.setdefault(value["day"], {}).update(value)
        days = []
        day = period_start
        for _ in range((period_end-period_start).days+1):
            values = {"original_due_amount":"0.00", "outstanding_due_amount":"0.00", "payments_amount":"0.00",
                      "reversals_amount":"0.00", "net_paid_amount":"0.00", **day_values.get(day.isoformat(), {})}
            days.append(PayablesDay.model_validate({**values, "day":day}))
            if day < period_end:
                day += timedelta(days=1)
        return PayablesSummary(company_id=company_id, as_of=today, period_start=period_start,
            period_end=period_end, upcoming_days=upcoming_days, current=current, period=period, days=days)
