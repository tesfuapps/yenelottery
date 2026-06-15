"""
utils/automation.py — Automation logic for Yene Lottery.
Handles auto-draws and recurring lottery spawning.
"""

import asyncio
import logging
from aiogram import Bot
from aiogram.types import BufferedInputFile

from config import cfg
import database.queries as db
from utils.draw import provably_fair_draw
from utils.poster import generate_winner_poster
from utils.helpers import esc

logger = logging.getLogger(__name__)

async def auto_execute_draw(bot: Bot, lottery_id: int):
    """
    Automated version of a lottery draw.
    Used when a draw_date is reached by the scheduler.
    """
    lottery = await db.get_lottery(lottery_id)
    if not lottery or not lottery["is_active"]:
        return

    entries = await db.get_verified_tickets_for_draw(lottery_id)
    if not entries:
        logger.info(f"⏳ Auto-draw for {lottery_id} skipped: No entries.")
        # Optionally extend the date or alert admin
        return

    # 1. Perform draw
    result = provably_fair_draw(list(entries))
    if not result:
        return

    # 2. Update DB
    await db.set_lottery_winner(lottery_id, result.winner_tg_id, result.winner_ticket)
    await db.record_draw(
        lottery_id=lottery_id,
        winner_tg_id=result.winner_tg_id,
        winner_ticket=result.winner_ticket,
        draw_seed=result.draw_seed,
        total_entries=result.total_entries,
    )

    # 3. Generate Poster
    poster_buf = generate_winner_poster(
        lottery_title  = lottery["title"],
        winner_name    = result.winner_name,
        winner_ticket  = result.winner_ticket,
        prize_pool     = lottery["prize_pool"],
        total_entries  = result.total_entries,
        draw_seed_short= result.draw_seed[:12],
    )
    poster_file = BufferedInputFile(file=poster_buf.read(), filename="winner.png")

    # 4. Broadcast to Public Group
    announcement = (
        f"🏆 <b>YENE LOTTERY — AUTO DRAW!</b>\n\n"
        f"🎱 <b>Lottery:</b> {esc(lottery['title'])}\n"
        f"🎫 <b>Winning Ticket:</b> #{result.winner_ticket:03d}\n"
        f"🏆 <b>Winner:</b> {esc(result.winner_name)}\n"
        f"🏅 <b>Prize:</b> {esc(lottery['prize_pool'])}\n\n"
        f"<i>🔑 Seed: <code>{result.draw_seed[:18]}...</code></i>\n"
    )

    try:
        await bot.send_photo(
            chat_id=cfg.public_group_id,
            photo=poster_file,
            caption=announcement,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Auto-draw broadcast failed: {e}")

    # 5. Notify Winner
    try:
        await bot.send_message(
            chat_id=result.winner_tg_id,
            text=f"🎁 <b>YOU WON!</b>\n\nYou won the <b>{esc(lottery['title'])}</b> lottery!\nTicket #{result.winner_ticket:03d}. Info sent to public channel.",
            parse_mode="HTML"
        )
    except Exception:
        pass

async def spawn_from_templates(bot: Bot):
    """
    Check enabled templates and create new lotteries if needed.
    (Self-healing: if no active lottery exists for a template, spawn it).
    """
    templates = await db.get_enabled_templates()
    active_lots = await db.get_active_lotteries()
    active_titles = {l["title"] for l in active_lots}

    for t in templates:
        if t["title"] not in active_titles:
            logger.info(f"🔄 Spawning recurring lottery from template: {t['title']}")
            
            # Create new lottery
            # Default draw date: 24h from now for daily
            from datetime import datetime, timedelta
            draw_date = None
            if t["frequency"] == "daily":
                draw_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            elif t["frequency"] == "weekly":
                draw_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

            new_lot = await db.create_lottery(
                title=t["title"],
                description=t["description"],
                price_per_ticket=t["price_per_ticket"],
                max_slots=t["max_slots"],
                prize_pool=t["prize_pool"],
                payment_info="See Admin for Bank/Telebirr info.", # Default or in template
                created_by=0, # System ID
                draw_date=draw_date
            )
            
            await db.update_template_spawn_time(t["id"])
            logger.info(f"✅ Spawned lottery ID: {new_lot['id']}")
