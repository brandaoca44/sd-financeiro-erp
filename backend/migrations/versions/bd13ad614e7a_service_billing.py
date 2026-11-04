"""Adiciona faturamento de serviços por empresa."""
import sqlalchemy as sa
from alembic import op

revision = "bd13ad614e7a"
down_revision = "02f783b41dca"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "service_billings",
        sa.Column("organization_id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, primary_key=True),
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("customer", sa.String(150), nullable=False),
        sa.Column("service", sa.String(250), nullable=False),
        sa.Column("competence", sa.Date, nullable=False),
        sa.Column("issue_date", sa.Date, nullable=False),
        sa.Column("amount", sa.Numeric, nullable=False),
        sa.Column("due_date", sa.Date),
        sa.Column("invoice_reference", sa.String(80)),
        sa.ForeignKeyConstraint(["organization_id", "company_id"], ["companies.organization_id", "companies.id"],
                                name="fk_service_billings_company", ondelete="RESTRICT"),
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE service_billings IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM service_billings)")):
        raise RuntimeError("Existem faturamentos registrados.")
    op.drop_table("service_billings")
