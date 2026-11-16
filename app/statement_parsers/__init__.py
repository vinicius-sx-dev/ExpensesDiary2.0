"""Institution strategies; format readers keep their security checks in statement_parser.

Profiles describe accepted columns, not a promise to support every export of a bank.
Only PicPay CSV/PDF has been checked against a supplied layout; see docs/STATEMENT_IMPORTS.md.
"""

import csv
import io
import re
from dataclasses import dataclass, field

if __package__ == "app.statement_parsers":
    from .. import statement_parser as core
else:  # Standalone restricted worker; never import application settings/secrets.
    import statement_parser as core


class BankStatementError(core.InvalidStatement):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def fail(code="unsupported_layout"):
    raise BankStatementError(code)


def safe_merchant(value):
    """Keep explicit purchase merchants only, without documents, links or control text."""
    value = re.sub(
        r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", "", value
    )
    value = " ".join(value.split()).strip(" -/")
    if not value:
        return ""
    if len(value) > 120 or re.search(
        r"[<>\x00-\x1f\x7f]|https?://|[\u202a-\u202e\u2066-\u2069]", value, re.I
    ):
        fail()
    return value


def check_issuer(text, institution):
    """Use issuer metadata, never bank names in merchant/transfer descriptions."""
    found = set()
    for line in text.splitlines():
        n = core.norm(line)
        for key, profile in REGISTRY.items():
            # Exact issuer line, a labeled bank, or the known PicPay legal footer.
            if any(
                n == name
                or re.match(r"^(?:banco|instituicao)\s*[:;=]\s*" + re.escape(name) + r"$", n)
                for name in profile.names
            ):
                found.add(key)
        if "picpay servicos s/a" in n:
            found.add("PICPAY")
    # OFX bank identifier is metadata; no guessing from MEMO/NAME.
    ids = re.findall(r"<BANKID>\s*(\d{1,8})\s*(?:<|$)", text, re.I)
    for identifier in ids:
        for key, profile in REGISTRY.items():
            if identifier.lstrip("0") in {i.lstrip("0") for i in profile.bank_ids}:
                found.add(key)
    if found and found != {institution}:
        fail("institution_mismatch")


@dataclass(frozen=True)
class BankStrategy:
    names: tuple[str, ...]
    bank_ids: tuple[str, ...]
    columns: dict[str, str] = field(default_factory=dict)

    @property
    def aliases(self):
        return {**core.ALIASES, **self.columns}

    def table(self, rows):
        # Find the header after a bounded issuer/account preamble.
        start = next(
            (
                i
                for i, row in enumerate(rows[:30])
                if "date" in [self.aliases.get(core.norm(c)) for c in row]
                and any(self.aliases.get(core.norm(c)) in {"amount", "credit"} for c in row)
            ),
            None,
        )
        if start is None:
            fail()
        rows = rows[start:]
        header = rows[0]
        clean = [header]
        for row in rows[1:]:
            if not any(c.strip() for c in row) or row == header:
                continue
            # Only explicit standalone summaries; never discard a dated transaction.
            if re.fullmatch(
                r"(?:saldo anterior|saldo final|total de entradas|total de saidas)",
                core.norm(row[0]),
            ):
                continue
            clean.append(row)
        mapped = [self.aliases.get(core.norm(c)) for c in header]
        if "merchant" not in mapped and "description" in mapped:
            index = mapped.index("description")
            enriched = [header + ["merchant"]]
            for row in clean[1:]:
                if len(row) != len(header):
                    fail()
                # Do not turn Pix recipient names into establishments.
                purchase = re.match(
                    r"(?i)^compra (?:cart[aã]o|no d[eé]bito|no cr[eé]dito)\s*[-:]\s*(.+)$",
                    row[index],
                )
                enriched.append(row + [safe_merchant(purchase[1]) if purchase else ""])
            clean = enriched
        return core.table(clean, self.aliases)

    def csv(self, data):
        s = core.text(data)
        # Sniff header + data instead of unrelated preamble lines.
        for delimiter in (";", ",", "\t"):
            try:
                rows = list(csv.reader(io.StringIO(s), delimiter=delimiter, strict=True))
                if any("date" in [self.aliases.get(core.norm(c)) for c in r] for r in rows[:30]):
                    return self.table(rows)
            except csv.Error:
                continue
        fail()

    def pdf(self, lines):
        rows = []
        started = False
        for line in lines:
            cells = re.split(r"\s{2,}|\t", line)
            mapped = [self.aliases.get(core.norm(c)) for c in cells]
            if "date" in mapped and any(k in mapped for k in ("amount", "credit")):
                started = True
                rows.append(cells)
            elif re.match(r"\d{2}[/.\-]\d{2}[/.\-]\d{4}|\d{4}-\d{2}-\d{2}", line):
                if not started:
                    fail()
                rows.append(cells)
            elif started and not re.match(r"(?i)^(saldo|total|pagina|página|extrato)\b", line):
                fail()
        return self.table(rows)


class PicPayStrategy(BankStrategy):
    HEADER = ["data", "hora", "tipo", "origem / destino", "valor", "forma de pagamento"]
    DEBIT = {
        "compra realizada",
        "pix enviado",
        "pix automatico enviado",
        "dinheiro guardado",
        "pagamento realizado",
        "boleto pago",
    }
    CREDIT = {
        "pix recebido",
        "dinheiro resgatado",
        "pix devolvido",
        "compra estornada",
        "rendimento",
    }
    MONTHS = {
        m: i + 1
        for i, m in enumerate(
            (
                "janeiro",
                "fevereiro",
                "marco",
                "abril",
                "maio",
                "junho",
                "julho",
                "agosto",
                "setembro",
                "outubro",
                "novembro",
                "dezembro",
            )
        )
    }

    def row(self, d, clock, kind, merchant, raw):
        kind = core.norm(kind)
        if kind not in self.DEBIT | self.CREDIT:
            fail()
        # A signed amount is mandatory: descriptive type cannot silently flip it.
        if not re.match(r"^[+\-−]\s*R\$", raw.strip()):
            fail()
        row = core.movement(d, raw)
        if kind != "pix devolvido" and (row["kind"] == "expense") != (kind in self.DEBIT):
            fail()
        values = {"time": clock}
        if kind in {"compra realizada", "compra estornada"}:
            values["merchant"] = safe_merchant(merchant)
        row["context"] = core.extract_context(values, row["on_date"])
        if kind in {"dinheiro guardado", "dinheiro resgatado"}:
            row["review_reason"] = "internal_transfer"
        return row

    def csv(self, data):
        try:
            rows = list(csv.reader(io.StringIO(core.text(data)), strict=True))
        except csv.Error:
            fail()
        if not rows or [core.norm(c) for c in rows[0]] != self.HEADER:
            return super().csv(data)
        result = []
        for row in rows[1:]:
            if not row:
                continue
            if len(row) != 6 or any(len(c) > 1000 for c in row):
                fail()
            d, clock, kind, merchant, raw, _payment = row
            result.append(self.row(d, clock, kind, merchant, raw))
        return result

    def pdf(self, lines):
        if not any("origem / destino" in core.norm(line) for line in lines):
            return super().pdf(lines)
        result, current_date, header, continuation, footer = [], None, False, False, False
        prefix = ""
        for line in lines:
            n = core.norm(line)
            match = re.match(r"^(\d{1,2}) de ([a-z]+) (?:de )?(\d{4})\s+saldo ao final do dia:", n)
            if match:
                month = self.MONTHS.get(match[2])
                if not month:
                    fail()
                current_date = f"{match[3]}-{month:02d}-{int(match[1]):02d}"
                header, continuation, footer = False, False, False
                continue
            if n.startswith("hora") and "origem / destino" in n and "valor" in n:
                header, continuation, footer = True, False, False
                continue
            if n.startswith("documento emitido em:"):
                footer, continuation = True, False
                continue
            if re.match(r"^\d{2}:\d{2}\s", line):
                if not current_date or not header or footer:
                    fail()
                cols = re.split(r"\s{2,}", line)
                if len(cols) not in (4, 5):
                    fail()
                clock, kind, merchant = cols[:3]
                result.append(
                    self.row(current_date, clock, kind, (prefix + " " + merchant).strip(), cols[-1])
                )
                prefix = ""
                continuation = True
                continue
            if header and not footer:
                # Wrapped merchant cell. Never treat an unrecognized monetary row as text.
                if "R$" in line or len(re.split(r"\s{2,}", line)) != 1:
                    fail()
                if not continuation:
                    prefix = safe_merchant((prefix + " " + line).strip())
                    continue
                context = result[-1]["context"]
                if "merchant" in context:
                    context["merchant"] = safe_merchant(context["merchant"] + " " + line)
        if prefix:
            fail()
        return result


REGISTRY = {
    "PICPAY": PicPayStrategy(("picpay",), ("380",)),
    "NUBANK": BankStrategy(("nubank", "nu pagamentos"), ("260",)),
    "BANCO_DO_BRASIL": BankStrategy(
        ("banco do brasil", "bb"),
        ("001",),
        {"data movimento": "date", "lote": "ignored", "valor r$": "amount"},
    ),
    "ITAU": BankStrategy(
        ("itau", "itau unibanco"),
        ("341",),
        {"valor (r$)": "amount", "saldo (r$)": "balance", "ag./origem": "ignored"},
    ),
    "BRADESCO": BankStrategy(
        ("bradesco", "banco bradesco"),
        ("237",),
        {
            "credito (r$)": "credit",
            "debito (r$)": "debit",
            "saldo (r$)": "balance",
            "docto.": "ignored",
        },
    ),
    "SANTANDER": BankStrategy(
        ("santander", "banco santander"),
        ("033",),
        {
            "data de movimentacao": "date",
            "descricao do lancamento": "description",
            "valor (r$)": "amount",
        },
    ),
    "CAIXA": BankStrategy(
        ("caixa", "caixa economica federal"),
        ("104",),
        {"data mov.": "date", "nr. doc.": "ignored", "valor (r$)": "amount"},
    ),
    "BTG": BankStrategy(
        ("btg", "btg pactual", "banco btg pactual"),
        ("208",),
        {
            "data de liquidacao": "date",
            "descricao do movimento": "description",
            "valor (r$)": "amount",
        },
    ),
    "SICREDI": BankStrategy(
        ("sicredi", "banco sicredi"),
        ("748",),
        {"data lanc.": "date", "num. documento": "ignored", "valor (r$)": "amount"},
    ),
    "MERCADO_PAGO": BankStrategy(
        ("mercado pago",),
        ("323",),
        {
            "date": "date",
            "transaction_type": "description",
            "transaction_net_amount": "amount",
            "reference_id": "ignored",
            "transaction_amount": "amount",
            "balance": "balance",
        },
    ),
}


def parse_bank(data, fmt, institution):
    strategy = REGISTRY.get(institution)
    if strategy is None:
        fail("invalid_institution")
    if fmt == "pdf":
        lines = core.pdf_lines(data)
        metadata = []
        for line in lines:
            if "picpay servicos s/a" in core.norm(line):
                metadata.append("PicPay")
            if "origem / destino" in core.norm(line) and institution != "PICPAY":
                fail("institution_mismatch")
        for line in lines:
            if re.match(r"(?i)^(data|date|hora)\b", line):
                break
            metadata.append(line)
        check_issuer("\n".join(metadata), institution)
        return strategy.pdf(lines)
    if fmt == "docx":
        rows, metadata = core.docx_table(data, with_metadata=True)
        check_issuer(
            metadata + "\n" + "\n".join(row[0] for row in rows if len(row) == 1), institution
        )
        return strategy.table(rows)
    s = core.text(data)
    if fmt == "csv":
        # Inspect only preamble, not transaction cells.
        preamble = []
        for line in s.splitlines()[:30]:
            if any(word in core.norm(line) for word in ("data", "date")) and any(
                sep in line for sep in (",", ";", "\t")
            ):
                break
            preamble.append(line)
        check_issuer("\n".join(preamble), institution)
        first = next(csv.reader(io.StringIO(s)), [])
        if [core.norm(c) for c in first] == PicPayStrategy.HEADER and institution != "PICPAY":
            fail("institution_mismatch")
        return strategy.csv(data)
    check_issuer(s, institution)
    return {"ofx": core.ofx_rows, "xml": core.xml_rows}[fmt](data)
