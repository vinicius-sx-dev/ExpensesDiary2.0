"""Regressions for explicit learning, import transactions and report aggregates."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from test_security_finance import login, entry

from app.advisor.engine import patterns
from app.classification import learned_categories, suggest
from app.config import settings
from app.db import SessionLocal
from app.models import Entry, StatementImport
from app.schemas import today


@pytest.fixture(autouse=True)
def encryption(monkeypatch):
    monkeypatch.setattr(settings, "statement_encryption_key", Fernet.generate_key().decode())


def upload(client, headers, day="2025-01-01", merchant="Loja Exemplo", amount=10):
    csv = ('data,hora,tipo,"origem / destino",valor,"forma de pagamento"\n'
           f'{day},10:00,"Compra realizada","{merchant}","−R$ {amount},00","Com saldo"\n')
    response = client.post("/imports/preview?institution=PICPAY&format=csv",
                           content=csv.encode(), headers={**headers, "Content-Type": "text/csv"})
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, h, preview, **extra):
    return client.post(f"/imports/{preview['id']}/confirm",
                       headers=h, json={"selected": [0], **extra})


def test_explicit_learning_is_private_and_unreviewed_predictions_do_not_train(client):
    a, _ = login(client)
    b, _ = login(client, "bob@example.com")
    p = upload(client, a)
    assert p["rows"][0]["category"] == "outros"
    choice = {"index": 0, "category": "restaurante", "niche": "fast_food", "essential": True}
    assert confirm(client, a, p, classifications=[choice]).status_code == 200
    assert confirm(client, a, p, classifications=[choice]).json()["already_confirmed"]
    q = upload(client, a, "2025-01-02")
    assert q["rows"][0]["category"] == "restaurante"
    assert q["rows"][0]["classification_source"] == "history"
    assert upload(client, b)["rows"][0]["category"] == "outros"
    assert confirm(client, a, q).status_code == 200
    rows = client.get("/entries", headers=a).json()
    reviewed = next(r for r in rows if r["context"]["classification_reviewed"])
    automatic = next(r for r in rows if not r["context"]["classification_reviewed"])
    assert reviewed["essential"] is True and automatic["essential"] is False
    assert client.delete(f"/entries/{reviewed['id']}", headers=a).status_code == 204
    # Removing the only explicit example also removes its learning; predictions cannot perpetuate it.
    assert upload(client, a, "2025-01-03")["rows"][0]["category"] == "outros"


def test_edit_reclassifies_old_import_and_keeps_encrypted_context(client):
    h, _ = login(client)
    p = upload(client, h)
    assert confirm(client, h, p).status_code == 200
    row = client.get("/entries", headers=h).json()[0]
    body = {key: row[key] for key in (
        "request_id", "kind", "category", "amount_cents", "on_date",
        "description", "essential", "payment_method"
    )}
    body.update(category="mercado", context={"merchant": "Loja Exemplo"})
    updated = client.put(f"/entries/{row['id']}", headers=h, json=body)
    assert updated.status_code == 200, updated.text
    assert updated.json()["context"]["source"] == "statement"
    assert updated.json()["context"]["classification_reviewed"] is True
    assert upload(client, h, "2025-01-02")["rows"][0]["category"] == "mercado"
    with SessionLocal() as db:
        stored = db.get(Entry, row["id"])
        assert b"Loja Exemplo" not in stored.protected_context


def test_hints_and_income_are_separate():
    expense = {"kind": "expense", "context": {"merchant": "Supermercado Exemplo"}}
    assert suggest(expense, {})["category"] == "mercado"
    assert suggest({**expense, "kind": "income"}, {})["category"] == "outras_receitas"
    assert suggest(expense, {("income", "supermercado exemplo"): "salario"})["category"] == "mercado"
    assert suggest({"kind": "expense", "context": {"merchant": "Supermercado e Drogaria"}}, {})["category"] == "outros"


def test_confirmation_rechecks_duplicates_and_allows_explicit_override(client):
    h, _ = login(client)
    first = upload(client, h)
    second = upload(client, h, merchant="Outra Loja")
    assert second["rows"][0]["possible_duplicate"] is False
    assert confirm(client, h, first).status_code == 200
    assert confirm(client, h, second).status_code == 409
    assert client.get(f"/imports/{second['id']}", headers=h).json()["rows"][0]["possible_duplicate"]
    assert confirm(client, h, second, allow_duplicates=True).status_code == 200
    assert len(client.get("/entries", headers=h).json()) == 2


@pytest.mark.parametrize("extra", [
    {"classifications": [{"index": 0, "category": "salario"}]},
    {"classifications": [{"index": 1, "category": "mercado"}]},
    {"classifications": [{"index": 0, "category": "mercado"}] * 2},
    {"classifications": [{"index": 0, "category": "mercado", "essential": "false"}]},
])
def test_invalid_classifications_do_not_confirm(client, extra):
    h, _ = login(client)
    p = upload(client, h)
    assert confirm(client, h, p, **extra).status_code == 422
    assert client.get("/entries", headers=h).json() == []
    with SessionLocal() as db:
        assert db.get(StatementImport, p["id"]).status == "pending"


def test_boolean_row_index_rejected(client):
    h, _ = login(client)
    p = upload(client, h)
    result = client.post(f"/imports/{p['id']}/confirm", headers=h, json={"selected": [False]})
    assert result.status_code == 422


def test_only_reviewed_nonessential_imports_feed_patterns():
    rows = [SimpleNamespace(
        kind="expense", category="restaurante", essential=False, amount_cents=1000,
        on_date=today() - timedelta(days=i * 7),
        context={"source": "statement", "classification_reviewed": False},
    ) for i in range(3)]
    assert patterns(rows, today()) == []
    for row in rows:
        row.context["classification_reviewed"] = True
    assert patterns(rows, today())[0]["occurrences"] == 3
    rows[0].essential = True
    assert patterns(rows, today()) == []


def test_reports_daily_and_category_totals_are_user_scoped(client):
    h, _ = login(client)
    other, _ = login(client, "other@example.com")
    assert client.post("/entries", headers=h, json=entry(10000, kind="income", category="salario")).status_code == 201
    assert client.post("/entries", headers=h, json=entry(2500, category="mercado")).status_code == 201
    assert client.post("/entries", headers=other, json=entry(9999)).status_code == 201
    report = client.get("/reports/weekly", headers=h).json()
    assert sum(d["income_cents"] for d in report["daily"]) == report["income_cents"] == 10000
    assert sum(d["expense_cents"] for d in report["daily"]) == report["expense_cents"] == 2500
    assert report["income_categories"] == [{"category": "salario", "amount_cents": 10000}]
    assert report["daily"][-1]["date"] == str(today())
    assert 1 <= len(report["daily"]) <= 7


def test_conflicting_explicit_labels_abstain_and_deletion_recalculates(client):
    h, _ = login(client)
    for category in ("mercado", "restaurante"):
        result = client.post("/entries", headers=h, json=entry(
            category=category, context={"merchant": "Loja Exemplo"}
        ))
        assert result.status_code == 201, result.text
    assert upload(client, h)["rows"][0]["category"] == "outros"
    assert client.delete(f"/entries/{result.json()['id']}", headers=h).status_code == 204
    assert upload(client, h, "2025-01-02")["rows"][0]["category"] == "mercado"


def test_confirmation_can_review_maximum_row_count_atomically(client, monkeypatch):
    from app import statement_imports
    h, _ = login(client)
    rows = [{"on_date": "2025-01-01", "amount_cents": i + 1, "kind": "expense"} for i in range(2000)]
    monkeypatch.setattr(statement_imports, "parse_isolated", lambda *args: rows)
    p = upload(client, h)
    response = client.post(f"/imports/{p['id']}/confirm", headers=h, json={
        "selected": list(range(2000)),
        "classifications": [{"index": i, "category": "mercado"} for i in range(2000)],
    })
    assert response.status_code == 200, response.text
    assert response.json()["imported_count"] == 2000


def test_picpay_internal_transfers_are_flagged_for_explicit_review():
    from app.statement_parser import parse
    csv = ('data,hora,tipo,"origem / destino",valor,"forma de pagamento"\n'
           '2025-01-01,10:00,"Dinheiro guardado","Reserva","−R$ 10,00","Com saldo"\n'
           '2025-01-02,10:00,"Dinheiro resgatado","Reserva","+R$ 10,00","Com saldo"\n')
    rows = parse(csv.encode(), "csv", "PICPAY")
    assert all(r["review_reason"] == "internal_transfer" for r in rows)
    assert [r["kind"] for r in rows] == ["expense", "income"]
