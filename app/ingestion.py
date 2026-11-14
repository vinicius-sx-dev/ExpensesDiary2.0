"""Shared context normalization for manual, statement and provider ingestion."""

import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

NICHES = {
    "fast_food": "restaurante",
    "subscriptions": "servicos_digitais",
    "impulse": "outros",
    "beauty": "beleza",
    "tattoo": "hobbies",
    "travel": "viagem",
    "investments": "outros",
}


class MovementContext(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    niche: (
        Literal[
            "fast_food", "subscriptions", "impulse", "beauty", "tattoo", "travel", "investments"
        ]
        | None
    ) = None
    merchant: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=200)
    occurred_at: datetime | None = None
    local_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    unplanned: bool = False

    @field_validator("merchant", "address")
    @classmethod
    def safe_text(cls, v):
        if v is None:
            return v
        v = v.strip()
        if re.search(
            r"[<>\x00-\x1f]|https?://|\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b",
            v,
            re.I,
        ):
            raise ValueError("Use somente estabelecimento/endereço sem documentos ou links")
        return v or None

    @field_validator("occurred_at")
    @classmethod
    def timestamp(cls, v):
        if v and (v.tzinfo is None or v > datetime.now(v.tzinfo)):
            raise ValueError("Horário deve ter fuso e não pode estar no futuro")
        return v


def normalized_context(context, on_date, source):
    value = MovementContext.model_validate(context or {})
    if value.local_time:
        if value.occurred_at:
            raise ValueError("Informe horário local ou timestamp, não ambos")
        timestamp = datetime.fromisoformat(str(on_date) + "T" + value.local_time).replace(
            tzinfo=ZoneInfo("America/Sao_Paulo")
        )
        value = MovementContext.model_validate(
            {**value.model_dump(), "local_time": None, "occurred_at": timestamp}
        )
    if value.niche == "investments":
        raise ValueError("Registre aportes na meta, sem duplicar despesas")
    if (
        value.occurred_at
        and value.occurred_at.astimezone(ZoneInfo("America/Sao_Paulo")).date() != on_date
    ):
        raise ValueError("Data e horário incompatíveis")
    data = value.model_dump(mode="json", exclude_none=True)
    data.update(source=source, weekday=on_date.weekday(), timezone="America/Sao_Paulo")
    return data


def apply_context(row, context, source):
    row.context = normalized_context(context, row.on_date, source)
    return row


def make_entry(*, user_id, source, context=None, **fields):
    """All ingestion sources use this boundary before persisting a ledger movement."""
    from app.models import Entry

    row = Entry(user_id=user_id, **fields)
    return apply_context(row, context, source)
