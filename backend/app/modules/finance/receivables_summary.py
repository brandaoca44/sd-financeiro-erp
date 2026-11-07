"""Posição de contas a receber em um único snapshot autorizado."""
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, case, func, select, text, true
from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.modules.finance.billing import Receipt, ServiceBilling
from app.modules.finance.movements import PayableMovementService
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Company

router = APIRouter(prefix='/organizations/{organization_id}/companies/{company_id}/receivables-summary', tags=['Contas a receber'])

class ReceivableSummary(BaseModel):
    as_of: date
    month: date
    upcoming_days: int = 7
    outstanding_amount: Decimal
    outstanding_count: int
    overdue_amount: Decimal
    overdue_count: int
    due_today_amount: Decimal
    due_today_count: int
    upcoming_amount: Decimal
    upcoming_count: int
    received_amount: Decimal
    received_count: int


async def summarize(session, organization_id, company_id, actor, month):
    today = PayableMovementService._today()
    start = date.fromisoformat(month + '-01') if month else today.replace(day=1)
    # Inclusive upper bound also handles December 9999 without overflow.
    import calendar
    end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
    company = select(Company.id).where(Company.id == company_id,
        CompanyAccessPolicy(session).operation_visibility(actor, organization_id, PermissionKey.BILLING_READ)).cte('receivable_company')
    bills = select(ServiceBilling.id, ServiceBilling.amount, ServiceBilling.due_date).join(
        company, company.c.id == ServiceBilling.company_id).where(
        ServiceBilling.organization_id == organization_id, ServiceBilling.company_id == company_id,
        ServiceBilling.due_date.is_not(None)).cte('receivable_bills')
    receipts = select(Receipt.billing_id, Receipt.amount, Receipt.received_on).join(bills,
        bills.c.id == Receipt.billing_id).where(Receipt.organization_id == organization_id,
        Receipt.company_id == company_id, Receipt.reversed.is_(False)).cte('valid_receipts')
    totals = select(receipts.c.billing_id, func.sum(receipts.c.amount).label('received')).group_by(
        receipts.c.billing_id).cte('receipt_totals')
    balances = select(bills, (bills.c.amount - func.coalesce(totals.c.received, 0)).label('outstanding')).outerjoin(
        totals, totals.c.billing_id == bills.c.id).cte('receivable_balances')
    b = balances.c
    def total(value, condition=true()):
        return func.coalesce(func.sum(case((condition, value), else_=0)), 0)
    open_ = b.outstanding > 0
    metrics = select(
        total(b.outstanding).label('outstanding_amount'), total(1, open_).label('outstanding_count'),
        total(b.outstanding, b.due_date < today).label('overdue_amount'), total(1, and_(open_, b.due_date < today)).label('overdue_count'),
        total(b.outstanding, b.due_date == today).label('due_today_amount'), total(1, and_(open_, b.due_date == today)).label('due_today_count'),
        total(b.outstanding, and_(b.due_date > today, b.due_date <= today + timedelta(days=7))).label('upcoming_amount'),
        total(1, and_(open_, b.due_date > today, b.due_date <= today + timedelta(days=7))).label('upcoming_count'),
        total(1, (b.outstanding < 0) | (b.outstanding > b.amount)).label('invalid'),
    ).select_from(balances).cte('receivable_metrics')
    monthly = select(func.coalesce(func.sum(receipts.c.amount), 0).label('received_amount'),
        func.count().label('received_count')).where(receipts.c.received_on.between(start, end)).cte('monthly_receipts')
    await session.execute(text("SET LOCAL statement_timeout = '5s'"))
    row = (await session.execute(select(*metrics.c, *monthly.c).select_from(company)
        .join(metrics, true()).join(monthly, true()))).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, 'Indicadores de recebimentos indisponíveis.')
    if row['invalid']:
        raise HTTPException(409, 'Os registros de recebimento precisam de revisão.')
    return ReceivableSummary(as_of=today, month=start, **{key:value for key,value in row.items() if key != 'invalid'})


@router.get('', response_model=ReceivableSummary)
async def receivables_summary(organization_id: UUID, company_id: UUID, request: Request,
    month: Annotated[str | None, Query(pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$')] = None,
    current=Depends(get_current_session), token=Depends(get_session_token)):
    if month is not None:
        try: date.fromisoformat(month + '-01')
        except ValueError: raise HTTPException(422, 'Mês inválido.') from None
    async with request.app.state.session_factory() as session:
        result = await summarize(session, organization_id, company_id, current.user_id, month)
    await record_authorized_activity(request, token)
    return result
