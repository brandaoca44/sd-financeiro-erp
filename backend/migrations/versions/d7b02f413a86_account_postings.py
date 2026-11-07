"""Vinculação explícita das movimentações às contas da empresa."""
import sqlalchemy as sa
from alembic import op
revision='d7b02f413a86'
down_revision='c9e2047d81af'
branch_labels=None
depends_on=None

def upgrade():
    for table,name in [('payable_movements','fk_payable_movement_account'),('billing_receipts','fk_billing_receipt_account')]:
        op.add_column(table,sa.Column('financial_account_id',sa.Uuid))
        op.create_foreign_key(name,table,'financial_accounts',['organization_id','company_id','financial_account_id'],['organization_id','company_id','id'],ondelete='RESTRICT')
    op.add_column('billing_receipts',sa.Column('reversed_on',sa.Date))
    op.execute("""CREATE FUNCTION protect_movement_account() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN IF OLD.financial_account_id IS NOT NULL AND NEW.financial_account_id IS DISTINCT FROM OLD.financial_account_id
      THEN RAISE EXCEPTION 'Movement account cannot be reassigned'; END IF; RETURN NEW; END; $$""")
    for table in ('payable_movements','billing_receipts'):
        op.execute(f'CREATE TRIGGER movement_account_immutable BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_movement_account()')

def downgrade():
    op.execute('LOCK TABLE payable_movements,billing_receipts IN ACCESS EXCLUSIVE MODE')
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM payable_movements WHERE financial_account_id IS NOT NULL) OR EXISTS(SELECT 1 FROM billing_receipts WHERE financial_account_id IS NOT NULL OR reversed_on IS NOT NULL)')):
        raise RuntimeError('Existem vínculos ou datas de estorno registrados.')
    for table,name in [('payable_movements','fk_payable_movement_account'),('billing_receipts','fk_billing_receipt_account')]:
        op.execute(f'DROP TRIGGER movement_account_immutable ON {table}')
        op.drop_constraint(name,table,type_='foreignkey');op.drop_column(table,'financial_account_id')
    op.execute('DROP FUNCTION protect_movement_account()')
    op.drop_column('billing_receipts','reversed_on')
