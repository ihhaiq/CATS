"""
Central configuration, loaded from environment variables (.env).
TODO (see AGENT.md step 1): validate required vars raise clear errors on boot.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    storage_backend: str = os.getenv("STORAGE_BACKEND", "json").lower()
    database_url: str = os.getenv("DATABASE_URL", "")
    json_data_file: str = os.getenv("JSON_DATA_FILE", "data/catibot.json")
    status_media_file_id: str = os.getenv("STATUS_MEDIA_FILE_ID", "")
    feed_media_file_id: str = os.getenv("FEED_MEDIA_FILE_ID", "")
    play_media_file_id: str = os.getenv("PLAY_MEDIA_FILE_ID", "")
    walk_media_file_id: str = os.getenv("WALK_MEDIA_FILE_ID", "")
    talk_media_file_id: str = os.getenv("TALK_MEDIA_FILE_ID", "")
    sleep_media_file_id: str = os.getenv("SLEEP_MEDIA_FILE_ID", "")
    cat_angry_sleep_media_file_id: str = os.getenv("CAT_ANGRY_SLEEP_MEDIA_FILE_ID", "")
    webhook_base_url: str = os.getenv("WEBHOOK_BASE_URL", "")  # e.g. https://catibot.up.railway.app
    webhook_path: str = os.getenv("WEBHOOK_PATH", "/webhook")
    port: int = int(os.getenv("PORT", "8080"))
    admin_ids: list[int] = None

    # Cooldowns (seconds)
    feed_cooldown: int = int(os.getenv("FEED_COOLDOWN_SECONDS", str(15 * 60)))
    play_cooldown: int = int(os.getenv("PLAY_COOLDOWN_SECONDS", str(15 * 60)))
    walk_cooldown: int = int(os.getenv("WALK_COOLDOWN_SECONDS", str(4 * 60 * 60)))
    talk_cooldown: int = int(os.getenv("TALK_COOLDOWN_SECONDS", str(5 * 60)))

    # Sleep need: by default the visible meter drops 1 point every 5 minutes awake.
    sleep_need_drop_interval_minutes: int = int(os.getenv("SLEEP_NEED_DROP_INTERVAL_MINUTES", "5"))
    sleep_need_drop_per_interval: int = int(os.getenv("SLEEP_NEED_DROP_PER_INTERVAL", "1"))
    sleep_recovery_per_hour: int = int(os.getenv("SLEEP_RECOVERY_PER_HOUR", "30"))

    # Notification thresholds
    hunger_alert_threshold: int = 70
    happiness_alert_threshold: int = 30
    notification_min_gap: int = 6 * 60 * 60  # don't re-alert same state within 6h
    notification_interval_minutes: int = int(os.getenv("NOTIFICATION_INTERVAL_MINUTES", "15"))


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
