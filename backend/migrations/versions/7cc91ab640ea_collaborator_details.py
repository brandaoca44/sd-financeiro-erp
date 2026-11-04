"""Adiciona dados de vínculo profissional ao cadastro."""
import sqlalchemy as sa
from alembic import op

revision = "7cc91ab640ea"
down_revision = "50d89c4a213f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("people_collaborators", sa.Column("employment_type", sa.String(20)))
    op.add_column("people_collaborators", sa.Column("work_model", sa.String(20)))
    op.add_column("people_collaborators", sa.Column("admission_date", sa.Date))
    op.add_column("people_collaborators", sa.Column("monthly_compensation", sa.Numeric))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE people_collaborators IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM people_collaborators WHERE employment_type IS NOT NULL "
        "OR work_model IS NOT NULL OR admission_date IS NOT NULL OR monthly_compensation IS NOT NULL)"
    )):
        raise RuntimeError("Existem dados profissionais cadastrados.")
    for column in ("monthly_compensation", "admission_date", "work_model", "employment_type"):
        op.drop_column("people_collaborators", column)
