"""Run every 15 min: python -m app.advisor.notifications.

Regular notification messages work with the app closed. At-most-once dispatch:
ambiguous network outcomes are not retried, avoiding duplicate alerts. OS delivery
is not guaranteed. No financial details are sent to lock screens or Expo.
"""

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from app.advisor.routes import Simulation, calculate, preferences
from app.balance import lock_wallet
from app.config import settings
from app.crypto import unseal
from app.db import SessionLocal
from app.models import Advice, AdvisorSettings, LoginSession, Notification, PushDevice
from app.security import digest

ZONE = ZoneInfo("America/Sao_Paulo")


def next_alert(pattern, now, pref):
    weekday, hour = pattern["weekday"], pattern["hour"]
    if weekday is None or hour is None:
        return None  # Never invent an afternoon habit when only the date is known.
    local = now.astimezone(ZONE)
    for days in range(8):
        day = local.date() + timedelta(days=days)
        if day.weekday() != weekday:
            continue
        spending = datetime.combine(day, datetime.min.time(), tzinfo=ZONE).replace(hour=hour)
        due = spending - timedelta(hours=2)
        if due.date() != day or due.hour < pref.quiet_end or due.hour >= pref.quiet_start:
            continue
        if due > local:
            return due
    return None


def schedule(uid, now):
    with SessionLocal() as db:
        lock_wallet(db, uid)
        pref = preferences(db, uid)
        if not pref.notifications_enabled or not pref.selected_goal_id:
            return
        candidates = []
        for advice in db.scalars(
            select(Advice)
            .where(Advice.user_id == uid, Advice.created_at >= int(now.timestamp()) - 30 * 86400)
            .order_by(Advice.created_at.desc())
            .limit(20)
        ):
            data = advice.data
            if (
                data["goal"]["goal_id"] == pref.selected_goal_id
                and data["result"].get("monthly_savings_cents", 0) > 0
            ):
                due = next_alert(data["pattern"], now, pref)
                if due:
                    candidates.append((data["result"]["monthly_savings_cents"], due, data["input"]))
        if not candidates:
            return
        _, due, payload = max(candidates, key=lambda v: v[0])
        key = digest(f"advisor:{uid}:{due.date()}")
        if not db.get(Notification, key):
            row = Notification(id=key, user_id=uid, due_at=int(due.timestamp()), status="pending")
            row.data = payload
            db.add(row)
            db.commit()


def dispatch(key, now):
    with SessionLocal() as db:
        row = db.get(Notification, key)
        if row is None:
            return
        lock_wallet(db, row.user_id)
        db.refresh(row)
        if row.status != "pending" or row.due_at > now:
            return
        pref = preferences(db, row.user_id)
        local = datetime.fromtimestamp(now, ZONE)
        recent = list(
            db.scalars(
                select(Notification.id).where(
                    Notification.user_id == row.user_id, Notification.sent_at >= now - 7 * 86400
                )
            )
        )
        daily = db.scalar(
            select(Notification.id)
            .where(Notification.user_id == row.user_id, Notification.sent_at >= now - 86400)
            .limit(1)
        )
        if (
            not pref.notifications_enabled
            or row.data["goal_id"] != pref.selected_goal_id
            or row.due_at < now - 3600
            or local.hour < pref.quiet_end
            or local.hour >= pref.quiet_start
            or len(recent) >= pref.max_per_week
            or daily
        ):
            row.status = "cancelled"
            db.commit()
            return
        # Recalculate immediately before dispatch; stale prices must never trigger a claim.
        payload = Simulation.model_validate(row.data)
        payload.humanize = False
        try:
            value = calculate(db, row.user_id, payload)
        except HTTPException:
            value = {"result": {"status": "unavailable"}}
        if (
            value["result"].get("status") != "ready"
            or value["result"].get("monthly_savings_cents", 0) <= 0
        ):
            row.status = "cancelled"
            db.commit()
            return
        pattern = value.get("pattern", {})
        if pattern.get("weekday") != local.weekday() or pattern.get("hour") != local.hour + 2:
            row.status = "cancelled"
            db.commit()
            return
        devices = list(
            db.scalars(
                select(PushDevice)
                .join(LoginSession, PushDevice.session_id == LoginSession.id)
                .where(
                    PushDevice.user_id == row.user_id,
                    LoginSession.user_id == row.user_id,
                    LoginSession.revoked.is_(False),
                    LoginSession.expires_at > now,
                )
                .limit(5)
            )
        )
        if not devices:
            row.status = "cancelled"
            db.commit()
            return
        # One device per user avoids duplicate alerts across devices.
        device = devices[0]
        token = unseal(device.protected_token, row.user_id, "push", device.token_hash)
        row.status, row.sent_at = "dispatching", now
        row.data = {"input": payload.model_dump(), "token_hash": device.token_hash}
        db.commit()  # Claim before network. Never automatically resend a claimed message.
        try:
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                response = client.post(
                    "https://exp.host/--/api/v2/push/send",
                    headers={"Authorization": "Bearer " + settings.expo_access_token},
                    json={
                        "to": token,
                        "title": "Um lembrete para sua meta",
                        "body": "Há uma alternativa para sua rotina. Abra o app para conferir os custos e a simulação atualizados.",
                        "data": {"screen": "advisor"},
                        "sound": "default",
                        "channelId": "advisor",
                        "ttl": 3600,
                    },
                )
                response.raise_for_status()
                ticket = response.json()["data"]
                if ticket.get("status") == "ok" and isinstance(ticket.get("id"), str):
                    row.status = "receipt_pending"
                    row.data = {"ticket": ticket["id"], "token_hash": device.token_hash}
                else:
                    row.status = "rejected"
                    if ticket.get("details", {}).get("error") == "DeviceNotRegistered":
                        db.delete(device)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            row.status = "unknown"
        db.commit()


def receipts(now):
    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(Notification)
                .where(Notification.status == "receipt_pending", Notification.sent_at < now - 900)
                .limit(100)
            )
        )
        if not rows:
            return
        tickets = {r.data["ticket"]: r for r in rows}
        try:
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                response = client.post(
                    "https://exp.host/--/api/v2/push/getReceipts",
                    headers={"Authorization": "Bearer " + settings.expo_access_token},
                    json={"ids": list(tickets)},
                )
                response.raise_for_status()
                results = response.json()["data"]
            for ticket, row in tickets.items():
                receipt = results.get(ticket)
                if receipt:
                    row.status = (
                        "provider_accepted" if receipt.get("status") == "ok" else "rejected"
                    )
                    if receipt.get("details", {}).get("error") == "DeviceNotRegistered":
                        device = db.get(PushDevice, row.data["token_hash"])
                        if device and device.user_id == row.user_id:
                            db.delete(device)
                elif row.sent_at < now - 86400:
                    row.status = "unknown"
            db.commit()
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return


def run():
    if not settings.advisor_push_enabled or not settings.expo_access_token:
        return
    now = int(time.time())
    receipts(now)
    # Process due work first so a new schedule cannot suppress yesterday's due job.
    with SessionLocal() as db:
        keys = list(
            db.scalars(
                select(Notification.id)
                .where(Notification.status == "pending", Notification.due_at <= now)
                .order_by(Notification.due_at)
                .limit(100)
            )
        )
    for key in keys:
        dispatch(key, now)
    cursor = 0
    while True:
        with SessionLocal() as db:
            ids = list(
                db.scalars(
                    select(AdvisorSettings.user_id)
                    .where(AdvisorSettings.user_id > cursor)
                    .order_by(AdvisorSettings.user_id)
                    .limit(100)
                )
            )
        if not ids:
            break
        for uid in ids:
            schedule(uid, datetime.fromtimestamp(now, ZONE))
        cursor = ids[-1]


if __name__ == "__main__":
    run()
