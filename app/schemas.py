from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES


def today():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


Money = Annotated[int, Field(strict=True, gt=0, le=100_000_000_00)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Register(Strict):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("name")
    @classmethod
    def name_valid(cls, v):
        if len(v.strip()) < 2:
            raise ValueError("Nome muito curto")
        return v.strip()


class Login(Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Verify(Strict):
    challenge_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    code: str = Field(pattern=r"^\d{6}$")


class Refresh(Strict):
    refresh_token: str = Field(min_length=40, max_length=200)


class UserRead(Strict):
    id: int
    name: str
    email: str


class Profile(Strict):
    name: str = Field(min_length=2, max_length=120)


class EntryInput(Strict):
    request_id: UUID
    kind: Literal["expense", "income"]
    category: str
    amount_cents: Money
    on_date: date
    description: str = Field(default="", max_length=240)
    essential: bool = False
    payment_method: Literal["pix", "debit", "credit", "cash", "transfer", "other"] = "pix"

    @model_validator(mode="after")
    def valid(self):
        allowed = EXPENSE_CATEGORIES if self.kind == "expense" else INCOME_CATEGORIES
        if self.category not in allowed:
            raise ValueError("Categoria incompatível")
        if self.on_date > today() or self.on_date < date(2000, 1, 1):
            raise ValueError("Data inválida")
        return self


class EntryRead(EntryInput):
    id: int


class BudgetInput(Strict):
    month: date
    category: str
    limit_cents: Money

    @model_validator(mode="after")
    def valid(self):
        if self.month.day != 1:
            raise ValueError("Use o primeiro dia do mês")
        if self.category not in EXPENSE_CATEGORIES | {"total"}:
            raise ValueError("Categoria inválida")
        return self


class BudgetRead(BudgetInput):
    id: int


class GoalInput(Strict):
    title: str = Field(min_length=2, max_length=100)
    motivation: str = Field(default="", max_length=240)
    target_cents: Money
    deadline: date

    @field_validator("deadline")
    @classmethod
    def future(cls, v):
        if v < today():
            raise ValueError("Prazo deve ser hoje ou futuro")
        return v


class GoalRead(Strict):
    id: int
    title: str
    motivation: str
    target_cents: int
    deadline: date


class ContributionInput(Strict):
    request_id: UUID
    amount_cents: Money
    on_date: date

    @field_validator("on_date")
    @classmethod
    def past(cls, v):
        if v > today() or v < date(2000, 1, 1):
            raise ValueError("Data inválida")
        return v


class ContributionRead(ContributionInput):
    id: int
    goal_id: int


class Insight(Strict):
    summary: str = Field(min_length=1, max_length=6000)
    suggestions: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=10)


class MovementRead(Strict):
    id: int
    request_id: str
    kind: Literal["expense", "income", "contribution"]
    category: str
    amount_cents: int
    on_date: date
    description: str
    essential: bool
    payment_method: str
    goal_id: int | None = None
