"""
handlers/payment.py — Phase 2: The "Vault"

Handles the payment screenshot upload flow:
  1. User clicks "Join & Pay" on a lottery → lottery_id stored in FSM state.
  2. User uploads a photo (payment screenshot).
  3. Bot creates a pending ticket in DB and records the transaction (file_id).
  4. Screenshot forwarded to the Admin Group with inline [Approve][Reject] buttons.
  5. User receives confirmation that their submission is under review.
"""

import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery,
    Message,
    BufferedInputFile,
    InputMediaPhoto,
)
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from datetime import datetime, timedelta, timezone

from config import cfg
from database import queries as db
from keyboards.inline import admin_review_keyboard, main_menu_keyboard
from states.forms import PaymentSubmission
from utils.helpers import esc, fmt_ticket_no
from utils.ocr import extract_receipt_info
import os
import aiofiles

logger = logging.getLogger(__name__)
router = Router(name="payment")


# ─────────────────────────────────────────────────────────────────────────────
#  Step 1: User selects a lottery to join
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("join_lottery:"))
async def cb_join_lottery(callback: CallbackQuery, state: FSMContext) -> None:
    """
    User taps 'Join & Pay' on a lottery.
    Verify they are registered, then prompt for screenshot upload.
    """
    lottery_id = int(callback.data.split(":")[1])
    tg_id      = callback.from_user.id

    # Guard: must be a registered user with accepted terms
    user = await db.get_user(tg_id)
    if not user:
        await callback.answer(
            "⚠️ Please /start first to register.", show_alert=True
        )
        return
    if not user["terms_accepted"]:
        await callback.answer(
            "⚠️ Please accept the Terms & Conditions first (/start).",
            show_alert=True,
        )
        return

    # Load lottery info
    lottery = await db.get_lottery(lottery_id)
    if not lottery or not lottery["is_active"]:
        await callback.answer("❌ This lottery is no longer active.", show_alert=True)
        return

    # Check if lottery is full
    verified_count = lottery["verified_count"] or 0
    if verified_count >= lottery["max_slots"]:
        await callback.answer(
            "😔 All slots are filled! Check back for the next lottery.", show_alert=True
        )
        return

    # Store lottery context in FSM
    await state.update_data(lottery_id=lottery_id)
    await state.set_state(PaymentSubmission.waiting_screenshot)

    await callback.message.edit_text(
        f"💳 <b>Payment Instructions</b>\n\n"
        f"🎱 Lottery: <b>{esc(lottery['title'])}</b>\n"
        f"💰 Amount to Pay: <b>{lottery['price_per_ticket']:,.2f} ETB</b>\n\n"
        f"📲 <b>Send payment to:</b>\n"
        f"<code>{esc(lottery['payment_info'] or 'Contact admin for payment details')}</code>\n\n"
        f"─────────────────────\n"
        f"📸 <b>Please upload your payment screenshot now:</b>\n"
        f"I will try to read the Transaction ID automatically.",
        parse_mode="HTML",
    )
    await callback.answer()


# Step 2: User provides transaction ID (Fallback if OCR fails)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PaymentSubmission.waiting_transaction_id, F.text)
async def process_manual_id(message: Message, state: FSMContext, bot: Bot) -> None:
    """Handle manual entry of ID after OCR fail or user rejection."""
    tx_id = message.text.strip().upper()
    data = await state.get_data()
    file_id = data.get("screenshot_file_id")
    
    if not file_id:
        await message.reply("❌ Screenshot missing. Please upload the screenshot again.")
        await state.set_state(PaymentSubmission.waiting_screenshot)
        return

    await state.update_data(transaction_ref=tx_id)
    await finalize_submission(message, state, bot, file_id, tx_id, None)

# ─────────────────────────────────────────────────────────────────────────────
#  Step 3: User uploads screenshot & OCR occurs
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PaymentSubmission.waiting_screenshot, F.photo)
async def process_payment_screenshot(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    """
    Receive the payment screenshot photo, perform OCR, and:
      1. If ID found: Ask user to confirm.
      2. If ID NOT found: Ask user to type it manually.
    """
    photo = message.photo[-1]
    file_id = photo.file_id
    
    msg = await message.answer("🔄 <b>Processing image...</b> Searching for Transaction ID...", parse_mode="HTML")
    
    # Download file for OCR
    file = await bot.get_file(file_id)
    file_path = f"temp_{file_id}.png"
    await bot.download_file(file.file_path, file_path)
    
    # Run OCR
    receipt_info = extract_receipt_info(file_path)
    extracted_id = receipt_info.get("tx_id", "")
    extracted_amount = receipt_info.get("amount")
    
    # Cleanup
    if os.path.exists(file_path):
        os.remove(file_path)
        
    await state.update_data(screenshot_file_id=file_id)
    
    if extracted_id:
        await msg.delete()
        await state.update_data(transaction_ref=extracted_id)
        if extracted_amount is not None:
            await state.update_data(transaction_amount=extracted_amount)
            
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        amount_str = f":{extracted_amount}" if extracted_amount is not None else ""
        kb.button(text=f"✅ Yes, Confirm", callback_data=f"confirm_id:{extracted_id}{amount_str}")
        kb.button(text="✍️ No, type manually", callback_data="manual_id")
        kb.adjust(1)
        
        amount_text = f"💰 <b>Paid Amount:</b> {extracted_amount} ETB\n" if extracted_amount else ""
        await message.answer(
            f"🔍 <b>OCR Result:</b>\n"
            f"🧾 <b>Transaction ID:</b> <code>{extracted_id}</code>\n"
            f"{amount_text}\n"
            f"Is this correct?",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
    else:
        await msg.edit_text(
            "⚠️ <b>OCR failed</b> to find a Transaction ID automatically.\n\n"
            "🔢 Please <b>type your Transaction ID</b> (e.g. FT...) manually:",
            parse_mode="HTML"
        )
        await state.set_state(PaymentSubmission.waiting_transaction_id)

@router.callback_query(F.data.startswith("confirm_id:"))
async def cb_confirm_id(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    tx_id = parts[1]
    amount = float(parts[2]) if len(parts) > 2 else None
    
    data = await state.get_data()
    file_id = data.get("screenshot_file_id")
    await callback.message.delete()
    await finalize_submission(callback.message, state, bot, file_id, tx_id, amount)

@router.callback_query(F.data == "manual_id")
async def cb_manual_id(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "🔢 Please <b>type your Transaction ID</b> manually:",
        parse_mode="HTML"
    )
    await state.set_state(PaymentSubmission.waiting_transaction_id)

async def finalize_submission(message: Message, state: FSMContext, bot: Bot, file_id: str, tx_id: str, amount: float = None):
    """The shared logic to save to DB and notify admin."""
    data = await state.get_data()
    lottery_id = data.get("lottery_id")
    tg_id = message.chat.id if hasattr(message, 'chat') else message.from_user.id
    user_name = message.from_user.full_name if message.from_user else "User"
    username = message.from_user.username if message.from_user and message.from_user.username else "N/A"

    lottery = await db.get_lottery(lottery_id)
    if not lottery or not lottery["is_active"]:
        await message.answer("❌ This lottery is no longer active.")
        await state.clear()
        return

    ticket = await db.create_ticket(lottery_id=lottery_id, holder_tg_id=tg_id)
    await db.create_transaction(
        ticket_id=ticket["id"],
        lottery_id=lottery_id,
        holder_tg_id=tg_id,
        file_id=file_id,
        transaction_ref=tx_id,
        amount=amount,
    )

    ticket_no = fmt_ticket_no(ticket["ticket_no"])
    ticket_id = ticket["id"]
    
    # ── Build the admin notification message ──────────────────────────────────
    extracted_amount_text = f"\n✅ OCR Paid Amount: <b>{amount:,.2f} ETB</b>" if amount else ""
    # Calculate expected review time in UTC+03:00 (24 hours from now)
    tz = timezone(timedelta(hours=3))
    expected_review_time = (datetime.now(tz) + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M UTC+03:00")
    admin_caption = (
        f"🔔 <b>New Payment Submission</b>\n\n"
        f"🎱 Lottery: <b>{esc(lottery['title'])}</b>\n"
        f"💰 Expected: <b>{lottery['price_per_ticket']:,.2f} ETB</b>{extracted_amount_text}\n"
        f"🧾 Tx Ref: <b>{esc(tx_id)}</b>\n\n"
        f"👤 <b>Participant Info</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 TG ID: <code>{tg_id}</code>\n"
        f"📛 Name: {esc(user_name)}\n"
        f"🔖 Username: @{username}\n"
        f"🎟️ Pending Ticket: <b>#{ticket_no}</b>\n"
        f"🆔 Ticket DB ID: <code>{ticket_id}</code>\n\n"
        f"📸 Review the payment screenshot and take action:"
    )

    # ── Forward screenshot to admin group ─────────────────────────────────────
    try:
        # Send screenshot directly to the super admin (first ID in SUPER_ADMIN_IDS) for approval
        admin_user_id = cfg.super_admin_ids[0] if cfg.super_admin_ids else cfg.admin_group_id
        await bot.send_photo(
            chat_id     = admin_user_id,
            photo       = file_id,
            caption     = admin_caption,
            parse_mode  = "HTML",
            reply_markup= admin_review_keyboard(ticket_id),
        )
        logger.info(
            f"📸 Payment screenshot forwarded to admin group for "
            f"ticket #{ticket_no} (ID: {ticket_id}), user {tg_id}."
        )
    except Exception as e:
        logger.error(f"Failed to forward screenshot to admin group: {e}")
        await message.answer(
            "⚠️ There was an issue forwarding your screenshot. Please contact support."
        )
        await state.clear()
        return

    # ── Confirm to user ───────────────────────────────────────────────────────
    await state.clear()
    await message.answer(
    f"<b>Submission Received!</b>\n\n"
    "Your payment screenshot has been submitted for review.\n\n"
    f"🎟️ <b>Pending Ticket:</b> #{ticket_no}\n"
    f"🎱 <b>Lottery:</b> {esc(lottery['title'])}\n\n"
    "🛡️ Our Admin or Support team will review and approve your payment within <b>24 hours</b>.\n"
    f"⏰ Expected review time: <b>{expected_review_time}</b>.\n"
    "You will receive a notification once your ticket is <b>verified</b>.\n\n"
    "Use /mytickets to track your submission.",
    parse_mode="HTML",
    reply_markup=main_menu_keyboard(),
)


@router.message(PaymentSubmission.waiting_screenshot)
async def process_screenshot_invalid(message: Message) -> None:
    """Handle non-photo messages during payment submission state."""
    await message.reply(
        "📸 Please send a <b>photo/screenshot</b> of your payment transaction.\n\n"
        "If you want to cancel, use /start to go back to the main menu.",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
#  /pay — Direct payment command
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("pay"))
async def cmd_pay(message: Message) -> None:
    """Shortcut command — shows active lotteries for payment."""
    from keyboards.inline import lottery_list_keyboard
    lotteries = await db.get_active_lotteries()
    if not lotteries:
        await message.answer(
            "😔 No active lotteries at the moment.\nCheck back soon!",
            parse_mode="HTML",
        )
        return
    await message.answer(
        "💳 <b>Select a Lottery to Join</b>\n\nChoose a lottery to pay for:",
        parse_mode="HTML",
        reply_markup=lottery_list_keyboard(lotteries),
    )
