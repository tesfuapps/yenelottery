"""
database/models.py — DDL for all tables in the Yene Lottery schema (SQLite version).
"""

import logging
from database.connection import get_conn

logger = logging.getLogger(__name__)

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    tg_id           INTEGER         PRIMARY KEY,
    username        TEXT,
    full_name       TEXT            NOT NULL,
    phone           TEXT,
    language        TEXT            DEFAULT 'am',
    is_banned       BOOLEAN         DEFAULT 0,
    terms_accepted  BOOLEAN         DEFAULT 0,
    referred_by     INTEGER,
    referral_points INTEGER         DEFAULT 0,
    registered_at   TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(referred_by) REFERENCES users(tg_id)
);
"""

CREATE_LOTTERIES = """
CREATE TABLE IF NOT EXISTS lotteries (
    id              INTEGER         PRIMARY KEY AUTOINCREMENT,
    title           TEXT            NOT NULL,
    description     TEXT,
    price_per_ticket REAL           NOT NULL,
    max_slots       INTEGER         NOT NULL,
    prize_pool      TEXT            NOT NULL,
    payment_info    TEXT,
    draw_date       TIMESTAMP,
    is_active       BOOLEAN         DEFAULT 1,
    winner_tg_id    INTEGER,
    winner_ticket   INTEGER,
    created_by      INTEGER         NOT NULL,
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_TICKETS = """
CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER         PRIMARY KEY AUTOINCREMENT,
    ticket_no       INTEGER         NOT NULL,
    lottery_id      INTEGER         NOT NULL,
    holder_tg_id    INTEGER         NOT NULL,
    status          TEXT            DEFAULT 'pending',
    issued_at       TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(lottery_id) REFERENCES lotteries(id) ON DELETE CASCADE,
    FOREIGN KEY(holder_tg_id) REFERENCES users(tg_id) ON DELETE CASCADE,
    UNIQUE(lottery_id, ticket_no)
);
"""

CREATE_TRANSACTIONS = """
CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER         PRIMARY KEY AUTOINCREMENT,
    ticket_id       INTEGER         NOT NULL,
    lottery_id      INTEGER         NOT NULL,
    holder_tg_id    INTEGER         NOT NULL,
    file_id         TEXT            NOT NULL,
    transaction_ref TEXT,
    amount          REAL,
    status          TEXT            DEFAULT 'under_review',
    admin_note      TEXT,
    reviewed_by     INTEGER,
    submitted_at    TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    reviewed_at     TIMESTAMP,
    FOREIGN KEY(ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
);
"""

CREATE_DRAW_HISTORY = """
CREATE TABLE IF NOT EXISTS draw_history (
    id              INTEGER         PRIMARY KEY AUTOINCREMENT,
    lottery_id      INTEGER         NOT NULL,
    winner_tg_id    INTEGER         NOT NULL,
    winner_ticket   INTEGER         NOT NULL,
    draw_seed       TEXT            NOT NULL,
    total_entries   INTEGER         NOT NULL,
    drawn_at        TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(lottery_id) REFERENCES lotteries(id)
);
"""

CREATE_LOTTERY_TEMPLATES = """
CREATE TABLE IF NOT EXISTS lottery_templates (
    id              INTEGER         PRIMARY KEY AUTOINCREMENT,
    title           TEXT            NOT NULL,
    description     TEXT,
    price_per_ticket REAL           NOT NULL,
    max_slots       INTEGER         NOT NULL,
    prize_pool      TEXT            NOT NULL,
    frequency       TEXT            DEFAULT 'daily', -- 'daily', 'weekly'
    is_enabled      BOOLEAN         DEFAULT 1,
    last_spawned_at TIMESTAMP,
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tickets_lottery ON tickets(lottery_id);",
    "CREATE INDEX IF NOT EXISTS idx_tickets_holder ON tickets(holder_tg_id);",
    "CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);",
    "CREATE INDEX IF NOT EXISTS idx_transactions_ticket ON transactions(ticket_id);",
    "CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);",
]

async def init_db() -> None:
    """Create all tables and indexes if they don't exist."""
    async with get_conn() as conn:
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute(CREATE_USERS)
        await conn.execute(CREATE_LOTTERIES)
        await conn.execute(CREATE_TICKETS)
        await conn.execute(CREATE_TRANSACTIONS)
        await conn.execute(CREATE_DRAW_HISTORY)
        await conn.execute(CREATE_LOTTERY_TEMPLATES)
        for idx in CREATE_INDEXES:
            await conn.execute(idx)
        try:
            await conn.execute("ALTER TABLE transactions ADD COLUMN transaction_ref TEXT;")
        except Exception:
            pass # Column already exists
            
        # Migration for Referrals
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER;")
            await conn.execute("ALTER TABLE users ADD COLUMN referral_points INTEGER DEFAULT 0;")
        except Exception:
            pass # Columns already exist
        await conn.commit()
    logger.info("✅ SQLite Database schema initialized.")
