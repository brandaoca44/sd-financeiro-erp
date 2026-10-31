"""Registra mudanças de propriedade sem armazenar segredos.

Revision ID: e7b1c90a42d3
Revises: d2a6f09b84c1
"""

from alembic import op
import sqlalchemy as sa

revision = "e7b1c90a42d3"
down_revision = "d2a6f09b84c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_ownership_changes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("previous_user_id", sa.UUID(), nullable=True),
        sa.Column("new_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["previous_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["new_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("previous_user_id IS NULL OR previous_user_id <> new_user_id",
                           name="ck_ownership_changes_distinct_users"),
    )
    op.create_index("ix_ownership_changes_organization", "organization_ownership_changes",
                    ["organization_id", "created_at"])


def downgrade() -> None:
    op.drop_table("organization_ownership_changes")
