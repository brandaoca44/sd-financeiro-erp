"""Fundação de contas a pagar; sem rotas ou concessões automáticas."""
from alembic import op
import sqlalchemy as sa

revision = "f07c4219be86"
down_revision = "e96b2130ad74"
branch_labels = None
depends_on = None

def upgrade():
    op.execute(sa.text("""
CREATE TABLE payables (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    company_id UUID NOT NULL,
    description VARCHAR(300) NOT NULL,
    amount NUMERIC NOT NULL,
    currency VARCHAR(3) DEFAULT 'BRL' NOT NULL,
    issue_date DATE NOT NULL,
    due_date DATE NOT NULL,
    status VARCHAR(9) DEFAULT 'OPEN' NOT NULL,
    revision INTEGER DEFAULT '1' NOT NULL,
    created_by_user_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_payables_company FOREIGN KEY(organization_id, company_id) REFERENCES companies (organization_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_payables_creator FOREIGN KEY(created_by_user_id, organization_id) REFERENCES organization_memberships (user_id, organization_id) ON DELETE RESTRICT,
    CONSTRAINT uq_payables_scope UNIQUE (organization_id, company_id, id),
    CONSTRAINT ck_payables_amount CHECK (amount > 0 AND amount <= 9999999999999999.99 AND scale(amount) <= 2),
    CONSTRAINT ck_payables_currency CHECK (currency = 'BRL'),
    CONSTRAINT ck_payables_status CHECK (status IN ('OPEN', 'CANCELLED')),
    CONSTRAINT ck_payables_revision CHECK (revision > 0),
    CONSTRAINT ck_payables_description CHECK (description = btrim(description) AND length(description) > 0),
    CONSTRAINT ck_payables_dates CHECK (isfinite(issue_date) AND isfinite(due_date) AND due_date >= issue_date)
)
"""))
    op.execute(sa.text("""
CREATE INDEX ix_payables_scope_due ON payables (organization_id, company_id, due_date, id)
"""))
    op.execute(sa.text("""
CREATE TABLE payable_movements (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    company_id UUID NOT NULL,
    payable_id UUID NOT NULL,
    kind VARCHAR(8) NOT NULL,
    amount NUMERIC NOT NULL,
    occurred_on DATE NOT NULL,
    reverses_id UUID,
    actor_user_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_payable_movements_title FOREIGN KEY(organization_id, company_id, payable_id) REFERENCES payables (organization_id, company_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_payable_movements_actor FOREIGN KEY(actor_user_id, organization_id) REFERENCES organization_memberships (user_id, organization_id) ON DELETE RESTRICT,
    CONSTRAINT uq_payable_movements_scope UNIQUE (organization_id, company_id, payable_id, id),
    CONSTRAINT fk_payable_movements_reversal FOREIGN KEY(organization_id, company_id, payable_id, reverses_id) REFERENCES payable_movements (organization_id, company_id, payable_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_payable_movements_reversal UNIQUE (reverses_id),
    CONSTRAINT ck_payable_movements_amount CHECK (amount > 0 AND amount <= 9999999999999999.99 AND scale(amount) <= 2),
    CONSTRAINT ck_payable_movements_kind CHECK ((kind = 'PAYMENT' AND reverses_id IS NULL) OR (kind = 'REVERSAL' AND reverses_id IS NOT NULL AND reverses_id <> id)),
    CONSTRAINT ck_payable_movements_date CHECK (isfinite(occurred_on))
)
"""))
    op.execute(sa.text("""
CREATE INDEX ix_payable_movements_scope ON payable_movements (organization_id, company_id, payable_id, created_at)
"""))
    op.execute(sa.text("""
CREATE TABLE payable_changes (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    company_id UUID NOT NULL,
    payable_id UUID NOT NULL,
    actor_user_id UUID NOT NULL,
    action VARCHAR(9) NOT NULL,
    before_state JSONB NOT NULL,
    after_state JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_payable_changes_title FOREIGN KEY(organization_id, company_id, payable_id) REFERENCES payables (organization_id, company_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_payable_changes_actor FOREIGN KEY(actor_user_id, organization_id) REFERENCES organization_memberships (user_id, organization_id) ON DELETE RESTRICT,
    CONSTRAINT ck_payable_changes_action CHECK (action IN ('CREATED', 'UPDATED', 'CANCELLED', 'PAYMENT', 'REVERSAL'))
)
"""))
    op.execute(sa.text("""
CREATE INDEX ix_payable_changes_scope ON payable_changes (organization_id, company_id, payable_id, created_at)
"""))

def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE payables, payable_movements, payable_changes IN ACCESS EXCLUSIVE MODE"))
    for table in ("payables", "payable_movements", "payable_changes"):
        if connection.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Downgrade bloqueado: existem registros financeiros que devem ser preservados.")
    op.drop_table("payable_changes")
    op.drop_table("payable_movements")
    op.drop_table("payables")
