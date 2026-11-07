"""Alertas calculados sobre saldos atuais, sem prolongar sessões por polling."""
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import Numeric, and_, case, cast, func, literal, select, union_all

from app.api.v1.auth import get_current_session
from app.modules.finance.models import Payable, PayableMovement
from app.modules.finance.movements import PayableMovementService
from app.modules.finance.recurring import ExpenseOccurrence
from app.modules.finance.expenses import ExpenseRule
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Company

AlertKind = Literal["OVERDUE", "TODAY", "UPCOMING", "REVIEW"]


class FinancialAlert(BaseModel):
    id: UUID
    kind: AlertKind
    description: str
    due_date: date
    amount: Decimal | None


class FinancialAlerts(BaseModel):
    as_of: date
    total: int
    overdue: int
    today: int
    upcoming: int
    review: int
    items: list[FinancialAlert]


router = APIRouter(prefix="/organizations/{organization_id}/companies/{company_id}/alerts", tags=["Alertas"])


@router.get("", response_model=FinancialAlerts)
async def financial_alerts(organization_id: UUID, company_id: UUID, request: Request, response: Response,
                           current=Depends(get_current_session)):
    today = PayableMovementService._today()
    horizon = today + timedelta(days=7)
    async with request.app.state.session_factory() as session:
        policy = CompanyAccessPolicy(session)
        visible = select(Company.id).where(
            Company.organization_id == organization_id, Company.id == company_id,
            policy.financial_visibility(current.user_id, organization_id, PermissionKey.PAYABLES_READ),
        ).exists()
        if not await session.scalar(select(visible)):
            raise HTTPException(404, "Alertas indisponíveis para este acesso.")
        movements = select(
            PayableMovement.payable_id,
            func.sum(case((PayableMovement.kind == "PAYMENT", PayableMovement.amount),
                          else_=-PayableMovement.amount)).label("paid"),
        ).where(PayableMovement.organization_id == organization_id,
                PayableMovement.company_id == company_id, visible).group_by(PayableMovement.payable_id).cte("alert_movements")
        outstanding = Payable.amount - func.coalesce(movements.c.paid, 0)
        titles = select(
            Payable.id,
            case((Payable.due_date < today, "OVERDUE"), (Payable.due_date == today, "TODAY"),
                 else_="UPCOMING").label("kind"),
            Payable.description, Payable.due_date, outstanding.label("amount"),
            case((Payable.due_date < today, 0), (Payable.due_date == today, 1), else_=3).label("priority"),
        ).outerjoin(movements, movements.c.payable_id == Payable.id).where(
            Payable.organization_id == organization_id, Payable.company_id == company_id, visible,
            Payable.status == "OPEN", outstanding > 0, Payable.due_date <= horizon,
        )
        drafts = select(
            ExpenseOccurrence.id, literal("REVIEW").label("kind"), ExpenseOccurrence.description,
            ExpenseOccurrence.due_date, cast(literal(None), Numeric).label("amount"), literal(2).label("priority"),
        ).join(ExpenseRule, and_(
            ExpenseRule.organization_id == ExpenseOccurrence.organization_id,
            ExpenseRule.company_id == ExpenseOccurrence.company_id, ExpenseRule.id == ExpenseOccurrence.rule_id,
        )).where(
            ExpenseOccurrence.organization_id == organization_id, ExpenseOccurrence.company_id == company_id, visible,
            ExpenseOccurrence.expense_id.is_(None), ExpenseRule.cancelled.is_(False),
        )
        alerts = union_all(titles, drafts).cte("financial_alerts")
        query = select(
            alerts, func.count().over().label("total"),
            *[func.count().filter(alerts.c.kind == key).over().label(label) for key, label in (
                ("OVERDUE", "overdue"), ("TODAY", "today"), ("UPCOMING", "upcoming"), ("REVIEW", "review"))],
        ).order_by(alerts.c.priority, alerts.c.due_date, alerts.c.id).limit(200)
        rows = (await session.execute(query)).mappings().all()
        counts = {key: rows[0][key] if rows else 0 for key in ("total", "overdue", "today", "upcoming", "review")}
        result = FinancialAlerts(as_of=today, items=[FinancialAlert.model_validate(row) for row in rows], **counts)
    response.headers["Cache-Control"] = "no-store"
    return result
