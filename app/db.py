import json
import time
import uuid

from cryptography.fernet import Fernet
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


def uid():
    return uuid.uuid4().hex


def now():
    return int(time.time())


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args={"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {})
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_config(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
fernet = Fernet(settings.encryption_key)


def encrypt(value):
    return fernet.encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()


def decrypt(value):
    return json.loads(fernet.decrypt(value.encode())) if value else None


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(256))
    credits: Mapped[int] = mapped_column(Integer, default=0)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class AuthSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


class ResetToken(Base):
    __tablename__ = "reset_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[int] = mapped_column(Integer)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    source_type: Mapped[str] = mapped_column(String(12))
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[str] = mapped_column(Text)
    warnings: Mapped[str] = mapped_column(Text, default="[]")
    word_count: Mapped[int] = mapped_column(Integer)
    price_cents: Mapped[int] = mapped_column(Integer)
    detector_cents: Mapped[int] = mapped_column(Integer, default=0)
    quote_breakdown: Mapped[str] = mapped_column(Text)
    quote_expires_at: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="quoted", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(80), default="Ready to begin")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    charged: Mapped[bool] = mapped_column(Boolean, default=False)
    refunded: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lease_until: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    updated_at: Mapped[int] = mapped_column(Integer, default=now)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


class Ledger(Base):
    __tablename__ = "ledger"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(200))
    reference: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class WeeklyGrant(Base):
    __tablename__ = "weekly_grants"
    __table_args__ = (UniqueConstraint("user_id", "period_key", name="uq_weekly_grant_user_period"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    period_key: Mapped[str] = mapped_column(String(16), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    stripe_session: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    stripe_intent: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[int] = mapped_column(Integer, default=now)


def init_db():
    Base.metadata.create_all(engine)
