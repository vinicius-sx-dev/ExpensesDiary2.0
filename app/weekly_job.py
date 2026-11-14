"""Generate last completed week's snapshots. Schedule Monday; safe to rerun.
No email or AI calls are made by this job. AI remains explicit opt-in in the app.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import User, WeeklyReport
from app.reports import build_report
from app.schemas import today


def run():
    start = today() - timedelta(days=today().weekday() + 7)
    cursor = 0
    while True:
        with SessionLocal() as db:
            ids = list(
                db.scalars(select(User.id).where(User.id > cursor).order_by(User.id).limit(100))
            )
        if not ids:
            break
        for uid in ids:
            with SessionLocal() as db:
                if db.scalar(
                    select(WeeklyReport.id).where(
                        WeeklyReport.user_id == uid, WeeklyReport.week_start == start
                    )
                ):
                    continue
                db.add(
                    WeeklyReport(user_id=uid, week_start=start, data=build_report(db, uid, start))
                )
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()  # concurrent job already saved this week
        cursor = ids[-1]


if __name__ == "__main__":
    run()
