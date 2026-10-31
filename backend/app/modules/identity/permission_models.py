"""Concessões explícitas por perfil, delegações limitadas e trilha administrativa."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

_ALLOWED = "permission_key IN ('organizations.read', 'identity.roles.read')"


class OrganizationRolePermission(Base):
    __tablename__ = "organization_role_permissions"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "role_id"], ["organization_roles.organization_id", "organization_roles.id"],
                            ondelete="RESTRICT", name="fk_role_permissions_role"),
        CheckConstraint(_ALLOWED, name="ck_role_permissions_known"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    permission_key: Mapped[str] = mapped_column(String(80), primary_key=True)


class OrganizationAccessDelegation(Base):
    __tablename__ = "organization_access_delegations"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_access_delegations_membership"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_access_delegations_status"),
        CheckConstraint("revision > 0 AND owner_revision > 0", name="ck_access_delegations_revision"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    granted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    owner_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="INACTIVE", server_default="INACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class OrganizationDelegationPermission(Base):
    __tablename__ = "organization_delegation_permissions"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "user_id"],
            ["organization_access_delegations.organization_id", "organization_access_delegations.user_id"],
            ondelete="RESTRICT", name="fk_delegation_permissions_delegation"),
        CheckConstraint(_ALLOWED, name="ck_delegation_permissions_known"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    permission_key: Mapped[str] = mapped_column(String(80), primary_key=True)


class OrganizationAccessChange(Base):
    """Snapshots mínimos de concessões; não recebe payloads livres do cliente."""
    __tablename__ = "organization_access_changes"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "role_id"], ["organization_roles.organization_id", "organization_roles.id"],
                            ondelete="RESTRICT", name="fk_access_changes_role"),
        ForeignKeyConstraint(["target_user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_access_changes_member"),
        CheckConstraint("action IN ('ROLE_CREATED', 'ROLE_UPDATED', 'ASSIGNMENT_SET', 'DELEGATION_SET', 'MEMBERSHIP_SET', 'LEGACY_READ_CONVERTED', 'LEGACY_READ_REVOKED')",
                        name="ck_access_changes_action"),
        Index("ix_access_changes_organization", "organization_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    before_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    after_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
