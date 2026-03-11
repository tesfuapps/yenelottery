"""
handlers/user.py — User registration, /start, main menu, /mytickets, /history.
Phase 1: The "Identity" Phase — user profile setup with FSMContext.
"""

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from database import queries as db
from keyboards.inline import (
    main_menu_keyboard,
    admin_menu_keyboard,
    terms_keyboard,
    share_phone_keyboard,
)
from states.forms import Registration
from utils.helpers import is_admin, esc, format_ticket, format_dt

logger = logging.getLogger(__name__)
router = Router(name="user")


# ─────────────────────────────────────────────────────────────────────────────
#  /start — Entry Point
# ─────────────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot) -> None:
    """
    Welcome new users and returning users.
    Handles referral deep links (e.g., /start ref12345).
    """
    await state.clear()
    
    # Check for referral in args
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referred_by = int(args[1].replace("ref", ""))
        except ValueError:
            pass

    tg_id     = message.from_user.id
    full_name = message.from_user.full_name
    username  = message.from_user.username
    
    # Check if user is new
    existing_user = await db.get_user(tg_id)
    
    # Upsert user record with referral info if new
    user = await db.upsert_user(tg_id, full_name, username, referred_by=referred_by)

    if not existing_user:
        # 🔔 Notify Admin about a new user starting the bot
        try:
            await bot.send_message(
                chat_id=cfg.admin_group_id,
                text=(
                    f"👤 <b>New User Started Bot</b>\n\n"
                    f"📛 Name: {esc(full_name)}\n"
                    f"🔖 Username: @{esc(username or 'N/A')}\n"
                    f"🆔 ID: <code>{tg_id}</code>\n"
                    f"⏱ Status: <i>Landing Page / Terms</i>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Admin notif failed for new user {tg_id}: {e}")

    if not user["terms_accepted"]:
        # New or unaccepted-terms user → show welcome + terms
        await message.answer(
            f"🎱 <b>Welcome to Yene Lottery!</b>\n\n"
            f"Hello, <b>{esc(full_name)}</b>! 👋\n\n"
            f"Yene Lottery is an automated, transparent, and provably fair "
            f"lottery platform operating on Telegram.\n\n"
            f"📜 <b>Terms & Conditions</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"• You must be 18 years or older to participate.\n"
            f"• All payments are manual (bank transfer/Telebirr).\n"
            f"• The draw is provably fair using cryptographic methods.\n"
            f"• The operator complies with Ethiopian Lottery Service (ELS) regulations.\n"
            f"• By participating, you accept all terms and conditions.\n\n"
            f"Do you accept the Terms & Conditions?",
            parse_mode="HTML",
            reply_markup=terms_keyboard(),
        )
    else:
        # Returning registered user
        kb = admin_menu_keyboard() if is_admin(tg_id, username) else main_menu_keyboard()
        await message.answer(
            f"👋 <b>Welcome back, {esc(full_name)}!</b>\n\n"
            f"What would you like to do today?",
            parse_mode="HTML",
            reply_markup=kb,
        )


@router.callback_query(F.data == "accept_terms")
async def cb_accept_terms(callback: CallbackQuery, state: FSMContext) -> None:
    """User accepts terms → begin phone registration."""
    await db.accept_terms(callback.from_user.id)
    await state.set_state(Registration.waiting_for_phone)
    await callback.message.edit_text(
        "✅ <b>Terms Accepted!</b>\n\n"
        "To complete your registration, please share your <b>phone number</b>.\n"
        "This helps us contact you if you win! 🏆",
        parse_mode="HTML",
    )
    await callback.message.answer(
        "👇 Tap the button below to share your phone number:",
        reply_markup=share_phone_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "decline_terms")
async def cb_decline_terms(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "😔 You have declined the Terms & Conditions.\n\n"
        "You cannot participate in Yene Lottery without accepting them.\n"
        "Use /start at any time to try again."
    )
    await callback.answer()


@router.message(Registration.waiting_for_phone, F.contact)
async def process_phone(message: Message, state: FSMContext, bot: Bot) -> None:
    """Receive shared contact/phone number."""
    phone = message.contact.phone_number
    await db.update_user_phone(message.from_user.id, phone)
    await state.clear()

    tg_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    # 🔔 Notify Admin about registration completion
    try:
        await bot.send_message(
            chat_id=cfg.admin_group_id,
            text=(
                f"✅ <b>Registration Completed</b>\n\n"
                f"👤 User: {esc(full_name)}\n"
                f"🔖 Username: @{esc(username or 'N/A')}\n"
                f"📱 Phone: <code>{phone}</code>\n"
                f"🆔 ID: <code>{tg_id}</code>"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Admin notif failed for reg completion {tg_id}: {e}")
    kb = admin_menu_keyboard() if is_admin(tg_id, username) else main_menu_keyboard()

    await message.answer(
        f"🎉 <b>Registration Complete!</b>\n\n"
        f"Welcome to Yene Lottery, <b>{esc(message.from_user.full_name)}</b>!\n"
        f"📱 Phone: <code>{phone}</code> saved.\n\n"
        f"You're all set to join lotteries. Good luck! 🍀",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "🏠 <b>Main Menu</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.message(Registration.waiting_for_phone)
async def process_phone_invalid(message: Message) -> None:
    await message.answer(
        "📱 Please use the button below to <b>share your phone number</b>.",
        parse_mode="HTML",
        reply_markup=share_phone_keyboard(),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Main Menu Navigation
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_profile")
async def cb_my_profile(callback: CallbackQuery) -> None:
    """Show the user's profile information and statistics."""
    tg_id = callback.from_user.id
    user = await db.get_user(tg_id)
    stats = await db.get_user_stats(tg_id)
    
    if not user:
        await callback.answer("⚠️ User not found.", show_alert=True)
        return

    profile_text = (
        f"👤 <b>Your Profile</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📛 <b>Name:</b> {esc(user['full_name'])}\n"
        f"🔖 <b>Username:</b> @{esc(user['username'] or 'N/A')}\n"
        f"🆔 <b>User ID:</b> <code>{tg_id}</code>\n"
        f"📱 <b>Phone:</b> {esc(user['phone'] or 'Not provided')}\n"
        f"📅 <b>Joined:</b> {format_dt(user['registered_at'])}\n\n"
        f"📊 <b>Statistics</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎟️ <b>Total Tickets:</b> {stats['total_tickets']}\n"
        f"🟢 <b>Active Entries:</b> {stats['active_tickets']}\n\n"
        f"🔗 <b>Referral System</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Friends Referred:</b> {await db.get_referral_count(tg_id)}\n"
        f"💎 <b>Referral Points:</b> {user.get('referral_points', 0)}\n\n"
        f"<i>Refer friends to earn points for free tickets!</i>"
    )

    from keyboards.inline import admin_menu_keyboard, main_menu_keyboard, profile_extra_keyboard
    base_kb = admin_menu_keyboard() if is_admin(tg_id, callback.from_user.username) else main_menu_keyboard()
    
    # Get the bot's username dynamically or from config for the ref link
    me = await callback.bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref{tg_id}"
    
    kb = profile_extra_keyboard(ref_link)
    # Merge keyboards or just use the extra one with a back button
    # For now, let's just use the profile_extra_keyboard which should have a back button
    
    await callback.message.edit_text(
        profile_text,
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    username = callback.from_user.username
    kb = admin_menu_keyboard() if is_admin(tg_id, username) else main_menu_keyboard()
    await callback.message.edit_text(
        "🏠 <b>Main Menu</b>\n\nWhat would you like to do?",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "ℹ️ <b>Yene Lottery — Help</b>\n\n"
        "🎫 <b>/start</b> — Open main menu\n"
        "🎟️ <b>/mytickets</b> — View your tickets\n"
        "📜 <b>/history</b> — View past draw winners\n"
        "💳 <b>/pay</b> — Submit payment for a lottery\n\n"
        "📞 <b>Support</b>\n"
        "Contact the operator for payment or prize questions.\n\n"
        "🔏 <b>Provably Fair</b>\n"
        "All draws use cryptographic randomness (Python secrets). "
        "The seed for each draw is public and verifiable.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
#  /mytickets
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("mytickets"))
@router.callback_query(F.data == "my_tickets")
async def show_my_tickets(update: Message | CallbackQuery) -> None:
    """Show the user all their tickets with current statuses."""
    if isinstance(update, CallbackQuery):
        tg_id = update.from_user.id
        respond = update.message.answer
        await update.answer()
    else:
        tg_id = update.from_user.id
        respond = update.answer

    tickets = await db.get_user_tickets(tg_id)
    if not tickets:
        text = (
            "🎟️ <b>My Tickets</b>\n\n"
            "You don't have any tickets yet.\n\n"
            "Join a lottery to get your first ticket!"
        )
    else:
        lines = ["🎟️ <b>My Tickets</b>\n"]
        for t in tickets:
            lines.append(format_ticket(dict(t)))
            lines.append("")
        text = "\n".join(lines)

    await respond(text, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
#  /history  — Public draw transparency
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("history"))
@router.callback_query(F.data == "draw_history")
async def show_history(update: Message | CallbackQuery) -> None:
    """Public command listing past draw winners."""
    if isinstance(update, CallbackQuery):
        respond = update.message.answer
        await update.answer()
    else:
        respond = update.answer

    history = await db.get_lottery_history(limit=10)
    if not history:
        text = (
            "📜 <b>Draw History</b>\n\n"
            "No draws have been completed yet.\n"
            "Be the first winner! 🏆"
        )
    else:
        lines = ["📜 <b>Draw History (Last 10 Draws)</b>\n"]
        for i, h in enumerate(history, 1):
            winner_display = (
                f"@{h['winner_username']}" if h["winner_username"]
                else esc(h["winner_name"])
            )
            lines.append(
                f"{i}. 🏆 <b>{esc(h['title'])}</b>\n"
                f"   Winner: {winner_display} — Ticket #{h['winner_ticket']:03d}\n"
                f"   Prize: {esc(h['prize_pool'])}\n"
                f"   Drawn: {format_dt(h['drawn_at'])}\n"
                f"   🔑 Seed: <code>{h['draw_seed'][:16]}...</code>\n"
            )
        text = "\n".join(lines)

    await respond(text, parse_mode="HTML")
