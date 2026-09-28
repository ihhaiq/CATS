"""Central configuration loaded from environment variables."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    storage_backend: str = os.getenv("STORAGE_BACKEND", "postgres").lower()
    database_url: str = os.getenv("DATABASE_URL", "")

    status_media_file_id: str = os.getenv("STATUS_MEDIA_FILE_ID", "")
    feed_media_file_id: str = os.getenv("FEED_MEDIA_FILE_ID", "")
    play_media_file_id: str = os.getenv("PLAY_MEDIA_FILE_ID", "")
    walk_media_file_id: str = os.getenv("WALK_MEDIA_FILE_ID", "")
    talk_media_file_id: str = os.getenv("TALK_MEDIA_FILE_ID", "")
    sleep_media_file_id: str = os.getenv("SLEEP_MEDIA_FILE_ID", "")
    cat_angry_sleep_media_file_id: str = os.getenv(
        "CAT_ANGRY_SLEEP_MEDIA_FILE_ID",
        "",
    )
    media_cache_chat_id: int = int(os.getenv("MEDIA_CACHE_CHAT_ID", "0") or 0)

    webhook_base_url: str = os.getenv("WEBHOOK_BASE_URL", "")
    webhook_path: str = os.getenv("WEBHOOK_PATH", "/webhook")
    asset_base_url: str = os.getenv("ASSET_BASE_URL", "").strip()
    railway_public_domain: str = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    port: int = int(os.getenv("PORT", "8080"))
    admin_ids: list[int] | None = None

    @property
    def public_asset_base_url(self) -> str:
        """Public HTTPS origin used by Telegram to fetch cat preview images."""
        explicit = self.asset_base_url.rstrip("/")
        if explicit:
            return explicit

        webhook = self.webhook_base_url.rstrip("/")
        if webhook:
            return webhook

        domain = self.railway_public_domain.strip().strip("/")
        if not domain:
            return ""
        if domain.startswith(("http://", "https://")):
            return domain.rstrip("/")
        return f"https://{domain}"

    feed_cooldown: int = 15 * 60
    treat_cooldown: int = 30 * 60
    play_cooldown: int = 15 * 60
    toy_cooldown: int = 15 * 60
    walk_cooldown: int = 4 * 60 * 60
    talk_cooldown: int = 10 * 60
    relax_cooldown: int = 20 * 60

    sleep_decay_interval_minutes: int = max(
        1,
        int(os.getenv("SLEEP_DECAY_INTERVAL_MINUTES", "5")),
    )
    sleep_decay_amount: int = max(
        1,
        int(os.getenv("SLEEP_DECAY_AMOUNT", "1")),
    )

    hunger_alert_threshold: int = 70
    happiness_alert_threshold: int = 30
    notification_min_gap: int = 6 * 60 * 60
    notification_interval_minutes: int = max(
        1,
        int(os.getenv("NOTIFICATION_INTERVAL_MINUTES", "15")),
    )
    wake_check_interval_minutes: int = max(
        1,
        int(os.getenv("WAKE_CHECK_INTERVAL_MINUTES", "1")),
    )


settings = Settings()
settings.admin_ids = [
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
]


def validate_settings() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is missing.")
    if settings.storage_backend != "postgres":
        raise RuntimeError(
            "Catibot requires STORAGE_BACKEND=postgres; JSON storage was removed."
        )
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is required because PostgreSQL is the only storage backend."
        )
