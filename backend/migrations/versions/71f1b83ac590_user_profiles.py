"""Persiste perfil privado por usuário com criptografia e revisão."""
import sqlalchemy as sa
from alembic import op

revision = "71f1b83ac590"
down_revision = "c0521e7b34ad"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("encrypted_data", sa.Text, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE user_profiles IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM user_profiles)")):
        raise RuntimeError("Existem perfis pessoais cadastrados.")
    op.drop_table("user_profiles")
