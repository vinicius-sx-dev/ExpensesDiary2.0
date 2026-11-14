"""Data-only parsers. Run through statement_worker, never in the API process."""

import csv
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from defusedxml import ElementTree as ET

MAX_BYTES = 5 * 1024 * 1024
MAX_TEXT = 2 * 1024 * 1024
MAX_ROWS = 2000


class InvalidStatement(ValueError):
    pass


def reject():
    raise InvalidStatement("Extrato inválido, ambíguo ou não suportado. Exporte em CSV ou OFX.")


def norm(s):
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.strip().lower()) if not unicodedata.combining(c)
    )


def text(data):
    if b"\x00" in data:
        reject()
    try:
        s = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        s = data.decode("cp1252")
    if len(s) > MAX_TEXT or any(ord(c) < 32 and c not in "\r\n\t" for c in s):
        reject()
    if re.search(r"<\s*(?:script|html|iframe)|<!\s*(?:DOCTYPE|ENTITY)", s, re.I):
        reject()
    return s


def day(s):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            d = datetime.strptime(s.strip(), fmt).date()
            if date(2000, 1, 1) <= d <= datetime.now(ZoneInfo("America/Sao_Paulo")).date():
                return d.isoformat()
        except ValueError:
            pass
    reject()


def money(s, decimal_comma):
    s = s.strip().replace("R$", "").replace(" ", "").replace("\xa0", "")
    # Do not guess ambiguous thousands/decimal separators.
    pattern = (
        r"[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{2})?" if decimal_comma else r"[+-]?\d+(?:\.\d{2})?"
    )
    if not re.fullmatch(pattern, s):
        reject()
    n = Decimal(s.replace(".", "").replace(",", ".") if decimal_comma else s) * 100
    if not n or abs(n) > 10_000_000_000:
        reject()
    return int(n)


def movement(d, value, direction="", decimal_comma=True):
    sign = norm(direction)
    credit = {"c", "credito", "credit", "entrada", "income", "receita"}
    debit = {"d", "debito", "debit", "saida", "expense", "despesa"}
    n = money(value, decimal_comma)
    if sign:
        if sign not in credit | debit or (n < 0 and sign in credit):
            reject()
        n = abs(n) * (-1 if sign in debit else 1)
    return {"on_date": day(d), "amount_cents": abs(n), "kind": "income" if n > 0 else "expense"}


ALIASES = {
    "data": "date",
    "date": "date",
    "data lancamento": "date",
    "data de lancamento": "date",
    "valor": "amount",
    "amount": "amount",
    "valor lancamento": "amount",
    "tipo": "direction",
    "natureza": "direction",
    "c/d": "direction",
    "d/c": "direction",
    "entrada": "credit",
    "credito": "credit",
    "credit": "credit",
    "saida": "debit",
    "debito": "debit",
    "debit": "debit",
    "descricao": "description",
    "historico": "description",
    "description": "description",
    "lancamento": "description",
    "saldo": "balance",
    "balance": "balance",
    "documento": "ignored",
    "identificador": "ignored",
    "id": "ignored",
    "cpf": "ignored",
    "cnpj": "ignored",
    "conta": "ignored",
    "agencia": "ignored",
}


def table(rows):
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not 2 <= len(rows) <= MAX_ROWS + 1 or len(rows[0]) > 20:
        reject()
    headers = [ALIASES.get(norm(c)) for c in rows[0]]
    if None in headers or headers.count("date") != 1:
        reject()
    for k in ("amount", "direction", "credit", "debit", "description", "balance"):
        if headers.count(k) > 1:
            reject()
    if not (("amount" in headers) ^ ("credit" in headers and "debit" in headers)):
        reject()
    result = []
    for r in rows[1:]:
        if len(r) != len(headers) or any(len(c) > 1000 for c in r):
            reject()
        v = dict(zip(headers, r))
        # A balance row must not become income/expense, even if it has a date.
        if re.search(r"\b(saldo|total|balance)\b", norm(v.get("description", ""))):
            reject()
        if "amount" in v:
            raw = v["amount"].strip()
            suffix = re.search(r"\s*([CD])$", raw, re.I)
            direction = v.get("direction", "")
            if suffix:
                if direction and norm(direction) != norm(suffix[1]):
                    reject()
                direction, raw = suffix[1], raw[: suffix.start()]
            # Decimal style is explicit per cell (both styles accepted, no 1.234 guessing).
            comma = "," in raw or "." not in raw
            result.append(movement(v["date"], raw, direction, comma))
        else:
            credit, debit = v["credit"].strip(), v["debit"].strip()
            zeros = {"", "0", "0,00", "0.00", "-"}
            if (credit in zeros) == (debit in zeros):
                reject()
            raw, direction = (debit, "d") if credit in zeros else (credit, "c")
            if raw.startswith("-"):
                reject()
            result.append(movement(v["date"], raw, direction, "," in raw or "." not in raw))
    return result


def csv_rows(data):
    s = text(data)
    try:
        dialect = csv.Sniffer().sniff(s[:8192], delimiters=";,\t")
        return table(list(csv.reader(io.StringIO(s), dialect, strict=True)))
    except csv.Error:
        reject()


def xml_rows(data):
    # Only explicit statement schemas, never arbitrary XML documents or invoices.
    root = ET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    if re.fullmatch(r"\{urn:iso:std:iso:20022:tech:xsd:camt\.053\.001\.\d{2}\}Document", root.tag):
        namespace = root.tag.split("}")[0] + "}"
        rows = []
        for entry in root.iter(namespace + "Ntry"):
            amount = entry.find(namespace + "Amt")
            indicator = entry.findtext(namespace + "CdtDbtInd", "")
            status = entry.find(namespace + "Sts")
            if (
                amount is None
                or amount.attrib.get("Ccy") != "BRL"
                or indicator not in {"CRDT", "DBIT"}
            ):
                reject()
            if (
                status is None
                or (status.text or "").strip() != "BOOK"
                and status.findtext(namespace + "Cd") != "BOOK"
            ):
                reject()
            book = entry.find(namespace + "BookgDt")
            if book is None:
                reject()
            d = book.findtext(namespace + "Dt", "")
            if not d:  # Do not silently truncate timestamps/time zones.
                reject()
            raw = amount.text or ""
            if raw.startswith("-"):
                reject()
            rows.append(movement(d, raw, "c" if indicator == "CRDT" else "d", False))
        return rows
    if root.tag not in {"extrato", "statement", "OFX", "Document"}:
        reject()
    if root.tag == "OFX":
        currencies = [e.text for e in root.iter("CURDEF")]
        if not currencies or any(c != "BRL" for c in currencies):
            reject()
        rows = []
        for tr in root.iter("STMTTRN"):
            d, amount = tr.findtext("DTPOSTED", ""), tr.findtext("TRNAMT", "")
            if not re.fullmatch(r"\d{8}(?:\d{6}(?:\.\d+)?(?:\[[^\]]{1,30}\])?)?", d):
                reject()
            rows.append(movement(f"{d[:4]}-{d[4:6]}-{d[6:8]}", amount, decimal_comma=False))
        return rows
    if root.tag == "Document":
        reject()  # Namespaced ISO 20022 is handled below.
    if root.attrib.get("currency", root.attrib.get("moeda", "BRL")) != "BRL":
        reject()
    rows = []
    for tr in root:
        if tr.tag not in {"movimentacao", "transaction"}:
            reject()
        keys = [e.tag for e in tr]
        if len(set(keys)) != len(keys) or set(keys) - {
            "data",
            "date",
            "valor",
            "amount",
            "tipo",
            "direction",
            "descricao",
            "description",
        }:
            reject()
        d = tr.findtext("data") or tr.findtext("date", "")
        a = tr.findtext("valor") or tr.findtext("amount", "")
        rows.append(
            movement(
                d, a, tr.findtext("tipo") or tr.findtext("direction", ""), "," in a or "." not in a
            )
        )
    return rows


def ofx_rows(data):
    s = text(data)
    start = s.find("<OFX>")
    if start < 0 or len(s[:start]) > 1024:
        reject()
    body = s[start:]
    if "</TRNAMT>" not in body:  # OFX 1.x SGML: close only known leaf elements.
        body = re.sub(
            r"<([A-Z0-9.]+)>([^<]+)",
            lambda m: f"<{m[1]}>{m[2].strip()}</{m[1]}>" if m[2].strip() else m[0],
            body,
        )
    return xml_rows(body.encode())


def docx_rows(data):
    if not data.startswith(b"PK\x03\x04"):
        reject()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = z.infolist()
        if len(infos) > 150 or sum(i.file_size for i in infos) > 10 * 1024 * 1024:
            reject()
        names = [i.filename for i in infos]
        if (
            len(set(names)) != len(names)
            or "word/document.xml" not in names
            or "[Content_Types].xml" not in names
        ):
            reject()
        for i in infos:
            if (
                i.flag_bits & 1
                or i.file_size > MAX_TEXT
                or i.file_size > max(i.compress_size, 1) * 100
            ):
                reject()
            if ".." in i.filename or i.filename.startswith("/") or "\\" in i.filename:
                reject()
            if not i.filename.endswith((".xml", ".rels")):
                reject()  # No macros, embedded files, images, executables.
            content = z.read(i)
            node = ET.fromstring(
                content, forbid_dtd=True, forbid_entities=True, forbid_external=True
            )
            for e in node.iter():
                if e.attrib.get("TargetMode") == "External" or any(
                    x in str(e.attrib).lower() for x in ("macroenabled", "vbaproject", "oleobject")
                ):
                    reject()
        root = ET.fromstring(z.read("word/document.xml"), forbid_dtd=True)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        if any(
            root.findall(".//w:" + tag, ns)
            for tag in ("instrText", "fldSimple", "object", "altChunk")
        ):
            reject()
        tables = root.findall(".//w:tbl", ns)
        if len(tables) != 1:
            reject()
        return table(
            [
                [
                    "".join(t.text or "" for t in cell.findall(".//w:t", ns))
                    for cell in row.findall("w:tc", ns)
                ]
                for row in tables[0].findall("w:tr", ns)
            ]
        )


def pdf_rows(data):
    from pypdf import PdfReader
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

    if not data.startswith(b"%PDF-") or not data.rstrip().endswith(b"%%EOF"):
        reject()
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted or len(reader.pages) > 100:
        reject()
    banned = {
        "/JavaScript",
        "/JS",
        "/OpenAction",
        "/AA",
        "/Launch",
        "/EmbeddedFiles",
        "/RichMedia",
        "/XFA",
        "/AcroForm",
        "/Filespec",
        "/URI",
        "/GoToR",
    }
    visited = set()

    def check(obj, depth=0):
        if depth > 60 or len(visited) > 50000:
            reject()
        if isinstance(obj, IndirectObject):
            key = (obj.idnum, obj.generation)
            if key in visited:
                return
            visited.add(key)
            obj = obj.get_object()
        if isinstance(obj, DictionaryObject):
            if banned.intersection(obj.keys()):
                reject()
            for v in obj.values():
                check(v, depth + 1)
        elif isinstance(obj, ArrayObject):
            for v in obj:
                check(v, depth + 1)

    check(reader.trailer)
    lines = []
    total = 0
    for page in reader.pages:
        s = page.extract_text(extraction_mode="layout")
        total += len(s)
        if total > MAX_TEXT:
            reject()
        lines.extend(line.strip() for line in s.splitlines() if line.strip())
    # Conservative tabular PDFs only: explicit column header, full date, no guessed sign.
    rows = []
    header = None
    for line in lines:
        cells = re.split(r"\s{2,}|\t", line)
        normalized = [ALIASES.get(norm(c)) for c in cells]
        if "date" in normalized and ("amount" in normalized or "credit" in normalized):
            if header is not None and cells != header:
                reject()
            header = cells
            if not rows:
                rows.append(cells)
        elif re.match(r"\d{2}[/.\-]\d{2}[/.\-]\d{4}|\d{4}-\d{2}-\d{2}", line):
            if header is None:
                reject()
            rows.append(cells)
        elif header is not None and not re.match(
            r"(?i)^(saldo|total|pagina|página|extrato)\b", line
        ):
            reject()
    return table(rows)


def parse(data, fmt):
    if not data or len(data) > MAX_BYTES:
        reject()
    parsers = {
        "csv": csv_rows,
        "xml": xml_rows,
        "ofx": ofx_rows,
        "docx": docx_rows,
        "pdf": pdf_rows,
    }
    if fmt not in parsers:
        reject()
    rows = parsers[fmt](data)
    if not 1 <= len(rows) <= MAX_ROWS:
        reject()
    return rows
