"""Run daily: python -m app.maintenance. Retain finance records; expire auth metadata only."""

import time

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import LoginChallenge, LoginSession, RateBucket, StatementImport, Advice, Notification

with SessionLocal() as db:
    now = int(time.time())
    for model in (RateBucket, LoginChallenge, LoginSession):
        db.execute(delete(model).where(model.expires_at < now - 86400))
    db.execute(delete(StatementImport).where(StatementImport.status == "pending", StatementImport.expires_at <= now))
    db.execute(delete(Advice).where(Advice.created_at < now - 90 * 86400))
    db.execute(delete(Notification).where(Notification.due_at < now - 90 * 86400))
    db.commit()
