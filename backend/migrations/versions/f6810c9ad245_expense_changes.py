"""Revisão e cancelamento de despesas com histórico transacional."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "f6810c9ad245"
down_revision = "d0a783e14bc2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("expenses", sa.Column("revision", sa.Integer, nullable=False, server_default="1"))
    op.add_column("expenses", sa.Column("status", sa.String(12), nullable=False, server_default="OPEN"))
    op.execute("""
        UPDATE expenses AS e SET status = 'CANCELLED'
        FROM payables AS p
        WHERE p.organization_id = e.organization_id AND p.company_id = e.company_id
          AND p.id = e.payable_id AND p.status = 'CANCELLED'
    """)
    op.create_check_constraint("ck_expenses_revision", "expenses", "revision > 0")
    op.create_check_constraint("ck_expenses_status", "expenses", "status IN ('OPEN', 'CANCELLED')")
    op.create_table(
        "expense_changes",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("organization_id", sa.Uuid, nullable=False),
        sa.Column("company_id", sa.Uuid, nullable=False),
        sa.Column("expense_id", sa.Uuid, nullable=False),
        sa.Column("actor_user_id", sa.Uuid, nullable=False),
        sa.Column("action", sa.String(12), nullable=False),
        sa.Column("before_state", postgresql.JSONB, nullable=False),
        sa.Column("after_state", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id", "company_id", "expense_id"],
            ["expenses.organization_id", "expenses.company_id", "expenses.id"],
            name="fk_expense_changes_expense", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            name="fk_expense_changes_actor", ondelete="RESTRICT"),
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE expenses, expense_changes IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM expense_changes)")):
        raise RuntimeError("Existem alterações de despesas registradas.")
    op.drop_table("expense_changes")
    op.drop_constraint("ck_expenses_status", "expenses", type_="check")
    op.drop_constraint("ck_expenses_revision", "expenses", type_="check")
    op.drop_column("expenses", "status")
    op.drop_column("expenses", "revision")
