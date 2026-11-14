"""Mock-only Pluggy boundary. No client-supplied financial payloads or provider URLs."""
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID, uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.balance import lock_wallet
from app.ingestion import make_entry
from app.config import settings
from app.db import get_db
from app.models import Entry, Contribution, Goal, PluggyReceipt
from app.reports import build_report, week
from app.schemas import today
from app.security import current_user, limit
from app.statement_imports import cipher


class Transaction(BaseModel):
    # Deliberately supported subset of the official schema; expand the adapter explicitly.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    id: UUID
    accountId: UUID
    date: datetime
    description: str = Field(max_length=240)
    amount: Decimal = Field(max_digits=14, decimal_places=2, allow_inf_nan=False)
    currencyCode: Literal["BRL"]
    type: Literal["CREDIT", "DEBIT"]
    status: Literal["POSTED", "PENDING"]
    merchant: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def valid_date(self):
        if self.date.tzinfo is None or self.amount == 0:
            raise ValueError("Invalid transaction")
        return self


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    id: UUID
    type: Literal["BANK"]
    subtype: Literal["CHECKING_ACCOUNT"]
    currencyCode: Literal["BRL"]
    name: str = Field(max_length=100)


class Provider(Protocol):
    def accounts(self) -> list[Account]: ...
    def transactions(self) -> list[Transaction]: ...


class MockProvider:
    def accounts(self):
        return [Account(id=uuid5(NAMESPACE_URL, "expenses-diary:mock:account"),
                        type="BANK", subtype="CHECKING_ACCOUNT", currencyCode="BRL",
                        name="Conta simulada")]

    def transactions(self):
        day = today()
        account = uuid5(NAMESPACE_URL, "expenses-diary:mock:account")
        samples = [("salary", "Salary", "CREDIT", "5000"),
                   ("groceries", "Groceries", "DEBIT", "350"),
                   ("restaurant", "Restaurants", "DEBIT", "120"),
                   ("investment", "Investments", "DEBIT", "500")]
        return [Transaction.model_validate({
            "id": str(uuid5(account, f"{day:%Y-%m}:{key}")), "accountId": str(account),
            "date": f"{day:%Y-%m}-01T15:00:00Z", "description": "Simulação",
            "amount": value if direction == "CREDIT" else "-" + value,
            "currencyCode": "BRL", "type": direction, "status": "POSTED", "category": category,
        }) for key, category, direction, value in samples]


class SyncInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    investment_goal_id: int | None = Field(default=None, gt=0)


class SyncResult(BaseModel):
    mode: Literal["mock"] = "mock"
    imported: int
    already_imported: int
    awaiting_goal: int


router = APIRouter(prefix="/pluggy", tags=["Pluggy (simulação)"])


def enabled():
    if not settings.pluggy_mock_enabled or settings.environment == "production":
        raise HTTPException(503, "Simulação Pluggy indisponível neste ambiente")


def request_id(uid, transaction):
    return str(uuid5(NAMESPACE_URL, f"pluggy:mock:{uid}:{transaction.id}"))


@router.post("/mock/sync", response_model=SyncResult, dependencies=[Depends(enabled)])
def sync(payload: SyncInput, user=Depends(current_user), db=Depends(get_db)):
    limit("pluggy-sync", str(user.id), 6, 3600)
    limit("pluggy-global", "all", 60, 3600)
    # Require the same key used by statement previews, even in mock mode.
    cipher()
    lock_wallet(db, user.id)
    if payload.investment_goal_id is not None and not db.scalar(select(Goal.id).where(
        Goal.id == payload.investment_goal_id, Goal.user_id == user.id
    ).with_for_update()):
        raise HTTPException(404, "Objetivo não encontrado")
    result = SyncResult(imported=0, already_imported=0, awaiting_goal=0)
    provider: Provider = MockProvider()
    accounts = {account.id for account in provider.accounts()}
    for transaction in provider.transactions():
        if transaction.accountId not in accounts:
            raise HTTPException(502, "Conta inesperada no provedor")
        # Provider data lives only in process memory; no raw payload or description is stored.
        tx = transaction
        if tx.status != "POSTED" or tx.date.date() > today():
            continue
        rid = request_id(user.id, tx)
        if db.get(PluggyReceipt, (user.id, rid)) or db.scalar(select(Entry.id).where(Entry.user_id == user.id, Entry.request_id == rid)) or db.scalar(
            select(Contribution.id).where(Contribution.user_id == user.id, Contribution.request_id == rid)
        ):
            result.already_imported += 1
            continue
        cents = int(abs(tx.amount) * 100)
        day = tx.date.astimezone(ZoneInfo("America/Sao_Paulo")).date()
        if tx.category == "Investments":
            if tx.type != "DEBIT" or payload.investment_goal_id is None:
                result.awaiting_goal += 1
                continue
            # An observed bank movement is factual; do not invent an income to fund it.
            db.add(Contribution(user_id=user.id, request_id=rid, goal_id=payload.investment_goal_id,
                                amount_cents=cents, on_date=day))
        else:
            kind = "income" if tx.type == "CREDIT" else "expense"
            mapping = {"Salary": "salario", "Groceries": "mercado", "Restaurants": "restaurante"}
            category = mapping.get(tx.category, "outras_receitas" if kind == "income" else "outros")
            db.add(make_entry(user_id=user.id, source="pluggy_mock", request_id=rid, kind=kind, category=category,
                         amount_cents=cents, on_date=day, description="", essential=False,
                         payment_method="other", context={"occurred_at": tx.date, "merchant": tx.merchant, "niche": "fast_food" if tx.category == "Restaurants" else None}))
        db.add(PluggyReceipt(user_id=user.id, request_id=rid))
        result.imported += 1
    db.commit()
    return result


@router.get("/insights")
def rule_insights(user=Depends(current_user), db=Depends(get_db)):
    limit("pluggy-insights", str(user.id), 30, 60)
    data = build_report(db, user.id, week(None))
    messages = []
    goals = [g for g in data["goals"] if g["status"] != "completed"]
    for budget in data["budgets"]:
        if budget["status"] == "exceeded":
            suffix = f" Isso pode atrasar seu objetivo {goals[0]['title']}." if goals else ""
            messages.append(f"Você ultrapassou o limite de {budget['category']}." + suffix)
        elif budget["status"] == "attention":
            messages.append(f"Você já utilizou pelo menos 80% do limite de {budget['category']}.")
    if goals and data["reserved_cents"] >= data["required_weekly_cents"] > 0:
        messages.append("Seus aportes nesta semana atingiram o ritmo estimado para as metas. Continue assim.")
    return {"engine": "rules-v1", "suggestions": messages[:10]}


@router.get("/mock/accounts", response_model=list[Account], dependencies=[Depends(enabled)])
def accounts(user=Depends(current_user)):
    limit("pluggy-accounts", str(user.id), 30, 60)
    return MockProvider().accounts()
