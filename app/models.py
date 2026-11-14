from datetime import date

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.crypto import seal, unseal, protected_field


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
    protected_context: Mapped[bytes | None] = mapped_column(LargeBinary)

    @property
    def context(self):
        return unseal(self.protected_context, self.user_id, "entry", self.request_id) if self.protected_context else {}

    @context.setter
    def context(self, value):
        self.protected_context = seal(value, self.user_id, "entry", self.request_id) if value else None



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
    # Legacy columns retain only inert sentinels for a restartable additive migration.
    legacy_title: Mapped[str] = mapped_column("title", String(100), default="")
    legacy_motivation: Mapped[str] = mapped_column("motivation", String(240), default="")
    legacy_target: Mapped[int] = mapped_column("target_cents", BigInteger, default=1)
    legacy_deadline: Mapped[date] = mapped_column("deadline", Date, default=date(2000, 1, 1))
    crypto_id: Mapped[str] = mapped_column(String(36))
    protected_data: Mapped[bytes] = mapped_column(LargeBinary)
    title = protected_field("title", "")
    motivation = protected_field("motivation", "")
    target_cents = protected_field("target_cents", 0)
    deadline = protected_field("deadline", as_date=True)
    planned_monthly_cents = protected_field("planned_monthly_cents", 0)
    contribution_day = protected_field("contribution_day", 1)


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
    legacy_data: Mapped[dict] = mapped_column("data", JSON, default=dict)
    protected_data: Mapped[bytes] = mapped_column(LargeBinary(length=1024 * 1024))

    @property
    def data(self):
        return unseal(self.protected_data, self.user_id, "report", self.week_start)

    @data.setter
    def data(self, value):
        self.protected_data = seal(value, self.user_id, "report", self.week_start)


class StatementImport(Base):
    __tablename__ = "statement_imports"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[bytes] = mapped_column(LargeBinary(length=1024 * 1024))
    expires_at: Mapped[int] = mapped_column(BigInteger, index=True)
    status: Mapped[str] = mapped_column(String(12))
    imported_count: Mapped[int] = mapped_column(default=0)


class ImportLease(Base):
    __tablename__ = "import_leases"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[int] = mapped_column(BigInteger)


class PluggyReceipt(Base):
    """Opaque transaction deduplication survives edits/deletion of ledger entries."""
    __tablename__ = "pluggy_receipts"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)


class AdvisorSettings(Base):
    __tablename__ = "advisor_settings"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    protected_data: Mapped[bytes] = mapped_column(LargeBinary)

    @property
    def data(self):
        return unseal(self.protected_data, self.user_id, "preferences", self.user_id)

    @data.setter
    def data(self, value):
        self.protected_data = seal(value, self.user_id, "preferences", self.user_id)


class Advice(Base):
    __tablename__ = "advisor_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[int] = mapped_column(BigInteger, index=True)
    protected_data: Mapped[bytes] = mapped_column(LargeBinary(length=1024 * 1024))

    @property
    def data(self):
        return unseal(self.protected_data, self.user_id, "advice", self.id)

    @data.setter
    def data(self, value):
        self.protected_data = seal(value, self.user_id, "advice", self.id)


class PushDevice(Base):
    __tablename__ = "advisor_devices"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("login_sessions.id", ondelete="CASCADE"), index=True)
    protected_token: Mapped[bytes] = mapped_column(LargeBinary)


class Notification(Base):
    __tablename__ = "advisor_notifications"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    due_at: Mapped[int] = mapped_column(BigInteger, index=True)
    sent_at: Mapped[int | None] = mapped_column(BigInteger, index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    protected_data: Mapped[bytes] = mapped_column(LargeBinary)

    @property
    def data(self):
        return unseal(self.protected_data, self.user_id, "notification", self.id)

    @data.setter
    def data(self, value):
        self.protected_data = seal(value, self.user_id, "notification", self.id)
