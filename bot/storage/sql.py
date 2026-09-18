"""
Postgres-backed repository.

Mirrors MemoryRepository exactly, so switching STORAGE_MODE changes durability
and nothing else. Every write that touches two tables (points + log, buy +
inventory) happens inside one transaction.
"""
from __future__ import annotations

import logging
import random
from typing import AsyncIterator

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.core.clock import now
from bot.core.enums import Breed
from bot.domain.entities import CatData, ItemData, UserData
from bot.domain.rules import generate_id_number
from bot.storage import models as m
from bot.storage.base import DEFAULT_ITEMS, Repository

logger = logging.getLogger("catibot.storage.sql")


def _to_cat(row: m.Cat) -> CatData:
    return CatData(
        cat_id=row.cat_id,
        owner_id=row.owner_id,
        name=row.name,
        breed=Breed(row.breed),
        id_number=row.id_number,
        title=row.title,
        partner_id=row.partner_id,
        age_days=row.age_days,
        hunger=row.hunger,
        happiness=row.happiness,
        love_bar=row.love_bar,
        partner_affinity=row.partner_affinity,
        is_fled=row.is_fled,
        is_guest=row.is_guest,
        created_at=row.created_at,
        last_fed=row.last_fed,
        last_played=row.last_played,
        last_walk=row.last_walk,
        last_decay_at=row.last_decay_at,
        fled_at=row.fled_at,
        last_notified_state=row.last_notified_state,
        last_notified_at=row.last_notified_at,
    )


def _to_item(row: m.Item) -> ItemData:
    return ItemData(
        item_id=row.item_id,
        name=row.name,
        price=row.price,
        effect_type=row.effect_type,
        effect_value=row.effect_value,
        emoji=row.emoji,
        description=row.description,
    )


CAT_FIELDS = (
    "owner_id partner_id name title breed age_days hunger happiness love_bar "
    "partner_affinity is_fled is_guest last_fed last_played last_walk last_decay_at "
    "fled_at last_notified_state last_notified_at"
).split()


class SQLRepository(Repository):
    name = "postgres"

    def __init__(self, database_url: str, *, create_all: bool = True) -> None:
        self._engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
        self._session: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )
        self._create_all = create_all
        self._rng = random.Random()

    # --- lifecycle --------------------------------------------------------
    async def setup(self) -> None:
        async with self._engine.begin() as conn:
            if self._create_all:
                # Convenience for first boot. In production prefer `alembic upgrade head`.
                await conn.run_sync(m.Base.metadata.create_all)
        await self._seed_items()

    async def _seed_items(self) -> None:
        async with self._session() as s:
            existing = await s.scalar(select(func.count()).select_from(m.Item))
            if existing:
                return
            s.add_all(
                [
                    m.Item(
                        item_id=i.item_id,
                        name=i.name,
                        price=i.price,
                        effect_type=i.effect_type,
                        effect_value=i.effect_value,
                        emoji=i.emoji,
                        description=i.description,
                    )
                    for i in DEFAULT_ITEMS
                ]
            )
            await s.commit()

    async def close(self) -> None:
        await self._engine.dispose()

    async def health(self) -> dict:
        try:
            async with self._session() as s:
                await s.execute(text("SELECT 1"))
            ok = True
        except Exception as exc:  # pragma: no cover - depends on a live DB
            logger.warning("db health check failed: %s", exc)
            ok = False
        payload = {"backend": "postgres", "ok": ok, "persistent": True}
        if ok:
            payload |= await self.counts()
        return payload

    async def counts(self) -> dict[str, int]:
        async with self._session() as s:
            return {
                "users": await s.scalar(select(func.count()).select_from(m.User)) or 0,
                "cats": await s.scalar(select(func.count()).select_from(m.Cat)) or 0,
                "fled": await s.scalar(
                    select(func.count()).select_from(m.Cat).where(m.Cat.is_fled.is_(True))
                )
                or 0,
                "items": await s.scalar(select(func.count()).select_from(m.Item)) or 0,
            }

    # --- users ------------------------------------------------------------
    async def get_or_create_user(
        self, user_id: int, *, username: str | None = None, is_guest: bool = False
    ) -> UserData:
        async with self._session() as s:
            row = await s.get(m.User, user_id)
            if row is None:
                row = m.User(user_id=user_id, username=username, is_guest=is_guest)
                s.add(row)
                try:
                    await s.commit()
                except IntegrityError:  # concurrent /start
                    await s.rollback()
                    row = await s.get(m.User, user_id)
            elif username and row.username != username:
                row.username = username
                await s.commit()
            return UserData(
                user_id=row.user_id,
                points=row.points,
                is_guest=row.is_guest,
                username=row.username,
                created_at=row.created_at,
            )

    async def save_user(self, user: UserData) -> None:
        async with self._session() as s:
            await s.execute(
                update(m.User)
                .where(m.User.user_id == user.user_id)
                .values(points=user.points, username=user.username)
            )
            await s.commit()

    async def add_points(self, user_id: int, delta: int, reason: str) -> int:
        async with self._session() as s:
            async with s.begin():
                row = await s.get(m.User, user_id, with_for_update=True)
                if row is None:
                    row = m.User(user_id=user_id)
                    s.add(row)
                    await s.flush()
                row.points = max(0, row.points + delta)
                s.add(m.PointsLog(user_id=user_id, delta=delta, reason=reason))
                return row.points

    async def points_history(self, user_id: int, limit: int = 10) -> list[tuple[int, str]]:
        async with self._session() as s:
            rows = await s.execute(
                select(m.PointsLog.delta, m.PointsLog.reason)
                .where(m.PointsLog.user_id == user_id)
                .order_by(m.PointsLog.ts.desc())
                .limit(limit)
            )
            return [(d, r) for d, r in rows.all()]

    # --- cats -------------------------------------------------------------
    async def create_cat(
        self, *, owner_id: int, name: str, breed: Breed, is_guest: bool = False
    ) -> CatData:
        async with self._session() as s:
            for _ in range(10):
                row = m.Cat(
                    owner_id=owner_id,
                    name=name,
                    breed=breed.value,
                    id_number=generate_id_number(self._rng),
                    is_guest=is_guest,
                )
                s.add(row)
                try:
                    await s.commit()
                    return _to_cat(row)
                except IntegrityError:
                    await s.rollback()  # id_number collision, try again
            raise RuntimeError("could not allocate a unique cat id_number")

    async def get_cat(self, cat_id: int) -> CatData | None:
        async with self._session() as s:
            row = await s.get(m.Cat, cat_id)
            return _to_cat(row) if row else None

    async def get_active_cat_for(self, user_id: int) -> CatData | None:
        async with self._session() as s:
            row = await s.scalar(
                select(m.Cat)
                .where(
                    m.Cat.is_fled.is_(False),
                    (m.Cat.owner_id == user_id) | (m.Cat.partner_id == user_id),
                )
                .order_by(m.Cat.cat_id.desc())
                .limit(1)
            )
            return _to_cat(row) if row else None

    async def save_cat(self, cat: CatData) -> None:
        values = {f: getattr(cat, f) for f in CAT_FIELDS}
        values["breed"] = cat.breed.value
        async with self._session() as s:
            await s.execute(update(m.Cat).where(m.Cat.cat_id == cat.cat_id).values(**values))
            await s.commit()

    async def delete_cat(self, cat_id: int) -> None:
        async with self._session() as s:
            await s.execute(delete(m.Cat).where(m.Cat.cat_id == cat_id))
            await s.commit()

    async def iter_active_cats(self, batch: int = 200) -> AsyncIterator[CatData]:
        last_id = 0
        while True:
            async with self._session() as s:
                rows = (
                    await s.scalars(
                        select(m.Cat)
                        .where(m.Cat.is_fled.is_(False), m.Cat.cat_id > last_id)
                        .order_by(m.Cat.cat_id)
                        .limit(batch)
                    )
                ).all()
            if not rows:
                return
            for row in rows:
                last_id = row.cat_id
                yield _to_cat(row)

    async def list_fled_cats(self, limit: int = 10) -> list[CatData]:
        async with self._session() as s:
            rows = (
                await s.scalars(
                    select(m.Cat)
                    .where(m.Cat.is_fled.is_(True))
                    .order_by(m.Cat.fled_at.desc().nullslast())
                    .limit(limit)
                )
            ).all()
            return [_to_cat(r) for r in rows]

    # --- items ------------------------------------------------------------
    async def list_items(self) -> list[ItemData]:
        async with self._session() as s:
            rows = (await s.scalars(select(m.Item).order_by(m.Item.price))).all()
            return [_to_item(r) for r in rows]

    async def get_item(self, item_id: int) -> ItemData | None:
        async with self._session() as s:
            row = await s.get(m.Item, item_id)
            return _to_item(row) if row else None

    async def inventory(self, user_id: int) -> list[tuple[ItemData, int]]:
        async with self._session() as s:
            rows = await s.execute(
                select(m.Item, m.UserInventory.qty)
                .join(m.UserInventory, m.UserInventory.item_id == m.Item.item_id)
                .where(m.UserInventory.user_id == user_id, m.UserInventory.qty > 0)
                .order_by(m.Item.price)
            )
            return [(_to_item(item), qty) for item, qty in rows.all()]

    async def change_inventory(self, user_id: int, item_id: int, delta: int) -> int:
        async with self._session() as s:
            async with s.begin():
                row = await s.scalar(
                    select(m.UserInventory)
                    .where(m.UserInventory.user_id == user_id, m.UserInventory.item_id == item_id)
                    .with_for_update()
                )
                if row is None:
                    if delta <= 0:
                        return 0
                    s.add(m.UserInventory(user_id=user_id, item_id=item_id, qty=delta))
                    return delta
                row.qty = max(0, row.qty + delta)
                return row.qty

    # --- maintenance ------------------------------------------------------
    async def reset_user(self, user_id: int) -> None:
        async with self._session() as s:
            async with s.begin():
                await s.execute(delete(m.Cat).where(m.Cat.owner_id == user_id))
                await s.execute(
                    update(m.Cat).where(m.Cat.partner_id == user_id).values(partner_id=None)
                )
                await s.execute(delete(m.UserInventory).where(m.UserInventory.user_id == user_id))
                await s.execute(delete(m.PointsLog).where(m.PointsLog.user_id == user_id))
                await s.execute(delete(m.User).where(m.User.user_id == user_id))
