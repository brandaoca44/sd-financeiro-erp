"""Amplia somente o catálogo permitido, sem criar ou ativar concessões."""
from alembic import op
import sqlalchemy as sa

revision = "a18d5320cf97"
down_revision = "f07c4219be86"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_company_grants_permission", "company_permission_grants", type_="check")
    op.create_check_constraint("ck_company_grants_permission", "company_permission_grants",
        "permission_key IN ('companies.read', 'payables.read', 'payables.manage', 'payables.settle', 'payables.reverse')")
    op.drop_constraint("ck_company_permission_changes_action", "company_permission_changes", type_="check")
    op.create_check_constraint("ck_company_permission_changes_action", "company_permission_changes",
        "(action = 'COMPANY_READ_SET' AND permission_key = 'companies.read') OR (action = 'COMPANY_PERMISSION_SET' AND permission_key IN ('payables.read', 'payables.manage', 'payables.settle', 'payables.reverse'))")


def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE company_permission_grants, company_permission_changes IN ACCESS EXCLUSIVE MODE"))
    for table in ("company_permission_grants", "company_permission_changes"):
        if connection.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} WHERE permission_key <> 'companies.read')")).scalar():
            raise RuntimeError("Downgrade bloqueado: existem concessões ou histórico financeiro que devem ser preservados.")
    op.drop_constraint("ck_company_permission_changes_action", "company_permission_changes", type_="check")
    op.create_check_constraint("ck_company_permission_changes_action", "company_permission_changes", "action = 'COMPANY_READ_SET'")
    op.drop_constraint("ck_company_grants_permission", "company_permission_grants", type_="check")
    op.create_check_constraint("ck_company_grants_permission", "company_permission_grants", "permission_key = 'companies.read'")
