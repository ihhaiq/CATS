"""
Central configuration, loaded from environment variables (.env).
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _default_json_data_file() -> str:
    configured = os.getenv("JSON_DATA_FILE", "").strip()
    volume_mount = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    if volume_mount and (not configured or configured == "data/catibot.json"):
        return os.path.join(volume_mount, "catibot.json")
    return configured or "data/catibot.json"


@dataclass
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    storage_backend: str = os.getenv("STORAGE_BACKEND", "json").lower()
    database_url: str = os.getenv("DATABASE_URL", "")
    json_data_file: str = _default_json_data_file()
    status_media_file_id: str = os.getenv("STATUS_MEDIA_FILE_ID", "")
    feed_media_file_id: str = os.getenv("FEED_MEDIA_FILE_ID", "")
    play_media_file_id: str = os.getenv("PLAY_MEDIA_FILE_ID", "")
    walk_media_file_id: str = os.getenv("WALK_MEDIA_FILE_ID", "")
    talk_media_file_id: str = os.getenv("TALK_MEDIA_FILE_ID", "")
    sleep_media_file_id: str = os.getenv("SLEEP_MEDIA_FILE_ID", "")
    cat_angry_sleep_media_file_id: str = os.getenv("CAT_ANGRY_SLEEP_MEDIA_FILE_ID", "")
    media_cache_chat_id: int = int(os.getenv("MEDIA_CACHE_CHAT_ID", "0") or 0)
    webhook_base_url: str = os.getenv("WEBHOOK_BASE_URL", "")
    webhook_path: str = os.getenv("WEBHOOK_PATH", "/webhook")
    port: int = int(os.getenv("PORT", "8080"))
    admin_ids: list[int] = None

    # Cooldowns (seconds)
    feed_cooldown: int = 15 * 60
    play_cooldown: int = 15 * 60
    toy_cooldown: int = 15 * 60
    walk_cooldown: int = 4 * 60 * 60
    talk_cooldown: int = 10 * 60
    relax_cooldown: int = 20 * 60

    # Rest/sleep: while awake the visible rest meter drops in discrete steps.
    sleep_decay_interval_minutes: int = max(1, int(os.getenv("SLEEP_DECAY_INTERVAL_MINUTES", "5")))
    sleep_decay_amount: int = max(1, int(os.getenv("SLEEP_DECAY_AMOUNT", "1")))

    # Notification thresholds
    hunger_alert_threshold: int = 70
    happiness_alert_threshold: int = 30
    notification_min_gap: int = 6 * 60 * 60
    notification_interval_minutes: int = max(
        1, int(os.getenv("NOTIFICATION_INTERVAL_MINUTES", "15"))
    )
    wake_check_interval_minutes: int = max(
        1, int(os.getenv("WAKE_CHECK_INTERVAL_MINUTES", "1"))
    )


settings = Settings()
settings.admin_ids = [
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
]


def validate_settings() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is missing. Copy .env.example to .env and set it.")
    if settings.storage_backend not in {"json", "postgres"}:
        raise RuntimeError("STORAGE_BACKEND must be either 'json' or 'postgres'.")
    if settings.storage_backend == "postgres" and not settings.database_url:
        raise RuntimeError("DATABASE_URL is required when STORAGE_BACKEND=postgres.")
