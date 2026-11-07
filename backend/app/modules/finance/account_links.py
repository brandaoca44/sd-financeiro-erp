"""Atribuição explícita de conta a movimentos antigos, sem reatribuição silenciosa."""
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from app.api.v1.auth import get_current_session,get_session_token
from app.modules.finance.router import writer
from app.modules.finance.account_posting import posting_account
from app.modules.finance.models import PayableMovement,Payable,PayableChange
from app.modules.finance.billing import Receipt
from app.modules.finance.schemas import CalendarDate
from app.modules.finance.movements import PayableMovementService
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.permissions import PermissionKey
from app.modules.audit.models import record_event

router=APIRouter(prefix='/organizations/{organization_id}/companies/{company_id}',tags=['Vínculos financeiros'])
class PaymentLink(BaseModel):
    model_config=ConfigDict(extra='forbid')
    financial_account_id:UUID
    expected_revision:int=Field(ge=1,strict=True)
class ReceiptLink(BaseModel):
    model_config=ConfigDict(extra='forbid')
    financial_account_id:UUID
    expected_reversed:bool=Field(strict=True)
    reversed_on:CalendarDate|None=None

async def authorize_link(service,org,company,token,permission):
    actor=await service._authorize_write(org,company,token,permission_key=permission)
    policy=CompanyAccessPolicy(service.session)
    if not await policy.has_operation_permission(actor,org,company,PermissionKey.ACCOUNTS_MANAGE) or not await policy.has_operation_permission(actor,org,company,PermissionKey.ACCOUNTS_READ):service.deny()
    return actor

@router.post('/payables/{payable_id}/payments/{payment_id}/account')
async def payment_account(organization_id:UUID,company_id:UUID,payable_id:UUID,payment_id:UUID,data:PaymentLink,request:Request,
    current=Depends(get_current_session),token=Depends(get_session_token)):
    async with writer(request,current.user_id) as service,service.session.begin():
        actor=await authorize_link(service,organization_id,company_id,token,PermissionKey.PAYABLES_SETTLE)
        row=await service.session.scalar(select(PayableMovement).where(PayableMovement.organization_id==organization_id,
            PayableMovement.company_id==company_id,PayableMovement.payable_id==payable_id,PayableMovement.id==payment_id,PayableMovement.kind=='PAYMENT').with_for_update())
        if row is None:service.deny()
        if row.financial_account_id is not None:
            if row.financial_account_id!=data.financial_account_id:raise HTTPException(409,'Movimento já vinculado a outra conta.')
            return {'linked':True}
        title=await service.session.scalar(select(Payable).where(Payable.id==payable_id,Payable.company_id==company_id,Payable.organization_id==organization_id).with_for_update())
        if title is None:service.deny()
        if title.revision!=data.expected_revision:raise HTTPException(409,'Título alterado. Atualize a consulta.')
        await posting_account(service.session,organization_id,company_id,actor,data.financial_account_id,row.occurred_on)
        reversals=list(await service.session.scalars(select(PayableMovement).where(PayableMovement.organization_id==organization_id,
            PayableMovement.company_id==company_id,PayableMovement.payable_id==payable_id,PayableMovement.reverses_id==payment_id).with_for_update()))
        for reversal in reversals:
            await posting_account(service.session,organization_id,company_id,actor,data.financial_account_id,reversal.occurred_on,reversal=True)
            if reversal.financial_account_id not in (None,data.financial_account_id):raise HTTPException(409,'Estorno vinculado a outra conta.')
            reversal.financial_account_id=data.financial_account_id
        row.financial_account_id=data.financial_account_id;title.revision+=1
        service.session.add(PayableChange(organization_id=organization_id,company_id=company_id,payable_id=payable_id,actor_user_id=actor,action="UPDATED",before_state={"financial_account_id":None},after_state={"financial_account_id":str(data.financial_account_id),"movement_id":str(payment_id),"revision":title.revision}))
        record_event(service.session,organization_id,company_id,actor,'ACCOUNTS','ACCOUNT',data.financial_account_id,'UPDATED')
        return {'linked':True}

@router.post('/billing/{billing_id}/receipts/{receipt_id}/account')
async def receipt_account(organization_id:UUID,company_id:UUID,billing_id:UUID,receipt_id:UUID,data:ReceiptLink,request:Request,
    current=Depends(get_current_session),token=Depends(get_session_token)):
    async with writer(request,current.user_id) as service,service.session.begin():
        actor=await authorize_link(service,organization_id,company_id,token,PermissionKey.BILLING_RECEIVE)
        row=await service.session.get(Receipt,(organization_id,company_id,billing_id,receipt_id),with_for_update=True)
        if row is None:service.deny()
        if row.financial_account_id is not None:
            if row.financial_account_id!=data.financial_account_id:raise HTTPException(409,'Movimento já vinculado a outra conta.')
            return {'linked':True}
        if row.reversed!=data.expected_reversed:raise HTTPException(409,'Recebimento alterado. Atualize a consulta.')
        if row.received_on>PayableMovementService._today():raise HTTPException(409,'Confira a data do recebimento.')
        await posting_account(service.session,organization_id,company_id,actor,data.financial_account_id,row.received_on)
        if row.reversed:
            if row.reversed_on is None and not await CompanyAccessPolicy(service.session).has_operation_permission(actor,organization_id,company_id,PermissionKey.BILLING_REVERSE):service.deny()
            if row.reversed_on is not None and data.reversed_on not in (None,row.reversed_on):raise HTTPException(409,'A data do estorno já está registrada.')
            day=row.reversed_on or data.reversed_on
            if day is None or not row.received_on<=day<=PayableMovementService._today():raise HTTPException(422,'Informe a data efetiva do estorno antigo.')
            row.reversed_on=day
        elif data.reversed_on is not None:raise HTTPException(422,'Recebimento sem estorno.')
        row.financial_account_id=data.financial_account_id
        record_event(service.session,organization_id,company_id,actor,'BILLING','RECEIPT',receipt_id,'UPDATED')
        record_event(service.session,organization_id,company_id,actor,'ACCOUNTS','ACCOUNT',data.financial_account_id,'UPDATED')
        return {'linked':True}
