"""Persist business contracts and company activations."""
from alembic import op
import sqlalchemy as sa

revision = "e81b346c9a10"
down_revision = "c30f7542eb19"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "business_contracts",
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("plan", sa.String(20), nullable=False),
        sa.Column("catalog_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("plan IN ('ESSENTIAL','PROFESSIONAL','ENTERPRISE')", name="ck_business_contract_plan"),
        sa.CheckConstraint("status IN ('PENDING','ACTIVE','SUSPENDED','CANCELLED')", name="ck_business_contract_status"),
        sa.CheckConstraint("valid_until > valid_from", name="ck_business_contract_period"),
    )
    op.create_table(
        "business_company_activations",
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("business_contracts.organization_id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("company_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(
            ("organization_id", "company_id"), ("companies.organization_id", "companies.id"),
            ondelete="RESTRICT", name="fk_business_activation_company",
        ),
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE business_company_activations, business_contracts IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM business_contracts)")):
        raise RuntimeError("Downgrade bloqueado: existem contratos empresariais.")
    op.drop_table("business_company_activations")
    op.drop_table("business_contracts")
