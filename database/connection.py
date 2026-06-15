"""
database/connection.py — SQLite connection management using aiosqlite.
"""

import aiosqlite
import logging

logger = logging.getLogger(__name__)

DB_PATH = "yene_lottery.db"

def get_conn():
    """Return an async context manager for SQLite DB connection."""
    return aiosqlite.connect(DB_PATH)

async def close_pool() -> None:
    """No-op for SQLite since we don't hold a persistent pool."""
    logger.info("SQLite finished.")
