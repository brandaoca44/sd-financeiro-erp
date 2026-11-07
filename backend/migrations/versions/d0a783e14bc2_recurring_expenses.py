"""Agenda competências e preserva ocorrências mensais das despesas."""
import sqlalchemy as sa
from alembic import op

revision = "d0a783e14bc2"
down_revision = "71f1b83ac590"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("expense_rules", sa.Column("authorized_by_user_id", sa.Uuid))
    op.add_column("expense_rules", sa.Column("next_month", sa.Date))
    op.execute("UPDATE expense_rules SET next_month = date_trunc('month', CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date")
    op.alter_column("expense_rules", "next_month", nullable=False)
    op.create_foreign_key("fk_expense_rules_authorizer", "expense_rules", "organization_memberships",
                          ["authorized_by_user_id", "organization_id"], ["user_id", "organization_id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_expense_rules_next_month", "expense_rules", "EXTRACT(DAY FROM next_month) = 1")
    op.create_table(
        "expense_occurrences",
        sa.Column("organization_id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, primary_key=True),
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("rule_id", sa.Uuid, nullable=False),
        sa.Column("competence", sa.Date, nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("supplier_id", sa.Uuid, nullable=False),
        sa.Column("supplier", sa.String(150), nullable=False),
        sa.Column("amount", sa.Numeric),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("document_type", sa.String(20)),
        sa.Column("document_reference", sa.String(100)),
        sa.Column("expense_id", sa.Uuid),
        sa.UniqueConstraint("organization_id", "company_id", "rule_id", "competence", name="uq_expense_occurrence_month"),
        sa.ForeignKeyConstraint(["organization_id", "company_id", "rule_id"],
            ["expense_rules.organization_id", "expense_rules.company_id", "expense_rules.id"],
            name="fk_expense_occurrences_rule", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id", "company_id", "supplier_id"],
            ["finance_suppliers.organization_id", "finance_suppliers.company_id", "finance_suppliers.id"],
            name="fk_expense_occurrences_supplier", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id", "company_id", "expense_id"],
            ["expenses.organization_id", "expenses.company_id", "expenses.id"],
            name="fk_expense_occurrences_expense", ondelete="RESTRICT"),
        sa.CheckConstraint("EXTRACT(DAY FROM competence) = 1 AND due_date >= competence", name="ck_expense_occurrence_dates"),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name="ck_expense_occurrence_amount"),
        sa.CheckConstraint("expense_id IS NULL OR amount IS NOT NULL", name="ck_expense_occurrence_confirmed"),
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE expense_occurrences, expense_rules IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM expense_occurrences)")):
        raise RuntimeError("Existem ocorrências mensais de despesas.")
    op.drop_table("expense_occurrences")
    op.drop_constraint("ck_expense_rules_next_month", "expense_rules", type_="check")
    op.drop_constraint("fk_expense_rules_authorizer", "expense_rules", type_="foreignkey")
    op.drop_column("expense_rules", "next_month")
    op.drop_column("expense_rules", "authorized_by_user_id")
