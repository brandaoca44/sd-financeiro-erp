"""Persiste convites de uso único e sua trilha mínima de concessão por tenant."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, false, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        ForeignKeyConstraint(["accepted_by_user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_invitations_accepted_membership"),
        CheckConstraint("kind IN ('OWNER', 'MEMBER')", name="ck_invitations_kind"),
        CheckConstraint("email = lower(btrim(email)) AND length(email) > 0", name="ck_invitations_email"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_invitations_token_hash"),
        CheckConstraint("expires_at > created_at", name="ck_invitations_expiration"),
        CheckConstraint("(accepted_at IS NULL) = (accepted_by_user_id IS NULL)", name="ck_invitations_acceptance"),
        CheckConstraint("(revoked_at IS NULL) = (revoked_by_user_id IS NULL)", name="ck_invitations_revocation"),
        CheckConstraint("accepted_at IS NULL OR (accepted_at >= created_at AND accepted_at < expires_at)",
                        name="ck_invitations_acceptance_time"),
        CheckConstraint("revoked_at IS NULL OR revoked_at >= created_at", name="ck_invitations_revocation_time"),
        CheckConstraint("accepted_at IS NULL OR revoked_at IS NULL", name="ck_invitations_terminal_state"),
        CheckConstraint("kind <> 'OWNER' OR can_read_organization", name="ck_invitations_owner_read"),
        Index("uq_invitations_pending_email", "organization_id", "email", unique=True,
              postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL")),
        Index("uq_invitations_pending_owner", "organization_id", unique=True,
              postgresql_where=text("kind = 'OWNER' AND accepted_at IS NULL AND revoked_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    kind: Mapped[str] = mapped_column(String(6), nullable=False)
    can_read_organization: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, deferred=True)
    issued_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
    )
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
