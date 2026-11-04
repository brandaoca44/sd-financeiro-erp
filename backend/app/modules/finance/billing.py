"""Faturamento de serviços e consulta das cobranças vinculadas."""
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy import Boolean, Date, ForeignKeyConstraint, Numeric, String, Uuid, select
from sqlalchemy.orm import mapped_column

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.database.base import Base
from app.modules.finance.models import scope_company
from app.modules.finance.router import writer
from app.modules.finance.schemas import CalendarDate, Money
from app.modules.finance.service import PayableConflictError
from app.modules.identity.access_models import OrganizationOwnership
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Company


class Customer(Base):
    __tablename__ = "billing_customers"
    __table_args__ = (scope_company("fk_billing_customers_company"),)
    organization_id = mapped_column(Uuid, primary_key=True)
    company_id = mapped_column(Uuid, primary_key=True)
    id = mapped_column(Uuid, primary_key=True)
    name = mapped_column(String(150), nullable=False)


class CustomerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class CustomerRow(CustomerInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class ServiceBilling(Base):
    __tablename__ = "service_billings"
    __table_args__ = (
        scope_company("fk_service_billings_company"),
        ForeignKeyConstraint(["organization_id", "company_id", "customer_id"],
                             ["billing_customers.organization_id", "billing_customers.company_id", "billing_customers.id"],
                             name="fk_service_billings_customer", ondelete="RESTRICT"),
    )
    organization_id = mapped_column(Uuid, primary_key=True)
    company_id = mapped_column(Uuid, primary_key=True)
    id = mapped_column(Uuid, primary_key=True)
    customer_id = mapped_column(Uuid, nullable=True)
    customer = mapped_column(String(150), nullable=False)
    service = mapped_column(String(250), nullable=False)
    competence = mapped_column(Date, nullable=False)
    issue_date = mapped_column(Date, nullable=False)
    amount = mapped_column(Numeric, nullable=False)
    due_date = mapped_column(Date)
    invoice_reference = mapped_column(String(80))


class Receipt(Base):
    __tablename__ = "billing_receipts"
    __table_args__ = (ForeignKeyConstraint(
        ["organization_id", "company_id", "billing_id"],
        ["service_billings.organization_id", "service_billings.company_id", "service_billings.id"],
        name="fk_billing_receipts_billing", ondelete="RESTRICT",
    ),)
    organization_id = mapped_column(Uuid, primary_key=True)
    company_id = mapped_column(Uuid, primary_key=True)
    billing_id = mapped_column(Uuid, primary_key=True)
    id = mapped_column(Uuid, primary_key=True)
    amount = mapped_column(Numeric, nullable=False)
    received_on = mapped_column(Date, nullable=False)
    reversed = mapped_column(Boolean, nullable=False, server_default="false")


class ReceiptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Money
    received_on: CalendarDate


class ReceiptRow(ReceiptInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    reversed: bool


class BillingPosition(BaseModel):
    received: Decimal
    outstanding: Decimal
    receipts: list[ReceiptRow]


class BillingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    customer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)] | None = None
    customer_id: UUID | None = None
    service: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]
    competence: CalendarDate
    issue_date: CalendarDate
    amount: Money
    due_date: CalendarDate | None = None
    invoice_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.competence.day != 1:
            raise ValueError("Informe o primeiro dia da competência.")
        if self.due_date is not None and self.due_date < self.issue_date:
            raise ValueError("O vencimento deve ser igual ou posterior à emissão.")
        return self


class BillingRow(BillingInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


def owner_condition(user_id, organization_id):
    return select(OrganizationOwnership.user_id).where(
        OrganizationOwnership.organization_id == organization_id, OrganizationOwnership.user_id == user_id,
    ).exists()


router = APIRouter(prefix="/organizations/{organization_id}/companies/{company_id}/billing", tags=["Faturamento"])


@router.post("", response_model=BillingRow, status_code=201)
async def register_billing(organization_id: UUID, company_id: UUID, data: BillingInput, request: Request,
                           request_id: UUID = Header(alias="Idempotency-Key"),
                           current=Depends(get_current_session), token=Depends(get_session_token)):
    if (data.customer_id is None) == (data.customer is None):
        raise HTTPException(422, "Selecione um cliente.")
    async with writer(request, current.user_id) as service:
        async with service.session.begin():
            actor = await service._authorize_write(organization_id, company_id, token)
            if not await service.session.scalar(select(owner_condition(actor, organization_id))):
                service.deny()
            row = await service.session.get(ServiceBilling, (organization_id, company_id, request_id))
            values = data.model_dump()
            if data.customer_id is not None:
                customer = await service.session.get(Customer, (organization_id, company_id, data.customer_id))
                if customer is None:
                    service.deny()
                values["customer"] = row.customer if row is not None else customer.name
            if row is None:
                row = ServiceBilling(organization_id=organization_id, company_id=company_id, id=request_id, **values)
                service.session.add(row)
            elif any(getattr(row, key) != value for key, value in values.items()):
                raise PayableConflictError()
            return BillingRow.model_validate(row)


@router.get("", response_model=list[BillingRow])
async def list_billing(organization_id: UUID, company_id: UUID, request: Request, receivables: bool = False,
                       current=Depends(get_current_session), token=Depends(get_session_token)):
    async with request.app.state.session_factory() as session:
        visible = select(Company.id).where(
            Company.organization_id == organization_id, Company.id == company_id,
            owner_condition(current.user_id, organization_id),
            CompanyAccessPolicy(session).financial_visibility(current.user_id, organization_id, PermissionKey.PAYABLES_READ),
        ).exists()
        if not await session.scalar(select(visible)):
            raise HTTPException(404, "Faturamento indisponível.")
        query = select(ServiceBilling).where(
            ServiceBilling.organization_id == organization_id, ServiceBilling.company_id == company_id, visible,
        )
        if receivables:
            query = query.where(ServiceBilling.due_date.is_not(None))
        rows = await session.scalars(query.order_by(ServiceBilling.issue_date.desc(), ServiceBilling.id.desc()).limit(100))
        result = [BillingRow.model_validate(row) for row in rows]
    await record_authorized_activity(request, token)
    return result


def receipts_query(organization_id, company_id, billing_id):
    return select(Receipt).where(Receipt.organization_id == organization_id,
                                 Receipt.company_id == company_id, Receipt.billing_id == billing_id)


@router.get("/{billing_id}/position", response_model=BillingPosition)
async def billing_position(organization_id: UUID, company_id: UUID, billing_id: UUID, request: Request,
                           current=Depends(get_current_session), token=Depends(get_session_token)):
    async with request.app.state.session_factory() as session:
        visible = select(Company.id).where(
            Company.organization_id == organization_id, Company.id == company_id,
            owner_condition(current.user_id, organization_id),
            CompanyAccessPolicy(session).financial_visibility(current.user_id, organization_id, PermissionKey.PAYABLES_READ),
        ).exists()
        billing = await session.scalar(select(ServiceBilling).where(
            ServiceBilling.organization_id == organization_id, ServiceBilling.company_id == company_id,
            ServiceBilling.id == billing_id, ServiceBilling.due_date.is_not(None), visible,
        ))
        if billing is None:
            raise HTTPException(404, "Cobrança indisponível.")
        rows = list(await session.scalars(receipts_query(organization_id, company_id, billing_id)
                    .where(visible).order_by(Receipt.received_on, Receipt.id)))
        received = sum((row.amount for row in rows if not row.reversed), Decimal(0))
        result = BillingPosition(received=received, outstanding=billing.amount - received, receipts=rows)
    await record_authorized_activity(request, token)
    return result


async def authorize_receipt(service, organization_id, company_id, billing_id, token):
    actor = await service._authorize_write(organization_id, company_id, token)
    if not await service.session.scalar(select(owner_condition(actor, organization_id))):
        service.deny()
    billing = await service.session.get(ServiceBilling, (organization_id, company_id, billing_id))
    if billing is None or billing.due_date is None:
        service.deny()
    return billing


@router.post("/{billing_id}/receipts", response_model=ReceiptRow, status_code=201)
async def receive_billing(organization_id: UUID, company_id: UUID, billing_id: UUID, data: ReceiptInput,
                          request: Request, request_id: UUID = Header(alias="Idempotency-Key"),
                          current=Depends(get_current_session), token=Depends(get_session_token)):
    async with writer(request, current.user_id) as service, service.session.begin():
        billing = await authorize_receipt(service, organization_id, company_id, billing_id, token)
        key = (organization_id, company_id, billing_id, request_id)
        previous = await service.session.get(Receipt, key)
        if previous is not None:
            if (previous.amount, previous.received_on) != (data.amount, data.received_on):
                raise PayableConflictError()
            return ReceiptRow.model_validate(previous)
        rows = await service.session.scalars(receipts_query(organization_id, company_id, billing_id)
                                             .where(Receipt.reversed.is_(False)))
        received = sum((row.amount for row in rows), Decimal(0))
        if received + data.amount > billing.amount:
            raise HTTPException(409, "O valor excede o saldo da cobrança.")
        row = Receipt(organization_id=organization_id, company_id=company_id, billing_id=billing_id,
                      id=request_id, reversed=False, **data.model_dump())
        service.session.add(row)
        return ReceiptRow.model_validate(row)


@router.post("/{billing_id}/receipts/{receipt_id}/reverse", status_code=204)
async def reverse_receipt(organization_id: UUID, company_id: UUID, billing_id: UUID, receipt_id: UUID,
                          request: Request, current=Depends(get_current_session), token=Depends(get_session_token)):
    async with writer(request, current.user_id) as service, service.session.begin():
        await authorize_receipt(service, organization_id, company_id, billing_id, token)
        row = await service.session.get(Receipt, (organization_id, company_id, billing_id, receipt_id))
        if row is None:
            service.deny()
        row.reversed = True


customers_router = APIRouter(
    prefix="/organizations/{organization_id}/companies/{company_id}/customers", tags=["Clientes"],
)


@customers_router.get("", response_model=list[CustomerRow])
async def list_customers(organization_id: UUID, company_id: UUID, request: Request,
                         current=Depends(get_current_session), token=Depends(get_session_token)):
    async with request.app.state.session_factory() as session:
        visible = select(Company.id).where(
            Company.organization_id == organization_id, Company.id == company_id,
            owner_condition(current.user_id, organization_id),
            CompanyAccessPolicy(session).financial_visibility(current.user_id, organization_id, PermissionKey.PAYABLES_READ),
        ).exists()
        if not await session.scalar(select(visible)):
            raise HTTPException(404, "Cadastro de clientes indisponível.")
        rows = await session.scalars(select(Customer).where(
            Customer.organization_id == organization_id, Customer.company_id == company_id, visible,
        ).order_by(Customer.name, Customer.id))
        result = [CustomerRow.model_validate(row) for row in rows]
    await record_authorized_activity(request, token)
    return result


@customers_router.post("", response_model=CustomerRow, status_code=201)
async def create_customer(organization_id: UUID, company_id: UUID, data: CustomerInput, request: Request,
                          request_id: UUID = Header(alias="Idempotency-Key"),
                          current=Depends(get_current_session), token=Depends(get_session_token)):
    async with writer(request, current.user_id) as service, service.session.begin():
        actor = await service._authorize_write(organization_id, company_id, token)
        if not await service.session.scalar(select(owner_condition(actor, organization_id))):
            service.deny()
        row = await service.session.get(Customer, (organization_id, company_id, request_id))
        if row is None:
            row = Customer(organization_id=organization_id, company_id=company_id, id=request_id, name=data.name)
            service.session.add(row)
        elif row.name != data.name:
            raise PayableConflictError()
        return CustomerRow.model_validate(row)
