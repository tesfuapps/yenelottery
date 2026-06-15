"""
handlers/admin.py — The Admin Bridge Handler for Yene Lottery.

This module handles:
  ─ Real-time Approve / Reject of payment screenshots via inline buttons.
  ─ Admin panel navigation and lottery management commands.
  ─ Manual draw trigger and lottery cancellation.
  ─ Live PostgreSQL status updates with immediate user notification.

Flow:
  User submits screenshot → forwarded to admin group with [Approve][Reject] buttons
  Admin clicks Approve  → ticket status: 'pending' → 'verified' in DB
                        → user notified with unique ticket number
  Admin clicks Reject   → ticket status: 'rejected'
                        → admin prompted for reason
                        → user notified with rejection reason
"""

import logging
import asyncio
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery,
    Message,
    BufferedInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from config import cfg
from database import queries as db
from keyboards.inline import (
    admin_panel_keyboard,
    admin_lottery_actions,
    confirm_keyboard,
    manage_lotteries_keyboard,
    admin_review_keyboard,
    broadcast_cta_keyboard,
)
from states.forms import AdminCreateLottery, AdminRejectReason, AdminBroadcast
from utils.helpers import is_admin, esc, format_lottery, fmt_ticket_no
from utils.draw import provably_fair_draw
from utils.poster import generate_winner_poster

logger = logging.getLogger(__name__)
router = Router(name="admin")


# ─────────────────────────────────────────────────────────────────────────────
#  GUARD: Middleware-style admin check
# ─────────────────────────────────────────────────────────────────────────────

async def _require_admin(entity: Message | CallbackQuery) -> bool:
    """Respond with an error if caller is not a super-admin."""
    user_id = entity.from_user.id
    username = entity.from_user.username
    if not is_admin(user_id, username):
        text = "⛔ You don't have permission to perform this action."
        if isinstance(entity, CallbackQuery):
            await entity.answer(text, show_alert=True)
        else:
            await entity.answer(text)
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 2: The Admin Bridge — Approve / Reject Callbacks
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("approve:"))
async def cb_approve_ticket(callback: CallbackQuery, bot: Bot) -> None:
    """
    Admin approves a payment screenshot.

    Steps:
      1. Parse ticket_id from callback data.
      2. Update ticket status → 'verified' in PostgreSQL.
      3. Update transaction status → 'approved'.
      4. Notify the ticket holder with their unique ticket number.
      5. Edit the admin message to reflect the approval.
      6. Auto-trigger draw if lottery is now full.
    """
    if not await _require_admin(callback):
        return

    ticket_id = int(callback.data.split(":")[1])
    admin_id  = callback.from_user.id
    admin_name = callback.from_user.full_name

    # ── 1. Update ticket in PostgreSQL ───────────────────────────────────────
    ticket = await db.update_ticket_status(ticket_id, "verified")
    if not ticket:
        await callback.answer("❌ Ticket not found in database.", show_alert=True)
        return

    # ── 2. Update transaction record ──────────────────────────────────────────
    await db.approve_transaction(ticket_id, admin_id)

    # ── 3. Fetch associated lottery ───────────────────────────────────────────
    lottery = await db.get_lottery(ticket["lottery_id"])

    # ── 4. Notify the user ───────────────────────────────────────────────────
    holder_id = ticket["holder_tg_id"]
    ticket_no = fmt_ticket_no(ticket["ticket_no"])
    try:
        await bot.send_message(
            chat_id=holder_id,
            text=(
                f"🎉 <b>Payment Approved!</b>\n\n"
                f"Your payment has been verified by our team.\n\n"
                f"🎫 <b>Your Ticket Number: #{ticket_no}</b>\n"
                f"🏆 Lottery: {esc(lottery['title'])}\n"
                f"🏅 Prize: {esc(lottery['prize_pool'])}\n\n"
                f"Good luck! The draw will be held when all slots are filled.\n"
                f"Use /mytickets to track your entries."
            ),
            parse_mode="HTML",
        )
        logger.info(f"✅ Ticket #{ticket_id} approved by admin {admin_id}. User {holder_id} notified.")
        
        # ── Referral Logic: Award points to the referrer ──────────────────
        user = await db.get_user(holder_id)
        if user and user.get("referred_by"):
            ref_id = user["referred_by"]
            await db.award_referral_points(ref_id, points=1)
            try:
                await bot.send_message(
                    chat_id=ref_id,
                    text=(
                        f"💎 <b>Referral Reward!</b>\n\n"
                        f"Your friend <b>{esc(user['full_name'])}</b> just bought a ticket!\n"
                        f"You have been awarded <b>1 Referral Point</b>. 🎁\n\n"
                        f"Accumulate points to win free tickets in the future!"
                    ),
                    parse_mode="HTML"
                )
            except Exception:
                pass # Referrer might have blocked the bot
                
    except Exception as e:
        logger.warning(f"Could not notify user {holder_id}: {e}")

    # ── 5. Edit admin panel message ───────────────────────────────────────────
    verified_count = lottery["verified_count"] or 0
    verified_count += 1  # reflect the just-approved ticket
    max_slots = lottery["max_slots"]

    await callback.message.edit_caption(
        caption=(
            f"✅ <b>APPROVED</b> by {esc(admin_name)}\n\n"
            f"🎟️ Ticket #{ticket_no} → <b>VERIFIED</b>\n"
            f"👥 Slots filled: {verified_count}/{max_slots}"
        ),
        parse_mode="HTML",
    )
    await callback.answer("✅ Ticket approved and user notified!", show_alert=False)

    # ── 6. Auto-trigger draw if lottery is now full ───────────────────────────
    if verified_count >= max_slots:
        await callback.message.reply(
            f"🔔 <b>Lottery '{esc(lottery['title'])}' is now FULL!</b>\n"
            f"Triggering automatic draw...",
            parse_mode="HTML",
        )
        await _execute_draw(
            bot=bot,
            lottery_id=lottery["id"],
            initiated_by=admin_id,
            reply_target=callback.message,
        )


@router.callback_query(F.data.startswith("reject:"))
async def cb_reject_ticket_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    """
    First step of rejection: ask admin for a rejection reason.
    """
    if not await _require_admin(callback):
        return

    ticket_id = int(callback.data.split(":")[1])
    await state.update_data(reject_ticket_id=ticket_id, reject_msg_id=callback.message.message_id)
    await state.set_state(AdminRejectReason.reason)

    await callback.message.reply(
        f"📝 Please type the <b>rejection reason</b> for Ticket #{ticket_id}.\n"
        f"The user will receive this message.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminRejectReason.reason)
async def process_rejection_reason(message: Message, state: FSMContext, bot: Bot) -> None:
    """
    Admin types rejection reason → updates DB, notifies user.
    """
    data = await state.get_data()
    ticket_id   = data.get("reject_ticket_id")
    reason      = message.text or "No reason provided."
    admin_id    = message.from_user.id
    admin_name  = message.from_user.full_name

    # ── Update DB ─────────────────────────────────────────────────────────────
    ticket = await db.update_ticket_status(ticket_id, "rejected")
    await db.reject_transaction(ticket_id, admin_id, note=reason)

    if not ticket:
        await message.reply("❌ Ticket not found.")
        await state.clear()
        return

    # ── Notify user ───────────────────────────────────────────────────────────
    holder_id = ticket["holder_tg_id"]
    try:
        await bot.send_message(
            chat_id=holder_id,
            text=(
                f"❌ <b>Payment Rejected</b>\n\n"
                f"Unfortunately, your payment screenshot for Ticket #{ticket_id} "
                f"could not be verified.\n\n"
                f"📋 <b>Reason:</b> {esc(reason)}\n\n"
                f"Please use /pay to resubmit with a valid screenshot, or "
                f"contact support if you believe this is an error."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Could not notify user {holder_id} of rejection: {e}")

    await state.clear()
    await message.reply(
        f"✅ Ticket #{ticket_id} rejected.\n"
        f"Reason sent to user: <i>{esc(reason)}</i>",
        parse_mode="HTML",
    )
    logger.info(f"❌ Ticket #{ticket_id} rejected by admin {admin_id}.")


@router.callback_query(F.data.startswith("user_info:"))
async def cb_user_info(callback: CallbackQuery) -> None:
    """Show the admin detailed info about a ticket holder."""
    if not await _require_admin(callback):
        return

    ticket_id = int(callback.data.split(":")[1])
    ticket    = await db.get_ticket(ticket_id)
    if not ticket:
        await callback.answer("Ticket not found.", show_alert=True)
        return

    user = await db.get_user(ticket["holder_tg_id"])
    if not user:
        await callback.answer("User not found.", show_alert=True)
        return

    info = (
        f"👤 <b>User Profile</b>\n\n"
        f"🆔 TG ID: <code>{user['tg_id']}</code>\n"
        f"📛 Name: {esc(user['full_name'])}\n"
        f"🔖 Username: @{user['username'] or 'N/A'}\n"
        f"📱 Phone: {user['phone'] or 'Not provided'}\n"
        f"📅 Joined: {user['registered_at'].strftime('%d %b %Y') if user['registered_at'] else 'N/A'}\n"
        f"📜 Terms: {'✅ Accepted' if user['terms_accepted'] else '❌ Not accepted'}"
    )
    await callback.answer()
    await callback.message.reply(info, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 3: Manual Draw Trigger & Lottery Management
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("draw:"))
async def cb_trigger_draw(callback: CallbackQuery, bot: Bot) -> None:
    """Admin manually triggers a draw for a lottery."""
    if not await _require_admin(callback):
        return

    lottery_id = int(callback.data.split(":")[1])
    await callback.answer("🎲 Initiating draw...", show_alert=False)
    await _execute_draw(
        bot=bot,
        lottery_id=lottery_id,
        initiated_by=callback.from_user.id,
        reply_target=callback.message,
    )


async def _execute_draw(
    bot: Bot,
    lottery_id: int,
    initiated_by: int,
    reply_target: Message,
) -> None:
    """
    Core draw execution — called by both auto-trigger and manual admin trigger.

    1. Fetch all verified tickets.
    2. Run provably_fair_draw().
    3. Persist winner and draw record to DB.
    4. Generate winner poster image.
    5. Broadcast to public group + notify winner privately.
    """
    lottery = await db.get_lottery(lottery_id)
    if not lottery:
        await reply_target.reply("❌ Lottery not found.")
        return

    if not lottery["is_active"]:
        await reply_target.reply("⚠️ This lottery is already closed.")
        return

    # ── Fetch verified entries ────────────────────────────────────────────────
    entries = await db.get_verified_tickets_for_draw(lottery_id)
    if not entries:
        await reply_target.reply(
            "⚠️ No verified entries found. Cannot draw."
        )
        return

    await reply_target.reply(
        f"🎲 Running provably fair draw for <b>{esc(lottery['title'])}</b>...\n"
        f"Total verified entries: <b>{len(entries)}</b>",
        parse_mode="HTML",
    )

    # ── Perform the draw ──────────────────────────────────────────────────────
    result = provably_fair_draw(list(entries))
    if not result:
        await reply_target.reply("❌ Draw failed — no entries.")
        return

    # ── Update DB ─────────────────────────────────────────────────────────────
    await db.set_lottery_winner(lottery_id, result.winner_tg_id, result.winner_ticket)
    await db.record_draw(
        lottery_id=lottery_id,
        winner_tg_id=result.winner_tg_id,
        winner_ticket=result.winner_ticket,
        draw_seed=result.draw_seed,
        total_entries=result.total_entries,
    )

    # ── Generate winner poster ────────────────────────────────────────────────
    poster_buf = generate_winner_poster(
        lottery_title  = lottery["title"],
        winner_name    = result.winner_name,
        winner_ticket  = result.winner_ticket,
        prize_pool     = lottery["prize_pool"],
        total_entries  = result.total_entries,
        draw_seed_short= result.draw_seed[:12],
    )
    poster_file = BufferedInputFile(
        file=poster_buf.read(),
        filename="winner_announcement.png",
    )

    # ── Broadcast to public group ─────────────────────────────────────────────
    announcement = (
        f"🏆 <b>YENE LOTTERY — DRAW RESULTS!</b>\n\n"
        f"🎱 <b>Lottery:</b> {esc(lottery['title'])}\n"
        f"🎫 <b>Winning Ticket:</b> #{result.winner_ticket:03d}\n"
        f"🏆 <b>Winner:</b> {esc(result.winner_name)}\n"
        f"🏅 <b>Prize:</b> {esc(lottery['prize_pool'])}\n\n"
        f"<i>🔑 Provably Fair Seed: <code>{result.draw_seed[:24]}...</code></i>\n"
        f"<i>Total Entries: {result.total_entries}</i>\n\n"
        f"Congratulations! 🎉 Use /history to verify this draw."
    )

    try:
        await bot.send_photo(
            chat_id=cfg.public_group_id,
            photo=poster_file,
            caption=announcement,
            parse_mode="HTML",
        )
        logger.info(f"🎲 Draw results broadcast to public group {cfg.public_group_id}.")
    except Exception as e:
        logger.error(f"Failed to broadcast to public group: {e}")
        # Still send to admin channel as fallback
        await reply_target.reply(announcement, parse_mode="HTML")

    # ── Notify winner privately ───────────────────────────────────────────────
    try:
        poster_buf.seek(0)
        winner_file = BufferedInputFile(
            file=poster_buf.read(),
            filename="your_win.png",
        )
        await bot.send_photo(
            chat_id=result.winner_tg_id,
            photo=winner_file,
            caption=(
                f"🎉 <b>Congratulations, {esc(result.winner_name)}!</b>\n\n"
                f"You have won the <b>{esc(lottery['title'])}</b> lottery!\n"
                f"🏅 <b>Prize: {esc(lottery['prize_pool'])}</b>\n\n"
                f"Our team will contact you shortly to arrange prize delivery.\n"
                f"🎫 Your winning ticket: #{result.winner_ticket:03d}"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Could not notify winner {result.winner_tg_id}: {e}")

    await reply_target.reply(
        f"✅ Draw complete!\n"
        f"🏆 Winner: <b>{esc(result.winner_name)}</b> — Ticket #{result.winner_ticket:03d}\n"
        f"Results posted to public group.",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cancel_lottery:"))
async def cb_cancel_lottery_confirm(callback: CallbackQuery) -> None:
    """Prompt admin to confirm lottery cancellation."""
    if not await _require_admin(callback):
        return
    lottery_id = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(
        reply_markup=confirm_keyboard("cancel", lottery_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_cancel:"))
async def cb_confirm_cancel(callback: CallbackQuery, bot: Bot) -> None:
    """Execute lottery cancellation after admin confirms."""
    if not await _require_admin(callback):
        return
    lottery_id = int(callback.data.split(":")[1])
    lottery    = await db.get_lottery(lottery_id)
    await db.deactivate_lottery(lottery_id)

    await callback.message.edit_text(
        f"🚫 Lottery <b>{esc(lottery['title'])}</b> (ID: {lottery_id}) has been cancelled.",
        parse_mode="HTML",
    )
    await callback.answer("Lottery cancelled.", show_alert=True)

    # Notify affected users who had pending tickets
    entries = await db.get_verified_tickets_for_draw(lottery_id)
    notified = 0
    for entry in entries:
        try:
            await bot.send_message(
                chat_id=entry["holder_tg_id"],
                text=(
                    f"⚠️ <b>Lottery Cancelled</b>\n\n"
                    f"The lottery <b>{esc(lottery['title'])}</b> has been cancelled "
                    f"by the operator. Please contact support for refund information."
                ),
                parse_mode="HTML",
            )
            notified += 1
        except Exception:
            pass

    logger.info(f"Lottery {lottery_id} cancelled. {notified} users notified.")


# ═══════════════════════════════════════════════════════════════════════════════
#  ADMIN PANEL — Commands & Navigation
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
    await callback.message.edit_text(
        "⚙️ <b>Admin Panel</b>\n\nWhat would you like to manage?",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "manage_lotteries")
async def cb_manage_lotteries(callback: CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
    lotteries = await db.get_active_lotteries()
    if not lotteries:
        await callback.answer("No active lotteries.", show_alert=True)
        return
    await callback.message.edit_text(
        "📋 <b>Active Lotteries</b>\n\nSelect a lottery to manage:",
        parse_mode="HTML",
        reply_markup=manage_lotteries_keyboard(lotteries),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("manage_lottery:"))
async def cb_manage_single_lottery(callback: CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
    lottery_id = int(callback.data.split(":")[1])
    lottery    = await db.get_lottery(lottery_id)
    if not lottery:
        await callback.answer("Lottery not found.", show_alert=True)
        return

    verified = lottery["verified_count"] or 0
    text = (
        f"📋 <b>Manage: {esc(lottery['title'])}</b>\n\n"
        f"{format_lottery(lottery)}\n\n"
        f"Choose an action:"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=admin_lottery_actions(lottery_id),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
#  ADMIN — Create Lottery FSM
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "create_lottery")
async def cb_start_create_lottery(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _require_admin(callback):
        return
    await state.set_state(AdminCreateLottery.title)
    await callback.message.edit_text(
        "➕ <b>Create New Lottery</b>\n\nStep 1/7 — Enter the <b>lottery title</b>:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminCreateLottery.title)
async def al_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text)
    await state.set_state(AdminCreateLottery.description)
    await message.reply("Step 2/7 — Enter the <b>description</b>:", parse_mode="HTML")


@router.message(AdminCreateLottery.description)
async def al_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text)
    await state.set_state(AdminCreateLottery.price)
    await message.reply(
        "Step 3/7 — Enter the <b>price per ticket</b> (ETB, numbers only).\n"
        "Example: <code>500</code>",
        parse_mode="HTML",
    )


@router.message(AdminCreateLottery.price, F.text.regexp(r"^\d+(\.\d{1,2})?$"))
async def al_price(message: Message, state: FSMContext) -> None:
    await state.update_data(price=float(message.text))
    await state.set_state(AdminCreateLottery.max_slots)
    await message.reply(
        "Step 4/7 — Enter the <b>maximum number of slots</b> (participants).\n"
        "Example: <code>100</code>",
        parse_mode="HTML",
    )


@router.message(AdminCreateLottery.price)
async def al_price_invalid(message: Message) -> None:
    await message.reply("⚠️ Please enter a valid number (e.g., <code>500</code> or <code>500.00</code>).", parse_mode="HTML")


@router.message(AdminCreateLottery.max_slots, F.text.regexp(r"^\d+$"))
async def al_max_slots(message: Message, state: FSMContext) -> None:
    await state.update_data(max_slots=int(message.text))
    await state.set_state(AdminCreateLottery.prize_pool)
    await message.reply(
        "Step 5/7 — Describe the <b>prize pool</b>.\n"
        "Example: <code>50,000 ETB + iPhone 15 Pro</code>",
        parse_mode="HTML",
    )


@router.message(AdminCreateLottery.max_slots)
async def al_max_slots_invalid(message: Message) -> None:
    await message.reply("⚠️ Please enter a whole number (e.g., <code>100</code>).", parse_mode="HTML")


@router.message(AdminCreateLottery.prize_pool)
async def al_prize_pool(message: Message, state: FSMContext) -> None:
    await state.update_data(prize_pool=message.text)
    await state.set_state(AdminCreateLottery.payment_info)
    await message.reply(
        "Step 6/7 — Enter <b>payment details</b> (bank account / Telebirr number).\n"
        "This is what participants will send money to.",
        parse_mode="HTML",
    )


@router.message(AdminCreateLottery.payment_info)
async def al_payment_info(message: Message, state: FSMContext) -> None:
    await state.update_data(payment_info=message.text)
    await state.set_state(AdminCreateLottery.confirm)
    data = await state.get_data()

    summary = (
        f"📋 <b>Lottery Summary — Please Confirm</b>\n\n"
        f"📌 Title: <b>{esc(data['title'])}</b>\n"
        f"📝 Description: {esc(data['description'])}\n"
        f"💰 Ticket Price: <b>{data['price']:,.2f} ETB</b>\n"
        f"👥 Max Slots: <b>{data['max_slots']}</b>\n"
        f"🏅 Prize Pool: <b>{esc(data['prize_pool'])}</b>\n"
        f"💳 Payment Info: <code>{esc(data['payment_info'])}</code>\n\n"
        f"Reply <b>YES</b> to create, or <b>NO</b> to cancel."
    )
    await message.reply(summary, parse_mode="HTML")


@router.message(AdminCreateLottery.confirm, F.text.lower() == "yes")
async def al_confirm_yes(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    lottery = await db.create_lottery(
        title        = data["title"],
        description  = data["description"],
        price_per_ticket = data["price"],
        max_slots    = data["max_slots"],
        prize_pool   = data["prize_pool"],
        payment_info = data["payment_info"],
        created_by   = message.from_user.id,
    )
    await state.clear()
    await message.reply(
        f"✅ <b>Lottery Created!</b>\n\n"
        f"🆔 Lottery ID: <code>{lottery['id']}</code>\n"
        f"🎱 Title: <b>{esc(lottery['title'])}</b>\n\n"
        f"📢 <b>Broadcasting notifications to all users...</b>",
        parse_mode="HTML",
    )

    # ── Notification Broadcast ───────────────────────────────────────────────
    users = await db.get_all_registered_users()
    if not users:
        return

    from keyboards.inline import lottery_detail_keyboard
    notification_kb = lottery_detail_keyboard(lottery["id"])
    
    msg_count = 0
    fail_count = 0
    
    for user_id in users:
        # Don't notify the admin who created it (optional, but cleaner)
        if user_id == message.from_user.id:
            continue
            
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎫 <b>NEW LOTTERY OPEN!</b>\n\n"
                    f"🎱 Title: <b>{esc(lottery['title'])}</b>\n"
                    f"🏆 Prize: <b>{esc(lottery['prize_pool'])}</b>\n"
                    f"💰 Price: <b>{lottery['price_per_ticket']:,.2f} ETB</b>\n\n"
                    f"Tap the button below to join now! 👇"
                ),
                parse_mode="HTML",
                reply_markup=notification_kb
            )
            msg_count += 1
            # Small delay to respect Telegram limits (30/sec)
            await asyncio.sleep(0.05) 
        except Exception as e:
            logger.warning(f"Failed to notify user {user_id}: {e}")
            fail_count += 1

    await message.answer(
        f"✅ <b>Broadcast Complete!</b>\n"
        f"Successfully notified <b>{msg_count}</b> users.\n"
        f"Failed for <b>{fail_count}</b> users (blocked bot/inactive)."
    )


@router.message(AdminCreateLottery.confirm)
async def al_confirm_no(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.reply("❌ Lottery creation cancelled.")


# ═══════════════════════════════════════════════════════════════════════════════
#  ADMIN BROADCAST & STATS
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _require_admin(callback):
        return
    await state.set_state(AdminBroadcast.waiting_message)
    await callback.message.edit_text(
        "📢 <b>Admin Global Broadcast</b>\n\n"
        "Please send the message you want to broadcast to <b>ALL registered users</b>.\n"
        "You can send text, an image with a caption, or a document.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminBroadcast.waiting_message)
async def process_admin_broadcast(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    
    # Fetch all registered users
    users = await db.get_all_registered_users()
    if not users:
        await message.reply("❌ No registered users found to broadcast to.")
        return

    status_msg = await message.answer(f"⏳ Starting broadcast to {len(users)} users...")
    
    success = 0
    failed = 0
    
    # Enhanced UI: Attach "Join Lottery" button to the copied message
    keyboard = broadcast_cta_keyboard()
    
    for user_id in users:
        try:
            # Copy the message to the user and attach the CTA button
            await message.copy_to(chat_id=user_id, reply_markup=keyboard)
            success += 1
            await asyncio.sleep(0.05) # Rate limiting
        except Exception:
            failed += 1
            
    await status_msg.edit_text(
        f"📢 <b>Broadcast Complete!</b>\n\n"
        f"✅ Successfully sent: <b>{success}</b>\n"
        f"❌ Failed (blocked/dead): <b>{failed}</b>",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "platform_stats")
async def cb_platform_stats(callback: CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
        
    # Implement basic stats. In a real app index these properly.
    # For now, quick counts.
    # Fetch basic counts
    async with db.get_conn() as conn:
        conn.row_factory = aiosqlite.Row
        c = await conn.execute("SELECT COUNT(*) FROM users")
        total_users = (await c.fetchone())[0]
        c = await conn.execute("SELECT COUNT(*) FROM lotteries")
        total_lots = (await c.fetchone())[0]
        c = await conn.execute("SELECT COUNT(*) FROM tickets WHERE status != 'rejected'")
        total_tickets = (await c.fetchone())[0]
        c = await conn.execute("SELECT SUM(amount) FROM transactions WHERE status = 'approved'")
        revenue = (await c.fetchone())[0] or 0.0

    # Fetch 24h metrics
    adv = await db.get_advanced_stats()

    stats_text = (
        f"📊 <b>Platform Statistics</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total Users:</b> {total_users}\n"
        f"🎱 <b>Total Lotteries:</b> {total_lots}\n"
        f"🎟️ <b>Total Tickets:</b> {total_tickets}\n"
        f"💰 <b>Total Revenue:</b> {revenue:,.2f} ETB\n\n"
        f"📈 <b>Last 24 Hours:</b>\n"
        f"💵 Revenue: <b>{adv['rev_24h']:,.2f} ETB</b>\n"
        f"🆕 New Users: <b>{adv['users_24h']}</b>\n"
        f"🎟️ Tickets Sold: <b>{adv['tickets_24h']}</b>\n"
    )
    
    await callback.message.edit_text(
        stats_text,
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_user_list")
async def cb_admin_user_list(callback: CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
        
    users = await db.get_all_users_detailed()
    if not users:
        await callback.message.edit_text("❌ No users found.", reply_markup=admin_panel_keyboard())
        return

    text = "👤 <b>Registered Users List</b>\n━━━━━━━━━━━━━━━━━━━\n\n"
    for u in users:
        username = f"@{esc(u['username'])}" if u['username'] else "N/A"
        date_str = u['registered_at'][:10] if u['registered_at'] else "N/A"
        text += (
            f"👤 {esc(u['full_name'])}\n"
            f"🔖 {username} | 🆔 <code>{u['tg_id']}</code>\n"
            f"📱 {esc(u['phone'] or 'No Phone')}\n"
            f"💎 Points: {u['referral_points']} | 📅 {date_str}\n"
            f"───────────────────\n"
        )
    
    # If text is too long (Telegram limit is 4096), we should truncate or paginate.
    # For now, let's truncate with a note if it's too big.
    if len(text) > 4000:
        text = text[:3900] + "\n\n<i>... (list truncated due to size)</i>"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard()
    )
    await callback.answer()
