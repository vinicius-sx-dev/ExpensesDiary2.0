"""Encrypted short-lived statement previews and shared processing leases."""

import sqlalchemy as sa
from alembic import op

revision = "002_statement_imports"
down_revision = "001_finance"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "statement_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("payload", sa.LargeBinary(length=1024 * 1024), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "fingerprint"),
    )
    op.create_index("ix_statement_imports_user_id", "statement_imports", ["user_id"])
    op.create_index("ix_statement_imports_expires_at", "statement_imports", ["expires_at"])
    op.create_table(
        "import_leases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
    )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled. Restore a verified database backup.")
