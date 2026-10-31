import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class OrganizationStatus(StrEnum):
    """Define os estados disponíveis para uma organização."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class CompanyStatus(StrEnum):
    """Define os estados disponíveis para uma empresa."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Organization(Base):
    """Representa o tenant e a fronteira de propriedade dos dados."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    status: Mapped[OrganizationStatus] = mapped_column(
        Enum(
            OrganizationStatus,
            name="organization_status",
        ),
        nullable=False,
        default=OrganizationStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    companies: Mapped[list["Company"]] = relationship(
        back_populates="organization",
    )


class Company(Base):
    """Representa uma entidade jurídica pertencente a uma organização."""

    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_companies_tenant_id"),
        Index("uq_companies_tenant_tax_id", "organization_id", "tax_id", unique=True),
        CheckConstraint("sd_is_valid_cnpj(tax_id)", name="ck_companies_cnpj"),
        CheckConstraint("legal_name = btrim(legal_name) AND length(legal_name) > 0", name="ck_companies_legal_name"),
        CheckConstraint("trade_name IS NULL OR (trade_name = btrim(trade_name) AND length(trade_name) > 0)", name="ck_companies_trade_name"),
        CheckConstraint("revision > 0", name="ck_companies_revision"),
    )

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    legal_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    trade_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    tax_id: Mapped[str] = mapped_column(
        String(14),
        nullable=False,
    )
    status: Mapped[CompanyStatus] = mapped_column(
        Enum(
            CompanyStatus,
            name="company_status",
        ),
        nullable=False,
        default=CompanyStatus.ACTIVE,
        server_default=CompanyStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(
        back_populates="companies",
    )


class CompanyChange(Base):
    """Trilha mínima de cadastro sem duplicar nomes e identificadores nos snapshots."""
    __tablename__ = "company_changes"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "company_id"], ["companies.organization_id", "companies.id"],
                            ondelete="RESTRICT", name="fk_company_changes_company"),
        CheckConstraint("action IN ('CREATED', 'UPDATED')", name="ck_company_changes_action"),
        Index("ix_company_changes_organization", "organization_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(12), nullable=False)
    before_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    after_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
