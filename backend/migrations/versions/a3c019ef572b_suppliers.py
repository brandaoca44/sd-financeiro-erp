"""Adiciona fornecedores vinculados à empresa."""
import sqlalchemy as sa
from alembic import op

revision = "a3c019ef572b"
down_revision = "f94d672b8c21"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "finance_suppliers",
        sa.Column("organization_id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, primary_key=True),
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "company_id"], ["companies.organization_id", "companies.id"],
                                name="fk_finance_suppliers_company", ondelete="RESTRICT"),
    )
    op.add_column("expenses", sa.Column("supplier_id", sa.Uuid))
    op.create_foreign_key("fk_expenses_supplier", "expenses", "finance_suppliers",
                          ["organization_id", "company_id", "supplier_id"],
                          ["organization_id", "company_id", "id"], ondelete="RESTRICT")


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE expenses, finance_suppliers IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM finance_suppliers)")):
        raise RuntimeError("Existem fornecedores registrados.")
    op.drop_constraint("fk_expenses_supplier", "expenses", type_="foreignkey")
    op.drop_column("expenses", "supplier_id")
    op.drop_table("finance_suppliers")
