"""Auditoria de faturamento e colaboradores sem payloads sensíveis."""
import sqlalchemy as sa
from alembic import op
revision = 'b57329d81c04'
down_revision = 'a14c5e93b207'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('operation_events',
        sa.Column('id', sa.Uuid, primary_key=True),
        sa.Column('organization_id', sa.Uuid, nullable=False), sa.Column('company_id', sa.Uuid, nullable=False),
        sa.Column('actor_user_id', sa.Uuid, nullable=False), sa.Column('domain', sa.String(12), nullable=False),
        sa.Column('resource_type', sa.String(16), nullable=False), sa.Column('resource_id', sa.Uuid, nullable=False),
        sa.Column('action', sa.String(12), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id','company_id'],['companies.organization_id','companies.id'],name='fk_operation_events_company',ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['actor_user_id','organization_id'],['organization_memberships.user_id','organization_memberships.organization_id'],name='fk_operation_events_actor',ondelete='RESTRICT'),
        sa.CheckConstraint("domain IN ('BILLING', 'PEOPLE')",name='ck_operation_events_domain'),
        sa.CheckConstraint("action IN ('CREATED', 'UPDATED', 'RECEIVED', 'REVERSAL', 'TERMINATED')",name='ck_operation_events_action'),
        sa.CheckConstraint("resource_type IN ('BILLING', 'CUSTOMER', 'RECEIPT', 'COLLABORATOR')",name='ck_operation_events_resource'))
    op.create_index('ix_expense_changes_timeline','expense_changes',['organization_id','company_id','created_at','id'])
    op.create_index('ix_payable_changes_timeline','payable_changes',['organization_id','company_id','created_at','id'])
    op.create_index('ix_operation_events_scope_time','operation_events',['organization_id','company_id','created_at','id'])
    op.execute("""CREATE FUNCTION protect_operation_events() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Audit records cannot be modified or deleted'; END; $$""")
    op.execute('CREATE TRIGGER operation_events_append_only BEFORE UPDATE OR DELETE ON operation_events FOR EACH ROW EXECUTE FUNCTION protect_operation_events()')

def downgrade():
    op.execute('LOCK TABLE operation_events IN ACCESS EXCLUSIVE MODE')
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM operation_events)')):
        raise RuntimeError('Existem eventos de auditoria; downgrade bloqueado para preservar o histórico.')
    op.drop_index('ix_expense_changes_timeline',table_name='expense_changes')
    op.drop_index('ix_payable_changes_timeline',table_name='payable_changes')
    op.drop_table('operation_events')
    op.execute('DROP FUNCTION protect_operation_events()')
