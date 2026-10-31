"""Cria usuários e vínculos organizacionais com privilégios negados por padrão.

Revision ID: 4db0f645bda1
Revises: ed92b41e1e71
"""

from alembic import op
import sqlalchemy as sa


revision = "4db0f645bda1"
down_revision = "ed92b41e1e71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Adiciona a base de identidade sem criar usuários ou conceder permissões."""

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column(
            "status", sa.Enum("ACTIVE", "INACTIVE", name="user_status"),
            server_default="INACTIVE", nullable=False,
        ),
        sa.Column("can_provision_organizations", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_users_name_not_blank"),
        sa.CheckConstraint(
            "email = btrim(email) AND length(email) > 0",
            name="ck_users_email_trimmed_not_blank",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_users_email_case_insensitive", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "organization_memberships",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "status", sa.Enum("ACTIVE", "INACTIVE", name="membership_status"),
            server_default="INACTIVE", nullable=False,
        ),
        sa.Column("can_read_organization", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("user_id", "organization_id"),
    )
    op.create_index(
        "ix_organization_memberships_organization_id", "organization_memberships", ["organization_id"],
    )


def downgrade() -> None:
    """Remove apenas a base de identidade e seus tipos, preservando o domínio anterior."""

    op.drop_index("ix_organization_memberships_organization_id", table_name="organization_memberships")
    op.drop_table("organization_memberships")
    op.drop_index("uq_users_email_case_insensitive", table_name="users")
    op.drop_table("users")
    sa.Enum(name="membership_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_status").drop(op.get_bind(), checkfirst=True)
