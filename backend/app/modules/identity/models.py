"""Define identidades e vínculos mínimos, sem implementar autenticação."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, SmallInteger, String, false, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserStatus(StrEnum):
    """Define se a identidade está habilitada para uso."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class MembershipStatus(StrEnum):
    """Define se o vínculo organizacional está habilitado."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class User(Base):
    """Identidade global; permissão de provisionamento não concede acesso a tenants."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_users_name_not_blank"),
        CheckConstraint(
            "email = btrim(email) AND length(email) > 0",
            name="ck_users_email_trimmed_not_blank",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"), nullable=False,
        default=UserStatus.INACTIVE, server_default=UserStatus.INACTIVE.value,
    )
    can_provision_organizations: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


Index("uq_users_email_case_insensitive", func.lower(User.email), unique=True)


class OrganizationMembership(Base):
    """Vincula usuário a tenant sem conceder permissões por padrão."""

    __tablename__ = "organization_memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"),
        primary_key=True, index=True,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        Enum(MembershipStatus, name="membership_status"), nullable=False,
        default=MembershipStatus.INACTIVE, server_default=MembershipStatus.INACTIVE.value,
    )
    can_read_organization: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class UserPasswordCredential(Base):
    """Armazena somente hash de senha, separado de dados e permissões do usuário."""

    __tablename__ = "user_password_credentials"
    __table_args__ = (
        CheckConstraint(
            "password_hash LIKE '$argon2id$%' AND length(password_hash) BETWEEN 50 AND 512",
            name="ck_user_password_credentials_argon2id",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False, deferred=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class UserSession(Base):
    """Persiste o hash de um token opaco, sua validade e eventual revogação."""

    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_user_sessions_token_hash"),
        CheckConstraint("expires_at > created_at", name="ck_user_sessions_expiration"),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at", name="ck_user_sessions_revocation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, deferred=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformBootstrap(Base):
    """Registra uma única inicialização, independente de alterações futuras no operador."""

    __tablename__ = "platform_bootstrap"
    __table_args__ = (CheckConstraint("id = 1", name="ck_platform_bootstrap_singleton"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
