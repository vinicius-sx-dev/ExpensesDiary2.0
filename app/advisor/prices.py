"""Regional price evidence boundary. No LLM estimates or scraped search snippets.

An operator-configured licensed feed must attest locality and offer conditions.
No provider is enabled by default: missing evidence means unavailable, not zero.
"""

from datetime import datetime, timezone
from decimal import ROUND_CEILING, Decimal
from typing import Literal, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings


class Quote(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    ingredient: Literal["bread", "cheese", "tomato", "oats", "milk", "banana"]
    product: str = Field(min_length=2, max_length=160)
    store_id: str = Field(min_length=1, max_length=80)
    municipality: str = Field(pattern=r"^41\d{5}$")
    unit: Literal["kg", "l", "unit"]
    package_quantity: Decimal = Field(gt=0, le=100, max_digits=8, decimal_places=4)
    package_price_cents: int = Field(strict=True, gt=0, le=1_000_000)
    source_url: str = Field(max_length=500)
    observed_at: datetime
    valid_until: datetime
    conditions: Literal["regular_in_store"]
    available: bool

    @field_validator("source_url")
    @classmethod
    def url(cls, value):
        u = urlsplit(value)
        if u.scheme != "https" or not u.hostname or u.username or u.password:
            raise ValueError("HTTPS source required")
        return value

    @field_validator("observed_at", "valid_until")
    @classmethod
    def aware(cls, v):
        if not v.tzinfo:
            raise ValueError("Timezone required")
        return v


class PriceProvider(Protocol):
    def quotes(self, municipality: str) -> list[Quote]: ...


class RegionalFeed:
    def quotes(self, municipality):
        if not settings.advisor_price_feed_url:
            return []
        # URL is server configuration, never supplied by clients or by the LLM.
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
                with client.stream(
                    "GET",
                    settings.advisor_price_feed_url,
                    params={"municipality": municipality},
                    headers={"Authorization": "Bearer " + settings.advisor_price_feed_token},
                ) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    for part in response.iter_bytes():
                        raw.extend(part)
                        if len(raw) > 256_000:
                            return []
            import json

            data = json.loads(raw)
            if not isinstance(data, list) or len(data) > 200:
                return []
            return [Quote.model_validate(q) for q in data]
        except (httpx.HTTPError, ValueError, TypeError):
            return []


RECIPES = {
    "sandwich": {
        "name": "Sanduíche frio de queijo e tomate",
        "portions": 2,
        "ingredients": [
            ("bread", "Pão", "kg", "0.12"),
            ("cheese", "Queijo", "kg", "0.08"),
            ("tomato", "Tomate", "kg", "0.10"),
        ],
        "steps": "Lave o tomate, corte e monte dois sanduíches com o pão e o queijo. Mantenha refrigerado até consumir.",
        "allergens": "Contém leite e pode conter trigo/glúten. Confira os rótulos e suas restrições.",
    },
    "oats": {
        "name": "Aveia com leite e banana",
        "portions": 2,
        "ingredients": [
            ("oats", "Aveia", "kg", "0.08"),
            ("milk", "Leite", "l", "0.30"),
            ("banana", "Banana", "kg", "0.20"),
        ],
        "steps": "Misture aveia e leite, deixe hidratar sob refrigeração e acrescente a banana descascada e cortada. Divida em duas porções.",
        "allergens": "Contém leite; aveia pode conter glúten. Confira os rótulos e suas restrições.",
    },
}


def ceil_cents(n):
    return int(n.to_integral_value(rounding=ROUND_CEILING))


def price_recipe(recipe_id, quotes, municipality, now=None):
    now = now or datetime.now(timezone.utc)
    recipe = RECIPES[recipe_id]
    items = []
    for ingredient, label, unit, quantity in recipe["ingredients"]:
        # One observation per store prevents a large catalog dominating the mean.
        by_store = {}
        for q in quotes:
            age = (now - q.observed_at).total_seconds()
            if (
                q.ingredient != ingredient
                or q.unit != unit
                or q.municipality != municipality
                or not q.available
                or not 0 <= age <= 86400
                or q.valid_until <= now
            ):
                continue
            old = by_store.get(q.store_id)
            if old is None or q.observed_at > old.observed_at:
                by_store[q.store_id] = q
        valid = list(by_store.values())
        if len(valid) < 2:
            return {
                "status": "unavailable",
                "message": "Preços locais indisponíveis: são necessárias duas fontes de lojas distintas por ingrediente, válidas nas últimas 24 horas.",
                "recipe_id": recipe_id,
                "name": recipe["name"],
            }
        amount = Decimal(quantity)
        mean_unit = sum(Decimal(q.package_price_cents) / q.package_quantity for q in valid) / len(
            valid
        )
        # Average full packages required for this recipe, not fractional checkout cost.
        checkout = sum(
            Decimal(ceil_cents(amount / q.package_quantity) * q.package_price_cents) for q in valid
        ) / len(valid)
        items.append(
            {
                "ingredient": ingredient,
                "name": label,
                "unit": unit,
                "quantity": quantity,
                "unit_price_cents": ceil_cents(mean_unit),
                "consumed_cents": ceil_cents(mean_unit * amount),
                "packages_cents": ceil_cents(checkout),
                "stores": len(valid),
                "sources": [q.model_dump(mode="json") for q in valid],
            }
        )
    consumed = sum(i["consumed_cents"] for i in items)
    return {
        "status": "verified",
        "recipe_id": recipe_id,
        "name": recipe["name"],
        "portions": recipe["portions"],
        "ingredients": items,
        "consumed_cents": consumed,
        "portion_cents": ceil_cents(Decimal(consumed) / recipe["portions"]),
        "packages_cents": sum(i["packages_cents"] for i in items),
        "steps": recipe["steps"],
        "allergens": recipe["allergens"],
        "note": "Média da amostra municipal; não é uma oferta garantida. Desembolso médio das embalagens não representa uma cesta disponível em uma única loja. Sobras precisam ser aproveitadas; deslocamento não incluído.",
    }
