"""Armazena dados pessoais e bancários protegidos."""
import sqlalchemy as sa
from alembic import op

revision = "81b37e10c2f5"
down_revision = "7cc91ab640ea"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("people_collaborators", sa.Column("private_data", sa.Text))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE people_collaborators IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM people_collaborators WHERE private_data IS NOT NULL)")):
        raise RuntimeError("Existem dados protegidos cadastrados.")
    op.drop_column("people_collaborators", "private_data")
