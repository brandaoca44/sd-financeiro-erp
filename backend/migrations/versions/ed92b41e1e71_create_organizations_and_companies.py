"""Cria as estruturas iniciais de organizações e empresas.

Revision ID: ed92b41e1e71
Revises:
Create Date: 2026-08-11 14:01:41.149040
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores da migration utilizados pelo Alembic.
revision: str = "ed92b41e1e71"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria as tabelas, relacionamentos, índices e tipos iniciais do domínio."""

    op.create_table(
        "organizations",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=150),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "INACTIVE",
                name="organization_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "companies",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "legal_name",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "trade_name",
            sa.String(length=200),
            nullable=True,
        ),
        sa.Column(
            "tax_id",
            sa.String(length=14),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "INACTIVE",
                name="company_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_companies_organization_id"),
        "companies",
        ["organization_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_companies_tax_id"),
        "companies",
        ["tax_id"],
        unique=True,
    )


def downgrade() -> None:
    """Remove completamente as estruturas criadas por esta migration."""

    op.drop_index(
        op.f("ix_companies_tax_id"),
        table_name="companies",
    )

    op.drop_index(
        op.f("ix_companies_organization_id"),
        table_name="companies",
    )

    op.drop_table("companies")
    op.drop_table("organizations")

    sa.Enum(
        name="company_status",
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )

    sa.Enum(
        name="organization_status",
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )