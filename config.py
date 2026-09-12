"""
Configuration loader for Stone FFA Bot.
Loads secrets and settings from environment variables (.env).
Guild-specific runtime config can also be stored/overridden in the database.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_int(key: str, default: Optional[int] = None) -> Optional[int]:
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value.strip())
    except ValueError:
        raise ValueError(f"Environment variable {key} must be an integer, got: {value!r}")


def _get_str(key: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return value.strip()


@dataclass(frozen=True)
class Settings:
    """Immutable settings loaded from environment."""

    discord_token: str
    guild_id: Optional[int]
    log_channel_id: Optional[int]
    staff_role_id: Optional[int]
    admin_role_id: Optional[int]
    ticket_category_id: Optional[int]
    transcript_channel_id: Optional[int]
    max_tickets_per_user: int
    bot_activity: str
    database_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        token = _get_str("DISCORD_TOKEN")
        if not token:
            raise RuntimeError(
                "DISCORD_TOKEN is not set. Copy .env.example to .env and set your bot token."
            )

        db_path_str = _get_str("DATABASE_PATH", "data/stone_ffa.db") or "data/stone_ffa.db"
        db_path = Path(db_path_str)
        if not db_path.is_absolute():
            db_path = BASE_DIR / db_path

        return cls(
            discord_token=token,
            guild_id=_get_int("GUILD_ID"),
            log_channel_id=_get_int("LOG_CHANNEL_ID"),
            staff_role_id=_get_int("STAFF_ROLE_ID"),
            admin_role_id=_get_int("ADMIN_ROLE_ID"),
            ticket_category_id=_get_int("TICKET_CATEGORY_ID"),
            transcript_channel_id=_get_int("TRANSCRIPT_CHANNEL_ID"),
            max_tickets_per_user=_get_int("MAX_TICKETS_PER_USER", 1) or 1,
            bot_activity=_get_str("BOT_ACTIVITY", "Stone FFA | /help") or "Stone FFA | /help",
            database_path=db_path,
        )


# Global settings instance (loaded once at import / startup)
settings: Settings = Settings.from_env()
