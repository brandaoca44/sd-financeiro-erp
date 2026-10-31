"""Adiciona concessões por perfil e delegação sem converter privilégios anteriores.

Revision ID: a81e73c405bf
Revises: f3a82c17d905
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a81e73c405bf"
down_revision = "f3a82c17d905"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, name in (("organization_ownerships", "ck_ownerships_revision"),
                        ("organization_roles", "ck_roles_revision"),
                        ("organization_role_assignments", "ck_role_assignments_revision")):
        op.add_column(table, sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
        if table != "organization_role_assignments":
            op.create_check_constraint(name, table, "revision > 0")
    op.create_table(
        "organization_role_permissions",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("permission_key", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "role_id", "permission_key"),
        sa.ForeignKeyConstraint(["organization_id", "role_id"], ["organization_roles.organization_id", "organization_roles.id"],
                                 ondelete="RESTRICT", name="fk_role_permissions_role"),
        sa.CheckConstraint("permission_key IN ('organizations.read', 'identity.roles.read')", name="ck_role_permissions_known"),
    )
    op.create_table(
        "organization_access_delegations",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("granted_by_user_id", sa.UUID(), nullable=False),
        sa.Column("owner_revision", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(8), server_default="INACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "user_id"),
        sa.ForeignKeyConstraint(["user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_access_delegations_membership"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_access_delegations_status"),
        sa.CheckConstraint("revision > 0 AND owner_revision > 0", name="ck_access_delegations_revision"),
    )
    op.create_table(
        "organization_delegation_permissions",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("permission_key", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "user_id", "permission_key"),
        sa.ForeignKeyConstraint(["organization_id", "user_id"],
            ["organization_access_delegations.organization_id", "organization_access_delegations.user_id"],
            ondelete="RESTRICT", name="fk_delegation_permissions_delegation"),
        sa.CheckConstraint("permission_key IN ('organizations.read', 'identity.roles.read')", name="ck_delegation_permissions_known"),
    )
    op.add_column("organization_role_assignments", sa.Column("delegated_by_user_id", sa.UUID(), nullable=True))
    op.add_column("organization_role_assignments", sa.Column("delegation_revision", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_role_assignments_delegation", "organization_role_assignments", "organization_access_delegations",
        ["organization_id", "delegated_by_user_id"], ["organization_id", "user_id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_role_assignments_source", "organization_role_assignments",
        "(delegated_by_user_id IS NULL) = (delegation_revision IS NULL)")
    op.create_check_constraint("ck_role_assignments_revision", "organization_role_assignments",
        "revision > 0 AND (delegation_revision IS NULL OR delegation_revision > 0)")
    op.create_table(
        "organization_access_changes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=True),
        sa.Column("target_user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("before_state", postgresql.JSONB(), nullable=False),
        sa.Column("after_state", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id", "role_id"], ["organization_roles.organization_id", "organization_roles.id"],
                                 ondelete="RESTRICT", name="fk_access_changes_role"),
        sa.ForeignKeyConstraint(["target_user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_access_changes_member"),
        sa.CheckConstraint("action IN ('ROLE_CREATED', 'ROLE_UPDATED', 'ASSIGNMENT_SET', 'DELEGATION_SET')", name="ck_access_changes_action"),
    )
    op.create_index("ix_access_changes_organization", "organization_access_changes", ["organization_id", "created_at"])


def downgrade() -> None:
    # Não transformar atribuições delegadas em concessões diretas ao perder a origem.
    op.execute("UPDATE organization_role_assignments SET status = 'INACTIVE' WHERE delegated_by_user_id IS NOT NULL")
    op.drop_table("organization_access_changes")
    for name, kind in (("fk_role_assignments_delegation", "foreignkey"),
                       ("ck_role_assignments_source", "check"), ("ck_role_assignments_revision", "check")):
        op.drop_constraint(name, "organization_role_assignments", type_=kind)
    op.drop_column("organization_role_assignments", "delegation_revision")
    op.drop_column("organization_role_assignments", "delegated_by_user_id")
    op.drop_table("organization_delegation_permissions")
    op.drop_table("organization_access_delegations")
    op.drop_table("organization_role_permissions")
    for table, name in (("organization_ownerships", "ck_ownerships_revision"), ("organization_roles", "ck_roles_revision")):
        op.drop_constraint(name, table, type_="check")
        op.drop_column(table, "revision")
    op.drop_column("organization_role_assignments", "revision")
