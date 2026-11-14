import json
import time
from datetime import timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select

from app.advisor.engine import WINDOW_DAYS, goal_state, patterns, scenario
from app.advisor.humanize import humanize
from app.advisor.prices import RECIPES, RegionalFeed, price_recipe
from app.balance import lock_wallet
from app.config import settings
from app.crypto import seal
from app.db import get_db
from app.models import Advice, AdvisorSettings, Contribution, Entry, Goal, Notification, PushDevice
from app.schemas import today
from app.security import current_user, digest, limit

MUNICIPALITIES = json.loads(Path(__file__).with_name("municipalities.json").read_text())

router = APIRouter(prefix="/advisor", tags=["Orientações"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class Preferences(Strict):
    municipality: str | None = Field(default=None, pattern=r"^41\d{5}$")
    notifications_enabled: bool = False
    selected_goal_id: int | None = Field(default=None, gt=0)
    timezone: Literal["America/Sao_Paulo"] = "America/Sao_Paulo"
    max_per_week: int = Field(default=2, ge=1, le=2)
    quiet_start: int = Field(default=20, ge=18, le=23)
    quiet_end: int = Field(default=9, ge=6, le=12)

    @field_validator("municipality")
    @classmethod
    def in_parana(cls, value):
        if value is not None and value not in MUNICIPALITIES:
            raise ValueError("Município do Paraná inválido")
        return value


class Simulation(Strict):
    goal_id: int = Field(gt=0)
    strategy: Literal["fast_food", "subscriptions", "impulse", "beauty", "tattoo", "travel"]
    recipe_id: Literal["sandwich", "oats"] = "sandwich"
    occurrences_per_month: int = Field(default=1, ge=1, le=30)
    replacement_cents: int | None = Field(default=None, ge=0, le=10_000_000_000)
    humanize: bool = False


def preferences(db, uid):
    row = db.get(AdvisorSettings, uid)
    return Preferences.model_validate(row.data) if row else Preferences()


def owned_goal(db, uid, goal_id):
    goal = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == uid))
    if goal is None:
        raise HTTPException(404, "Objetivo não encontrado")
    return goal


def inputs(db, uid):
    entries = list(
        db.scalars(
            select(Entry)
            .where(Entry.user_id == uid, Entry.on_date >= today() - timedelta(days=WINDOW_DAYS - 1))
            .order_by(Entry.id)
            .limit(10001)
        )
    )
    contributions = list(
        db.scalars(
            select(Contribution)
            .where(Contribution.user_id == uid)
            .order_by(Contribution.id)
            .limit(10001)
        )
    )
    if len(entries) > 10000 or len(contributions) > 10000:
        raise HTTPException(
            422, "Histórico excede o limite desta análise; nenhuma projeção parcial foi calculada."
        )
    return entries, contributions


@router.get("/regions")
def regions(user=Depends(current_user)):
    return MUNICIPALITIES


@router.get("/preferences", response_model=Preferences)
def read_preferences(user=Depends(current_user), db=Depends(get_db)):
    return preferences(db, user.id)


@router.put("/preferences", response_model=Preferences)
def update_preferences(payload: Preferences, user=Depends(current_user), db=Depends(get_db)):
    lock_wallet(db, user.id)
    if payload.selected_goal_id:
        owned_goal(db, user.id, payload.selected_goal_id)
    row = db.get(AdvisorSettings, user.id)
    if row is None:
        row = AdvisorSettings(user_id=user.id)
        db.add(row)
    row.data = payload.model_dump()
    db.execute(
        delete(Notification).where(
            Notification.user_id == user.id, Notification.status == "pending"
        )
    )
    db.commit()
    return payload


@router.get("/patterns")
def detect(goal_id: int = Query(gt=0), user=Depends(current_user), db=Depends(get_db)):
    limit("advisor-read", str(user.id), 12, 60)
    goal = owned_goal(db, user.id, goal_id)
    entries, contributions = inputs(db, user.id)
    return {
        "goal": goal_state(goal, contributions, today()),
        "patterns": patterns(entries, today()),
        "recipes": [{"id": key, "name": r["name"]} for key, r in RECIPES.items()],
        "note": "Padrões observados não provam a causa do déficit. Classificações pessoais podem ser corrigidas nos lançamentos.",
    }


def calculate(db, uid, payload):
    goal = owned_goal(db, uid, payload.goal_id)
    entries, contributions = inputs(db, uid)
    found = next((p for p in patterns(entries, today()) if p["strategy"] == payload.strategy), None)
    if not found:
        raise HTTPException(422, "Histórico insuficiente para este padrão.")
    pref = preferences(db, uid)
    quotes = (
        RegionalFeed().quotes(pref.municipality)
        if payload.strategy == "fast_food" and pref.municipality
        else []
    )
    recipe = (
        price_recipe(payload.recipe_id, quotes, pref.municipality)
        if payload.strategy == "fast_food"
        else {}
    )
    state = goal_state(goal, contributions, today())
    if state["remaining_cents"] == 0:
        raise HTTPException(422, "Objetivo já concluído.")
    return {
        "goal": state,
        "pattern": found,
        "result": scenario(
            goal,
            state,
            found,
            recipe,
            today(),
            payload.occurrences_per_month,
            payload.replacement_cents,
        ),
    }


@router.post("/simulate")
def simulate(payload: Simulation, user=Depends(current_user), db=Depends(get_db)):
    limit("advisor-simulate", str(user.id), 6, 3600)
    limit("advisor-simulate-global", "all", 100, 3600)
    value = calculate(db, user.id, payload)
    if payload.humanize and value["result"]["status"] == "ready":
        limit("ai", str(user.id), 5, 3600)
        limit("ai-global", "all", settings.ai_global_hourly_limit, 3600)
        value["message"] = humanize(value["pattern"], value["result"])
    row = Advice(id=str(uuid4()), user_id=user.id, created_at=int(time.time()))
    row.data = {**value, "input": payload.model_dump()}
    db.add(row)
    db.commit()
    return {"id": row.id, **value}


@router.get("/history")
def history(offset: int = Query(default=0, ge=0), user=Depends(current_user), db=Depends(get_db)):
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            **{k: v for k, v in r.data.items() if k != "input"},
        }
        for r in db.scalars(
            select(Advice)
            .where(Advice.user_id == user.id)
            .order_by(Advice.created_at.desc(), Advice.id)
            .offset(offset)
            .limit(20)
        )
    ]


@router.delete("/history/{advice_id}", status_code=204)
def remove(advice_id: UUID, user=Depends(current_user), db=Depends(get_db)):
    db.execute(delete(Advice).where(Advice.user_id == user.id, Advice.id == str(advice_id)))
    db.commit()


class Device(Strict):
    token: str = Field(pattern=r"^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]{10,200}\]$")


@router.post("/devices", status_code=204)
def register_device(
    payload: Device, request: Request, user=Depends(current_user), db=Depends(get_db)
):
    limit("push-register", str(user.id), 10, 3600)
    lock_wallet(db, user.id)
    if not preferences(db, user.id).notifications_enabled:
        raise HTTPException(409, "Ative os lembretes antes de registrar o aparelho.")
    key = digest("push:" + payload.token)
    row = db.get(PushDevice, key)
    if row is not None and row.user_id != user.id:
        # Do not silently reassign a token guessed by another account.
        raise HTTPException(409, "Aparelho já registrado. Desative os lembretes na conta anterior.")
    if row is None:
        if (
            len(
                list(db.scalars(select(PushDevice.token_hash).where(PushDevice.user_id == user.id)))
            )
            >= 5
        ):
            raise HTTPException(409, "Limite de aparelhos atingido")
        row = PushDevice(token_hash=key, user_id=user.id)
        db.add(row)
    row.session_id = request.state.session_id
    row.protected_token = seal(payload.token, user.id, "push", key)
    db.commit()


@router.delete("/devices", status_code=204)
def unregister_device(request: Request, user=Depends(current_user), db=Depends(get_db)):
    db.execute(
        delete(PushDevice).where(
            PushDevice.user_id == user.id, PushDevice.session_id == request.state.session_id
        )
    )
    db.commit()
