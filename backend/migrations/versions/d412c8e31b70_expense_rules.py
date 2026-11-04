"""Armazena regras mensais de despesas por empresa."""
import sqlalchemy as sa
from alembic import op

revision = "d412c8e31b70"
down_revision = "a3c019ef572b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "expense_rules",
        sa.Column("organization_id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, primary_key=True),
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("supplier_id", sa.Uuid, nullable=False),
        sa.Column("due_day", sa.Numeric(2, 0), nullable=False),
        sa.Column("fixed_amount", sa.Numeric),
        sa.ForeignKeyConstraint(
            ["organization_id", "company_id", "supplier_id"],
            ["finance_suppliers.organization_id", "finance_suppliers.company_id", "finance_suppliers.id"],
            name="fk_expense_rules_supplier", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("due_day IN (5, 10, 15, 20, 25, 30)", name="ck_expense_rules_due_day"),
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE expense_rules IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM expense_rules)")):
        raise RuntimeError("Existem regras de despesas registradas.")
    op.drop_table("expense_rules")
