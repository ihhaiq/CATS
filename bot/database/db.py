"""Storage initialization for local JSON mode and future PostgreSQL mode."""
import json
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings
from bot.database.models import Base

logger = logging.getLogger("catibot.database")

engine = None
async_session = None


def _json_path() -> Path:
    path = Path(settings.json_data_file)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path


def _init_json_store() -> None:
    path = _json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            json.dumps(
                {
                    "users": {},
                    "cats": [],
                    "items": [],
                    "user_inventory": [],
                    "points_log": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


if settings.storage_backend == "postgres":
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required when STORAGE_BACKEND=postgres")
    database_url = settings.database_url
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    if settings.storage_backend == "json":
        _init_json_store()
        return

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        logger.warning("PostgreSQL unavailable (%s); falling back to JSON storage", exc)
        settings.storage_backend = "json"
        _init_json_store()


def get_session() -> AsyncSession:
    if async_session is None:
        raise RuntimeError("SQL sessions are unavailable while STORAGE_BACKEND=json")
    return async_session()
