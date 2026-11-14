from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from test_security_finance import entry, login

from app.advisor.engine import completion_date, goal_state, patterns, scenario
from app.advisor.humanize import anonymous_payload
from app.advisor.notifications import next_alert
from app.advisor.prices import Quote, price_recipe
from app.advisor.routes import Preferences
from app.crypto import seal, unseal
from app.db import SessionLocal
from app.models import Goal
from app.schemas import today
from app.statement_parser import InvalidStatement, parse


def quotes(now):
    return [
        Quote(
            ingredient=ingredient,
            product=ingredient + " 1 kg",
            store_id=store,
            municipality="4106902",
            unit="kg",
            package_quantity=Decimal("1"),
            package_price_cents=1000,
            source_url="https://retailer.example/product",
            observed_at=now,
            valid_until=now + timedelta(hours=1),
            conditions="regular_in_store",
            available=True,
        )
        for ingredient in ["bread", "cheese", "tomato"]
        for store in ["a", "b"]
    ]


def test_price_evidence_and_full_packages():
    now = datetime.now(timezone.utc)
    evidence = quotes(now)
    result = price_recipe("sandwich", evidence, "4106902", now)
    assert result["consumed_cents"] == 300
    assert result["portion_cents"] == 150
    assert result["packages_cents"] == 3000
    assert price_recipe("sandwich", evidence, "4114501", now)["status"] == "unavailable"
    assert (
        price_recipe("sandwich", evidence, "4106902", now + timedelta(days=2))["status"]
        == "unavailable"
    )
    assert price_recipe("sandwich", evidence[:1] * 10, "4106902", now)["status"] == "unavailable"
    evidence[0].observed_at = now + timedelta(hours=1)
    assert price_recipe("sandwich", evidence, "4106902", now)["status"] == "unavailable"


def test_crypto_binding_and_tampering():
    encrypted = seal({"merchant": "private"}, 1, "entry", "a")
    assert b"private" not in encrypted
    assert unseal(encrypted, 1, "entry", "a")["merchant"] == "private"
    for uid, purpose, key in [(2, "entry", "a"), (1, "goal", "a"), (1, "entry", "b")]:
        with pytest.raises(HTTPException):
            unseal(encrypted, uid, purpose, key)


def test_calendar_and_zero_baseline():
    assert completion_date(500000, 80000, date(2026, 11, 14), 1) == date(2027, 6, 1)
    assert completion_date(500000, 50000, date(2026, 11, 14), 1) == date(2027, 9, 1)
    assert completion_date(500000, 0, date(2026, 11, 14), 1) is None
    assert completion_date(0, 0, date(2026, 11, 14), 1) == date(2026, 11, 14)


def test_no_price_no_claim_and_no_double_allocation():
    goal = SimpleNamespace(
        id=1,
        target_cents=500000,
        planned_monthly_cents=80000,
        contribution_day=1,
        deadline=date(2027, 8, 1),
    )
    state = goal_state(goal, [], date(2026, 11, 14))
    pattern = {"strategy": "fast_food", "occurrences": 12, "average_cents": 4000}
    result = scenario(
        goal,
        state,
        pattern,
        {"status": "unavailable", "message": "indisponível"},
        date(2026, 11, 14),
        1,
    )
    assert result["status"] == "prices_unavailable"
    assert "monthly_savings_cents" not in result
    result = scenario(
        goal, state, pattern, {"status": "verified", "portion_cents": 1000}, date(2026, 11, 14), 4
    )
    assert result["monthly_savings_cents"] == 12000
    assert result["days_earlier"] is None  # no invented acceleration from zero baseline
    assert state["goal_id"] == 1
    assert (
        scenario(
            goal,
            state,
            pattern,
            {"status": "verified", "portion_cents": 1000},
            date(2026, 11, 14),
            5,
        )["status"]
        == "invalid_frequency"
    )


def test_patterns_require_evidence_and_respect_essential():
    as_of = date(2026, 11, 14)
    rows = [
        SimpleNamespace(
            kind="expense",
            category="restaurante",
            essential=False,
            on_date=date(2026, 11, 13) - timedelta(days=7 * i),
            amount_cents=4000,
            context={},
        )
        for i in range(4)
    ]
    p = patterns(rows, as_of)[0]
    assert p["weekday"] == 4 and p["hour"] is None
    assert next_alert(p, datetime(2026, 11, 14, tzinfo=timezone.utc), Preferences()) is None
    for row in rows:
        row.essential = True
    assert patterns(rows, as_of) == []


def test_parser_explicit_context_and_pii_rejection():
    result = parse(
        b"data;valor;estabelecimento;horario\n01/11/2026;-20,00;Lanchonete;18:30\n", "csv"
    )
    assert result[0]["context"]["merchant"] == "Lanchonete"
    assert result[0]["context"]["occurred_at"].endswith("18:30:00-03:00")
    with pytest.raises(InvalidStatement):
        parse(b"data;valor;estabelecimento\n01/11/2026;-20,00;123.456.789-00\n", "csv")


def test_llm_allowlist():
    p = {"strategy": "fast_food", "merchant": "SECRET", "user_id": 1}
    result = dict(
        per_occurrence_cents=1000,
        monthly_savings_cents=4000,
        days_earlier=7,
        address="SECRET",
        title="SECRET",
    )
    payload = anonymous_payload(p, result)
    assert set(payload) == {
        "category",
        "context",
        "per_occurrence_cents",
        "monthly_savings_cents",
        "days_earlier",
    }
    assert "SECRET" not in str(payload)


def test_encrypted_goal_report_context_and_tenant_routes(client):
    a, _ = login(client)
    b, _ = login(client, "second@example.com")
    g = client.post(
        "/goals",
        headers=a,
        json={
            "title": "Private computer",
            "motivation": "private motive",
            "target_cents": 500000,
            "deadline": str(today() + timedelta(days=300)),
            "planned_monthly_cents": 80000,
        },
    ).json()
    assert g["planned_monthly_cents"] == 80000
    assert (
        client.get("/advisor/patterns", params={"goal_id": g["id"]}, headers=b).status_code == 404
    )
    r = client.post(
        "/entries",
        headers=a,
        json=entry(context={"merchant": "Private store", "niche": "fast_food"}),
    )
    assert r.status_code == 201, r.text
    assert r.json()["context"]["merchant"] == "Private store"
    report = client.post("/reports/weekly", headers=a)
    assert report.status_code == 200
    with SessionLocal() as db:
        goal = db.scalar(select(Goal))
        assert goal.legacy_title == "" and goal.legacy_target == 1
        assert b"Private" not in goal.protected_data
        raw = db.execute(text("SELECT data, protected_data FROM finance_reports")).first()
        assert "Private" not in str(raw)
        ctx = db.execute(text("SELECT protected_context FROM finance_entries")).scalar()
        assert b"Private" not in ctx
    assert (
        client.put("/advisor/preferences", headers=a, json={"municipality": "3550308"}).status_code
        == 422
    )
    assert (
        client.put(
            "/advisor/preferences",
            headers=a,
            json={"municipality": "4106902", "selected_goal_id": g["id"]},
        ).status_code
        == 200
    )


def test_alert_lead_time_and_quiet_hours():
    now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
    due = next_alert({"weekday": 4, "hour": 18}, now, Preferences())
    assert due.hour == 16 and due.date() == date(2026, 11, 13)
    assert next_alert({"weekday": 4, "hour": 8}, now, Preferences()) is None


def test_migration_preserves_values_and_removes_plaintext(tmp_path):
    import json
    import os
    import sqlite3
    import subprocess
    import sys

    from app.config import settings

    path = tmp_path / "migration.db"
    env = {
        **os.environ,
        "DATABASE_URL": "sqlite:///" + str(path),
        "STATEMENT_ENCRYPTION_KEY": settings.statement_encryption_key,
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "003_pluggy_receipts"],
        env=env,
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO users VALUES (1,'test','test@example.com','hash')")
        c.execute(
            "INSERT INTO finance_goals VALUES (1,1,'secret-title','secret-motivation',500000,'2027-08-01')"
        )
        c.execute(
            "INSERT INTO finance_reports VALUES (1,1,'2026-11-02',?)",
            (json.dumps({"goals": [{"title": "secret-title"}]}),),
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(path) as c:
        row = c.execute(
            "SELECT title,motivation,target_cents,deadline,crypto_id,protected_data FROM finance_goals"
        ).fetchone()
        assert row[:4] == ("", "", 1, "2000-01-01")
        assert unseal(row[5], 1, "goal", row[4])["target_cents"] == 500000
        report = c.execute("SELECT data,protected_data FROM finance_reports").fetchone()
        assert json.loads(report[0]) == {}
        assert unseal(report[1], 1, "report", "2026-11-02")["goals"][0]["title"] == "secret-title"


def test_notification_dispatch_claim_throttle_and_receipts(client, monkeypatch):

    from app.advisor import notifications as n
    from app.advisor.routes import Simulation
    from app.models import AdvisorSettings, LoginSession, Notification, PushDevice
    from app.security import digest

    a, _ = login(client)
    now = int(datetime(2026, 11, 14, 15, tzinfo=timezone.utc).timestamp())
    with SessionLocal() as db:
        session = db.scalar(select(LoginSession))
        session.expires_at = now + 86400
        pref = AdvisorSettings(
            user_id=session.user_id,
            data=Preferences(notifications_enabled=True, selected_goal_id=1).model_dump(),
        )
        db.add(pref)
        token = "ExponentPushToken[abcdefghijklmno]"
        token_hash = digest("push:" + token)
        device = PushDevice(
            token_hash=token_hash,
            user_id=session.user_id,
            session_id=session.id,
            protected_token=seal(token, session.user_id, "push", token_hash),
        )
        db.add(device)
        for key in ("one", "two"):
            row = Notification(id=key, user_id=session.user_id, due_at=now - 60, status="pending")
            row.data = Simulation(goal_id=1, strategy="fast_food").model_dump()
            db.add(row)
        db.commit()
    monkeypatch.setattr(
        n,
        "calculate",
        lambda *args: {
            "result": {"status": "ready", "monthly_savings_cents": 1000},
            "pattern": {"weekday": 5, "hour": 14},
        },
    )
    sent = []

    class Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kw):
            sent.append(kw["json"])
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"data": {"status": "ok", "id": "ticket-one"}},
            )

    monkeypatch.setattr(n.httpx, "Client", Client)
    n.dispatch("one", now)
    n.dispatch("one", now)
    n.dispatch("two", now)
    assert len(sent) == 1
    assert sent[0]["data"] == {"screen": "advisor"}
    assert "1000" not in str(sent[0])
    with SessionLocal() as db:
        assert db.get(Notification, "one").status == "receipt_pending"
        assert db.get(Notification, "two").status == "cancelled"
