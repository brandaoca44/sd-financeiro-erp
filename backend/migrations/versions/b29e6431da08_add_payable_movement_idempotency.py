"""Guarda resultado idempotente e motivo de estorno, sem movimentos iniciais."""
from alembic import op
import sqlalchemy as sa

revision = "b29e6431da08"
down_revision = "a18d5320cf97"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payable_movements", sa.Column("reversal_reason", sa.String(300), nullable=True))
    op.create_check_constraint("ck_payable_movements_reason", "payable_movements",
        "reversal_reason IS NULL OR (kind = 'REVERSAL' AND reversal_reason = btrim(reversal_reason) AND length(reversal_reason) > 0)")
    op.create_table("payable_movement_requests",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("operation", sa.String(8), nullable=False),
        sa.Column("request_key", sa.UUID(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payable_id", sa.UUID(), nullable=False),
        sa.Column("movement_id", sa.UUID(), nullable=False),
        sa.Column("title_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("organization_id", "company_id", "actor_user_id", "operation", "request_key"),
        sa.ForeignKeyConstraint(["actor_user_id", "organization_id"], ["organization_memberships.user_id", "organization_memberships.organization_id"],
                                ondelete="RESTRICT", name="fk_payable_requests_actor"),
        sa.ForeignKeyConstraint(["organization_id", "company_id", "payable_id", "movement_id"],
            ["payable_movements.organization_id", "payable_movements.company_id", "payable_movements.payable_id", "payable_movements.id"],
            ondelete="RESTRICT", name="fk_payable_requests_movement"),
        sa.CheckConstraint("operation IN ('PAYMENT', 'REVERSAL')", name="ck_payable_requests_operation"),
        sa.CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="ck_payable_requests_hash"),
        sa.CheckConstraint("title_revision > 0", name="ck_payable_requests_revision"))


def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE payable_movement_requests, payable_movements IN ACCESS EXCLUSIVE MODE"))
    for table in ("payable_movement_requests", "payable_movements"):
        if connection.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Downgrade bloqueado: existem movimentos ou resultados idempotentes financeiros.")
    op.drop_table("payable_movement_requests")
    op.drop_constraint("ck_payable_movements_reason", "payable_movements", type_="check")
    op.drop_column("payable_movements", "reversal_reason")
