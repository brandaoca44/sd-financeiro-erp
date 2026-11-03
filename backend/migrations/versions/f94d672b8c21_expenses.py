"""Cria o registro de despesas separado dos títulos financeiros."""
import sqlalchemy as sa
from alembic import op

revision = "f94d672b8c21"
down_revision = "e81b346c9a10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "expenses",
        sa.Column("organization_id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, primary_key=True),
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("created_by_user_id", sa.Uuid, nullable=False),
        sa.Column("payable_id", sa.Uuid),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("supplier", sa.String(150), nullable=False),
        sa.Column("document_type", sa.String(20)),
        sa.Column("document_reference", sa.String(100)),
        sa.Column("amount", sa.Numeric, nullable=False),
        sa.Column("issue_date", sa.Date, nullable=False),
        sa.Column("due_date", sa.Date),
        sa.ForeignKeyConstraint(["organization_id", "company_id"], ["companies.organization_id", "companies.id"],
                                name="fk_expenses_company", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id", "organization_id"],
                                ["organization_memberships.user_id", "organization_memberships.organization_id"],
                                name="fk_expenses_creator", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id", "company_id", "payable_id"],
                                ["payables.organization_id", "payables.company_id", "payables.id"],
                                name="fk_expenses_payable", ondelete="RESTRICT"),
        sa.UniqueConstraint("payable_id", name="uq_expenses_payable"),
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE expenses IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM expenses)")):
        raise RuntimeError("Existem despesas registradas.")
    op.drop_table("expenses")
