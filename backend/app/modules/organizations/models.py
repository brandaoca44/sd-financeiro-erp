import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
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
        unique=True,
        index=True,
    )
    status: Mapped[CompanyStatus] = mapped_column(
        Enum(
            CompanyStatus,
            name="company_status",
        ),
        nullable=False,
        default=CompanyStatus.ACTIVE,
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