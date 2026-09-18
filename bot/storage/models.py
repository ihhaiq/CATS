"""
SQLAlchemy models for the Postgres backend.

Changes vs the original scaffold:
  * `fled_at` and `last_decay_at` columns now exist (the logic referenced them).
  * Real foreign keys + indexes on the columns the sweep and lookups filter by.
  * `user_inventory` has a composite unique constraint so a user can't end up
    with two rows for the same item.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bot.core.clock import now
from bot.domain.entities import _actionable


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class Cat(Base):
    __tablename__ = "cats"

    cat_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    partner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, default="🏷️ الأليف", nullable=False)
    id_number: Mapped[str] = mapped_column(String(6), unique=True, nullable=False)
    breed: Mapped[str] = mapped_column(Text, nullable=False)
    age_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    hunger: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    happiness: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    love_bar: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    partner_affinity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_fled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    last_fed: Mapped[datetime] = mapped_column(DateTime, default=_actionable, nullable=False)
    last_played: Mapped[datetime] = mapped_column(DateTime, default=_actionable, nullable=False)
    last_walk: Mapped[datetime] = mapped_column(DateTime, default=_actionable, nullable=False)
    last_decay_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    fled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_notified_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_cats_owner_active", "owner_id", "is_fled"),
        Index("ix_cats_partner", "partner_id"),
        Index("ix_cats_fled", "is_fled", "fled_at"),
    )


class Item(Base):
    __tablename__ = "items"

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    effect_type: Mapped[str] = mapped_column(Text, nullable=False)
    effect_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🎁", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)


class UserInventory(Base):
    __tablename__ = "user_inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "item_id", name="uq_inventory_user_item"),)


class PointsLog(Base):
    __tablename__ = "points_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class PartnerHistory(Base):
    """Audit trail so the one-time join bonus can't be farmed by re-inviting."""

    __tablename__ = "partner_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    partner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)

    __table_args__ = (UniqueConstraint("cat_id", "partner_id", name="uq_partner_once"),)
