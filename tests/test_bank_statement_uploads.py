"""Multipart -> auth/limits -> real isolated worker -> encrypted preview -> confirmation.

Fixtures use fictitious data. Non-PicPay profiles are contract tests, not certification
of every export produced by those institutions.
"""

import io
import json
import os
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from test_security_finance import login

from app.config import settings
from app.db import SessionLocal
from app.models import Entry, ImportLease, StatementImport
from app.statement_imports import MIMES, parse_isolated
from app.statement_parser import InvalidStatement, parse
from app.statement_parsers import REGISTRY

FIXTURES = Path(__file__).parent / "fixtures" / "statements"


def pdf(lines, unicode_map=False):
    # Fixed Courier makes table spacing deterministic; no real bank/customer data.
    def literal(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("cp1252")

    stream = b"BT /F1 9 Tf 25 800 Td "
    stream += b" 0 -16 Td ".join(b"(" + literal(line) + b") Tj" for line in lines) + b" ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 900 850] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    if unicode_map:
        objects[3] = objects[3][:-2] + b" /ToUnicode 6 0 R >>"
        cmap = b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap 1 begincodespacerange <00> <ff> endcodespacerange 1 beginbfrange <00> <ff> <0000> endbfrange endcmap end end"
        objects.append(
            b"<< /Length " + str(len(cmap)).encode() + b" >>\nstream\n" + cmap + b"\nendstream"
        )
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode() + b"".join(
        f"{o:010d} 00000 n \n".encode() for o in offsets
    )
    return (
        out
        + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n".encode()
        + str(start).encode()
        + b"\n%%EOF\n"
    )


def fixture(bank, fmt):
    name = REGISTRY[bank].names[0]
    if fmt == "csv":
        return (FIXTURES / f"{bank.lower()}.csv").read_bytes()
    if fmt == "ofx":
        return (
            f"OFXHEADER:100\nDATA:OFXSGML\n\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>BRL\n"
            f"<BANKACCTFROM><BANKID>{REGISTRY[bank].bank_ids[0]}\n</BANKACCTFROM><BANKTRANLIST>"
            "<STMTTRN><DTPOSTED>20251113\n<TRNAMT>-26.00\n<MEMO>Private counterparty\n</STMTTRN>"
            "<STMTTRN><DTPOSTED>20251113\n<TRNAMT>1234.56\n</STMTTRN>"
            "</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"
        ).encode()
    if fmt == "pdf":
        if bank == "PICPAY":
            return pdf(
                [
                    "PicPay",
                    "13 de novembro 2025     Saldo ao final do dia: R$ 1.208,56",
                    "Hora     Tipo                   Origem / Destino     Forma de pagamento     Valor",
                    "20:13    Compra realizada       Loja Exemplo         Com saldo              -R$ 26,00",
                    "10:00    Pix recebido           Pessoa ficticia      Com saldo              +R$ 1.234,56",
                    "Documento emitido em:   PicPay Serviços S/A",
                ]
            )
        return pdf(
            [
                name,
                "Data          Valor        Estabelecimento",
                "13/11/2025    -26,00       Loja Exemplo",
                "13/11/2025    1.234,56     Fonte Exemplo",
            ]
        )
    if fmt == "docx":
        out = io.BytesIO()
        rows = [["Data", "Valor"], ["13/11/2025", "-26,00"], ["13/11/2025", "1.234,56"]]
        table = "".join(
            "<w:tr>"
            + "".join("<w:tc><w:p><w:r><w:t>" + escape(c) + "</w:t></w:r></w:p></w:tc>" for c in r)
            + "</w:tr>"
            for r in rows
        )
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
                + name
                + "</w:t></w:r></w:p><w:tbl>"
                + table
                + "</w:tbl></w:body></w:document>",
            )
        return out.getvalue()
    raise AssertionError(fmt)


def upload(client, headers, bank="PICPAY", fmt="csv", content=None, mime=None):
    return client.post(
        "/imports/preview",
        headers=headers,
        data={"institution": bank},
        files={
            "file": (
                "statement." + fmt,
                fixture(bank, fmt) if content is None else content,
                mime or sorted(MIMES[fmt])[0],
            )
        },
    )


@pytest.mark.parametrize("bank", REGISTRY)
@pytest.mark.parametrize("fmt", ["csv", "pdf", "ofx", "docx"])
def test_real_multipart_worker_confirm(client, bank, fmt):
    headers, _ = login(client)
    response = upload(client, headers, bank, fmt)
    assert response.status_code == 200, response.text
    p = response.json()
    assert len(p["rows"]) == 2
    assert (p["income_cents"], p["expense_cents"]) == (123456, 2600)
    assert "Pessoa ficticia" not in response.text and "Private counterparty" not in response.text
    with SessionLocal() as db:
        preview = db.get(StatementImport, p["id"])
        assert b"Loja Exemplo" not in preview.payload and b"amount_cents" not in preview.payload
        assert (
            len(
                json.loads(
                    Fernet(settings.statement_encryption_key.encode()).decrypt(preview.payload)
                )["rows"]
            )
            == 2
        )
        assert not db.scalars(select(Entry)).all()
    confirmed = client.post(
        f"/imports/{p['id']}/confirm", headers=headers, json={"selected": [0, 1]}
    )
    assert confirmed.status_code == 200 and confirmed.json()["imported_count"] == 2
    with SessionLocal() as db:
        entries = db.scalars(select(Entry)).all()
        assert len(entries) == 2
        assert sorted(e.amount_cents for e in entries) == [2600, 123456]
        for entry in entries:
            assert entry.protected_context and b"Loja Exemplo" not in entry.protected_context
        if fmt == "csv":
            assert entries[0].context["merchant"] == "Loja Exemplo"


@pytest.mark.parametrize("fmt", ["csv", "pdf", "ofx", "docx"])
def test_other_bank_rejected(client, fmt):
    headers, _ = login(client)
    r = upload(client, headers, "NUBANK", fmt, fixture("PICPAY", fmt))
    assert r.status_code == 422 and r.headers["X-Error-Code"] == "institution_mismatch"
    with SessionLocal() as db:
        assert not db.scalars(select(StatementImport)).all()
        assert not db.scalars(select(Entry)).all()
        assert all(not r.token for r in db.scalars(select(ImportLease)))


def test_multipart_contract_and_auth(client):
    headers, _ = login(client)
    assert upload(client, {}).status_code == 401
    assert (
        client.post(
            "/imports/preview", headers=headers, files={"file": ("x.csv", b"x")}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/imports/preview",
            headers=headers,
            data={"institution": "UNKNOWN"},
            files={"file": ("x.csv", b"x")},
        ).status_code
        == 422
    )
    assert upload(client, headers, content=b"MZ executable").status_code == 422
    assert upload(client, headers, mime="application/pdf").status_code == 415
    assert upload(client, headers, content=b"").status_code == 413


def test_multipart_size_rate_limit_and_duplicate_fields(client):
    headers, _ = login(client)
    assert upload(client, headers, content=b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    assert upload(client, headers, content=b"x" * (5 * 1024 * 1024 + 65537)).status_code == 413
    r = client.post(
        "/imports/preview",
        headers=headers,
        files=[
            ("institution", (None, "PICPAY")),
            ("institution", (None, "NUBANK")),
            ("file", ("x.csv", b"x")),
        ],
    )
    assert r.status_code == 422
    for _ in range(3):
        assert upload(client, headers, content=b"invalid").status_code == 422
    assert upload(client, headers).status_code == 429


def test_picpay_unicode_minus_clock_and_privacy():
    data = fixture("PICPAY", "csv")
    rows = parse_isolated(data, "csv", "PICPAY")
    assert rows[0]["amount_cents"] == 2600 and rows[0]["kind"] == "expense"
    assert rows[0]["context"]["occurred_at"] == "2025-11-13T20:13:00-03:00"
    assert "merchant" not in rows[1]["context"]
    for changed in [
        data.replace("−R$".encode(), b"+R$"),
        data.replace(b"20:13", b"99:99"),
        data.replace(b"2025-11-13", b"2099-11-13"),
        data.replace(b"Loja Exemplo", b"<script>evil</script>"),
    ]:
        with pytest.raises(InvalidStatement):
            parse(changed, "csv", "PICPAY")


def test_picpay_refund_follows_signed_amount():
    data = fixture("PICPAY", "csv").replace(b"Compra realizada", b"Pix devolvido")
    assert parse(data, "csv", "PICPAY")[0]["kind"] == "expense"
    assert parse(data.replace("−R$".encode(), b"+R$"), "csv", "PICPAY")[0]["kind"] == "income"


def test_unicode_font_map_in_real_worker(client):
    data = pdf(
        [
            "PicPay",
            "13 de novembro 2025     Saldo ao final do dia: R$ 0,00",
            "Hora     Tipo                   Origem / Destino     Forma de pagamento     Valor",
            "20:13    Compra realizada       Loja Exemplo         Com saldo              -R$ 26,00",
        ],
        unicode_map=True,
    )
    headers, _ = login(client)
    r = upload(client, headers, "PICPAY", "pdf", data)
    assert r.status_code == 200, r.text
    assert r.json()["expense_cents"] == 2600


@pytest.mark.parametrize("bank", REGISTRY)
def test_bankid_cross_validation(bank):
    other = "NUBANK" if bank != "NUBANK" else "ITAU"
    with pytest.raises(InvalidStatement, match="institution_mismatch"):
        parse(fixture(bank, "ofx"), "ofx", other)


def test_cp1252_bom_preambles_and_unknown_columns():
    data = fixture("ITAU", "csv").decode()
    assert parse(data.encode("cp1252"), "csv", "ITAU") == parse(
        data.encode("utf-8-sig"), "csv", "ITAU"
    )
    with pytest.raises(InvalidStatement):
        parse(data.replace("Ag./Origem", "Unknown").encode(), "csv", "ITAU")


def test_malformed_multipart_and_slot_release(client):
    headers, _ = login(client)
    r = client.post(
        "/imports/preview",
        headers={**headers, "Content-Type": "multipart/form-data"},
        content=b"broken",
    )
    assert r.status_code == 400
    r = client.post(
        "/imports/preview",
        headers=headers,
        data={"institution": "PICPAY"},
        files=[("file", ("one.csv", b"x")), ("file", ("two.csv", b"x"))],
    )
    assert r.status_code == 400
    with SessionLocal() as db:
        assert all(not lease.token for lease in db.scalars(select(ImportLease)))


def test_cors_upload_preflight(client):
    r = client.options(
        "/imports/preview",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,x-device-id",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:8081"


@pytest.mark.skipif(
    not os.environ.get("PRIVATE_STATEMENT_PDF"), reason="Optional private sample; never committed"
)
def test_private_picpay_pdf_full_http(client):
    data = Path(os.environ["PRIVATE_STATEMENT_PDF"]).read_bytes()
    headers, _ = login(client)
    r = upload(client, headers, "PICPAY", "pdf", data)
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert len(rows) == 118
    assert sum(row["kind"] == "expense" for row in rows) == 101
    assert all(not re.search(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", json.dumps(row)) for row in rows)
