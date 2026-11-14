"""Opaque Pluggy import receipts."""
import sqlalchemy as sa
from alembic import op
revision = "003_pluggy_receipts"
down_revision = "002_statement_imports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("pluggy_receipts",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("request_id", sa.String(36), primary_key=True))


def downgrade():
    raise RuntimeError("Restore a verified backup instead of deleting import receipts.")
