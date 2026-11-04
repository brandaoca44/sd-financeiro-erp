"""Adiciona competência explícita às despesas sem inferir dados antigos."""
import sqlalchemy as sa
from alembic import op

revision = "c0521e7b34ad"
down_revision = "91ec04a37bf2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("expenses", sa.Column("competence", sa.Date))
    op.create_check_constraint("ck_expenses_competence", "expenses",
                               "competence IS NULL OR EXTRACT(DAY FROM competence) = 1")


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE expenses IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM expenses WHERE competence IS NOT NULL)")):
        raise RuntimeError("Existem competências de despesas registradas.")
    op.drop_constraint("ck_expenses_competence", "expenses", type_="check")
    op.drop_column("expenses", "competence")
