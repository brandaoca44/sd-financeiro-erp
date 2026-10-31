"""Adiciona armazenamento separado para hashes de senha.

Revision ID: 9e3d7a51c286
Revises: 4db0f645bda1
"""

from alembic import op
import sqlalchemy as sa


revision = "9e3d7a51c286"
down_revision = "4db0f645bda1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Cria credenciais sem gerar senhas, usuários ou privilégios iniciais."""

    op.create_table(
        "user_password_credentials",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "password_hash LIKE '$argon2id$%' AND length(password_hash) BETWEEN 50 AND 512",
            name="ck_user_password_credentials_argon2id",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    """Remove hashes sem alterar os dados ou permissões dos usuários."""

    op.drop_table("user_password_credentials")
