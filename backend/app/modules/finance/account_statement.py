"""Extrato gerencial por conta, com saldos exatos no mesmo snapshot autorizado."""
import base64
import json
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from pydantic import BaseModel
from sqlalchemy import String,case,cast,func,literal,select,true,tuple_,union_all
from app.api.v1.auth import get_current_session,get_session_token,record_authorized_activity
from app.modules.finance.accounts import FinancialAccount,visibility
from app.modules.finance.billing import Receipt,ServiceBilling
from app.modules.finance.models import Payable,PayableMovement
from app.modules.finance.movements import PayableMovementService
from app.modules.identity.permissions import PermissionKey

router=APIRouter(prefix='/organizations/{organization_id}/companies/{company_id}/financial-accounts',tags=['Extrato por conta'])
class StatementEntry(BaseModel):
    id:UUID
    source:Literal['PAYABLE','RECEIPT','RECEIPT_REVERSAL']
    reference_id:UUID
    day:date
    kind:Literal['PAYMENT','REVERSAL','RECEIVED','RECEIPT_REVERSAL']
    description:str
    amount:Decimal
    direction:Literal['IN','OUT']
    balance:Decimal
class Statement(BaseModel):
    account_id:UUID
    start:date
    end:date
    initial_date:date
    initial_balance:Decimal
    opening_balance:Decimal
    incoming:Decimal
    outgoing:Decimal
    closing_balance:Decimal
    items:list[StatementEntry]
    next_cursor:str|None


def cursor_value(value):
    try:
        day,source,identifier,reference=json.loads(base64.b64decode(value,altchars=b'-_',validate=True))
        if source not in {'PAYABLE','RECEIPT','RECEIPT_REVERSAL'}:raise ValueError()
        return date.fromisoformat(day),source,str(UUID(identifier)),str(UUID(reference))
    except (ValueError,TypeError,UnicodeError):
        raise HTTPException(422,'Cursor de extrato inválido.') from None


@router.get('/{account_id}/statement',response_model=Statement)
async def statement(organization_id:UUID,company_id:UUID,account_id:UUID,start:date,end:date,request:Request,
    cursor:str|None=Query(default=None,max_length=512),limit:int=Query(default=50,ge=1,le=100),
    current=Depends(get_current_session),token=Depends(get_session_token)):
    if end<start or (end-start).days>92 or end>PayableMovementService._today():
        raise HTTPException(422,'Selecione até 93 dias, sem datas futuras.')
    a=FinancialAccount
    async with request.app.state.session_factory() as session:
        account=select(a.id,a.opening_balance,a.opening_date).where(a.organization_id==organization_id,
            a.company_id==company_id,a.id==account_id,
            *[visibility(current.user_id,organization_id,company_id,key) for key in
              (PermissionKey.ACCOUNTS_READ,PermissionKey.PAYABLES_READ,PermissionKey.BILLING_READ)]).cte('statement_account')
        p=PayableMovement;r=Receipt
        payments=select(p.id,literal('PAYABLE').label('source'),p.payable_id.label('reference_id'),p.occurred_on.label('day'),
            p.kind,Payable.description,p.amount,case((p.kind=='REVERSAL',p.amount),else_=-p.amount).label('signed')).join(
            account,account.c.id==p.financial_account_id).join(Payable,(Payable.id==p.payable_id)&
            (Payable.company_id==p.company_id)&(Payable.organization_id==p.organization_id)).where(
            p.organization_id==organization_id,p.company_id==company_id,p.occurred_on>=account.c.opening_date,p.occurred_on<=end)
        def received(reversed_):
            day=r.reversed_on if reversed_ else r.received_on
            return select(r.id,literal('RECEIPT_REVERSAL' if reversed_ else 'RECEIPT').label('source'),r.billing_id.label('reference_id'),day.label('day'),
                literal('RECEIPT_REVERSAL' if reversed_ else 'RECEIVED').label('kind'),ServiceBilling.service.label('description'),r.amount,
                (-r.amount if reversed_ else r.amount).label('signed')).join(account,account.c.id==r.financial_account_id).join(
                ServiceBilling,(ServiceBilling.id==r.billing_id)&(ServiceBilling.company_id==r.company_id)&
                (ServiceBilling.organization_id==r.organization_id)).where(r.organization_id==organization_id,r.company_id==company_id,
                day>=account.c.opening_date,day<=end, (r.reversed.is_(True)&r.reversed_on.is_not(None)) if reversed_ else true())
        ledger=union_all(payments,received(False),received(True)).cte('statement_ledger')
        order=(ledger.c.day,ledger.c.source,cast(ledger.c.id,String),cast(ledger.c.reference_id,String))
        running=select(ledger,(account.c.opening_balance+func.sum(ledger.c.signed).over(order_by=order,rows=(None,0))).label('balance')).select_from(ledger).join(account,true()).cte('statement_running')
        def sum_(condition,value):
            return select(func.coalesce(func.sum(value),0)).where(condition).scalar_subquery()
        during=ledger.c.day.between(start,end)
        meta=select(account.c.opening_date.label('initial_date'),account.c.opening_balance.label('initial_balance'),
            (account.c.opening_balance+sum_(ledger.c.day<start,ledger.c.signed)).label('opening_balance'),
            sum_(during & (ledger.c.signed>0),ledger.c.signed).label('incoming'),
            sum_(during & (ledger.c.signed<0),-ledger.c.signed).label('outgoing'),
            (account.c.opening_balance+sum_(true(),ledger.c.signed)).label('closing_balance'),
            select(r.id).join(account,account.c.id==r.financial_account_id).where(r.organization_id==organization_id,
                r.company_id==company_id,r.reversed.is_(True),r.reversed_on.is_(None)).exists().label('invalid')
        ).select_from(account).cte('statement_meta')
        page=select(running).where(running.c.day.between(start,end))
        if cursor is not None:page=page.where(tuple_(running.c.day,running.c.source,cast(running.c.id,String),cast(running.c.reference_id,String))>tuple_(*cursor_value(cursor)))
        page=page.order_by(running.c.day,running.c.source,cast(running.c.id,String),cast(running.c.reference_id,String)).limit(limit+1).cte('statement_page')
        records=(await session.execute(select(meta,page).select_from(meta).outerjoin(page,true()).order_by(page.c.day,page.c.source,cast(page.c.id,String),cast(page.c.reference_id,String)))).mappings().all()
        if not records:raise HTTPException(404,'Extrato indisponível.')
        metadata=records[0]
        if start<metadata['initial_date']:raise HTTPException(422,'O período deve começar na data inicial da conta ou depois.')
        if metadata['invalid']:raise HTTPException(409,'Existe estorno vinculado sem data financeira. Revise os registros.')
        rows=[row for row in records if row['id'] is not None]
        items=[StatementEntry(**{key:row[key] for key in ('id','source','reference_id','day','kind','description','amount','balance')},
            direction='IN' if row['signed']>0 else 'OUT') for row in rows[:limit]]
        next_cursor=None
        if len(rows)>limit:
            last=items[-1];next_cursor=base64.urlsafe_b64encode(json.dumps([last.day.isoformat(),last.source,str(last.id),str(last.reference_id)]).encode()).decode()
        result=Statement(account_id=account_id,start=start,end=end,items=items,next_cursor=next_cursor,
            **{key:metadata[key] for key in ('initial_date','initial_balance','opening_balance','incoming','outgoing','closing_balance')})
    await record_authorized_activity(request,token)
    return result
