"""Vincula clientes por empresa ao faturamento, preservando registros anteriores."""
import sqlalchemy as sa
from alembic import op

revision = "91ec04a37bf2"
down_revision = "6f83ac210d72"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_customers",
        sa.Column("organization_id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, primary_key=True),
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "company_id"], ["companies.organization_id", "companies.id"],
                                name="fk_billing_customers_company", ondelete="RESTRICT"),
    )
    op.add_column("service_billings", sa.Column("customer_id", sa.Uuid))
    op.create_foreign_key("fk_service_billings_customer", "service_billings", "billing_customers",
                          ["organization_id", "company_id", "customer_id"], ["organization_id", "company_id", "id"],
                          ondelete="RESTRICT")


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE billing_customers, service_billings IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM billing_customers)")):
        raise RuntimeError("Existem clientes cadastrados.")
    op.drop_constraint("fk_service_billings_customer", "service_billings", type_="foreignkey")
    op.drop_column("service_billings", "customer_id")
    op.drop_table("billing_customers")
