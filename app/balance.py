"""Aportes são transferências internas: uma única fonte de débito do disponível."""
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import case, func, select

from app.models import Contribution, Entry, User


def lock_wallet(db, uid):
    # Todas as mutações do caixa usam a mesma ordem de locks, inclusive metas distintas.
    db.scalar(select(User).where(User.id == uid).with_for_update())


def balance_at(db, uid, end):
    net = int(db.scalar(select(func.coalesce(func.sum(
        case((Entry.kind == "income", Entry.amount_cents), else_=-Entry.amount_cents)
    ), 0)).where(Entry.user_id == uid, Entry.on_date <= end)))
    reserved = int(db.scalar(select(func.coalesce(func.sum(Contribution.amount_cents), 0))
        .where(Contribution.user_id == uid, Contribution.on_date <= end)))
    return {"available_cents": net - reserved, "reserved_total_cents": reserved,
            "recorded_total_cents": net}


def ensure_funded(db, uid, on_date, amount):
    # Locking reads enxergam commits anteriores mesmo sob REPEATABLE READ do MySQL.
    flows = defaultdict(int)
    for day, kind, value in db.execute(select(Entry.on_date, Entry.kind, Entry.amount_cents)
            .where(Entry.user_id == uid).with_for_update()):
        flows[day] += value if kind == "income" else -value
    for day, value in db.execute(select(Contribution.on_date, Contribution.amount_cents)
            .where(Contribution.user_id == uid).with_for_update()):
        flows[day] -= value
    flows[on_date] -= amount
    running = 0
    for day in sorted(flows):
        running += flows[day]
        if day >= on_date and running < 0:
            raise HTTPException(409, "Saldo disponível insuficiente para o aporte. "
                "Registre a origem do dinheiro ou ajuste o valor/data. "
                "O aporte também precisa respeitar as movimentações posteriores.")
