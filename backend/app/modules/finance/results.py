"""Resultado gerencial parcial por competência, em um snapshot autorizado."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.modules.finance.billing import ServiceBilling, owner_condition
from app.modules.finance.expenses import Expense
from app.modules.finance.models import Payable
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Company


class CompetenceResult(BaseModel):
    month: date
    revenue: Decimal
    expenses: Decimal
    result: Decimal
    status: Literal["PROFIT", "LOSS", "BREAK_EVEN", "NO_ACTIVITY"]
    revenue_count: int
    expense_count: int
    unassigned_expenses: int
    unlinked_payables: int
    partial: Literal[True] = True


router = APIRouter(prefix="/organizations/{organization_id}/companies/{company_id}/results", tags=["Resultado"])


@router.get("", response_model=CompetenceResult)
async def competence_result(organization_id: UUID, company_id: UUID, request: Request,
                            month: Annotated[str, Query(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")],
                            current=Depends(get_current_session), token=Depends(get_session_token)):
    try:
        start = date.fromisoformat(month + "-01")
    except ValueError:
        raise HTTPException(422, "Competência inválida.") from None

    async with request.app.state.session_factory() as session:
        authorized = select(Company.id).where(
            Company.id == company_id, Company.organization_id == organization_id,
            owner_condition(current.user_id, organization_id),
            CompanyAccessPolicy(session).financial_visibility(current.user_id, organization_id, PermissionKey.PAYABLES_READ),
        ).cte("result_company")

        revenue = select(ServiceBilling.amount).join(
            authorized, authorized.c.id == ServiceBilling.company_id,
        ).where(ServiceBilling.organization_id == organization_id,
                ServiceBilling.company_id == company_id, ServiceBilling.competence == start).cte("result_revenue")

        expenses = select(Expense.id, Expense.competence,
                          func.coalesce(Payable.amount, Expense.amount).label("amount")).join(
            authorized, authorized.c.id == Expense.company_id,
        ).outerjoin(Payable, and_(
            Payable.organization_id == Expense.organization_id, Payable.company_id == Expense.company_id,
            Payable.id == Expense.payable_id,
        )).where(Expense.organization_id == organization_id, Expense.company_id == company_id, Expense.status == "OPEN",
                 or_(Expense.payable_id.is_(None), Payable.status == "OPEN")).cte("result_expenses")

        linked_expense = select(Expense.id).where(
            Expense.organization_id == organization_id, Expense.company_id == company_id,
            Expense.payable_id == Payable.id,
        ).exists()

        statement = select(
            select(func.coalesce(func.sum(revenue.c.amount), 0)).scalar_subquery().label("revenue"),
            select(func.count()).select_from(revenue).scalar_subquery().label("revenue_count"),
            select(func.coalesce(func.sum(expenses.c.amount), 0)).where(
                expenses.c.competence == start).scalar_subquery().label("expenses"),
            select(func.count()).select_from(expenses).where(
                expenses.c.competence == start).scalar_subquery().label("expense_count"),
            select(func.count()).select_from(expenses).where(
                expenses.c.competence.is_(None)).scalar_subquery().label("unassigned_expenses"),
            select(func.count()).select_from(Payable).where(
                Payable.organization_id == organization_id, Payable.company_id == company_id,
                Payable.status == "OPEN", ~linked_expense).scalar_subquery().label("unlinked_payables"),
        ).select_from(authorized)

        row = (await session.execute(statement)).mappings().one_or_none()
        if row is None:
            raise HTTPException(404, "Resultado indisponível para este acesso.")
        balance = row["revenue"] - row["expenses"]
        status = "NO_ACTIVITY" if not row["revenue_count"] and not row["expense_count"] else (
            "PROFIT" if balance > 0 else "LOSS" if balance < 0 else "BREAK_EVEN"
        )
        result = CompetenceResult(month=start, result=balance, status=status, **row)
    await record_authorized_activity(request, token)
    return result
