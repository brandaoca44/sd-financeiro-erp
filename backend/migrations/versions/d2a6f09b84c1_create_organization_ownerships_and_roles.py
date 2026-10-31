"""Adiciona propriedade, perfis e atribuições com escopo organizacional.

Revision ID: d2a6f09b84c1
Revises: c418d69a02be
"""

from alembic import op
import sqlalchemy as sa


revision = "d2a6f09b84c1"
down_revision = "c418d69a02be"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Cria estruturas sem atribuir propriedade, cargos ou permissões existentes."""

    op.create_table(
        "organization_ownerships",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_organization_ownerships_membership",
        ),
        sa.PrimaryKeyConstraint("organization_id"),
    )
    op.create_index("ix_organization_ownerships_user_id", "organization_ownerships", ["user_id"])
    op.create_table(
        "organization_roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("category", sa.Enum(
            "COLLABORATOR", "ASSISTANT", "LEAD", "MANAGER", "COORDINATOR", "DIRECTOR", "CEO", "CUSTOM",
            name="organization_role_category",
        ), server_default="CUSTOM", nullable=False),
        sa.Column("status", sa.Enum("ACTIVE", "INACTIVE", name="organization_role_status"),
                  server_default="INACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("name = btrim(name) AND length(name) > 0", name="ck_organization_roles_name"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_organization_roles_tenant_id"),
    )
    op.create_index("ix_organization_roles_organization_id", "organization_roles", ["organization_id"])
    op.create_index("uq_organization_roles_name", "organization_roles", ["organization_id", sa.text("lower(name)")], unique=True)
    op.create_table(
        "organization_role_assignments",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Enum("ACTIVE", "INACTIVE", name="organization_role_assignment_status"),
                  server_default="INACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_organization_role_assignments_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "role_id"], ["organization_roles.organization_id", "organization_roles.id"],
            ondelete="RESTRICT", name="fk_organization_role_assignments_role",
        ),
        sa.PrimaryKeyConstraint("organization_id", "user_id", "role_id"),
    )
    op.create_index("ix_organization_role_assignments_role", "organization_role_assignments", ["organization_id", "role_id"])


def downgrade() -> None:
    """Remove apenas as novas estruturas e seus enums, preservando vínculos anteriores."""

    op.drop_index("ix_organization_role_assignments_role", table_name="organization_role_assignments")
    op.drop_table("organization_role_assignments")
    op.drop_index("ix_organization_ownerships_user_id", table_name="organization_ownerships")
    op.drop_table("organization_ownerships")
    op.drop_index("uq_organization_roles_name", table_name="organization_roles")
    op.drop_index("ix_organization_roles_organization_id", table_name="organization_roles")
    op.drop_table("organization_roles")
    for name in ("organization_role_assignment_status", "organization_role_status", "organization_role_category"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
