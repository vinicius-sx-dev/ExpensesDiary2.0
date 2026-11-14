"""Encrypt goals/report copies and add private advisor records.

Stop API/jobs and take a verified backup before running. Restartable on MySQL:
add columns if missing, verify each envelope before clearing plaintext.
Old binaries MUST NOT run after this migration. Downgrade intentionally disabled.
"""

from datetime import date
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

from app.crypto import cipher, seal, unseal

revision = "004_advisor"
down_revision = "003_pluggy_receipts"
branch_labels = depends_on = None


def upgrade():
    cipher()  # fail before any DDL if the key is missing
    conn = op.get_bind()
    additions = {
        "finance_entries": [sa.Column("protected_context", sa.LargeBinary(), nullable=True)],
        "finance_goals": [
            sa.Column("crypto_id", sa.String(36), nullable=True),
            sa.Column("protected_data", sa.LargeBinary(), nullable=True),
        ],
        "finance_reports": [
            sa.Column("protected_data", sa.LargeBinary(length=1024 * 1024), nullable=True)
        ],
    }
    for table, columns in additions.items():
        present = {c["name"] for c in sa.inspect(conn).get_columns(table)}
        for column in columns:
            if column.name not in present:
                op.add_column(table, column)
    meta = sa.MetaData()
    goals = sa.Table("finance_goals", meta, autoload_with=conn)
    reports = sa.Table("finance_reports", meta, autoload_with=conn)
    for table, purpose in [(goals, "goal"), (reports, "report")]:
        cursor = 0
        while True:
            rows = (
                conn.execute(
                    sa.select(table).where(table.c.id > cursor).order_by(table.c.id).limit(100)
                )
                .mappings()
                .all()
            )
            if not rows:
                break
            for row in rows:
                key = (row["crypto_id"] or str(uuid4())) if purpose == "goal" else row["week_start"]
                if row["protected_data"]:
                    unseal(row["protected_data"], row["user_id"], purpose, key)
                else:
                    data = (
                        {k: row[k] for k in ("title", "motivation", "target_cents", "deadline")}
                        if purpose == "goal"
                        else row["data"]
                    )
                    payload = seal(data, row["user_id"], purpose, key)
                    unseal(payload, row["user_id"], purpose, key)
                    values = {"protected_data": payload}
                    if purpose == "goal":
                        values["crypto_id"] = key
                    conn.execute(table.update().where(table.c.id == row["id"]).values(**values))
                values = (
                    {"title": "", "motivation": "", "target_cents": 1, "deadline": date(2000, 1, 1)}
                    if purpose == "goal"
                    else {"data": {}}
                )
                conn.execute(table.update().where(table.c.id == row["id"]).values(**values))
            cursor = rows[-1]["id"]
    # Metadata is imported only for the new tables; historical transformations above are explicit.
    from app.models import Advice, AdvisorSettings, Notification, PushDevice

    for model in (AdvisorSettings, Advice, PushDevice, Notification):
        model.__table__.create(conn, checkfirst=True)


def downgrade():
    raise RuntimeError("Restore a verified backup; do not restore plaintext in place.")
