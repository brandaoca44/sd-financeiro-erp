"""Permite auditoria da revisão de flags sem converter concessões automaticamente.

Revision ID: c74e901a6bd2
Revises: b92f8d06e4a1
"""

from alembic import op
import sqlalchemy as sa

revision = "c74e901a6bd2"
down_revision = "b92f8d06e4a1"
branch_labels = None
depends_on = None

_PREVIOUS = "action IN ('ROLE_CREATED', 'ROLE_UPDATED', 'ASSIGNMENT_SET', 'DELEGATION_SET', 'MEMBERSHIP_SET')"
_CURRENT = "action IN ('ROLE_CREATED', 'ROLE_UPDATED', 'ASSIGNMENT_SET', 'DELEGATION_SET', 'MEMBERSHIP_SET', 'LEGACY_READ_CONVERTED', 'LEGACY_READ_REVOKED')"


def upgrade() -> None:
    op.drop_constraint("ck_access_changes_action", "organization_access_changes", type_="check")
    op.create_check_constraint("ck_access_changes_action", "organization_access_changes", _CURRENT)


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM organization_access_changes WHERE action IN ('LEGACY_READ_CONVERTED', 'LEGACY_READ_REVOKED'))")).scalar():
        raise RuntimeError("Downgrade bloqueado: existe histórico de revisão de concessões antigas.")
    op.drop_constraint("ck_access_changes_action", "organization_access_changes", type_="check")
    op.create_check_constraint("ck_access_changes_action", "organization_access_changes", _PREVIOUS)
