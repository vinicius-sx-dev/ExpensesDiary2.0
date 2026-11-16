from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import literal, select, union_all
from sqlalchemy.exc import IntegrityError

from app.balance import ensure_funded, lock_wallet
from app.categories import catalog
from app.db import get_db
from app.models import Budget, Contribution, Entry, Goal, User
from app.schemas import (
    BudgetInput,
    BudgetRead,
    ContributionInput,
    ContributionRead,
    EntryInput,
    EntryRead,
    GoalInput,
    GoalRead,
    MovementRead,
)
from app.security import current_user
from app.ingestion import normalized_context, make_entry

router = APIRouter(tags=["Finanças"], dependencies=[Depends(current_user)])


def owned(db, model, item_id, user_id):
    item = db.scalar(
        select(model).where(model.id == item_id, model.user_id == user_id).with_for_update()
    )
    if item is None:
        raise HTTPException(404, "Registro não encontrado")
    return item


def save(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Registro duplicado ou conflitante")


def values(payload):
    data = payload.model_dump()
    if "request_id" in data:
        data["request_id"] = str(data["request_id"])
    if "context" in data:
        context = data.pop("context")
        data["context"] = context  # bind ciphertext only after immutable request_id
    return data


@router.get("/categories")
def categories():
    return catalog()


@router.get("/entries", response_model=list[EntryRead])
def entries(
    start: date | None = None,
    end: date | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    if start and end and start > end:
        raise HTTPException(422, "Intervalo inválido")
    q = select(Entry).where(Entry.user_id == user.id)
    if start:
        q = q.where(Entry.on_date >= start)
    if end:
        q = q.where(Entry.on_date <= end)
    return db.scalars(
        q.order_by(Entry.on_date.desc(), Entry.id.desc()).offset(offset).limit(limit)
    ).all()


@router.post("/entries", response_model=EntryRead, status_code=201)
def add_entry(payload: EntryInput, user=Depends(current_user), db=Depends(get_db)):
    lock_wallet(db, user.id)
    data = values(payload)
    data["context"] = normalized_context(data["context"], payload.on_date, "manual")
    existing = db.scalar(
        select(Entry).where(Entry.user_id == user.id, Entry.request_id == data["request_id"]).with_for_update()
    )
    if existing:
        if any(getattr(existing, k) != v for k, v in data.items()):
            raise HTTPException(409, "Identificador já utilizado")
        return existing
    raw_context = payload.context.model_dump()
    data.pop("context")
    row = make_entry(user_id=user.id, source="manual", context=raw_context, **data)
    db.add(row)
    save(db)
    return row


@router.put("/entries/{item_id}", response_model=EntryRead)
def edit_entry(item_id: int, payload: EntryInput, user=Depends(current_user), db=Depends(get_db)):
    lock_wallet(db, user.id)
    row = owned(db, Entry, item_id, user.id)
    if str(payload.request_id) != row.request_id:
        raise HTTPException(409, "Identificador imutável")
    data = values(payload)
    data["context"] = normalized_context(data["context"], payload.on_date, row.context.get("source", "manual"))
    data["context"]["classification_reviewed"] = True
    for k, v in data.items():
        setattr(row, k, v)
    save(db)
    return row


@router.delete("/entries/{item_id}", status_code=204)
def delete_entry(item_id: int, user=Depends(current_user), db=Depends(get_db)):
    lock_wallet(db, user.id)
    db.delete(owned(db, Entry, item_id, user.id))
    save(db)


@router.get("/budgets", response_model=list[BudgetRead])
def budgets(month: date, user=Depends(current_user), db=Depends(get_db)):
    return db.scalars(
        select(Budget).where(Budget.user_id == user.id, Budget.month == month).order_by(Budget.id)
    ).all()


@router.post("/budgets", response_model=BudgetRead, status_code=201)
def add_budget(payload: BudgetInput, user=Depends(current_user), db=Depends(get_db)):
    row = Budget(user_id=user.id, **values(payload))
    db.add(row)
    save(db)
    return row


@router.put("/budgets/{item_id}", response_model=BudgetRead)
def edit_budget(item_id: int, payload: BudgetInput, user=Depends(current_user), db=Depends(get_db)):
    row = owned(db, Budget, item_id, user.id)
    for k, v in values(payload).items():
        setattr(row, k, v)
    save(db)
    return row


@router.delete("/budgets/{item_id}", status_code=204)
def delete_budget(item_id: int, user=Depends(current_user), db=Depends(get_db)):
    db.delete(owned(db, Budget, item_id, user.id))
    save(db)


@router.get("/goals", response_model=list[GoalRead])
def goals(offset: int = Query(0, ge=0), user=Depends(current_user), db=Depends(get_db)):
    return db.scalars(
        select(Goal).where(Goal.user_id == user.id).order_by(Goal.id).offset(offset).limit(100)
    ).all()


@router.post("/goals", response_model=GoalRead, status_code=201)
def add_goal(payload: GoalInput, user=Depends(current_user), db=Depends(get_db)):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    if len(db.scalars(select(Goal.id).where(Goal.user_id == user.id).with_for_update()).all()) >= 100:
        raise HTTPException(409, "Limite de 100 objetivos atingido")
    row = Goal(user_id=user.id, **values(payload))
    db.add(row)
    save(db)
    return row


@router.put("/goals/{item_id}", response_model=GoalRead)
def edit_goal(item_id: int, payload: GoalInput, user=Depends(current_user), db=Depends(get_db)):
    row = owned(db, Goal, item_id, user.id)
    for k, v in values(payload).items():
        setattr(row, k, v)
    save(db)
    return row


@router.delete("/goals/{item_id}", status_code=204)
def delete_goal(item_id: int, user=Depends(current_user), db=Depends(get_db)):
    row = owned(db, Goal, item_id, user.id)
    if db.scalar(select(Contribution.id).where(Contribution.goal_id == row.id).limit(1)):
        raise HTTPException(409, "Remova os aportes antes de excluir a meta")
    db.delete(row)
    save(db)


@router.get("/goals/{item_id}/contributions", response_model=list[ContributionRead])
def contributions(
    item_id: int, offset: int = Query(0, ge=0), user=Depends(current_user), db=Depends(get_db)
):
    owned(db, Goal, item_id, user.id)
    return db.scalars(
        select(Contribution)
        .where(Contribution.user_id == user.id, Contribution.goal_id == item_id)
        .order_by(Contribution.on_date.desc(), Contribution.id.desc())
        .offset(offset)
        .limit(100)
    ).all()


@router.post("/goals/{item_id}/contributions", response_model=ContributionRead, status_code=201)
def contribute(
    item_id: int, payload: ContributionInput, user=Depends(current_user), db=Depends(get_db)
):
    lock_wallet(db, user.id)
    owned(db, Goal, item_id, user.id)
    data = values(payload)
    existing = db.scalar(
        select(Contribution).where(
            Contribution.user_id == user.id, Contribution.request_id == data["request_id"]
        ).with_for_update()
    )
    if existing:
        if existing.goal_id != item_id or any(getattr(existing, k) != v for k, v in data.items()):
            raise HTTPException(409, "Identificador já utilizado")
        return existing
    ensure_funded(db, user.id, payload.on_date, payload.amount_cents)
    row = Contribution(user_id=user.id, goal_id=item_id, **data)
    db.add(row)
    save(db)
    return row


@router.delete("/contributions/{item_id}", status_code=204)
def delete_contribution(item_id: int, user=Depends(current_user), db=Depends(get_db)):
    lock_wallet(db, user.id)
    db.delete(owned(db, Contribution, item_id, user.id))
    save(db)


@router.get("/movements", response_model=list[MovementRead])
def movements(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
              user=Depends(current_user), db=Depends(get_db)):
    # União somente de leitura: não cria uma segunda despesa para o mesmo aporte.
    entries = select(Entry.id, Entry.request_id, Entry.kind, Entry.category,
        Entry.amount_cents, Entry.on_date, Entry.description, Entry.essential,
        Entry.payment_method, literal(None).label("goal_id")).where(Entry.user_id == user.id)
    contributions = select(Contribution.id, Contribution.request_id,
        literal("contribution"), literal("goal_contribution"), Contribution.amount_cents,
        Contribution.on_date, literal(""), literal(False), literal("transfer"),
        Contribution.goal_id).join(Goal, Goal.id == Contribution.goal_id).where(
            Contribution.user_id == user.id, Goal.user_id == user.id)
    ledger = union_all(entries, contributions).subquery()
    rows = [dict(r) for r in db.execute(select(ledger).order_by(ledger.c.on_date.desc(), ledger.c.kind,
        ledger.c.id.desc()).offset(offset).limit(limit)).mappings().all()]
    goal_ids = [r["goal_id"] for r in rows if r["goal_id"]]
    titles = {g.id: g.title for g in db.scalars(select(Goal).where(Goal.user_id == user.id, Goal.id.in_(goal_ids)))}
    entry_ids = [r["id"] for r in rows if r["kind"] != "contribution"]
    contexts = {e.id: e.context for e in db.scalars(select(Entry).where(Entry.user_id == user.id, Entry.id.in_(entry_ids)))}
    for r in rows:
        r["context"] = contexts.get(r["id"], {}) if r["kind"] != "contribution" else {}
        if r["goal_id"]:
            r["description"] = titles.get(r["goal_id"], "")
    return rows
