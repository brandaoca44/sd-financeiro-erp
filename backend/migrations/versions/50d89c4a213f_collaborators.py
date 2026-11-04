"""Cria o cadastro profissional de colaboradores."""
import sqlalchemy as sa
from alembic import op

revision = "50d89c4a213f"
down_revision = "eb52ce910146"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "people_collaborators",
        sa.Column("organization_id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, primary_key=True),
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("job_title", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "company_id"], ["companies.organization_id", "companies.id"],
                                name="fk_people_collaborators_company", ondelete="RESTRICT"),
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE people_collaborators IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM people_collaborators)")):
        raise RuntimeError("Existem colaboradores cadastrados.")
    op.drop_table("people_collaborators")
