"""Private suggestions learned only from explicit user classifications."""
import re
import unicodedata

from sqlalchemy import select

from app.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES
from app.models import Entry


def merchant_key(value):
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())


def learned_categories(db, uid):
    result = {}
    rows = db.scalars(
        select(Entry).where(Entry.user_id == uid)
        .order_by(Entry.id.desc()).limit(5000)
    )
    for entry in rows:
        context = entry.context
        if not (context.get("classification_reviewed") or context.get("source") == "manual"):
            continue
        key = (entry.kind, merchant_key(context.get("merchant")))
        if not key[1]:
            continue
        if key not in result:
            result[key] = entry.category
        elif result[key] != entry.category:
            # Conflicting explicit labels are not evidence for an arbitrary latest-ID winner.
            result[key] = "outros" if entry.kind == "expense" else "outras_receitas"
    return result


def suggest(row, learned):
    kind = row["kind"]
    fallback = "outros" if kind == "expense" else "outras_receitas"
    merchant = merchant_key((row.get("context") or {}).get("merchant"))
    category = learned.get((kind, merchant))
    allowed = EXPENSE_CATEGORIES if kind == "expense" else INCOME_CATEGORIES
    if category in allowed:
        return {"category": category, "classification_source": "history"}
    if kind == "expense" and merchant:
        hints = {
            "mercado": r"\b(supermercado|supermercados|mercearia)\b",
            "padaria": r"\b(padaria|panificadora)\b",
            "restaurante": r"\b(restaurante|pizzaria|lanchonete)\b",
            "medicamentos": r"\b(farmacia|farmácia|drogaria)\b",
        }
        matches = [c for c, pattern in hints.items() if re.search(pattern, merchant)]
        if len(matches) == 1:
            return {"category": matches[0], "classification_source": "hint"}
    return {"category": fallback, "classification_source": "unclassified"}
