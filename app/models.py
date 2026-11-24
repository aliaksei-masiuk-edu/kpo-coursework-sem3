from datetime import date, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'operator')"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="operator")
    is_active: Mapped[bool] = mapped_column(default=True)


class LoginSession(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))


class RepairOrder(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("cost_cents >= 0"),
        CheckConstraint("planned_on >= received_on"),
        CheckConstraint("completed_on IS NULL OR completed_on >= received_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_name: Mapped[str] = mapped_column(String(100))
    brand: Mapped[str] = mapped_column(String(100))
    owner_name: Mapped[str] = mapped_column(String(150))
    owner_phone: Mapped[str] = mapped_column(String(30))
    cost_cents: Mapped[int]
    received_on: Mapped[date] = mapped_column(index=True)
    planned_on: Mapped[date] = mapped_column(index=True)
    completed_on: Mapped[date | None] = mapped_column(index=True, default=None)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
