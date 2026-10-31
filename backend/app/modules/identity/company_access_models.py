"""Concessões diretas por empresa e vínculo, sem escopos globais ou futuros."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class CompanyPermissionGrant(Base):
    __tablename__ = "company_permission_grants"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "company_id"], ["companies.organization_id", "companies.id"],
                            ondelete="RESTRICT", name="fk_company_grants_company"),
        ForeignKeyConstraint(["user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_company_grants_member"),
        CheckConstraint("permission_key = 'companies.read'", name="ck_company_grants_permission"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_company_grants_status"),
        CheckConstraint("revision > 0", name="ck_company_grants_revision"),
        Index("ix_company_grants_member", "organization_id", "user_id"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    permission_key: Mapped[str] = mapped_column(String(80), primary_key=True, default="companies.read", server_default="companies.read")
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="INACTIVE", server_default="INACTIVE")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class CompanyPermissionChange(Base):
    __tablename__ = "company_permission_changes"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "company_id", "user_id", "permission_key"],
            ["company_permission_grants.organization_id", "company_permission_grants.company_id",
             "company_permission_grants.user_id", "company_permission_grants.permission_key"],
            ondelete="RESTRICT", name="fk_company_permission_changes_grant"),
        CheckConstraint("action = 'COMPANY_READ_SET'", name="ck_company_permission_changes_action"),
        Index("ix_company_permission_changes_scope", "organization_id", "company_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    permission_key: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    before_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    after_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
