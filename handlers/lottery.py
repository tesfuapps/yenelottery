"""
handlers/lottery.py — Lottery browsing and selection handler.
Handles: view_lotteries, lottery_detail, back_to_list, refresh_lotteries.
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command

from database import queries as db
from keyboards.inline import lottery_list_keyboard, lottery_detail_keyboard, main_menu_keyboard
from utils.helpers import esc, format_lottery

logger = logging.getLogger(__name__)
router = Router(name="lottery")


@router.message(Command("lotteries"))
@router.callback_query(F.data.in_({"view_lotteries", "refresh_lotteries", "back_to_list"}))
async def show_lotteries(update: Message | CallbackQuery) -> None:
    """Show all currently active lotteries."""
    is_cb = isinstance(update, CallbackQuery)

    lotteries = await db.get_active_lotteries()

    if not lotteries:
        text = (
            "🎰 <b>Active Lotteries</b>\n\n"
            "😔 There are no active lotteries right now.\n\n"
            "Check back later or follow our announcements channel!"
        )
        if is_cb:
            await update.message.edit_text(text, parse_mode="HTML", reply_markup=main_menu_keyboard())
            await update.answer()
        else:
            await update.answer(text, parse_mode="HTML")
        return

    text = f"🎰 <b>Active Lotteries ({len(lotteries)} available)</b>\n\nSelect a lottery for details:"
    if is_cb:
        await update.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=lottery_list_keyboard(lotteries),
        )
        await update.answer()
    else:
        await update.answer(
            text,
            parse_mode="HTML",
            reply_markup=lottery_list_keyboard(lotteries),
        )


@router.callback_query(F.data.startswith("lottery_detail:"))
async def show_lottery_detail(callback: CallbackQuery) -> None:
    """Show detailed info for a single lottery."""
    lottery_id = int(callback.data.split(":")[1])
    lottery    = await db.get_lottery(lottery_id)

    if not lottery or not lottery["is_active"]:
        await callback.answer("❌ This lottery is no longer active.", show_alert=True)
        return

    text = (
        f"🎱 <b>Lottery Details</b>\n\n"
        f"{format_lottery(dict(lottery))}\n\n"
        f"💳 <b>Payment Info:</b>\n<code>{esc(lottery['payment_info'] or 'Contact admin')}</code>\n\n"
        f"Ready to join? Tap <b>Join & Pay</b> to get your ticket!"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=lottery_detail_keyboard(lottery_id),
    )
    await callback.answer()
