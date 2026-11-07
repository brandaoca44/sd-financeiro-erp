"""Persistência financeira por tenant/empresa. Operações de baixa serão serviços próprios."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def scope_company(name):
    return ForeignKeyConstraint(["organization_id", "company_id"], ["companies.organization_id", "companies.id"], ondelete="RESTRICT", name=name)


def actor_member(column, name):
    return ForeignKeyConstraint([column, "organization_id"], ["organization_memberships.user_id", "organization_memberships.organization_id"], ondelete="RESTRICT", name=name)


def exact_amount(name):
    return CheckConstraint("amount > 0 AND amount <= 9999999999999999.99 AND scale(amount) <= 2", name=name)


class Payable(Base):
    __tablename__ = "payables"
    __table_args__ = (
        scope_company("fk_payables_company"), actor_member("created_by_user_id", "fk_payables_creator"),
        UniqueConstraint("organization_id", "company_id", "id", name="uq_payables_scope"),
        exact_amount("ck_payables_amount"),
        CheckConstraint("currency = 'BRL'", name="ck_payables_currency"),
        CheckConstraint("status IN ('OPEN', 'CANCELLED')", name="ck_payables_status"),
        CheckConstraint("revision > 0", name="ck_payables_revision"),
        CheckConstraint("description = btrim(description) AND length(description) > 0", name="ck_payables_description"),
        CheckConstraint("isfinite(issue_date) AND isfinite(due_date) AND due_date >= issue_date", name="ck_payables_dates"),
        Index("ix_payables_scope_due", "organization_id", "company_id", "due_date", "id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    # Numeric sem typmod evita arredondamento ANTES do CHECK no PostgreSQL.
    amount: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL", server_default="BRL")
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(9), nullable=False, default="OPEN", server_default="OPEN")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PayableMovement(Base):
    __tablename__ = "payable_movements"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "company_id", "financial_account_id"], ["financial_accounts.organization_id", "financial_accounts.company_id", "financial_accounts.id"], name="fk_payable_movement_account", ondelete="RESTRICT"),
        ForeignKeyConstraint(["organization_id", "company_id", "payable_id"], ["payables.organization_id", "payables.company_id", "payables.id"], ondelete="RESTRICT", name="fk_payable_movements_title"),
        actor_member("actor_user_id", "fk_payable_movements_actor"),
        UniqueConstraint("organization_id", "company_id", "payable_id", "id", name="uq_payable_movements_scope"),
        ForeignKeyConstraint(["organization_id", "company_id", "payable_id", "reverses_id"], ["payable_movements.organization_id", "payable_movements.company_id", "payable_movements.payable_id", "payable_movements.id"], ondelete="RESTRICT", name="fk_payable_movements_reversal"),
        UniqueConstraint("reverses_id", name="uq_payable_movements_reversal"),
        exact_amount("ck_payable_movements_amount"),
        CheckConstraint("(kind = 'PAYMENT' AND reverses_id IS NULL) OR (kind = 'REVERSAL' AND reverses_id IS NOT NULL AND reverses_id <> id)", name="ck_payable_movements_kind"),
        CheckConstraint("isfinite(occurred_on)", name="ck_payable_movements_date"),
        CheckConstraint("reversal_reason IS NULL OR (kind = 'REVERSAL' AND reversal_reason = btrim(reversal_reason) AND length(reversal_reason) > 0)", name="ck_payable_movements_reason"),
        Index("ix_payable_movements_scope", "organization_id", "company_id", "payable_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payable_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    financial_account_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    reverses_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PayableChange(Base):
    __tablename__ = "payable_changes"
    __table_args__ = (
        Index("ix_payable_changes_timeline", "organization_id", "company_id", "created_at", "id"),
        ForeignKeyConstraint(["organization_id", "company_id", "payable_id"], ["payables.organization_id", "payables.company_id", "payables.id"], ondelete="RESTRICT", name="fk_payable_changes_title"),
        actor_member("actor_user_id", "fk_payable_changes_actor"),
        CheckConstraint("action IN ('CREATED', 'UPDATED', 'CANCELLED', 'PAYMENT', 'REVERSAL')", name="ck_payable_changes_action"),
        Index("ix_payable_changes_scope", "organization_id", "company_id", "payable_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payable_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(9), nullable=False)
    before_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    after_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PayableMovementRequest(Base):
    """Resultado mínimo idempotente; chave isolada por ator/empresa/operação."""
    __tablename__ = "payable_movement_requests"
    __table_args__ = (
        actor_member("actor_user_id", "fk_payable_requests_actor"),
        ForeignKeyConstraint(["organization_id", "company_id", "payable_id", "movement_id"],
            ["payable_movements.organization_id", "payable_movements.company_id", "payable_movements.payable_id", "payable_movements.id"],
            ondelete="RESTRICT", name="fk_payable_requests_movement"),
        CheckConstraint("operation IN ('PAYMENT', 'REVERSAL')", name="ck_payable_requests_operation"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="ck_payable_requests_hash"),
        CheckConstraint("title_revision > 0", name="ck_payable_requests_revision"),
    )
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    operation: Mapped[str] = mapped_column(String(8), primary_key=True)
    request_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payable_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    movement_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    title_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
