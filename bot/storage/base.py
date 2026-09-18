"""
The storage contract.

Handlers only ever talk to this interface, so guest mode and Postgres mode run
exactly the same code paths. Adding a third backend (SQLite, Redis) means
implementing this class and nothing else.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from bot.core.enums import Breed
from bot.domain.entities import CatData, ItemData, UserData

DEFAULT_ITEMS: list[ItemData] = [
    ItemData(1, "علبة تونة", 30, "hunger_down", 35, "🐟", "تنزّل الجوع بسرعة."),
    ItemData(2, "حليب دافئ", 20, "hunger_down", 20, "🥛", "وجبة خفيفة."),
    ItemData(3, "كرة صوف", 40, "happiness_up", 30, "🧶", "ترفع السعادة."),
    ItemData(4, "عشبة القطط", 60, "happiness_up", 50, "🌿", "سعادة قوية."),
    ItemData(5, "طوق ذهبي", 150, "love_up", 25, "📿", "هدية ترفع الحب."),
    ItemData(6, "لقب: ملك البيت", 300, "cosmetic_title", 0, "👑", "لقب دائم للقطة."),
]


class Repository(ABC):
    """Every method is async so the SQL implementation can await its session."""

    name: str = "base"

    # --- lifecycle --------------------------------------------------------
    @abstractmethod
    async def setup(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def health(self) -> dict: ...

    # --- users ------------------------------------------------------------
    @abstractmethod
    async def get_or_create_user(
        self, user_id: int, *, username: str | None = None, is_guest: bool = False
    ) -> UserData: ...

    @abstractmethod
    async def save_user(self, user: UserData) -> None: ...

    @abstractmethod
    async def add_points(self, user_id: int, delta: int, reason: str) -> int:
        """Returns the new balance. Must write the log row in the same transaction."""

    @abstractmethod
    async def points_history(self, user_id: int, limit: int = 10) -> list[tuple[int, str]]: ...

    # --- cats -------------------------------------------------------------
    @abstractmethod
    async def create_cat(
        self, *, owner_id: int, name: str, breed: Breed, is_guest: bool = False
    ) -> CatData: ...

    @abstractmethod
    async def get_cat(self, cat_id: int) -> CatData | None: ...

    @abstractmethod
    async def get_active_cat_for(self, user_id: int) -> CatData | None:
        """The user's living cat, whether they own it or co-own it."""

    @abstractmethod
    async def save_cat(self, cat: CatData) -> None: ...

    @abstractmethod
    async def delete_cat(self, cat_id: int) -> None: ...

    @abstractmethod
    async def iter_active_cats(self, batch: int = 200) -> AsyncIterator[CatData]:
        """Paginated so the sweep doesn't load the whole table at once."""

    @abstractmethod
    async def list_fled_cats(self, limit: int = 10) -> list[CatData]: ...

    # --- items ------------------------------------------------------------
    @abstractmethod
    async def list_items(self) -> list[ItemData]: ...

    @abstractmethod
    async def get_item(self, item_id: int) -> ItemData | None: ...

    @abstractmethod
    async def inventory(self, user_id: int) -> list[tuple[ItemData, int]]: ...

    @abstractmethod
    async def change_inventory(self, user_id: int, item_id: int, delta: int) -> int: ...

    # --- maintenance ------------------------------------------------------
    @abstractmethod
    async def reset_user(self, user_id: int) -> None:
        """Wipe one user's cat, points and bag. Used by /dev_reset."""

    @abstractmethod
    async def counts(self) -> dict[str, int]: ...
