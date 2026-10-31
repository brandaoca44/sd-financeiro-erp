"""Registra a inicialização única do primeiro operador.

Revision ID: c418d69a02be
Revises: ba72c81409ef
"""

from alembic import op
import sqlalchemy as sa


revision = "c418d69a02be"
down_revision = "ba72c81409ef"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Cria somente o marcador; não cria contas ou privilégios."""

    op.create_table(
        "platform_bootstrap",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_platform_bootstrap_singleton"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    """Remove o marcador preservando contas e credenciais já criadas."""

    op.drop_table("platform_bootstrap")
