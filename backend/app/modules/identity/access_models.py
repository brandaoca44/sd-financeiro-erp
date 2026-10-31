"""Persiste propriedade, perfis e atribuições por tenant sem conceder acesso implícito."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint, DateTime, Enum, ForeignKey, ForeignKeyConstraint,
    Index, String, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class RoleCategory(StrEnum):
    """Classifica o perfil sem estabelecer herança ou nível de privilégio."""

    COLLABORATOR = "COLLABORATOR"
    ASSISTANT = "ASSISTANT"
    LEAD = "LEAD"
    MANAGER = "MANAGER"
    COORDINATOR = "COORDINATOR"
    DIRECTOR = "DIRECTOR"
    CEO = "CEO"
    CUSTOM = "CUSTOM"


class RoleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class RoleAssignmentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class OrganizationOwnership(Base):
    """Registra no máximo um proprietário por organização e exige vínculo existente."""

    __tablename__ = "organization_ownerships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_organization_ownerships_membership",
        ),
        Index("ix_organization_ownerships_user_id", "user_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class OrganizationRole(Base):
    """Perfil do cliente, independente do cargo e sem permissões automáticas."""

    __tablename__ = "organization_roles"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_organization_roles_tenant_id"),
        CheckConstraint(
            "name = btrim(name) AND length(name) > 0", name="ck_organization_roles_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[RoleCategory] = mapped_column(
        Enum(RoleCategory, name="organization_role_category"), nullable=False,
        default=RoleCategory.CUSTOM, server_default=RoleCategory.CUSTOM.value,
    )
    status: Mapped[RoleStatus] = mapped_column(
        Enum(RoleStatus, name="organization_role_status"), nullable=False,
        default=RoleStatus.INACTIVE, server_default=RoleStatus.INACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


Index("uq_organization_roles_name", OrganizationRole.organization_id, func.lower(OrganizationRole.name), unique=True)


class OrganizationRoleAssignment(Base):
    """Associa perfil e vínculo do mesmo tenant, sem escopo empresarial implícito."""

    __tablename__ = "organization_role_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_organization_role_assignments_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "role_id"],
            ["organization_roles.organization_id", "organization_roles.id"],
            ondelete="RESTRICT", name="fk_organization_role_assignments_role",
        ),
        Index("ix_organization_role_assignments_role", "organization_id", "role_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    status: Mapped[RoleAssignmentStatus] = mapped_column(
        Enum(RoleAssignmentStatus, name="organization_role_assignment_status"), nullable=False,
        default=RoleAssignmentStatus.INACTIVE, server_default=RoleAssignmentStatus.INACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
