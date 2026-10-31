"""Adiciona sessões com token resumido, expiração e revogação.

Revision ID: ba72c81409ef
Revises: 9e3d7a51c286
"""

from alembic import op
import sqlalchemy as sa


revision = "ba72c81409ef"
down_revision = "9e3d7a51c286"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Cria o armazenamento de sessões sem emitir tokens iniciais."""

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_user_sessions_token_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_user_sessions_expiration"),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at", name="ck_user_sessions_revocation",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])


def downgrade() -> None:
    """Remove apenas sessões, preservando identidades e hashes de senha."""

    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
