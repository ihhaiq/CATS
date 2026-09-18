"""
The guest store: everything lives in process memory.

This is what makes the bot runnable with nothing but a BOT_TOKEN — no Postgres,
no migrations, no Docker. It's also the backend the test-suite and the /dev
scenario runner use, because it can be reset instantly.

Concurrency: aiogram runs handlers concurrently on one loop, so a single
asyncio.Lock around mutations is enough to keep read-modify-write sequences
(points, inventory) atomic.
"""
from __future__ import annotations

import asyncio
import random
from copy import deepcopy
from typing import AsyncIterator

from bot.core.clock import now
from bot.core.enums import Breed
from bot.domain.entities import CatData, ItemData, UserData
from bot.domain.rules import generate_id_number
from bot.storage.base import DEFAULT_ITEMS, Repository


class MemoryRepository(Repository):
    name = "guest"

    def __init__(self, *, rng: random.Random | None = None) -> None:
        self._users: dict[int, UserData] = {}
        self._cats: dict[int, CatData] = {}
        self._items: dict[int, ItemData] = {}
        self._log: list[tuple[int, int, str]] = []
        self._next_cat_id = 1
        self._lock = asyncio.Lock()
        self._rng = rng or random.Random()

    # --- lifecycle --------------------------------------------------------
    async def setup(self) -> None:
        for item in DEFAULT_ITEMS:
            self._items[item.item_id] = deepcopy(item)

    async def close(self) -> None:
        return None

    async def health(self) -> dict:
        return {"backend": "memory", "ok": True, "persistent": False, **(await self.counts())}

    async def counts(self) -> dict[str, int]:
        return {
            "users": len(self._users),
            "cats": len(self._cats),
            "fled": sum(1 for c in self._cats.values() if c.is_fled),
            "items": len(self._items),
        }

    # --- users ------------------------------------------------------------
    async def get_or_create_user(
        self, user_id: int, *, username: str | None = None, is_guest: bool = False
    ) -> UserData:
        async with self._lock:
            user = self._users.get(user_id)
            if user is None:
                user = UserData(user_id=user_id, username=username, is_guest=is_guest)
                self._users[user_id] = user
            elif username and user.username != username:
                user.username = username
            return user

    async def save_user(self, user: UserData) -> None:
        async with self._lock:
            self._users[user.user_id] = user

    async def add_points(self, user_id: int, delta: int, reason: str) -> int:
        async with self._lock:
            user = self._users.setdefault(user_id, UserData(user_id=user_id))
            user.points = max(0, user.points + delta)
            self._log.append((user_id, delta, reason))
            return user.points

    async def points_history(self, user_id: int, limit: int = 10) -> list[tuple[int, str]]:
        rows = [(d, r) for uid, d, r in self._log if uid == user_id]
        return rows[-limit:][::-1]

    # --- cats -------------------------------------------------------------
    async def create_cat(
        self, *, owner_id: int, name: str, breed: Breed, is_guest: bool = False
    ) -> CatData:
        async with self._lock:
            taken = {c.id_number for c in self._cats.values()}
            id_number = generate_id_number(self._rng)
            while id_number in taken:
                id_number = generate_id_number(self._rng)

            cat = CatData(
                cat_id=self._next_cat_id,
                owner_id=owner_id,
                name=name,
                breed=breed,
                id_number=id_number,
                is_guest=is_guest,
            )
            self._cats[cat.cat_id] = cat
            self._next_cat_id += 1
            return cat

    async def get_cat(self, cat_id: int) -> CatData | None:
        return self._cats.get(cat_id)

    async def get_active_cat_for(self, user_id: int) -> CatData | None:
        for cat in self._cats.values():
            if cat.is_fled:
                continue
            if cat.owner_id == user_id or cat.partner_id == user_id:
                return cat
        return None

    async def save_cat(self, cat: CatData) -> None:
        async with self._lock:
            self._cats[cat.cat_id] = cat

    async def delete_cat(self, cat_id: int) -> None:
        async with self._lock:
            self._cats.pop(cat_id, None)

    async def iter_active_cats(self, batch: int = 200) -> AsyncIterator[CatData]:
        for cat in list(self._cats.values()):
            if not cat.is_fled:
                yield cat

    async def list_fled_cats(self, limit: int = 10) -> list[CatData]:
        fled = [c for c in self._cats.values() if c.is_fled]
        fled.sort(key=lambda c: c.fled_at or c.created_at, reverse=True)
        return fled[:limit]

    # --- items ------------------------------------------------------------
    async def list_items(self) -> list[ItemData]:
        return sorted(self._items.values(), key=lambda i: i.price)

    async def get_item(self, item_id: int) -> ItemData | None:
        return self._items.get(item_id)

    async def inventory(self, user_id: int) -> list[tuple[ItemData, int]]:
        user = self._users.get(user_id)
        if not user:
            return []
        rows = []
        for item_id, qty in user.inventory.items():
            item = self._items.get(item_id)
            if item and qty > 0:
                rows.append((item, qty))
        return rows

    async def change_inventory(self, user_id: int, item_id: int, delta: int) -> int:
        async with self._lock:
            user = self._users.setdefault(user_id, UserData(user_id=user_id))
            qty = max(0, user.inventory.get(item_id, 0) + delta)
            if qty:
                user.inventory[item_id] = qty
            else:
                user.inventory.pop(item_id, None)
            return qty

    # --- maintenance ------------------------------------------------------
    async def reset_user(self, user_id: int) -> None:
        async with self._lock:
            self._users.pop(user_id, None)
            for cat_id in [
                cid
                for cid, c in self._cats.items()
                if c.owner_id == user_id or c.partner_id == user_id
            ]:
                self._cats.pop(cat_id, None)
            self._log = [row for row in self._log if row[0] != user_id]

    async def purge_stale_guests(self, ttl_hours: int) -> int:
        """Drop guest cats nobody has touched in a while, so memory can't grow forever."""
        cutoff = now()
        removed = 0
        async with self._lock:
            for cat_id, cat in list(self._cats.items()):
                if not cat.is_guest:
                    continue
                idle_h = (cutoff - max(cat.last_fed, cat.last_played, cat.last_walk)).total_seconds() / 3600
                if idle_h > ttl_hours:
                    self._cats.pop(cat_id, None)
                    removed += 1
        return removed
