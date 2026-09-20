"""SQLAlchemy models retained for the Railway PostgreSQL migration."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    points: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Cat(Base):
    __tablename__ = "cats"

    cat_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"))
    partner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="🏷️ الأليف")
    id_number: Mapped[str] = mapped_column(String(6), unique=True)
    breed: Mapped[str] = mapped_column(Text)
    age_days: Mapped[int] = mapped_column(Integer, default=30)
    hunger: Mapped[int] = mapped_column(Integer, default=50)
    happiness: Mapped[int] = mapped_column(Integer, default=100)
    love_bar: Mapped[int] = mapped_column(Integer, default=100)
    partner_affinity: Mapped[int] = mapped_column(Integer, default=0)
    is_fled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_fed: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_played: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_walk: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_notified_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Item(Base):
    __tablename__ = "items"

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text)
    price: Mapped[int] = mapped_column(Integer)
    effect_type: Mapped[str] = mapped_column(Text)
    effect_value: Mapped[int] = mapped_column(Integer)


class UserInventory(Base):
    __tablename__ = "user_inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    item_id: Mapped[int] = mapped_column(Integer)
    qty: Mapped[int] = mapped_column(Integer, default=1)


class PointsLog(Base):
    __tablename__ = "points_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
