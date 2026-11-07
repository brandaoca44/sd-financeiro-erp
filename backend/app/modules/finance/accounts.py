"""Contas da empresa e posições iniciais, separadas de dados bancários pessoais."""
import json
import re
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import CheckConstraint, Date, DateTime, Integer, Numeric, String, Text, Uuid, func, select
from sqlalchemy.orm import mapped_column
from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.database.base import Base
from app.modules.audit.models import record_event
from app.modules.finance.models import actor_member, scope_company
from app.modules.finance.movements import PayableMovementService
from app.modules.finance.router import writer
from app.modules.finance.schemas import CalendarDate, MAX_MONEY
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Company

class FinancialAccount(Base):
    __tablename__='financial_accounts'
    __table_args__=(scope_company('fk_financial_accounts_company'),actor_member('created_by_user_id','fk_financial_accounts_creator'),
        CheckConstraint("kind IN ('BANK','CASH','PAYMENT')",name='ck_financial_accounts_kind'),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')",name='ck_financial_accounts_status'),
        CheckConstraint("currency = 'BRL'",name='ck_financial_accounts_currency'),
        CheckConstraint('revision > 0',name='ck_financial_accounts_revision'),
        CheckConstraint("opening_balance <> 'NaN'::numeric AND abs(opening_balance) <= 9999999999999999.99 AND scale(opening_balance) <= 2",name='ck_financial_accounts_opening'),
        CheckConstraint('isfinite(opening_date)',name='ck_financial_accounts_date'))
    organization_id=mapped_column(Uuid,primary_key=True)
    company_id=mapped_column(Uuid,primary_key=True)
    id=mapped_column(Uuid,primary_key=True)
    name=mapped_column(String(100),nullable=False)
    kind=mapped_column(String(10),nullable=False)
    currency=mapped_column(String(3),nullable=False,server_default='BRL')
    opening_balance=mapped_column(Numeric,nullable=False)
    opening_date=mapped_column(Date,nullable=False)
    encrypted_bank=mapped_column(Text)
    status=mapped_column(String(8),nullable=False,server_default='ACTIVE')
    revision=mapped_column(Integer,nullable=False,server_default='1')
    created_by_user_id=mapped_column(Uuid,nullable=False)
    created_at=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())

Text100=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=100)]
Digits=Annotated[str,StringConstraints(pattern=r'^[0-9]{1,30}$')]
class BankDetails(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    institution:Text100
    branch:Digits|None=None
    account:Digits


def signed_money(value):
    if not isinstance(value,str) or len(value)>20 or not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?',value):
        raise ValueError('Informe saldo decimal com até duas casas.')
    amount=Decimal(value)
    if not amount.is_finite() or abs(amount)>MAX_MONEY:raise ValueError('Saldo inválido.')
    return amount.quantize(Decimal('0.01'))

class AccountCreate(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    name:Text100
    kind:Literal['BANK','CASH','PAYMENT']
    opening_balance:Annotated[Decimal,BeforeValidator(signed_money,json_schema_input_type=str)]
    opening_date:CalendarDate
    bank_details:BankDetails|None=None
    @model_validator(mode='after')
    def check(self):
        if self.opening_date>PayableMovementService._today():raise ValueError('A data inicial não pode ser futura.')
        validate_bank(self.kind,self.bank_details)
        return self

class AccountUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    name:Text100
    status:Literal['ACTIVE','INACTIVE']
    expected_revision:int=Field(ge=1,strict=True)
    bank_details:BankDetails|None=None

class AccountRow(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID
    name:str
    kind:Literal['BANK','CASH','PAYMENT']
    currency:Literal['BRL']
    opening_balance:Decimal
    opening_date:CalendarDate
    status:Literal['ACTIVE','INACTIVE']
    revision:int

class AccountPage(BaseModel):
    items:list[AccountRow]
    next_cursor:UUID|None

class AccountReceipt(BaseModel):
    id:UUID
    revision:int


def validate_bank(kind,details):
    if kind=='CASH' and details is not None:raise ValueError('Caixa não recebe dados bancários.')
    if kind!='CASH' and details is None:raise ValueError('Informe os dados da conta.')
    if kind=='BANK' and not details.branch:raise ValueError('Informe a agência.')


def bank_cipher(request):
    key=request.app.state.settings.auth_identity_encryption_key
    if key is None:raise HTTPException(503,'Dados bancários temporariamente indisponíveis.')
    return Fernet(key.get_secret_value().encode('ascii'))


def bank_values(row,request):
    if row.encrypted_bank is None:return None
    try:
        data=json.loads(bank_cipher(request).decrypt(row.encrypted_bank.encode('ascii')))
        if data['scope']!=[str(row.organization_id),str(row.company_id),str(row.id)]:raise ValueError()
        return BankDetails.model_validate(data['details'])
    except (InvalidToken,ValueError,KeyError,TypeError):
        raise HTTPException(503,'Dados bancários temporariamente indisponíveis.') from None


def set_bank(row,details,request):
    if details is not None:
        data=dict(scope=[str(row.organization_id),str(row.company_id),str(row.id)],details=details.model_dump())
        row.encrypted_bank=bank_cipher(request).encrypt(json.dumps(data).encode()).decode('ascii')


def visibility(actor,org,company,permission):
    return select(Company.id).where(Company.id==company,
        CompanyAccessPolicy(None).operation_visibility(actor,org,permission)).exists()

router=APIRouter(prefix='/organizations/{organization_id}/companies/{company_id}/financial-accounts',tags=['Contas financeiras'])

@router.get('',response_model=AccountPage)
async def list_accounts(organization_id:UUID,company_id:UUID,request:Request,cursor:UUID|None=None,
    status:Literal['ACTIVE','INACTIVE']|None=None,limit:int=Query(default=50,ge=1,le=100),
    current=Depends(get_current_session),token=Depends(get_session_token)):
    async with request.app.state.session_factory() as session:
        allowed=visibility(current.user_id,organization_id,company_id,PermissionKey.ACCOUNTS_READ)
        if not await session.scalar(select(allowed)):raise HTTPException(404,'Contas financeiras indisponíveis.')
        query=select(FinancialAccount).where(FinancialAccount.organization_id==organization_id,FinancialAccount.company_id==company_id,allowed)
        if cursor is not None:query=query.where(FinancialAccount.id>cursor)
        if status is not None:query=query.where(FinancialAccount.status==status)
        rows=list(await session.scalars(query.order_by(FinancialAccount.id).limit(limit+1)))
        page=AccountPage(items=[AccountRow.model_validate(row) for row in rows[:limit]],next_cursor=rows[limit-1].id if len(rows)>limit else None)
    await record_authorized_activity(request,token)
    return page

@router.post('',response_model=AccountReceipt,status_code=201)
async def create_account(organization_id:UUID,company_id:UUID,data:AccountCreate,request:Request,
    request_id:UUID=Header(alias='Idempotency-Key'),current=Depends(get_current_session),token=Depends(get_session_token)):
    async with writer(request,current.user_id) as service,service.session.begin():
        session=service.session
        actor=await service._authorize_write(organization_id,company_id,token,permission_key=PermissionKey.ACCOUNTS_MANAGE)
        if data.bank_details is not None and not await CompanyAccessPolicy(session).has_operation_permission(actor,organization_id,company_id,PermissionKey.ACCOUNTS_BANK):service.deny()
        row=await session.get(FinancialAccount,(organization_id,company_id,request_id))
        if row is not None:
            if row.created_by_user_id!=actor or any(getattr(row,key)!=getattr(data,key) for key in ('name','kind','opening_date','opening_balance')):
                raise HTTPException(409,'Cadastro já processado com outros dados.')
            if bank_values(row,request)!=data.bank_details:
                raise HTTPException(409,'Cadastro já processado com outros dados.')
        else:
            row=FinancialAccount(organization_id=organization_id,company_id=company_id,id=request_id,
                name=data.name,kind=data.kind,opening_balance=data.opening_balance,opening_date=data.opening_date,
                currency='BRL',status='ACTIVE',revision=1,created_by_user_id=actor)
            set_bank(row,data.bank_details,request);session.add(row)
            record_event(session,organization_id,company_id,actor,'ACCOUNTS','ACCOUNT',request_id,'CREATED')
        return AccountReceipt(id=row.id,revision=row.revision)

@router.put('/{account_id}',response_model=AccountReceipt)
async def update_account(organization_id:UUID,company_id:UUID,account_id:UUID,data:AccountUpdate,request:Request,
    current=Depends(get_current_session),token=Depends(get_session_token)):
    async with writer(request,current.user_id) as service,service.session.begin():
        session=service.session
        actor=await service._authorize_write(organization_id,company_id,token,permission_key=PermissionKey.ACCOUNTS_MANAGE)
        row=await session.get(FinancialAccount,(organization_id,company_id,account_id),with_for_update=True)
        if row is None:service.deny()
        if row.revision!=data.expected_revision:raise HTTPException(409,'Conta alterada. Atualize o cadastro.')
        if 'bank_details' in data.model_fields_set:
            if not await CompanyAccessPolicy(session).has_operation_permission(actor,organization_id,company_id,PermissionKey.ACCOUNTS_BANK):service.deny()
            try:validate_bank(row.kind,data.bank_details)
            except ValueError:raise HTTPException(422,'Confira os dados da conta.') from None
            set_bank(row,data.bank_details,request)
        row.name=data.name;row.status=data.status;row.revision+=1
        record_event(session,organization_id,company_id,actor,'ACCOUNTS','ACCOUNT',account_id,'UPDATED')
        return AccountReceipt(id=row.id,revision=row.revision)

@router.get('/{account_id}/bank-details',response_model=BankDetails|None)
async def bank_details(organization_id:UUID,company_id:UUID,account_id:UUID,request:Request,
    current=Depends(get_current_session),token=Depends(get_session_token)):
    async with request.app.state.session_factory() as session:
        row=await session.scalar(select(FinancialAccount).where(FinancialAccount.organization_id==organization_id,
            FinancialAccount.company_id==company_id,FinancialAccount.id==account_id,
            visibility(current.user_id,organization_id,company_id,PermissionKey.ACCOUNTS_READ),
            visibility(current.user_id,organization_id,company_id,PermissionKey.ACCOUNTS_BANK)))
        if row is None:raise HTTPException(404,'Dados bancários indisponíveis.')
        result=bank_values(row,request)
    await record_authorized_activity(request,token)
    return result
class AccountPosition(BaseModel):
    as_of:CalendarDate
    opening_balance:Decimal
    opening_date:CalendarDate
    receipts_amount:Decimal
    payments_amount:Decimal
    receipt_reversals_amount:Decimal
    payment_reversals_amount:Decimal
    current_balance:Decimal
    unassigned_payments:int
    unassigned_receipts:int

@router.get('/{account_id}/position',response_model=AccountPosition)
async def account_position(organization_id:UUID,company_id:UUID,account_id:UUID,request:Request,
    current=Depends(get_current_session),token=Depends(get_session_token)):
    from app.modules.finance.models import PayableMovement
    from app.modules.finance.billing import Receipt
    today=PayableMovementService._today()
    a=FinancialAccount
    async with request.app.state.session_factory() as session:
        def total(model,day,*conditions):
            return select(func.coalesce(func.sum(model.amount),0)).where(model.organization_id==organization_id,
                model.company_id==company_id,model.financial_account_id==a.id,
                day>=a.opening_date,day<=today,*conditions).correlate(a).scalar_subquery()
        def unassigned(model,*conditions):
            return select(func.count()).select_from(model).where(model.organization_id==organization_id,
                model.company_id==company_id,model.financial_account_id.is_(None),*conditions).scalar_subquery()
        statement=select(a.opening_balance,a.opening_date,
            total(Receipt,Receipt.received_on).label('receipts_amount'),
            total(Receipt,Receipt.reversed_on,Receipt.reversed.is_(True)).label('receipt_reversals_amount'),
            total(PayableMovement,PayableMovement.occurred_on,PayableMovement.kind=='PAYMENT').label('payments_amount'),
            total(PayableMovement,PayableMovement.occurred_on,PayableMovement.kind=='REVERSAL').label('payment_reversals_amount'),
            unassigned(PayableMovement,PayableMovement.kind=='PAYMENT').label('unassigned_payments'),
            unassigned(Receipt).label('unassigned_receipts')).where(
                a.organization_id==organization_id,a.company_id==company_id,a.id==account_id,
                visibility(current.user_id,organization_id,company_id,PermissionKey.ACCOUNTS_READ),
                visibility(current.user_id,organization_id,company_id,PermissionKey.PAYABLES_READ),
                visibility(current.user_id,organization_id,company_id,PermissionKey.BILLING_READ))
        row=(await session.execute(statement)).mappings().one_or_none()
        if row is None:raise HTTPException(404,'Saldo da conta indisponível.')
        balance=row['opening_balance']+row['receipts_amount']-row['receipt_reversals_amount']-row['payments_amount']+row['payment_reversals_amount']
        result=AccountPosition(as_of=today,current_balance=balance,**row)
    await record_authorized_activity(request,token)
    return result
