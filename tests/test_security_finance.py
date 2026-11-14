import uuid
from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import LoginChallenge
from app.schemas import today

DEVICE = str(uuid.uuid4())
PASSWORD = "a secure test password!"


def login(client, email="alice@example.com"):
    headers = {"X-Device-ID": str(uuid.uuid4())}
    result = client.post(
        "/auth/register",
        json={"name": "Test User", "email": email, "password": PASSWORD},
        headers=headers,
    )
    assert result.status_code == 202, result.text
    result = client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}, headers=headers
    )
    assert result.status_code == 200, result.text
    challenge = result.json()["challenge_id"]
    result = client.post(
        "/auth/verify",
        json={"challenge_id": challenge, "code": client.sent[-1][1]},
        headers=headers,
    )
    assert result.status_code == 200, result.text
    pair = result.json()
    return {**headers, "Authorization": "Bearer " + pair["access_token"]}, pair


def entry(amount=1250, **extra):
    return {
        "request_id": str(uuid.uuid4()),
        "kind": "expense",
        "category": "mercado",
        "amount_cents": amount,
        "on_date": str(today()),
        **extra,
    }


def test_closed_legacy_and_me(client):
    assert client.get("/users/1").status_code == 404
    assert client.get("/auth/me").status_code == 401
    headers, _ = login(client)
    response = client.get("/auth/me", headers=headers)
    assert set(response.json()) == {"id", "name", "email"}
    assert (
        client.patch(
            "/auth/me", json={"name": "ok", "password_hash": "attack"}, headers=headers
        ).status_code
        == 422
    )


def test_tenant_isolation_and_injection(client):
    a, _ = login(client)
    b, _ = login(client, "bob@example.com")
    payload = entry(description="'; DROP TABLE users; --")
    created = client.post("/entries", json=payload, headers=a)
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    assert client.get("/entries", headers=b).json() == []
    assert client.put(f"/entries/{eid}", json=payload, headers=b).status_code == 404
    assert client.delete(f"/entries/{eid}", headers=b).status_code == 404
    goal = client.post(
        "/goals",
        json={
            "title": "Reserva",
            "target_cents": 10000,
            "deadline": str(today() + timedelta(days=30)),
        },
        headers=a,
    ).json()
    assert (
        client.post(
            f"/goals/{goal['id']}/contributions",
            json={"request_id": str(uuid.uuid4()), "amount_cents": 1000, "on_date": str(today())},
            headers=b,
        ).status_code
        == 404
    )
    assert client.get("/reports/weekly", headers=b).json()["expense_cents"] == 0
    assert client.get("/auth/me", headers=a).status_code == 200


def test_validation_and_idempotency(client):
    h, _ = login(client)
    for value in [-1, 0, 1.5, True, "100", 10_000_000_001]:
        assert client.post("/entries", json=entry(value), headers=h).status_code == 422
    assert client.post("/entries", json=entry(category="salario"), headers=h).status_code == 422
    assert client.post("/entries", json=entry(user_id=100), headers=h).status_code == 422
    assert (
        client.post(
            "/entries", json=entry(on_date=str(today() + timedelta(days=1))), headers=h
        ).status_code
        == 422
    )
    payload = entry()
    a = client.post("/entries", json=payload, headers=h).json()
    b = client.post("/entries", json=payload, headers=h).json()
    assert a["id"] == b["id"]
    assert (
        client.post("/entries", json={**payload, "amount_cents": 2000}, headers=h).status_code
        == 409
    )


def test_otp_attempts_expiry_reuse(client):
    h = {"X-Device-ID": DEVICE}
    client.post(
        "/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": PASSWORD},
        headers=h,
    )
    challenge = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": PASSWORD}, headers=h
    ).json()["challenge_id"]
    correct = client.sent[-1][1]
    wrong = "111111" if correct != "111111" else "222222"
    for _ in range(5):
        assert (
            client.post(
                "/auth/verify", json={"challenge_id": challenge, "code": wrong}, headers=h
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/auth/verify", json={"challenge_id": challenge, "code": correct}, headers=h
        ).status_code
        == 401
    )
    new = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": PASSWORD}, headers=h
    ).json()["challenge_id"]
    code = client.sent[-1][1]
    assert (
        client.post("/auth/verify", json={"challenge_id": new, "code": code}, headers=h).status_code
        == 200
    )
    assert (
        client.post("/auth/verify", json={"challenge_id": new, "code": code}, headers=h).status_code
        == 401
    )


def test_refresh_rotation_reuse_revokes(client):
    h, pair = login(client)
    dev = {"X-Device-ID": h["X-Device-ID"]}
    updated = client.post(
        "/auth/refresh", json={"refresh_token": pair["refresh_token"]}, headers=dev
    )
    assert updated.status_code == 200
    assert updated.json()["refresh_token"] != pair["refresh_token"]
    assert (
        client.post(
            "/auth/refresh", json={"refresh_token": pair["refresh_token"]}, headers=dev
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/auth/me", headers={**h, "Authorization": "Bearer " + updated.json()["access_token"]}
        ).status_code
        == 401
    )


def test_device_binding_and_logout(client):
    h, _ = login(client)
    assert (
        client.get("/auth/me", headers={**h, "X-Device-ID": str(uuid.uuid4())}).status_code == 401
    )
    assert client.post("/auth/logout", headers=h).status_code == 204
    assert client.get("/auth/me", headers=h).status_code == 401


def test_rate_limit_account_cannot_be_bypassed_by_device(client):
    for i in range(11):
        result = client.post(
            "/auth/login",
            headers={"X-Device-ID": str(uuid.uuid4())},
            json={"email": "unknown@example.com", "password": "bad"},
        )
    assert result.status_code == 429
    assert int(result.headers["retry-after"]) > 0


def test_report_calculations_and_budgets(client):
    h, _ = login(client)
    client.post("/entries", json=entry(10000, kind="income", category="salario"), headers=h)
    client.post("/entries", json=entry(2500, essential=True), headers=h)
    payload = {"month": str(today().replace(day=1)), "category": "mercado", "limit_cents": 2000}
    assert client.post("/budgets", json=payload, headers=h).status_code == 201
    assert client.post("/budgets", json=payload, headers=h).status_code == 409
    goal = client.post(
        "/goals",
        json={
            "title": "Viagem",
            "target_cents": 9000,
            "deadline": str(today() + timedelta(days=28)),
        },
        headers=h,
    ).json()
    assert (
        client.post(
            f"/goals/{goal['id']}/contributions",
            json={"request_id": str(uuid.uuid4()), "amount_cents": 1000, "on_date": str(today())},
            headers=h,
        ).status_code
        == 201
    )
    r = client.get("/reports/weekly", headers=h).json()
    assert (
        r["income_cents"],
        r["expense_cents"],
        r["net_cents"],
        r["reserved_cents"],
        r["unreserved_flow_cents"],
    ) == (10000, 2500, 7500, 1000, 6500)
    assert r["budgets"][0]["status"] == "exceeded"
    assert r["categories"][0]["essential_cents"] == 2500
    assert r["goals"][0]["saved_cents"] == 1000
    assert r["goals"][0]["required_weekly_cents"] == 2000
    assert client.post("/reports/weekly", headers=h).status_code == 200
    assert len(client.get("/reports/history", headers=h).json()) == 1
    assert client.delete(f"/goals/{goal['id']}", headers=h).status_code == 409


def test_errors_do_not_echo_sensitive_values_and_body_limit(client):
    secret = "SECRET_SHOULD_NOT_APPEAR"
    result = client.post("/auth/login", json={"email": "bad", "password": secret, "extra": secret})
    assert secret not in result.text
    assert result.status_code == 422
    assert client.post("/auth/login", content="x" * 17000).status_code == 413
    assert client.get("/health").headers["cache-control"] == "no-store"


def test_smtp_failure_is_closed(client, monkeypatch):
    from app import auth

    h = {"X-Device-ID": DEVICE}
    client.post(
        "/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": PASSWORD},
        headers=h,
    )

    def fail(*a):
        raise RuntimeError("SMTP_PASSWORD_SECRET")

    monkeypatch.setattr(auth, "send_code", fail)
    result = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": PASSWORD}, headers=h
    )
    assert result.status_code == 503
    assert "SMTP_PASSWORD_SECRET" not in result.text
    with SessionLocal() as db:
        assert db.scalar(select(LoginChallenge)) is None


def test_invalid_expired_and_wrong_audience_jwt(client):
    import time

    import jwt

    from app.config import settings

    h, pair = login(client)
    claims = jwt.decode(
        pair["access_token"],
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
    )
    for change in [{"exp": int(time.time()) - 1}, {"aud": "another-app"}, {"type": "refresh"}]:
        bad = jwt.encode({**claims, **change}, settings.jwt_secret, algorithm="HS256")
        assert (
            client.get("/auth/me", headers={**h, "Authorization": "Bearer " + bad}).status_code
            == 401
        )


def test_report_month_boundary_and_empty_income(client, monkeypatch):
    from datetime import date

    from app import reports
    from app.models import Budget, Entry

    h, _ = login(client)
    uid = client.get("/auth/me", headers=h).json()["id"]
    with SessionLocal() as db:
        db.add_all(
            [
                Entry(
                    user_id=uid,
                    request_id=str(uuid.uuid4()),
                    kind="expense",
                    category="mercado",
                    amount_cents=1000,
                    on_date=date(2026, 10, 1),
                    description="",
                    essential=False,
                    payment_method="pix",
                ),
                Entry(
                    user_id=uid,
                    request_id=str(uuid.uuid4()),
                    kind="expense",
                    category="mercado",
                    amount_cents=2000,
                    on_date=date(2026, 10, 30),
                    description="",
                    essential=False,
                    payment_method="pix",
                ),
                Entry(
                    user_id=uid,
                    request_id=str(uuid.uuid4()),
                    kind="expense",
                    category="mercado",
                    amount_cents=3000,
                    on_date=date(2026, 11, 1),
                    description="",
                    essential=False,
                    payment_method="pix",
                ),
                Budget(user_id=uid, month=date(2026, 10, 1), category="mercado", limit_cents=4000),
                Budget(user_id=uid, month=date(2026, 11, 1), category="mercado", limit_cents=2000),
            ]
        )
        db.commit()
    monkeypatch.setattr(reports, "today", lambda: date(2026, 11, 5))
    r = client.get("/reports/weekly?week_start=2026-10-26", headers=h).json()
    assert r["expense_cents"] == 5000
    assert r["income_cents"] == 0
    assert [b["spent_cents"] for b in r["budgets"]] == [3000, 3000]
    assert [b["status"] for b in r["budgets"]] == ["within", "exceeded"]


def test_weekly_job_is_idempotent(client):
    from app.weekly_job import run

    h, _ = login(client)
    run()
    run()
    rows = client.get("/reports/history", headers=h).json()
    assert len(rows) == 1
    assert not rows[0]["partial"]


def test_concurrent_otp_consumed_once_mysql(client):
    from concurrent.futures import ThreadPoolExecutor

    import pytest

    from app.db import engine

    if engine.dialect.name != "mysql":
        pytest.skip("Requires real MySQL row locks")
    h = {"X-Device-ID": str(uuid.uuid4())}
    client.post(
        "/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": PASSWORD},
        headers=h,
    )
    cid = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": PASSWORD}, headers=h
    ).json()["challenge_id"]
    payload = {"challenge_id": cid, "code": client.sent[-1][1]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(
                lambda _: client.post("/auth/verify", json=payload, headers=h).status_code, range(2)
            )
        )
    assert sorted(statuses) == [200, 401]


def test_expired_otp_and_forwarded_ip_spoofing(client):
    from sqlalchemy import update

    h = {"X-Device-ID": DEVICE}
    client.post(
        "/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": PASSWORD},
        headers=h,
    )
    cid = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": PASSWORD}, headers=h
    ).json()["challenge_id"]
    with SessionLocal() as db:
        db.execute(update(LoginChallenge).where(LoginChallenge.id == cid).values(expires_at=0))
        db.commit()
    assert (
        client.post(
            "/auth/verify", json={"challenge_id": cid, "code": client.sent[-1][1]}, headers=h
        ).status_code
        == 401
    )
    for i in range(31):
        r = client.post(
            "/auth/login",
            json={"email": f"user{i}@example.com", "password": "bad"},
            headers={"X-Device-ID": str(uuid.uuid4()), "X-Forwarded-For": f"10.1.0.{i}"},
        )
    assert r.status_code == 429


def test_ai_only_receives_aggregates_and_validates_response(client, monkeypatch):
    import json

    from app import reports

    h, _ = login(client)
    client.post("/entries", json=entry(description="private secret medical detail"), headers=h)
    monkeypatch.setattr(reports.settings, "groq_api_key", "unit-test-only")
    captured = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Dentro dos dados informados.",
                                    "suggestions": ["Defina um orçamento."],
                                }
                            )
                        }
                    }
                ]
            }

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            captured.append(kwargs["json"])
            return Response()

    monkeypatch.setattr(reports.httpx, "Client", Client)
    result = client.post("/reports/weekly/insights", headers=h)
    assert result.status_code == 200, result.text
    sent = json.dumps(captured)
    assert "private secret medical detail" not in sent
    assert "alice@example.com" not in sent
    payload = json.loads(captured[0]["messages"][1]["content"])
    assert "user_id" not in payload
    assert all("id" not in g and "title" not in g for g in payload["goals"])


def test_mysql_concurrent_refresh_and_limiter(client):
    from concurrent.futures import ThreadPoolExecutor

    import pytest
    from fastapi import HTTPException

    from app.db import engine
    from app.security import limit

    if engine.dialect.name != "mysql":
        pytest.skip("Requires real MySQL concurrency")
    h, pair = login(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: (
                    client.post(
                        "/auth/refresh", json={"refresh_token": pair["refresh_token"]}, headers=h
                    ).status_code
                ),
                range(2),
            )
        )
    assert sorted(results) == [200, 401]

    def attempt(_):
        try:
            limit("concurrency-test", "one-account", 3, 60)
            return 200
        except HTTPException as e:
            return e.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count(200) == 3 and results.count(429) == 5


def test_contribution_debits_available_not_consumption_and_reverses(client):
    h, _ = login(client)
    other, _ = login(client, "other@example.com")
    client.post("/entries", json=entry(10000, kind="income", category="salario",
        on_date=str(today() - timedelta(days=14))), headers=h)
    goal = client.post("/goals", json={"title": "Reserva", "target_cents": 20000,
        "deadline": str(today() + timedelta(days=30))}, headers=h).json()
    path = f"/goals/{goal['id']}/contributions"
    payload = {"request_id": str(uuid.uuid4()), "amount_cents": 3000, "on_date": str(today())}
    r = client.post(path, json=payload, headers=h)
    assert r.status_code == 201, r.text
    assert client.post(path, json=payload, headers=h).json()["id"] == r.json()["id"]
    report = client.get("/reports/weekly", headers=h).json()
    movements = client.get("/movements", headers=h).json()
    assert len(movements) == 2
    assert movements[0]["kind"] == "contribution"
    assert movements[0]["goal_id"] == goal["id"]
    assert client.get("/movements", headers=other).json() == []
    assert report["available_cents"] == 7000
    assert report["reserved_total_cents"] == 3000
    assert report["expense_cents"] == 0
    assert report["income_cents"] == 0  # carry-over from a previous week
    assert report["goals"][0]["saved_cents"] == 3000
    assert client.get("/reports/weekly", headers=other).json()["available_cents"] == 0
    assert client.delete(f"/contributions/{r.json()['id']}", headers=other).status_code == 404
    assert client.post(path, json={**payload, "request_id": str(uuid.uuid4()),
        "amount_cents": 7001}, headers=h).status_code == 409
    assert client.delete(f"/contributions/{r.json()['id']}", headers=h).status_code == 204
    assert client.get("/reports/weekly", headers=h).json()["available_cents"] == 10000


def test_backdated_contribution_cannot_spend_future_income(client):
    h, _ = login(client)
    goal = client.post("/goals", json={"title": "Reserva", "target_cents": 10000,
        "deadline": str(today() + timedelta(days=30))}, headers=h).json()
    path = f"/goals/{goal['id']}/contributions"
    payload = {"request_id": str(uuid.uuid4()), "amount_cents": 1000,
        "on_date": str(today() - timedelta(days=1))}
    assert client.post(path, json=payload, headers=h).status_code == 409
    client.post("/entries", json=entry(2000, kind="income", category="salario"), headers=h)
    assert client.post(path, json=payload, headers=h).status_code == 409
    assert client.get(path, headers=h).json() == []


def test_ai_failure_diagnostics_and_long_valid_output(client, monkeypatch):
    import json

    import httpx

    from app import reports
    h, _ = login(client)
    monkeypatch.setattr(reports.settings, "groq_api_key", "test-secret")
    original = httpx.Client
    cases = [
        (401, {"error": {"message": "SECRET"}}, "AI_HTTP_401"),
        (429, {"error": {}}, "AI_HTTP_429"),
        (200, {"choices": [{"finish_reason": "length", "message": {"content": "{"}}]}, "AI_TRUNCATED"),
        (200, {"choices": [{"message": {"content": "not json"}}]}, "AI_INVALID_RESPONSE"),
        (200, {"choices": [{"message": {"content": json.dumps({"summary": "a" * 1500,
            "suggestions": ["Defina seus limites."]})}}]}, None),
    ]
    for status, body, code in cases:
        transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
        monkeypatch.setattr(reports.httpx, "Client", lambda **kwargs: original(transport=transport))
        r = client.post("/reports/weekly/insights", headers=h)
        assert "SECRET" not in r.text
        if code:
            assert r.status_code in (502, 503)
            assert r.headers["x-error-code"] == code
        else:
            assert r.status_code == 200, r.text


def test_concurrent_contributions_share_one_available_balance_mysql(client):
    from concurrent.futures import ThreadPoolExecutor

    import pytest

    from app.db import engine
    if engine.dialect.name != "mysql":
        pytest.skip("Requires real MySQL row locks")
    h, _ = login(client)
    client.post("/entries", json=entry(10000, kind="income", category="salario"), headers=h)
    ids = [client.post("/goals", json={"title": f"Meta {i}", "target_cents": 10000,
        "deadline": str(today() + timedelta(days=30))}, headers=h).json()["id"] for i in range(2)]
    def contribute(goal):
        return client.post(f"/goals/{goal}/contributions", json={"request_id": str(uuid.uuid4()),
            "amount_cents": 7000, "on_date": str(today())}, headers=h).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(contribute, ids)) == [201, 409]
    assert client.get("/reports/weekly", headers=h).json()["available_cents"] == 3000
