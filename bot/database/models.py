"""PostgreSQL model for Catibot's complete runtime state."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def default_runtime_state() -> dict:
    return {
        "users": {},
        "cats": [],
        "items": [],
        "user_inventory": [],
        "points_log": [],
        "media": {},
        "media_types": {},
        "media_cache": {},
        "media_overrides": {},
    }


class Base(DeclarativeBase):
    pass


class RuntimeState(Base):
    __tablename__ = "catibot_runtime_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=default_runtime_state,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
