"""Versiona vínculos e permite auditar mudanças de status sem alterar concessões.

Revision ID: b92f8d06e4a1
Revises: a81e73c405bf
"""

from alembic import op
import sqlalchemy as sa

revision = "b92f8d06e4a1"
down_revision = "a81e73c405bf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_memberships", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_memberships_revision", "organization_memberships", "revision > 0")
    op.drop_constraint("ck_access_changes_action", "organization_access_changes", type_="check")
    op.create_check_constraint("ck_access_changes_action", "organization_access_changes",
        "action IN ('ROLE_CREATED', 'ROLE_UPDATED', 'ASSIGNMENT_SET', 'DELEGATION_SET', 'MEMBERSHIP_SET')")


def downgrade() -> None:
    # Histórico de segurança não é apagado para permitir um downgrade incompatível.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM organization_access_changes WHERE action = 'MEMBERSHIP_SET')")).scalar():
        raise RuntimeError("Downgrade bloqueado: existe histórico de ciclo de vida de vínculos.")
    op.drop_constraint("ck_access_changes_action", "organization_access_changes", type_="check")
    op.create_check_constraint("ck_access_changes_action", "organization_access_changes",
        "action IN ('ROLE_CREATED', 'ROLE_UPDATED', 'ASSIGNMENT_SET', 'DELEGATION_SET')")
    op.drop_constraint("ck_memberships_revision", "organization_memberships", type_="check")
    op.drop_column("organization_memberships", "revision")
