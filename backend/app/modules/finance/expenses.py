"""Registro de despesas e geração transacional da obrigação financeira."""
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import Date, ForeignKeyConstraint, Numeric, String, UniqueConstraint, Uuid, select
from sqlalchemy.orm import mapped_column

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.database.base import Base
from app.modules.finance.models import actor_member, scope_company
from app.modules.finance.router import writer
from app.modules.finance.schemas import CalendarDate, Money, PayableCreate
from app.modules.finance.service import PayableConflictError, PayableService
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Company


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        scope_company("fk_expenses_company"),
        actor_member("created_by_user_id", "fk_expenses_creator"),
        ForeignKeyConstraint(
            ["organization_id", "company_id", "payable_id"],
            ["payables.organization_id", "payables.company_id", "payables.id"],
            ondelete="RESTRICT", name="fk_expenses_payable",
        ),
        UniqueConstraint("payable_id", name="uq_expenses_payable"),
    )
    organization_id = mapped_column(Uuid, primary_key=True)
    company_id = mapped_column(Uuid, primary_key=True)
    id = mapped_column(Uuid, primary_key=True)
    created_by_user_id = mapped_column(Uuid, nullable=False)
    payable_id = mapped_column(Uuid, nullable=True)
    description = mapped_column(String(300), nullable=False)
    category = mapped_column(String(20), nullable=False)
    supplier = mapped_column(String(150), nullable=False)
    document_type = mapped_column(String(20), nullable=True)
    document_reference = mapped_column(String(100), nullable=True)
    amount = mapped_column(Numeric, nullable=False)
    issue_date = mapped_column(Date, nullable=False)
    due_date = mapped_column(Date, nullable=True)


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    category: Literal["INTERNET", "ENERGIA", "AGUA", "ESGOTO", "ALUGUEL", "PESSOAL", "OUTROS"]
    supplier: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    document_type: Literal["BOLETO", "NOTA_FISCAL", "OUTRO"] | None = None
    document_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    amount: Money
    issue_date: CalendarDate
    due_date: CalendarDate | None = None


class ExpenseReceipt(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    payable_id: UUID | None


class ExpenseResponse(ExpenseCreate, ExpenseReceipt):
    model_config = ConfigDict(from_attributes=True)


class ExpenseService(PayableService):
    async def register(self, organization_id, company_id, data, token, request_id):
        async with self.session.begin():
            actor = await self._authorize_write(organization_id, company_id, token)
            values = data.model_dump()
            previous = await self.session.get(Expense, (organization_id, company_id, request_id))
            if previous:
                if previous.created_by_user_id != actor or any(
                    getattr(previous, key) != value for key, value in values.items()
                ):
                    raise PayableConflictError()
                return previous
            payable = None
            if data.due_date is not None:
                title = PayableCreate(description=data.description, amount=data.amount,
                                      issue_date=data.issue_date, due_date=data.due_date)
                payable = await self.repository.create(organization_id, company_id, actor, title)
            expense = Expense(organization_id=organization_id, company_id=company_id, id=request_id,
                              created_by_user_id=actor, payable_id=payable.id if payable else None, **values)
            self.session.add(expense)
            await self.session.flush()
        return expense


router = APIRouter(prefix="/organizations/{organization_id}/companies/{company_id}/expenses", tags=["Despesas"])


@router.post("", response_model=ExpenseReceipt, status_code=201)
async def register_expense(organization_id: UUID, company_id: UUID, data: ExpenseCreate, request: Request,
                           request_id: UUID = Header(alias="Idempotency-Key"),
                           current=Depends(get_current_session), token=Depends(get_session_token)):
    if data.due_date is not None and data.due_date < data.issue_date:
        raise HTTPException(422, "O vencimento deve ser igual ou posterior à emissão.")
    if data.document_reference and not data.document_type:
        raise HTTPException(422, "Selecione o tipo de documento.")
    async with writer(request, current.user_id, service_class=ExpenseService) as service:
        return ExpenseReceipt.model_validate(await service.register(organization_id, company_id, data, token, request_id))


@router.get("", response_model=list[ExpenseResponse])
async def list_expenses(organization_id: UUID, company_id: UUID, request: Request,
                        current=Depends(get_current_session), token=Depends(get_session_token)):
    async with request.app.state.session_factory() as session:
        policy = CompanyAccessPolicy(session)
        if not await policy.has_financial_permission(current.user_id, organization_id, company_id, PermissionKey.PAYABLES_READ):
            raise HTTPException(404, "Operação financeira não permitida.")
        visible_company = select(Company.id).where(
            Company.id == company_id, Company.organization_id == organization_id,
            policy.financial_visibility(current.user_id, organization_id, PermissionKey.PAYABLES_READ),
        ).exists()
        rows = await session.scalars(select(Expense).where(
            Expense.organization_id == organization_id, Expense.company_id == company_id, visible_company,
        ).order_by(Expense.issue_date.desc(), Expense.id.desc()).limit(100))
        result = [ExpenseResponse.model_validate(row) for row in rows]
    await record_authorized_activity(request, token)
    return result
