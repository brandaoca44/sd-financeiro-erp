"""Registra recebimentos vinculados ao faturamento."""
import sqlalchemy as sa
from alembic import op

revision = "6f83ac210d72"
down_revision = "bd13ad614e7a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_receipts",
        sa.Column("organization_id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, primary_key=True),
        sa.Column("billing_id", sa.Uuid, primary_key=True),
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("amount", sa.Numeric, nullable=False),
        sa.Column("received_on", sa.Date, nullable=False),
        sa.Column("reversed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["organization_id", "company_id", "billing_id"],
                                ["service_billings.organization_id", "service_billings.company_id", "service_billings.id"],
                                name="fk_billing_receipts_billing", ondelete="RESTRICT"),
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE billing_receipts IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM billing_receipts)")):
        raise RuntimeError("Existem recebimentos registrados.")
    op.drop_table("billing_receipts")
