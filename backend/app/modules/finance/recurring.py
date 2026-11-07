"""Geração mensal transacional e revisão de despesas variáveis."""
import asyncio
import logging
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy import CheckConstraint, Date, ForeignKeyConstraint, Numeric, String, UniqueConstraint, Uuid, and_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import mapped_column

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.database.base import Base
from app.modules.finance.expenses import Expense, ExpenseRule, Supplier, record_expense_change
from app.modules.finance.movements import PayableMovementService
from app.modules.finance.recurrence_calendar import monthly_occurrence
from app.modules.finance.repository import PayableRepository
from app.modules.finance.router import writer
from app.modules.finance.schemas import CalendarDate, Money, PayableCreate
from app.modules.finance.service import PayableConflictError
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.models import OrganizationMembership, User
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Company, Organization


class ExpenseOccurrence(Base):
    __tablename__ = "expense_occurrences"
    __table_args__ = (
        CheckConstraint("EXTRACT(DAY FROM competence) = 1 AND due_date >= competence", name="ck_expense_occurrence_dates"),
        CheckConstraint("amount IS NULL OR amount > 0", name="ck_expense_occurrence_amount"),
        CheckConstraint("expense_id IS NULL OR amount IS NOT NULL", name="ck_expense_occurrence_confirmed"),
        UniqueConstraint("organization_id", "company_id", "rule_id", "competence", name="uq_expense_occurrence_month"),
        ForeignKeyConstraint(["organization_id", "company_id", "rule_id"],
            ["expense_rules.organization_id", "expense_rules.company_id", "expense_rules.id"],
            name="fk_expense_occurrences_rule", ondelete="RESTRICT"),
        ForeignKeyConstraint(["organization_id", "company_id", "supplier_id"],
            ["finance_suppliers.organization_id", "finance_suppliers.company_id", "finance_suppliers.id"],
            name="fk_expense_occurrences_supplier", ondelete="RESTRICT"),
        ForeignKeyConstraint(["organization_id", "company_id", "expense_id"],
            ["expenses.organization_id", "expenses.company_id", "expenses.id"],
            name="fk_expense_occurrences_expense", ondelete="RESTRICT"),
    )
    organization_id = mapped_column(Uuid, primary_key=True)
    company_id = mapped_column(Uuid, primary_key=True)
    id = mapped_column(Uuid, primary_key=True)
    rule_id = mapped_column(Uuid, nullable=False)
    competence = mapped_column(Date, nullable=False)
    description = mapped_column(String(300), nullable=False)
    category = mapped_column(String(20), nullable=False)
    supplier_id = mapped_column(Uuid, nullable=False)
    supplier = mapped_column(String(150), nullable=False)
    amount = mapped_column(Numeric)
    due_date = mapped_column(Date, nullable=False)
    document_type = mapped_column(String(20))
    document_reference = mapped_column(String(100))
    expense_id = mapped_column(Uuid)


def next_month(month: date) -> date:
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


async def materialize(session, occurrence, actor):
    """Despesas, título e auditoria são confirmados pela transação do chamador."""
    title = await PayableRepository(session).create(
        occurrence.organization_id, occurrence.company_id, actor,
        PayableCreate(description=occurrence.description, amount=occurrence.amount,
                      issue_date=occurrence.competence, due_date=occurrence.due_date),
    )
    expense = Expense(organization_id=occurrence.organization_id, company_id=occurrence.company_id,
                      id=occurrence.id, created_by_user_id=actor, payable_id=title.id,
                      description=occurrence.description, category=occurrence.category,
                      supplier_id=occurrence.supplier_id, supplier=occurrence.supplier,
                      amount=occurrence.amount, competence=occurrence.competence,
                      issue_date=occurrence.competence, due_date=occurrence.due_date,
                      document_type=occurrence.document_type, document_reference=occurrence.document_reference)
    session.add(expense)
    await session.flush()
    record_expense_change(session, expense, actor, "CREATED", {})
    occurrence.expense_id = expense.id


async def generate_rule(factory, key, today):
    """Serializa com edição, cancelamento e revogações pelo lock da organização."""
    organization_id, company_id, rule_id = key
    async with factory() as session, session.begin():
        await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        await session.scalar(select(Organization).where(Organization.id == organization_id).with_for_update())
        rule = await session.get(ExpenseRule, key)
        if rule is None or rule.cancelled or rule.authorized_by_user_id is None or rule.next_month > today:
            return False
        actor = rule.authorized_by_user_id
        await session.scalar(select(User).where(User.id == actor).with_for_update())
        await session.scalar(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == actor).with_for_update())
        await session.scalar(select(Company).where(
            Company.organization_id == organization_id, Company.id == company_id).with_for_update())
        policy = CompanyAccessPolicy(session)
        if not await policy.lock_financial_contract(organization_id, company_id):
            return False
        if not await policy.has_financial_permission(actor, organization_id, company_id, PermissionKey.PAYABLES_MANAGE):
            return False
        if rule.category == "PESSOAL":
            return False
        supplier = await session.get(Supplier, (organization_id, company_id, rule.supplier_id))
        if supplier is None:
            return False
        occurrence_id, due_date = monthly_occurrence(rule.id, rule.next_month, int(rule.due_day))
        occurrence = await session.get(ExpenseOccurrence, (organization_id, company_id, occurrence_id))
        if occurrence is None:
            occurrence = ExpenseOccurrence(
                organization_id=organization_id, company_id=company_id, id=occurrence_id, rule_id=rule.id,
                competence=rule.next_month, description=rule.description, category=rule.category,
                supplier_id=rule.supplier_id, supplier=supplier.name, due_date=due_date,
                amount=rule.fixed_amount,
            )
            session.add(occurrence)
            await session.flush()
            if rule.fixed_amount is not None:
                await materialize(session, occurrence, actor)
        rule.next_month = next_month(rule.next_month)
        return True


async def generate_due_expenses(factory, *, today=None):
    """Uma passagem processa até 12 competências por regra; a próxima recupera o restante."""
    today = today or PayableMovementService._today()
    async with factory() as session:
        keys = list((await session.execute(select(
            ExpenseRule.organization_id, ExpenseRule.company_id, ExpenseRule.id,
        ).where(ExpenseRule.cancelled.is_(False), ExpenseRule.authorized_by_user_id.is_not(None),
                ExpenseRule.next_month <= today))).all())
    processed = 0
    for key in keys:
        for _ in range(12):
            try:
                generated = await generate_rule(factory, tuple(key), today)
            except SQLAlchemyError:
                logging.getLogger(__name__).warning("recurring_expense_generation_failed")
                break
            if not generated:
                break
            processed += 1
    return processed


async def recurring_expense_worker(factory):
    while True:
        try:
            await generate_due_expenses(factory)
        except SQLAlchemyError:
            logging.getLogger(__name__).warning("recurring_expense_scan_failed")
        await asyncio.sleep(60)


class OccurrenceResponse(BaseModel):
    id: UUID
    rule_id: UUID
    competence: date
    description: str
    supplier: str
    due_date: date
    amount: Decimal | None
    expense_id: UUID | None
    status: Literal["PENDING", "GENERATED", "CANCELLED"]


class ConfirmOccurrence(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    amount: Money
    due_date: CalendarDate
    document_type: Literal["BOLETO", "NOTA_FISCAL", "OUTRO"] | None = None
    document_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None

    @model_validator(mode="after")
    def validate_document(self):
        if self.document_reference and self.document_type is None:
            raise ValueError("Selecione o tipo de comprovante.")
        return self


router = APIRouter(prefix="/organizations/{organization_id}/companies/{company_id}/expense-occurrences",
                   tags=["Despesas recorrentes"])


@router.get("", response_model=list[OccurrenceResponse])
async def list_occurrences(organization_id: UUID, company_id: UUID, request: Request,
                           current=Depends(get_current_session), token=Depends(get_session_token), occurrence_id: UUID | None = None):
    async with request.app.state.session_factory() as session:
        policy = CompanyAccessPolicy(session)
        visible = select(Company.id).where(
            Company.id == company_id, Company.organization_id == organization_id,
            policy.financial_visibility(current.user_id, organization_id, PermissionKey.PAYABLES_READ),
        ).exists()
        if not await session.scalar(select(visible)):
            raise HTTPException(404, "Operação financeira não permitida.")
        query = (select(ExpenseOccurrence, ExpenseRule.cancelled).join(ExpenseRule, and_(
            ExpenseRule.organization_id == ExpenseOccurrence.organization_id,
            ExpenseRule.company_id == ExpenseOccurrence.company_id, ExpenseRule.id == ExpenseOccurrence.rule_id,
        )).where(ExpenseOccurrence.organization_id == organization_id, ExpenseOccurrence.company_id == company_id, visible)
        .order_by(ExpenseOccurrence.competence.desc(), ExpenseOccurrence.id.desc()).limit(200))
        if occurrence_id is not None:
            query = query.where(ExpenseOccurrence.id == occurrence_id)
        rows = (await session.execute(query)).all()
        result = [OccurrenceResponse(
            id=row.id, rule_id=row.rule_id, competence=row.competence, description=row.description,
            supplier=row.supplier, due_date=row.due_date, amount=row.amount, expense_id=row.expense_id,
            status="GENERATED" if row.expense_id else "CANCELLED" if cancelled else "PENDING",
        ) for row, cancelled in rows]
    await record_authorized_activity(request, token)
    return result


@router.post("/{occurrence_id}/confirm", response_model=dict[str, UUID])
async def confirm_occurrence(organization_id: UUID, company_id: UUID, occurrence_id: UUID,
                             data: ConfirmOccurrence, request: Request,
                             current=Depends(get_current_session), token=Depends(get_session_token)):
    async with writer(request, current.user_id) as service, service.session.begin():
        actor = await service._authorize_write(organization_id, company_id, token)
        occurrence = await service.session.get(ExpenseOccurrence, (organization_id, company_id, occurrence_id))
        if occurrence is None:
            service.deny()
        if occurrence.expense_id:
            if any(getattr(occurrence, key) != value for key, value in data.model_dump().items()):
                raise PayableConflictError()
            return {"expense_id": occurrence.expense_id}
        rule = await service.session.get(ExpenseRule, (organization_id, company_id, occurrence.rule_id))
        if rule is None or rule.cancelled:
            raise PayableConflictError()
        if data.due_date < occurrence.competence:
            raise HTTPException(422, "Confira o vencimento da cobrança.")
        for key, value in data.model_dump().items():
            setattr(occurrence, key, value)
        await materialize(service.session, occurrence, actor)
        return {"expense_id": occurrence.expense_id}
