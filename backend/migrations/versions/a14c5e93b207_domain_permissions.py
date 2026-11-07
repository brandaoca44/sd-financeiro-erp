"""Independent billing and people grants; no automatic grants to members."""
from alembic import op
from sqlalchemy import text
revision = "a14c5e93b207"
down_revision = "f6810c9ad245"
branch_labels = None
depends_on = None
OLD = "'payables.read', 'payables.manage', 'payables.settle', 'payables.reverse'"
NEW = "'payables.read', 'payables.manage', 'payables.settle', 'payables.reverse', 'billing.read', 'billing.manage', 'billing.receive', 'billing.reverse', 'people.read', 'people.create', 'people.update', 'people.terminate', 'people.documents', 'people.compensation', 'people.bank'"

def constraints(keys):
    op.drop_constraint("ck_company_grants_permission", "company_permission_grants", type_="check")
    op.create_check_constraint("ck_company_grants_permission", "company_permission_grants", f"permission_key IN ('companies.read', {keys})")
    op.drop_constraint("ck_company_permission_changes_action", "company_permission_changes", type_="check")
    op.create_check_constraint("ck_company_permission_changes_action", "company_permission_changes", f"(action = 'COMPANY_READ_SET' AND permission_key = 'companies.read') OR (action = 'COMPANY_PERMISSION_SET' AND permission_key IN ({keys}))")

def upgrade():
    constraints(NEW)

def downgrade():
    op.execute("LOCK TABLE company_permission_grants, company_permission_changes IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(text(f"SELECT EXISTS (SELECT 1 FROM company_permission_grants WHERE permission_key NOT IN ('companies.read', {OLD}))")):
        raise RuntimeError("New permission grants exist; preserve their audit history before downgrading.")
    constraints(OLD)
