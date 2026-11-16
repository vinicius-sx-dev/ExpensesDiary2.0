"""Pure deterministic strategies. No external calls, personal prose or database access."""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

WINDOW_DAYS = 84


class Strategy(Protocol):
    key: str
    categories: set[str]

    def matches(self, entry) -> bool: ...
    def alternative(self) -> str: ...


class SpendingStrategy:
    def __init__(self, key, categories, action, declared=False):
        self.key, self.categories, self.action, self.declared = key, categories, action, declared

    def matches(self, entry):
        context = entry.context
        if self.declared:
            return context.get("niche") == self.key and context.get("unplanned", False)
        if context.get("niche"):
            return context["niche"] == self.key
        return entry.category in self.categories

    def alternative(self):
        return self.action


STRATEGIES = [
    SpendingStrategy(
        "fast_food",
        {"restaurante", "delivery", "cafe", "padaria"},
        "Substituir uma refeição fora por uma receita caseira",
    ),
    SpendingStrategy(
        "subscriptions",
        {"streaming", "servicos_digitais"},
        "Revisar uma assinatura e confirmar cancelamento sem multa",
    ),
    SpendingStrategy(
        "impulse", set(), "Adiar uma compra identificada por você como não planejada", True
    ),
    SpendingStrategy(
        "beauty",
        {"beleza"},
        "Espaçar um atendimento opcional; confirme que não há custo de cancelamento",
    ),
    SpendingStrategy(
        "tattoo",
        set(),
        "Planejar uma sessão para depois da meta; confirme condições com o profissional",
    ),
    SpendingStrategy("travel", set(), "Planejar a próxima viagem sem comprometer o aporte", True),
]


def patterns(entries, as_of):
    start = as_of - timedelta(days=WINDOW_DAYS - 1)
    result = []
    for strategy in STRATEGIES:
        rows = [
            e
            for e in entries
            if e.kind == "expense"
            and not e.essential
            and e.context.get("classification_reviewed") is not False
            and start <= e.on_date <= as_of
            and strategy.matches(e)
        ]
        # Categories alone do not prove that two payments belong to the same subscription.
        if strategy.key == "subscriptions":
            groups = defaultdict(list)
            for e in rows:
                merchant = e.context.get("merchant")
                if merchant:
                    groups[merchant.casefold()].append(e)
            rows = [
                e
                for group in groups.values()
                if len({(r.on_date.year, r.on_date.month) for r in group}) >= 2
                for e in group
            ]
        weeks = {e.on_date.isocalendar()[:2] for e in rows}
        if len(rows) < 3 or len(weeks) < 3:
            continue
        weekdays = Counter(e.on_date.weekday() for e in rows)
        weekday, dominant = weekdays.most_common(1)[0]
        times = []
        for row in rows:
            stamp = row.context.get("occurred_at")
            if stamp and row.on_date.weekday() == weekday:
                times.append(
                    datetime.fromisoformat(stamp).astimezone(ZoneInfo("America/Sao_Paulo")).hour
                )
        habit = dominant * 100 >= len(rows) * 60
        result.append(
            {
                "strategy": strategy.key,
                "occurrences": len(rows),
                "distinct_weeks": len(weeks),
                "total_cents": sum(e.amount_cents for e in rows),
                "average_cents": sum(e.amount_cents for e in rows) // len(rows),
                "window_days": WINDOW_DAYS,
                "weekday": weekday if habit else None,
                "hour": sorted(times)[len(times) // 2] if len(times) >= 3 and habit else None,
                "action": strategy.alternative(),
            }
        )
    return result


def completion_date(remaining, monthly, as_of, contribution_day):
    if remaining <= 0:
        return as_of
    if monthly <= 0:
        return None
    periods = (remaining + monthly - 1) // monthly
    candidate = as_of.replace(day=contribution_day)
    offset = (0 if candidate > as_of else 1) + periods - 1
    index = as_of.year * 12 + as_of.month - 1 + offset
    year, month = divmod(index, 12)
    if year > 9999:
        return None
    return date(year, month + 1, contribution_day)


def goal_state(goal, contributions, as_of):
    relevant = [c for c in contributions if c.goal_id == goal.id and c.on_date <= as_of]
    saved = sum(c.amount_cents for c in relevant)
    month = as_of.replace(day=1)
    index = month.year * 12 + month.month - 1 - 3
    first = date(index // 12, index % 12 + 1, 1)
    actual = sum(c.amount_cents for c in relevant if first <= c.on_date < month) // 3
    remaining = max(0, goal.target_cents - saved)
    baseline = completion_date(remaining, actual, as_of, goal.contribution_day)
    return {
        "goal_id": goal.id,
        "remaining_cents": remaining,
        "planned_monthly_cents": goal.planned_monthly_cents,
        "actual_monthly_cents": actual,
        "gap_cents": max(0, goal.planned_monthly_cents - actual),
        "deadline": goal.deadline.isoformat(),
        "baseline_date": baseline.isoformat() if baseline else None,
        "behind_deadline": remaining > 0 and (baseline is None or baseline > goal.deadline),
        "observation_start": first.isoformat(),
        "observation_end": (month - timedelta(days=1)).isoformat(),
        "assumptions": "Média dos aportes registrados nos três meses completos anteriores, incluindo meses sem registros. Pode subestimar o ritmo se o histórico estiver incompleto. Sem juros; aporte na data mensal escolhida; toda economia desta simulação vai exclusivamente para esta meta.",
    }


def scenario(goal, state, pattern, recipe, as_of, occurrences, replacement_cents=None):
    if pattern["strategy"] == "fast_food":
        if recipe["status"] != "verified":
            return {
                "status": "prices_unavailable",
                "message": recipe["message"],
                "alternative": recipe,
            }
        replacement = recipe["portion_cents"]
    else:
        # User must explicitly set a replacement/cancellation cost; never assume zero.
        if replacement_cents is None:
            return {
                "status": "needs_cost",
                "message": "Informe o custo da alternativa, incluindo multas, para simular.",
            }
        replacement = replacement_cents
    observed_per_month = Decimal(pattern["occurrences"]) * 30 / WINDOW_DAYS
    if Decimal(occurrences) > observed_per_month:
        return {
            "status": "invalid_frequency",
            "message": "A quantidade escolhida supera a frequência observada (mês de referência de 30 dias).",
        }
    per = max(0, pattern["average_cents"] - replacement)
    monthly = per * occurrences
    improved = completion_date(
        state["remaining_cents"],
        state["actual_monthly_cents"] + monthly,
        as_of,
        goal.contribution_day,
    )
    baseline = date.fromisoformat(state["baseline_date"]) if state["baseline_date"] else None
    days = (baseline - improved).days if baseline and improved else None
    return {
        "status": "ready",
        "per_occurrence_cents": per,
        "monthly_savings_cents": monthly,
        "occurrences_per_month": occurrences,
        "replacement_cents": replacement,
        "completion_date": improved.isoformat() if improved else None,
        "days_earlier": max(0, days) if days is not None else None,
        "weeks_earlier": str(Decimal(max(0, days)) / 7) if days is not None else None,
        "alternative": recipe
        if pattern["strategy"] == "fast_food"
        else {"name": pattern["action"]},
        "note": "Simulação condicional, não transferência nem promessa. Economia de uma porção pressupõe aproveitamento das demais porções e sobras. Não some cenários alternativos nem reutilize a mesma economia em outras metas.",
    }
