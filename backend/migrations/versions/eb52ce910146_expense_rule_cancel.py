"""Preserva recorrências canceladas no histórico."""
import sqlalchemy as sa
from alembic import op

revision = "eb52ce910146"
down_revision = "d412c8e31b70"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("expense_rules", sa.Column("cancelled", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE expense_rules IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM expense_rules WHERE cancelled)")):
        raise RuntimeError("Existem recorrências canceladas.")
    op.drop_column("expense_rules", "cancelled")
