"""Contas financeiras empresariais e saldos iniciais preservados."""
import sqlalchemy as sa
from alembic import op
revision='c9e2047d81af'
down_revision='b57329d81c04'
branch_labels=None
depends_on=None
OLD="'payables.read', 'payables.manage', 'payables.settle', 'payables.reverse', 'billing.read', 'billing.manage', 'billing.receive', 'billing.reverse', 'people.read', 'people.create', 'people.update', 'people.terminate', 'people.documents', 'people.compensation', 'people.bank'"
NEW="'payables.read', 'payables.manage', 'payables.settle', 'payables.reverse', 'billing.read', 'billing.manage', 'billing.receive', 'billing.reverse', 'people.read', 'people.create', 'people.update', 'people.terminate', 'people.documents', 'people.compensation', 'people.bank', 'accounts.read', 'accounts.manage', 'accounts.bank'"

def grants(keys):
    op.drop_constraint('ck_company_grants_permission','company_permission_grants',type_='check')
    op.create_check_constraint('ck_company_grants_permission','company_permission_grants',f"permission_key IN ('companies.read', {keys})")
    op.drop_constraint('ck_company_permission_changes_action','company_permission_changes',type_='check')
    op.create_check_constraint('ck_company_permission_changes_action','company_permission_changes',f"(action = 'COMPANY_READ_SET' AND permission_key = 'companies.read') OR (action = 'COMPANY_PERMISSION_SET' AND permission_key IN ({keys}))")

def audit(new):
    op.drop_constraint('ck_operation_events_domain','operation_events',type_='check')
    op.create_check_constraint('ck_operation_events_domain','operation_events',"domain IN ('BILLING', 'PEOPLE', 'ACCOUNTS')" if new else "domain IN ('BILLING', 'PEOPLE')")
    op.drop_constraint('ck_operation_events_resource','operation_events',type_='check')
    op.create_check_constraint('ck_operation_events_resource','operation_events',"resource_type IN ('BILLING', 'CUSTOMER', 'RECEIPT', 'COLLABORATOR', 'ACCOUNT')" if new else "resource_type IN ('BILLING', 'CUSTOMER', 'RECEIPT', 'COLLABORATOR')")

def upgrade():
    grants(NEW);audit(True)
    op.create_table('financial_accounts',
        sa.Column('organization_id',sa.Uuid,primary_key=True),sa.Column('company_id',sa.Uuid,primary_key=True),sa.Column('id',sa.Uuid,primary_key=True),
        sa.Column('name',sa.String(100),nullable=False),sa.Column('kind',sa.String(10),nullable=False),
        sa.Column('currency',sa.String(3),nullable=False,server_default='BRL'),
        sa.Column('opening_balance',sa.Numeric,nullable=False),sa.Column('opening_date',sa.Date,nullable=False),sa.Column('encrypted_bank',sa.Text),
        sa.Column('status',sa.String(8),nullable=False,server_default='ACTIVE'),sa.Column('revision',sa.Integer,nullable=False,server_default='1'),
        sa.Column('created_by_user_id',sa.Uuid,nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id','company_id'],['companies.organization_id','companies.id'],name='fk_financial_accounts_company',ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by_user_id','organization_id'],['organization_memberships.user_id','organization_memberships.organization_id'],name='fk_financial_accounts_creator',ondelete='RESTRICT'),
        sa.CheckConstraint("kind IN ('BANK','CASH','PAYMENT')",name='ck_financial_accounts_kind'),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')",name='ck_financial_accounts_status'),
        sa.CheckConstraint("currency = 'BRL'",name='ck_financial_accounts_currency'),
        sa.CheckConstraint('revision > 0',name='ck_financial_accounts_revision'),
        sa.CheckConstraint("opening_balance <> 'NaN'::numeric AND abs(opening_balance) <= 9999999999999999.99 AND scale(opening_balance) <= 2",name='ck_financial_accounts_opening'),
        sa.CheckConstraint('isfinite(opening_date)',name='ck_financial_accounts_date'))
    op.execute("""CREATE FUNCTION protect_account_opening() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Financial accounts cannot be deleted'; END IF;
      IF ROW(NEW.organization_id,NEW.company_id,NEW.id,NEW.kind,NEW.currency,NEW.opening_balance,NEW.opening_date,NEW.created_by_user_id,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.organization_id,OLD.company_id,OLD.id,OLD.kind,OLD.currency,OLD.opening_balance,OLD.opening_date,OLD.created_by_user_id,OLD.created_at)
      THEN RAISE EXCEPTION 'Initial account position cannot be changed'; END IF; RETURN NEW; END; $$""")
    op.execute('CREATE TRIGGER financial_account_opening BEFORE UPDATE OR DELETE ON financial_accounts FOR EACH ROW EXECUTE FUNCTION protect_account_opening()')

def downgrade():
    op.execute('LOCK TABLE financial_accounts, operation_events, company_permission_grants, company_permission_changes IN ACCESS EXCLUSIVE MODE')
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM financial_accounts) OR EXISTS (SELECT 1 FROM operation_events WHERE domain='ACCOUNTS') OR EXISTS (SELECT 1 FROM company_permission_grants WHERE permission_key LIKE 'accounts.%')")):
        raise RuntimeError('Existem contas ou concessões registradas; preserve o histórico antes do downgrade.')
    op.drop_table('financial_accounts');op.execute('DROP FUNCTION protect_account_opening()')
    audit(False);grants(OLD)
