"""
utils/helpers.py — Shared utility functions (formatting, guards, text).
"""

import html
from datetime import datetime, timezone
from typing import Optional
from config import cfg


# ─────────────────────────────────────────────────────────────────────────────
#  Admin Guard
# ─────────────────────────────────────────────────────────────────────────────

def is_admin(tg_id: int, username: Optional[str] = None) -> bool:
    """Check if a Telegram user ID or username belongs to a super admin."""
    if tg_id in cfg.super_admin_ids:
        return True
    if username is not None and username.lower() in [u.lower() for u in cfg.super_admin_usernames]:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  Text / Formatting
# ─────────────────────────────────────────────────────────────────────────────

def esc(text: str) -> str:
    """HTML-escape a string for safe Telegram HTML messages."""
    return html.escape(str(text))


def format_lottery(lot: dict, idx: int = 0) -> str:
    """
    Format a lottery record into a readable Telegram HTML message block.
    """
    slots_filled = lot.get("verified_count") or 0
    slots_left   = lot["max_slots"] - slots_filled
    pct          = int((slots_filled / lot["max_slots"]) * 100) if lot["max_slots"] else 0
    bar_filled   = "█" * (pct // 10)
    bar_empty    = "░" * (10 - (pct // 10))

    draw_info = ""
    if lot.get("draw_date"):
        draw_info = f"\n📅 <b>Draw Date:</b> {format_dt(lot['draw_date'])}"

    return (
        f"{'─' * 30}\n"
        f"🎱 <b>{esc(lot['title'])}</b>\n"
        f"💬 {esc(lot.get('description') or 'No description.')}\n\n"
        f"💰 <b>Prize:</b> {esc(lot['prize_pool'])}\n"
        f"🎫 <b>Ticket Price:</b> {lot['price_per_ticket']:,.2f} ETB\n"
        f"👥 <b>Slots:</b> {slots_filled}/{lot['max_slots']} filled\n"
        f"📊 [{bar_filled}{bar_empty}] {pct}%\n"
        f"🟢 <b>Slots Left:</b> {slots_left}"
        f"{draw_info}"
    )


def format_ticket(ticket: dict) -> str:
    """Format a single ticket for /mytickets display."""
    status_emoji = {
        "pending":  "⏳",
        "verified": "✅",
        "rejected": "❌",
    }.get(ticket["status"], "❓")

    return (
        f"🎟️ <b>Ticket #{ticket['ticket_no']:03d}</b>\n"
        f"   Lottery: {esc(ticket['title'])}\n"
        f"   Prize: {esc(ticket['prize_pool'])}\n"
        f"   Status: {status_emoji} {ticket['status'].capitalize()}\n"
        f"   Issued: {format_dt(ticket['issued_at'])}"
    )


def format_dt(dt) -> str:
    """Format a datetime to a friendly Addis Ababa readable string."""
    if dt is None:
        return "TBD"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return dt
            
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d %b %Y at %H:%M UTC")


def progress_bar(current: int, maximum: int, width: int = 10) -> str:
    """ASCII progress bar."""
    if maximum == 0:
        return "░" * width
    filled = int(width * current / maximum)
    return "█" * filled + "░" * (width - filled)


# ─────────────────────────────────────────────────────────────────────────────
#  Ticket Number Formatting
# ─────────────────────────────────────────────────────────────────────────────

def fmt_ticket_no(n: int) -> str:
    """Format ticket number as zero-padded 3-digit string."""
    return f"{n:03d}"
