"""Estado de confirmação, MFA e desafios sem tokens em texto puro."""
import uuid
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, false, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class AccountSecurity(Base):
    __tablename__ = "account_security"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    registration_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cpf_encrypted: Mapped[str | None] = mapped_column(Text)
    cpf_digest: Mapped[str | None] = mapped_column(String(64), unique=True)
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    mfa_pending_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_last_step: Mapped[int] = mapped_column(Integer, nullable=False, default=-1, server_default="-1")
    recovery_hashes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (CheckConstraint("NOT mfa_enabled OR mfa_secret IS NOT NULL", name="ck_account_security_mfa"),)


class AccountAction(Base):
    __tablename__ = "account_actions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(12), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    credential_hash: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("purpose IN ('VERIFY', 'RESET', 'MFA_LOGIN')", name="ck_account_actions_purpose"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_account_actions_hash"),
        CheckConstraint("expires_at > created_at", name="ck_account_actions_expiration"),
    )
