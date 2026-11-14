"""Run daily: python -m app.maintenance. Retain finance records; expire auth metadata only."""

import time

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import LoginChallenge, LoginSession, RateBucket

with SessionLocal() as db:
    now = int(time.time())
    for model in (RateBucket, LoginChallenge, LoginSession):
        db.execute(delete(model).where(model.expires_at < now - 86400))
    db.commit()
