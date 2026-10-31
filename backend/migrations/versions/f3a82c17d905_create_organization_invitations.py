"""Cria convites sem atribuir usuários ou privilégios existentes.

Revision ID: f3a82c17d905
Revises: e7b1c90a42d3
"""

from alembic import op
import sqlalchemy as sa

revision = "f3a82c17d905"
down_revision = "e7b1c90a42d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("kind", sa.String(6), nullable=False),
        sa.Column("can_read_organization", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("issued_by_user_id", sa.UUID(), nullable=False),
        sa.Column("accepted_by_user_id", sa.UUID(), nullable=True),
        sa.Column("revoked_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_by_user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_invitations_accepted_membership"),
        sa.CheckConstraint("kind IN ('OWNER', 'MEMBER')", name="ck_invitations_kind"),
        sa.CheckConstraint("email = lower(btrim(email)) AND length(email) > 0", name="ck_invitations_email"),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_invitations_token_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_invitations_expiration"),
        sa.CheckConstraint("(accepted_at IS NULL) = (accepted_by_user_id IS NULL)", name="ck_invitations_acceptance"),
        sa.CheckConstraint("(revoked_at IS NULL) = (revoked_by_user_id IS NULL)", name="ck_invitations_revocation"),
        sa.CheckConstraint("accepted_at IS NULL OR (accepted_at >= created_at AND accepted_at < expires_at)",
                           name="ck_invitations_acceptance_time"),
        sa.CheckConstraint("revoked_at IS NULL OR revoked_at >= created_at", name="ck_invitations_revocation_time"),
        sa.CheckConstraint("accepted_at IS NULL OR revoked_at IS NULL", name="ck_invitations_terminal_state"),
        sa.CheckConstraint("kind <> 'OWNER' OR can_read_organization", name="ck_invitations_owner_read"),
    )
    op.create_index("ix_organization_invitations_organization_id", "organization_invitations", ["organization_id"])
    op.create_index("uq_invitations_pending_email", "organization_invitations", ["organization_id", "email"],
                    unique=True, postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"))
    op.create_index("uq_invitations_pending_owner", "organization_invitations", ["organization_id"],
                    unique=True, postgresql_where=sa.text("kind = 'OWNER' AND accepted_at IS NULL AND revoked_at IS NULL"))


def downgrade() -> None:
    op.drop_table("organization_invitations")
