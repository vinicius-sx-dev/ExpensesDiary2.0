import io
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select
from test_security_finance import login

from app.config import Settings, settings
from app.db import SessionLocal
from app.models import Entry, StatementImport
from app.statement_imports import acquire_slot, parse_isolated, release_slot
from app.statement_parser import InvalidStatement, parse

CSV = "Data;Valor;Descrição;CPF;Conta\n01/11/2025;1234,56;Pix Pessoa privada;12345678901;000123\n02/11/2025;-34,56;Local privado;12345678901;000123\n".encode()


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(settings, "statement_encryption_key", Fernet.generate_key().decode())


def upload(client, headers, data=CSV, fmt="csv"):
    return client.post(
        "/imports/preview?institution=NUBANK&format=" + fmt,
        content=data,
        headers={**headers, "Content-Type": "application/octet-stream"},
    )


def test_upload_preview_confirm_privacy_and_balance(client):
    h, _ = login(client)
    response = upload(client, h)
    assert response.status_code == 200, response.text
    p = response.json()
    assert p["income_cents"] == 123456 and p["expense_cents"] == 3456
    for private in ["Pessoa", "privado", "12345678901", "000123"]:
        assert private not in response.text
    with SessionLocal() as db:
        assert not db.scalars(select(Entry)).all()
        row = db.get(StatementImport, p["id"])
        assert b"123456" not in row.payload and b"on_date" not in row.payload
        plain = Fernet(settings.statement_encryption_key.encode()).decrypt(row.payload)
        assert b"CPF" not in plain and b"privado" not in plain and b"Conta" not in plain
    assert upload(client, h).json()["id"] == p["id"]
    for _ in range(2):
        r = client.post(f"/imports/{p['id']}/confirm", json={"selected": [0, 1]}, headers=h)
        assert r.status_code == 200 and r.json()["imported_count"] == 2
    assert upload(client, h).status_code == 409
    with SessionLocal() as db:
        rows = db.scalars(select(Entry)).all()
        assert len(rows) == 2 and all(
            e.description == "" and e.payment_method == "other" for e in rows
        )
        assert db.get(StatementImport, p["id"]).payload == b""
        from app.balance import balance_at
        from app.schemas import today

        assert balance_at(db, rows[0].user_id, today())["available_cents"] == 120000


def test_auth_ownership_expiry_and_selection(client):
    a, _ = login(client)
    b, _ = login(client, "bob@example.com")
    assert upload(client, {}).status_code == 401
    p = upload(client, a).json()
    path = "/imports/" + p["id"]
    assert client.get(path, headers=b).status_code == 404
    assert client.delete(path, headers=b).status_code == 404
    assert client.post(path + "/confirm", headers=b, json={"selected": [0]}).status_code == 404
    for selected in [[], [-1], [0, 0], [2]]:
        assert (
            client.post(path + "/confirm", headers=a, json={"selected": selected}).status_code
            == 422
        )
    with SessionLocal() as db:
        row = db.get(StatementImport, p["id"])
        row.payload = Fernet(settings.statement_encryption_key.encode()).encrypt_at_time(
            b"{}", int(time.time()) - 4000
        )
        db.commit()
    assert client.post(path + "/confirm", headers=a, json={"selected": [0]}).status_code == 410
    assert client.delete(path, headers=a).status_code == 204


def test_duplicates_are_multiset_not_silent_deletion(client):
    h, _ = login(client)
    p = upload(client, h).json()
    assert (
        client.post(f"/imports/{p['id']}/confirm", headers=h, json={"selected": [0]}).status_code
        == 200
    )
    p2 = upload(client, h, CSV + b"01/11/2025;1234,56;Other;0;0\n").json()
    assert [r["possible_duplicate"] for r in p2["rows"]] == [True, False, False]


def test_limits_and_content_type(client):
    h, _ = login(client)
    assert upload(client, h, b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    assert upload(client, h, b"dummy", "doc").status_code == 415
    assert (
        client.post(
            "/imports/preview?institution=NUBANK&format=csv",
            headers={**h, "Content-Type": "application/pdf"},
            content=CSV,
        ).status_code
        == 415
    )
    for _ in range(5):
        assert upload(client, h, b"not a statement").status_code == 422
    r = upload(client, h)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_global_slots():
    one, two = acquire_slot(), acquire_slot()
    with pytest.raises(HTTPException) as err:
        acquire_slot()
    assert err.value.status_code == 429
    release_slot(one)
    three = acquire_slot()
    release_slot(two)
    release_slot(three)


def test_pending_limit_and_delete(client):
    h, _ = login(client)
    for n in range(3):
        r = upload(client, h, CSV + b"\n" * n)
        assert r.status_code == 200
    assert upload(client, h, CSV + b"\n" * 3).status_code == 409
    assert len(client.get("/imports", headers=h).json()) == 3
    assert client.delete("/imports/" + r.json()["id"], headers=h).status_code == 204
    assert upload(client, h, CSV + b"\n" * 3).status_code == 200


@pytest.mark.parametrize(
    "data",
    [
        b"MZ executable",
        b"%PDF-1.4 fake",
        b"PK\x03\x04 fake",
        b"\x00csv",
        b"<html>hello</html>",
        b"date;amount\n2025-01-01;NaN",
        b"date;amount\n2025-01-01;1.234",
        b"date;amount\n2099-01-01;10",
        b"date;amount\n2025-01-01;10\nwrong line",
        b"data;valor;historico\n01/01/2025;100;Saldo anterior",
        b"date;amount\n2025-01-01;0",
        b"date;amount;amount\n2025-01-01;1;2",
    ],
)
def test_reject_non_statement_and_ambiguous_rows(data):
    with pytest.raises((InvalidStatement, ValueError)):
        parse(data, "csv")


@pytest.mark.parametrize(
    "fmt,data",
    [
        (
            "xml",
            b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><statement>&x;</statement>',
        ),
        ("xml", b"<invoice><amount>100</amount></invoice>"),
        (
            "ofx",
            b"<OFX><CURDEF>USD</CURDEF><STMTTRN><DTPOSTED>20250101</DTPOSTED><TRNAMT>100</TRNAMT></STMTTRN></OFX>",
        ),
        ("pdf", b"%PDF-1.4\n/JavaScript evil\n%%EOF"),
    ],
)
def test_isolated_worker_rejects_bad_documents(fmt, data):
    with pytest.raises(HTTPException) as err:
        parse_isolated(data, fmt)
    assert err.value.status_code == 422


def test_structured_formats():
    xml = b"<extrato><movimentacao><data>01/01/2025</data><valor>10,50</valor><tipo>D</tipo></movimentacao></extrato>"
    assert parse_isolated(xml, "xml")[0]["kind"] == "expense"
    ofx = b"OFXHEADER:100\nDATA:OFXSGML\n\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>BRL\n<BANKTRANLIST><STMTTRN><DTPOSTED>20250101\n<TRNAMT>-10.50\n<MEMO>private\n</STMTTRN></BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"
    rows = parse_isolated(ofx, "ofx")
    assert rows == [{"on_date": "2025-01-01", "amount_cents": 1050, "kind": "expense"}]
    assert parse(CSV, "csv") == parse_isolated(CSV, "csv")


def docx(extra=None):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr(
            "word/document.xml",
            """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Data</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Valor</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>01/01/2025</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>-10,00</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>""",
        )
        if extra:
            z.writestr(*extra)
    return out.getvalue()


def test_docx_and_active_content():
    assert parse_isolated(docx(), "docx")[0]["amount_cents"] == 1000
    for extra in [
        ("word/vbaProject.bin", b"macro"),
        ("../evil.xml", b"<x/>"),
        (
            "word/_rels/document.xml.rels",
            b'<Relationships><Relationship TargetMode="External" Target="https://example.com"/></Relationships>',
        ),
    ]:
        with pytest.raises(HTTPException):
            parse_isolated(docx(extra), "docx")


def test_zip_bomb():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", b"a" * 3_000_000)
    with pytest.raises(HTTPException):
        parse_isolated(out.getvalue(), "docx")


def test_missing_encryption_key(client, monkeypatch):
    h, _ = login(client)
    monkeypatch.setattr(settings, "statement_encryption_key", "")
    assert upload(client, h).status_code == 503


def test_mysql_concurrent_confirmation(client):
    from app.db import engine

    if engine.dialect.name != "mysql":
        pytest.skip("Requires MySQL row locks; exercised in CI")
    h, _ = login(client)
    p = upload(client, h).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.post(
                    f"/imports/{p['id']}/confirm", headers=h, json={"selected": [0, 1]}
                ),
                range(2),
            )
        )
    assert all(r.status_code == 200 for r in results)
    with SessionLocal() as db:
        assert len(db.scalars(select(Entry)).all()) == 2


def test_production_requires_db_tls():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="DATABASE_SSL_CA"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="mysql+pymysql://test/db",
            jwt_secret="testing" * 10,
            database_ssl_ca="",
        )


def pdf_fixture(active=False):
    # Minimal deterministic text PDF; no real customer statement or extra dependency.
    stream = b"BT /F1 12 Tf 50 750 Td (Data        Valor) Tj 0 -20 Td (01/01/2025  -10,00) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R"
        + (b" /OpenAction << /S /JavaScript /JS (alert) >>" if active else b"")
        + b" >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    start = len(pdf)
    pdf += b"xref\n0 6\n0000000000 65535 f \n"
    pdf += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    pdf += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(start).encode() + b"\n%%EOF\n"
    return pdf


def test_text_pdf_and_javascript_rejected():
    assert parse_isolated(pdf_fixture(), "pdf") == [
        {"on_date": "2025-01-01", "amount_cents": 1000, "kind": "expense"}
    ]
    with pytest.raises(HTTPException):
        parse_isolated(pdf_fixture(active=True), "pdf")


def test_timeout_kills_worker(monkeypatch):
    import subprocess

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("worker", 12)

    monkeypatch.setattr("app.statement_imports.subprocess.run", timeout)
    with pytest.raises(HTTPException) as error:
        parse_isolated(CSV, "csv")
    assert error.value.status_code == 504


def test_camt_booked_brl_only():
    xml = b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt><Stmt><Ntry><Amt Ccy="BRL">10.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts><BookgDt><Dt>2025-01-01</Dt></BookgDt></Ntry></Stmt></BkToCstmrStmt></Document>'
    assert parse_isolated(xml, "xml")[0]["kind"] == "expense"
    for changed in [xml.replace(b"BRL", b"USD"), xml.replace(b"BOOK", b"PDNG")]:
        with pytest.raises(HTTPException):
            parse_isolated(changed, "xml")
