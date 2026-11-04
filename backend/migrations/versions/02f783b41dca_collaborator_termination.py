"""Registra o desligamento sem excluir o colaborador."""
import sqlalchemy as sa
from alembic import op

revision = "02f783b41dca"
down_revision = "81b37e10c2f5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("people_collaborators", sa.Column("termination_date", sa.Date))
    op.add_column("people_collaborators", sa.Column("termination_reason", sa.String(30)))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE people_collaborators IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM people_collaborators WHERE termination_date IS NOT NULL)")):
        raise RuntimeError("Existem desligamentos registrados.")
    op.drop_column("people_collaborators", "termination_reason")
    op.drop_column("people_collaborators", "termination_date")
