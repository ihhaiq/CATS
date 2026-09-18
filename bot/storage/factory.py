"""
Picks a backend and — importantly — degrades instead of crashing.

If Postgres is configured but unreachable at boot, the bot starts in guest mode
and logs loudly rather than crash-looping on the host. A pet bot that answers
with temporary state beats a bot that answers nothing.
"""
from __future__ import annotations

import logging

from bot.config import Settings
from bot.storage.base import Repository
from bot.storage.memory import MemoryRepository

logger = logging.getLogger("catibot.storage")


async def build_repository(settings: Settings) -> tuple[Repository, bool]:
    """Returns (repository, degraded) — degraded=True means we fell back to guest."""
    if settings.is_guest_storage:
        repo = MemoryRepository()
        await repo.setup()
        logger.info("storage: guest (in-memory) — no DATABASE_URL configured")
        return repo, False

    try:
        from bot.storage.sql import SQLRepository  # imported lazily: needs asyncpg

        repo = SQLRepository(settings.database_url)
        await repo.setup()
        logger.info("storage: postgres")
        return repo, False
    except Exception as exc:
        logger.error("postgres unavailable (%s) — falling back to guest mode", exc)
        fallback = MemoryRepository()
        await fallback.setup()
        return fallback, True
