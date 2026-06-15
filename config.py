"""
config.py — Central configuration for Yene Lottery Bot
Loads all settings from the .env file.
"""

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _parse_ids(raw: str) -> List[int]:
    """Parse comma-separated integer IDs."""
    return [int(x.strip()) for x in raw.split(",") if x.strip() and x.strip().isdigit()]

def _parse_strs(raw: str) -> List[str]:
    """Parse comma-separated strings."""
    return [x.strip().replace("@", "") for x in raw.split(",") if x.strip()]


@dataclass
class Config:
    # ── Bot ─────────────────────────────────────
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))

    # ── Group targets ────────────────────────────
    admin_group_id: int = field(
        default_factory=lambda: int(os.getenv("ADMIN_GROUP_ID", "0"))
    )
    public_group_id: int = field(
        default_factory=lambda: int(os.getenv("PUBLIC_GROUP_ID", "0"))
    )

    # ── Admins ───────────────────────────────────
    super_admin_ids: List[int] = field(
        default_factory=lambda: _parse_ids(os.getenv("SUPER_ADMIN_IDS", ""))
    )
    super_admin_usernames: List[str] = field(
        default_factory=lambda: _parse_strs(os.getenv("SUPER_ADMIN_USERNAMES", ""))
    )

    # ── Database ─────────────────────────────────
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:password@localhost:5432/yene_lottery",
        )
    )

    # ── Misc ─────────────────────────────────────
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "False").lower() == "true"
    )


# Singleton instance — import this everywhere
cfg = Config()
