"""PostgreSQL bootstrap and one-time legacy JSON migration."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings
from bot.database.models import Base, RuntimeState, default_runtime_state

logger = logging.getLogger("catibot.database")

engine = None
async_session: async_sessionmaker[AsyncSession] | None = None


def _database_url() -> str:
    url = settings.database_url.strip()
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _legacy_json_candidates() -> list[Path]:
    candidates: list[Path] = []

    configured = os.getenv("JSON_DATA_FILE", "").strip()
    if configured:
        candidates.append(Path(configured))

    volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    if volume:
        candidates.append(Path(volume) / "catibot.json")

    candidates.append(
        Path(__file__).resolve().parents[2] / "data" / "catibot.json"
    )

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        resolved = str(path.expanduser().resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(Path(resolved))
    return unique


def _state_has_data(data: dict | None) -> bool:
    if not isinstance(data, dict):
        return False
    return any(
        bool(data.get(key))
        for key in (
            "users",
            "cats",
            "items",
            "user_inventory",
            "points_log",
            "media",
            "media_types",
            "media_cache",
            "media_overrides",
        )
    )


def _normalize_legacy_state(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("legacy Catibot state must be a JSON object")

    normalized = default_runtime_state()
    for key in normalized:
        value = data.get(key)
        if value is not None:
            normalized[key] = value
    return normalized


def _remove_legacy_files(paths: list[Path]) -> None:
    for path in paths:
        for candidate in (path, path.with_name(path.name + ".bak")):
            try:
                if candidate.exists():
                    candidate.unlink()
                    logger.info("Removed legacy JSON state file: %s", candidate)
            except OSError:
                logger.warning(
                    "PostgreSQL is authoritative, but legacy JSON file could not be removed: %s",
                    candidate,
                )


async def _migrate_legacy_json() -> None:
    candidates = _legacy_json_candidates()
    existing = [path for path in candidates if path.is_file()]
    cleanup_after_commit = False

    async with get_session() as session:
        async with session.begin():
            row = await session.get(RuntimeState, 1, with_for_update=True)
            if row is None:
                row = RuntimeState(id=1, data=default_runtime_state())
                session.add(row)
                await session.flush()

            if _state_has_data(row.data):
                cleanup_after_commit = bool(existing)
            elif existing:
                errors: list[str] = []
                migrated = False

                for path in existing:
                    try:
                        raw = json.loads(path.read_text(encoding="utf-8"))
                        row.data = _normalize_legacy_state(raw)
                        row.updated_at = datetime.utcnow()
                        migrated = True
                        cleanup_after_commit = True
                        logger.info(
                            "Migrated legacy Catibot JSON state into PostgreSQL from %s",
                            path,
                        )
                        break
                    except (OSError, json.JSONDecodeError, ValueError) as exc:
                        errors.append(f"{path}: {exc}")
                        logger.warning(
                            "Legacy JSON candidate could not be imported: %s (%s)",
                            path,
                            exc,
                        )

                if not migrated:
                    raise RuntimeError(
                        "Legacy JSON state files exist but none could be migrated; "
                        "startup stopped to prevent data loss. "
                        + " | ".join(errors)
                    )

    if cleanup_after_commit:
        _remove_legacy_files(existing)


async def init_db() -> None:
    global engine, async_session

    if async_session is not None:
        return

    engine = create_async_engine(
        _database_url(),
        echo=False,
        pool_pre_ping=True,
    )
    async_session = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        async with session.begin():
            row = await session.get(RuntimeState, 1)
            if row is None:
                session.add(
                    RuntimeState(
                        id=1,
                        data=default_runtime_state(),
                    )
                )

    await _migrate_legacy_json()
    logger.info("PostgreSQL runtime state initialized")


def get_session() -> AsyncSession:
    if async_session is None:
        raise RuntimeError(
            "PostgreSQL is not initialized. init_db() must run before storage access."
        )
    return async_session()


async def close_db() -> None:
    global engine, async_session
    if engine is not None:
        await engine.dispose()
    engine = None
    async_session = None
