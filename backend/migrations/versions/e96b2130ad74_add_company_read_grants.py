"""Persiste acesso explícito por empresa sem semear permissões de clientes.

Revision ID: e96b2130ad74
Revises: d85fa1049ce3
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e96b2130ad74"
down_revision = "d85fa1049ce3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_permission_grants",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("permission_key", sa.String(80), nullable=False, server_default="companies.read"),
        sa.Column("status", sa.String(8), nullable=False, server_default="INACTIVE"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("organization_id", "company_id", "user_id", "permission_key"),
        sa.ForeignKeyConstraint(["organization_id", "company_id"], ["companies.organization_id", "companies.id"],
                                 ondelete="RESTRICT", name="fk_company_grants_company"),
        sa.ForeignKeyConstraint(["user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_company_grants_member"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("permission_key = 'companies.read'", name="ck_company_grants_permission"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_company_grants_status"),
        sa.CheckConstraint("revision > 0", name="ck_company_grants_revision"),
    )
    op.create_index("ix_company_grants_member", "company_permission_grants", ["organization_id", "user_id"])
    op.create_table(
        "company_permission_changes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("permission_key", sa.String(80), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("before_state", postgresql.JSONB(), nullable=False),
        sa.Column("after_state", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id", "company_id", "user_id", "permission_key"],
            ["company_permission_grants.organization_id", "company_permission_grants.company_id",
             "company_permission_grants.user_id", "company_permission_grants.permission_key"],
            ondelete="RESTRICT", name="fk_company_permission_changes_grant"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("action = 'COMPANY_READ_SET'", name="ck_company_permission_changes_action"),
    )
    op.create_index("ix_company_permission_changes_scope", "company_permission_changes", ["organization_id", "company_id", "created_at"])


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE company_permission_grants, company_permission_changes IN ACCESS EXCLUSIVE MODE"))
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM company_permission_changes)")).scalar():
        raise RuntimeError("Downgrade bloqueado: existe histórico de concessões por empresa.")
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM company_permission_grants)")).scalar():
        raise RuntimeError("Downgrade bloqueado: existem concessões por empresa que exigem revisão.")
    op.drop_table("company_permission_changes")
    op.drop_table("company_permission_grants")
