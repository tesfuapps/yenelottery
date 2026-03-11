"""
keyboards/inline.py — All InlineKeyboardMarkup builders for Yene Lottery.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN — Payment Review Panel
# ─────────────────────────────────────────────────────────────────────────────

def admin_review_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    """
    Inline keyboard sent to admin group with each payment screenshot.
    Data format: "action:ticket_id"
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Approve",
            callback_data=f"approve:{ticket_id}",
        ),
        InlineKeyboardButton(
            text="❌ Reject",
            callback_data=f"reject:{ticket_id}",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="👤 View User Profile",
            callback_data=f"user_info:{ticket_id}",
        )
    )
    return builder.as_markup()


def admin_lottery_actions(lottery_id: int) -> InlineKeyboardMarkup:
    """Admin controls for an individual lottery."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🎲 Trigger Draw NOW",
            callback_data=f"draw:{lottery_id}",
        ),
        InlineKeyboardButton(
            text="🚫 Cancel Lottery",
            callback_data=f"cancel_lottery:{lottery_id}",
        ),
    )
    return builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
#  USERS — Lottery List
# ─────────────────────────────────────────────────────────────────────────────

def lottery_list_keyboard(lotteries: list) -> InlineKeyboardMarkup:
    """One button per active lottery."""
    builder = InlineKeyboardBuilder()
    for lot in lotteries:
        slots_left = lot["max_slots"] - (lot["verified_count"] or 0)
        builder.row(
            InlineKeyboardButton(
                text=f"🎫 {lot['title']} — {slots_left} slots left",
                callback_data=f"lottery_detail:{lot['id']}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="🔄 Refresh", callback_data="refresh_lotteries")
    )
    return builder.as_markup()


def lottery_detail_keyboard(lottery_id: int) -> InlineKeyboardMarkup:
    """Detail view — Join or Go Back."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="💳 Join & Pay",
            callback_data=f"join_lottery:{lottery_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Back to List", callback_data="back_to_list")
    )
    return builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
#  USERS — Registration / Terms
# ─────────────────────────────────────────────────────────────────────────────

def terms_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ I Accept", callback_data="accept_terms"),
        InlineKeyboardButton(text="❌ Decline", callback_data="decline_terms"),
    )
    return builder.as_markup()


def share_phone_keyboard():
    """Reply keyboard asking user to share their phone number."""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Share My Phone Number", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN MENU
# ─────────────────────────────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎫 View Lotteries", callback_data="view_lotteries"),
        InlineKeyboardButton(text="🎟️ My Tickets",   callback_data="my_tickets"),
    )
    builder.row(
        InlineKeyboardButton(text="👤 My Profile",     callback_data="my_profile"),
        InlineKeyboardButton(text="📜 Draw History",  callback_data="draw_history"),
    )
    builder.row(
        InlineKeyboardButton(text="ℹ️ Help",          callback_data="help"),
    )
    return builder.as_markup()


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Extended menu for admins."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎫 View Lotteries", callback_data="view_lotteries"),
        InlineKeyboardButton(text="🎟️ My Tickets",   callback_data="my_tickets"),
    )
    builder.row(
        InlineKeyboardButton(text="👤 My Profile",     callback_data="my_profile"),
        InlineKeyboardButton(text="📜 Draw History",  callback_data="draw_history"),
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Admin Panel",  callback_data="admin_panel"),
        InlineKeyboardButton(text="ℹ️ Help",          callback_data="help"),
    )
    return builder.as_markup()


def profile_extra_keyboard(ref_link: str) -> InlineKeyboardMarkup:
    """Extra actions for the profile view (Invite friends)."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔗 Invite Friends",
            url=f"https://t.me/share/url?url={ref_link}&text=Join%20Yene%20Lottery%20and%20win%20big!%20%F0%9F%8E%B0"
        )
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="main_menu")
    )
    return builder.as_markup()


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Create Lottery", callback_data="create_lottery"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 Manage Lotteries", callback_data="manage_lotteries"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Platform Stats", callback_data="platform_stats"),
        InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast"),
    )
    builder.row(
        InlineKeyboardButton(text="👤 Users List", callback_data="admin_user_list"),
        InlineKeyboardButton(text="🔙 Back", callback_data="main_menu"),
    )
    return builder.as_markup()


def broadcast_cta_keyboard() -> InlineKeyboardMarkup:
    """Call-to-action keyboard for broadcast messages."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎰 Join a Lottery Now!", callback_data="join_lottery")
    )
    return builder.as_markup()


def confirm_keyboard(action: str, lottery_id: int) -> InlineKeyboardMarkup:
    """Generic confirm/cancel keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Confirm", callback_data=f"confirm_{action}:{lottery_id}"),
        InlineKeyboardButton(text="❌ Cancel",  callback_data="admin_panel"),
    )
    return builder.as_markup()


def manage_lotteries_keyboard(lotteries: list) -> InlineKeyboardMarkup:
    """Admin listing of all lotteries for management."""
    builder = InlineKeyboardBuilder()
    for lot in lotteries:
        status = "🟢" if lot["is_active"] else "🔴"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {lot['title']} (ID: {lot['id']})",
                callback_data=f"manage_lottery:{lot['id']}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data="admin_panel"),
    )
    return builder.as_markup()
