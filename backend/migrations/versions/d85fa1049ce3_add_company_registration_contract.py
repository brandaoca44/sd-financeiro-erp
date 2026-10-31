"""Valida cadastro de Company e limita unicidade do CNPJ ao tenant.

Revision ID: d85fa1049ce3
Revises: c74e901a6bd2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d85fa1049ce3"
down_revision = "c74e901a6bd2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE companies IN ACCESS EXCLUSIVE MODE"))
    op.execute("""
        CREATE FUNCTION sd_is_valid_cnpj(value text) RETURNS boolean
        LANGUAGE plpgsql IMMUTABLE STRICT AS $$
        DECLARE n integer; pos integer; total integer; remainder integer; digit integer;
        BEGIN
            IF value COLLATE "C" !~ '^[A-Z0-9]{12}[0-9]{2}$' OR value = repeat(left(value, 1), 14) THEN
                RETURN false;
            END IF;
            FOR n IN 12..13 LOOP
                total := 0;
                FOR pos IN 1..n LOOP
                    total := total + (ascii(substr(value, pos, 1)) - 48) * (2 + ((n - pos) % 8));
                END LOOP;
                remainder := total % 11;
                digit := CASE WHEN remainder < 2 THEN 0 ELSE 11 - remainder END;
                IF digit <> ascii(substr(value, n + 1, 1)) - 48 THEN
                    RETURN false;
                END IF;
            END LOOP;
            RETURN true;
        END $$
    """)
    invalid = connection.execute(sa.text("""
        SELECT EXISTS (SELECT 1 FROM companies WHERE NOT sd_is_valid_cnpj(tax_id)
            OR legal_name <> btrim(legal_name) OR length(btrim(legal_name)) = 0
            OR (trade_name IS NOT NULL AND (trade_name <> btrim(trade_name) OR length(btrim(trade_name)) = 0)))
    """)).scalar()
    if invalid:
        raise RuntimeError("Migration bloqueada: há cadastros de empresa que exigem revisão, sem correção automática.")
    op.add_column("companies", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("companies", "status", server_default="ACTIVE")
    op.create_unique_constraint("uq_companies_tenant_id", "companies", ["organization_id", "id"])
    op.create_index("uq_companies_tenant_tax_id", "companies", ["organization_id", "tax_id"], unique=True)
    op.drop_index("ix_companies_tax_id", table_name="companies")
    op.create_check_constraint("ck_companies_cnpj", "companies", "sd_is_valid_cnpj(tax_id)")
    op.create_check_constraint("ck_companies_legal_name", "companies", "legal_name = btrim(legal_name) AND length(legal_name) > 0")
    op.create_check_constraint("ck_companies_trade_name", "companies", "trade_name IS NULL OR (trade_name = btrim(trade_name) AND length(trade_name) > 0)")
    op.create_check_constraint("ck_companies_revision", "companies", "revision > 0")
    op.create_table(
        "company_changes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(12), nullable=False),
        sa.Column("before_state", postgresql.JSONB(), nullable=False),
        sa.Column("after_state", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id", "company_id"], ["companies.organization_id", "companies.id"],
                                 ondelete="RESTRICT", name="fk_company_changes_company"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("action IN ('CREATED', 'UPDATED')", name="ck_company_changes_action"),
    )
    op.create_index("ix_company_changes_organization", "company_changes", ["organization_id", "created_at"])


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE companies IN ACCESS EXCLUSIVE MODE"))
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM company_changes)")).scalar():
        raise RuntimeError("Downgrade bloqueado: existe histórico de cadastro de empresas.")
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM companies GROUP BY tax_id HAVING count(*) > 1)")).scalar():
        raise RuntimeError("Downgrade bloqueado: há CNPJs em tenants distintos incompatíveis com unicidade global.")
    op.drop_table("company_changes")
    for name in ("ck_companies_cnpj", "ck_companies_legal_name", "ck_companies_trade_name", "ck_companies_revision"):
        op.drop_constraint(name, "companies", type_="check")
    op.create_index("ix_companies_tax_id", "companies", ["tax_id"], unique=True)
    op.drop_index("uq_companies_tenant_tax_id", table_name="companies")
    op.drop_constraint("uq_companies_tenant_id", "companies", type_="unique")
    op.drop_column("companies", "revision")
    op.alter_column("companies", "status", server_default=None)
    op.execute("DROP FUNCTION sd_is_valid_cnpj(text)")
