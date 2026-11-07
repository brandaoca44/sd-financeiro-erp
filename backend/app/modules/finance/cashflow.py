"""Fluxo gerencial: movimentação válida e pendências por vencimento, sem saldo bancário presumido."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import and_, case, func, select, text, true, union_all
from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.modules.finance.billing import Receipt, ServiceBilling
from app.modules.finance.models import Payable, PayableMovement
from app.modules.finance.movements import PayableMovementService
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Company

router=APIRouter(prefix='/organizations/{organization_id}/companies/{company_id}/cashflow',tags=['Fluxo de caixa'])

class FlowAmounts(BaseModel):
    realized_in:Decimal
    realized_out:Decimal
    pending_in:Decimal
    pending_out:Decimal
    realized_net:Decimal
    projected_net:Decimal

class FlowDay(FlowAmounts):
    day:date
    cumulative_realized:Decimal
    cumulative_projected:Decimal

class Cashflow(BaseModel):
    as_of:date
    start:date
    end:date
    totals:FlowAmounts
    days:list[FlowDay]


async def cashflow_snapshot(session,organization_id,company_id,actor,start,end):
    policy=CompanyAccessPolicy(session)
    authorized=select(Company.id).where(Company.id==company_id,
        policy.operation_visibility(actor,organization_id,PermissionKey.BILLING_READ),
        policy.operation_visibility(actor,organization_id,PermissionKey.PAYABLES_READ)).cte('flow_company')
    bills=select(ServiceBilling.id,ServiceBilling.amount,ServiceBilling.due_date).join(authorized,
        authorized.c.id==ServiceBilling.company_id).where(ServiceBilling.organization_id==organization_id,
        ServiceBilling.company_id==company_id,ServiceBilling.due_date.is_not(None)).cte('flow_bills')
    receipts=select(Receipt.billing_id,Receipt.amount,Receipt.received_on).join(bills,bills.c.id==Receipt.billing_id).where(
        Receipt.organization_id==organization_id,Receipt.company_id==company_id,Receipt.reversed.is_(False)).cte('flow_receipts')
    received=select(receipts.c.billing_id,func.sum(receipts.c.amount).label('amount')).group_by(receipts.c.billing_id).cte('flow_received')
    incoming=select(bills.c.due_date.label('day'),(bills.c.amount-func.coalesce(received.c.amount,0)).label('balance')).outerjoin(
        received,received.c.billing_id==bills.c.id).cte('flow_incoming')
    titles=select(Payable.id,Payable.amount,Payable.due_date,Payable.status).join(authorized,
        authorized.c.id==Payable.company_id).where(Payable.organization_id==organization_id,
        Payable.company_id==company_id).cte('flow_titles')
    moves=select(PayableMovement.payable_id,PayableMovement.occurred_on,
        case((PayableMovement.kind=='PAYMENT',PayableMovement.amount),else_=-PayableMovement.amount).label('net')).join(
        titles,titles.c.id==PayableMovement.payable_id).where(PayableMovement.organization_id==organization_id,
        PayableMovement.company_id==company_id).cte('flow_moves')
    paid=select(moves.c.payable_id,func.sum(moves.c.net).label('amount')).group_by(moves.c.payable_id).cte('flow_paid')
    outgoing=select(titles.c.due_date.label('day'),titles.c.status,
        (titles.c.amount-func.coalesce(paid.c.amount,0)).label('balance'),
        func.coalesce(paid.c.amount,0).label('paid'),titles.c.amount).outerjoin(paid,paid.c.payable_id==titles.c.id).cte('flow_outgoing')
    from sqlalchemy import Numeric, cast, literal
    def rows(day,rin,rout,pin,pout,source):
        return select(day.label('day'),rin.label('realized_in'),rout.label('realized_out'),
            pin.label('pending_in'),pout.label('pending_out')).select_from(source).where(day.between(start,end))
    zero=cast(literal(0),Numeric)
    flows=union_all(
        rows(receipts.c.received_on,receipts.c.amount,zero,zero,zero,receipts),
        rows(moves.c.occurred_on,zero,moves.c.net,zero,zero,moves),
        rows(incoming.c.day,zero,zero,incoming.c.balance,zero,incoming),
        select(outgoing.c.day,zero,zero,zero,outgoing.c.balance).where(
            outgoing.c.status=='OPEN',outgoing.c.day.between(start,end)),
    ).subquery('flow_rows')
    daily=select(flows.c.day,*[func.sum(flows.c[key]).label(key) for key in
        ('realized_in','realized_out','pending_in','pending_out')]).group_by(flows.c.day).cte('flow_daily')
    invalid_in=select(incoming.c.day).where(incoming.c.balance<0).exists()
    invalid_out=select(outgoing.c.day).where((outgoing.c.balance<0)|(outgoing.c.balance>outgoing.c.amount)|
        and_(outgoing.c.status=='CANCELLED',outgoing.c.paid!=0)).exists()
    query=select(daily, (invalid_in|invalid_out).label('invalid')).select_from(authorized).outerjoin(daily,true()).order_by(daily.c.day)
    await session.execute(text("SET LOCAL statement_timeout = '5s'"))
    records=(await session.execute(query)).mappings().all()
    if not records:raise HTTPException(404,'Fluxo de caixa indisponível.')
    if any(row['invalid'] for row in records):raise HTTPException(409,'Os registros financeiros precisam de revisão.')
    by_day={row['day']:row for row in records if row['day'] is not None}
    amounts=('realized_in','realized_out','pending_in','pending_out')
    totals={key:Decimal('0.00') for key in amounts};days=[];realized=projected=Decimal('0.00')
    for offset in range((end-start).days+1):
        day=start+timedelta(days=offset);row=by_day.get(day,{})
        values={key:row.get(key,Decimal('0.00')) for key in amounts}
        net=values['realized_in']-values['realized_out'];projection=net+values['pending_in']-values['pending_out']
        realized+=net;projected+=projection
        for key in amounts:totals[key]+=values[key]
        days.append(FlowDay(day=day,realized_net=net,projected_net=projection,cumulative_realized=realized,
            cumulative_projected=projected,**values))
    return Cashflow(as_of=PayableMovementService._today(),start=start,end=end,
        totals=FlowAmounts(realized_net=realized,projected_net=projected,**totals),days=days)


@router.get('',response_model=Cashflow)
async def cashflow(organization_id:UUID,company_id:UUID,start:date,end:date,request:Request,
    current=Depends(get_current_session),token=Depends(get_session_token)):
    if end<start or (end-start).days>92:
        raise HTTPException(422,'Selecione um período de até 93 dias.')
    async with request.app.state.session_factory() as session:
        result=await cashflow_snapshot(session,organization_id,company_id,current.user_id,start,end)
    await record_authorized_activity(request,token)
    return result
