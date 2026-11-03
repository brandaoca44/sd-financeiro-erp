"""Confirmação de e-mail, recuperação e segundo fator, sem alterar contas existentes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c30f7542eb19"
down_revision = "b29e6431da08"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("account_security",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("registration_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("cpf_encrypted", sa.Text()), sa.Column("cpf_digest", sa.String(64), unique=True),
        sa.Column("mfa_secret", sa.Text()), sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mfa_pending_expires_at", sa.DateTime(timezone=True)),
        sa.Column("mfa_last_step", sa.Integer(), nullable=False, server_default="-1"), sa.Column("recovery_hashes", sa.Text()),
        sa.CheckConstraint("NOT mfa_enabled OR mfa_secret IS NOT NULL", name="ck_account_security_mfa"))
    op.create_table("account_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purpose", sa.String(12), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("credential_hash", sa.String(512)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("purpose IN ('VERIFY', 'RESET', 'MFA_LOGIN')", name="ck_account_actions_purpose"),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_account_actions_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_account_actions_expiration"))
    op.create_index("ix_account_actions_user_id", "account_actions", ["user_id"])


def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE account_actions, account_security IN ACCESS EXCLUSIVE MODE"))
    if connection.execute(sa.text("SELECT EXISTS(SELECT 1 FROM account_actions) OR EXISTS(SELECT 1 FROM account_security)")).scalar():
        raise RuntimeError("Downgrade bloqueado: existem registros de segurança de contas.")
    op.drop_table("account_actions")
    op.drop_table("account_security")
