from datetime import date

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class LoginChallenge(Base):
    __tablename__ = "login_challenges"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    device_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[int] = mapped_column(BigInteger)
    attempts: Mapped[int] = mapped_column(default=0)
    consumed: Mapped[bool] = mapped_column(default=False)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_hash: Mapped[str] = mapped_column(String(64))
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[int] = mapped_column(BigInteger)
    revoked: Mapped[bool] = mapped_column(default=False)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[int] = mapped_column(BigInteger, index=True)


class Entry(Base):
    __tablename__ = "finance_entries"
    __table_args__ = (
        CheckConstraint("amount_cents > 0"),
        UniqueConstraint("user_id", "request_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(60))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    on_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(240), default="")
    essential: Mapped[bool] = mapped_column(default=False)
    payment_method: Mapped[str] = mapped_column(String(20))


class Budget(Base):
    __tablename__ = "finance_budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "month", "category"),
        CheckConstraint("limit_cents > 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    month: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(60))
    limit_cents: Mapped[int] = mapped_column(BigInteger)


class Goal(Base):
    __tablename__ = "finance_goals"
    __table_args__ = (CheckConstraint("target_cents > 0"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    motivation: Mapped[str] = mapped_column(String(240), default="")
    target_cents: Mapped[int] = mapped_column(BigInteger)
    deadline: Mapped[date] = mapped_column(Date)


class Contribution(Base):
    __tablename__ = "finance_contributions"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id"),
        CheckConstraint("amount_cents > 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    goal_id: Mapped[int] = mapped_column(
        ForeignKey("finance_goals.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(36))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    on_date: Mapped[date] = mapped_column(Date)


class WeeklyReport(Base):
    __tablename__ = "finance_reports"
    __table_args__ = (UniqueConstraint("user_id", "week_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    data: Mapped[dict] = mapped_column(JSON)
