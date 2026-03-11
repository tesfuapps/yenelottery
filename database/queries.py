"""
database/queries.py — All async database operations for Yene Lottery (SQLite version).
"""

import aiosqlite
import logging
from typing import Optional
from database.connection import get_conn

logger = logging.getLogger(__name__)

async def upsert_user(tg_id: int, full_name: str, username: Optional[str] = None, referred_by: Optional[int] = None):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        
        # Check if user exists first to avoid overwriting referred_by
        cursor = await conn.execute("SELECT referred_by FROM users WHERE tg_id = ?", (tg_id,))
        existing = await cursor.fetchone()
        
        if existing:
            # Update existing user
            cursor = await conn.execute(
                """
                UPDATE users 
                SET full_name = ?, username = ?
                WHERE tg_id = ?
                RETURNING *
                """,
                (full_name, username, tg_id),
            )
        else:
            # Create new user with optional referred_by
            # Ensure referred_by is a valid existing user and not self
            ref_id = referred_by if referred_by and referred_by != tg_id else None
            
            cursor = await conn.execute(
                """
                INSERT INTO users (tg_id, full_name, username, referred_by)
                VALUES (?, ?, ?, ?)
                RETURNING *
                """,
                (tg_id, full_name, username, ref_id),
            )
        
        row = await cursor.fetchone()
        await conn.commit()
        return dict(row)

async def award_referral_points(tg_id: int, points: int = 1):
    """Award points to a user for a successful referral."""
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE users SET referral_points = referral_points + ? WHERE tg_id = ?",
            (points, tg_id),
        )
        await conn.commit()

async def get_referral_count(tg_id: int):
    """Count how many people this user has referred."""
    async with get_conn() as conn:
        cursor = await conn.execute("SELECT COUNT(*) as count FROM users WHERE referred_by = ?", (tg_id,))
        row = await cursor.fetchone()
        return row[0]

async def get_user(tg_id: int):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_all_registered_users():
    """Retrieve all users who have accepted terms for notifications."""
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT tg_id FROM users WHERE terms_accepted = 1")
        rows = await cursor.fetchall()
        return [r['tg_id'] for r in rows]

async def update_user_phone(tg_id: int, phone: str) -> None:
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("UPDATE users SET phone = ? WHERE tg_id = ?", (phone, tg_id))
        await conn.commit()

async def accept_terms(tg_id: int) -> None:
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("UPDATE users SET terms_accepted = 1 WHERE tg_id = ?", (tg_id,))
        await conn.commit()

async def get_active_lotteries():
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT l.*,
                   (SELECT COUNT(id) FROM tickets t WHERE t.lottery_id = l.id AND t.status = 'verified') AS verified_count
            FROM   lotteries l
            WHERE  l.is_active = 1
            ORDER BY l.created_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_lottery(lottery_id: int):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT l.*,
                   (SELECT COUNT(id) FROM tickets t WHERE t.lottery_id = l.id AND t.status = 'verified') AS verified_count
            FROM   lotteries l
            WHERE  l.id = ?
            """,
            (lottery_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

async def create_lottery(title, description, price_per_ticket, max_slots, prize_pool, payment_info, created_by, draw_date=None):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            INSERT INTO lotteries
                (title, description, price_per_ticket, max_slots, prize_pool, payment_info, created_by, draw_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING *
            """,
            (title, description, price_per_ticket, max_slots, prize_pool, payment_info, created_by, draw_date),
        )
        row = await cursor.fetchone()
        await conn.commit()
        return dict(row)

async def deactivate_lottery(lottery_id: int) -> None:
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("UPDATE lotteries SET is_active = 0 WHERE id = ?", (lottery_id,))
        await conn.commit()

async def set_lottery_winner(lottery_id: int, winner_tg_id: int, winner_ticket: int) -> None:
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            "UPDATE lotteries SET is_active = 0, winner_tg_id = ?, winner_ticket = ? WHERE id = ?",
            (winner_tg_id, winner_ticket, lottery_id),
        )
        await conn.commit()

async def get_lottery_history(limit: int = 10):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT dh.*, l.title, l.prize_pool,
                   u.full_name AS winner_name, u.username AS winner_username
            FROM   draw_history dh
            JOIN   lotteries l ON l.id = dh.lottery_id
            JOIN   users u ON u.tg_id = dh.winner_tg_id
            ORDER BY dh.drawn_at DESC
            LIMIT  ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def next_ticket_number(lottery_id: int) -> int:
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT COALESCE(MAX(ticket_no), 0) + 1 AS next_n FROM tickets WHERE lottery_id = ?",
            (lottery_id,),
        )
        row = await cursor.fetchone()
        return row["next_n"] if row else 1

async def create_ticket(lottery_id: int, holder_tg_id: int):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        ticket_no = await next_ticket_number(lottery_id)
        cursor = await conn.execute(
            "INSERT INTO tickets (ticket_no, lottery_id, holder_tg_id, status) VALUES (?, ?, ?, 'pending') RETURNING *",
            (ticket_no, lottery_id, holder_tg_id),
        )
        row = await cursor.fetchone()
        await conn.commit()
        return dict(row)

async def get_ticket(ticket_id: int):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def update_ticket_status(ticket_id: int, status: str):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "UPDATE tickets SET status = ? WHERE id = ? RETURNING *",
            (status, ticket_id),
        )
        row = await cursor.fetchone()
        await conn.commit()
        return dict(row) if row else None

async def get_user_tickets(tg_id: int):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT t.*, l.title, l.prize_pool
            FROM   tickets t
            JOIN   lotteries l ON l.id = t.lottery_id
            WHERE  t.holder_tg_id = ?
            ORDER BY t.issued_at DESC
            """,
            (tg_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_verified_tickets_for_draw(lottery_id: int):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT t.ticket_no, t.holder_tg_id, u.full_name
            FROM   tickets t
            JOIN   users u ON u.tg_id = t.holder_tg_id
            WHERE  t.lottery_id = ? AND t.status = 'verified'
            ORDER BY t.ticket_no
            """,
            (lottery_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def create_transaction(ticket_id: int, lottery_id: int, holder_tg_id: int, file_id: str, transaction_ref: str, amount: Optional[float] = None):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            INSERT INTO transactions (ticket_id, lottery_id, holder_tg_id, file_id, transaction_ref, amount)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING *
            """,
            (ticket_id, lottery_id, holder_tg_id, file_id, transaction_ref, amount),
        )
        row = await cursor.fetchone()
        await conn.commit()
        return dict(row)

async def get_transaction_by_ticket(ticket_id: int):
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM transactions WHERE ticket_id = ? ORDER BY submitted_at DESC LIMIT 1",
            (ticket_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

async def approve_transaction(ticket_id: int, reviewed_by: int) -> None:
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            "UPDATE transactions SET status = 'approved', reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP WHERE ticket_id = ?",
            (reviewed_by, ticket_id),
        )
        await conn.commit()

async def reject_transaction(ticket_id: int, reviewed_by: int, note: str = "") -> None:
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            "UPDATE transactions SET status = 'rejected', reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP, admin_note = ? WHERE ticket_id = ?",
            (reviewed_by, ticket_id, note),
        )
        await conn.commit()

async def record_draw(lottery_id: int, winner_tg_id: int, winner_ticket: int, draw_seed: str, total_entries: int) -> None:
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            """
            INSERT INTO draw_history (lottery_id, winner_tg_id, winner_ticket, draw_seed, total_entries)
            VALUES (?, ?, ?, ?, ?)
            """,
            (lottery_id, winner_tg_id, winner_ticket, draw_seed, total_entries),
        )
        await conn.commit()

async def get_user_stats(tg_id: int):
    """Fetch count of total tickets and currently active verified tickets."""
    async with get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT 
                (SELECT COUNT(*) FROM tickets WHERE holder_tg_id = ?) as total_tickets,
                (SELECT COUNT(*) FROM tickets t 
                 JOIN lotteries l ON t.lottery_id = l.id 
                 WHERE t.holder_tg_id = ? AND t.status = 'verified' AND l.is_active = 1) as active_tickets
            """,
            (tg_id, tg_id),
        )
        row = await cursor.fetchone()
        return dict(row)
