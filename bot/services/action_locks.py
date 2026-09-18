"""Per-user locks for JSON-backed read/modify/write flows."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass


@dataclass
class _Entry:
    lock: asyncio.Lock
    users: int = 0


_guard = asyncio.Lock()
_entries: dict[int, _Entry] = {}


@asynccontextmanager
async def user_action_lock(user_id: int):
    """Serialize one user's state mutations and release idle lock objects."""
    async with _guard:
        entry = _entries.get(user_id)
        if entry is None:
            entry = _Entry(lock=asyncio.Lock())
            _entries[user_id] = entry
        entry.users += 1

    try:
        async with entry.lock:
            yield
    finally:
        async with _guard:
            entry.users -= 1
            if entry.users == 0 and not entry.lock.locked():
                _entries.pop(user_id, None)
