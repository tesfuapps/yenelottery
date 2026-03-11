"""
states/forms.py — FSM state groups for all multi-step flows.
"""

from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    """New user onboarding flow."""
    waiting_for_name  = State()
    waiting_for_phone = State()
    accepting_terms   = State()


class PaymentSubmission(StatesGroup):
    """Lottery ticket payment upload flow."""
    choosing_lottery       = State()
    waiting_transaction_id = State()
    waiting_screenshot     = State()
    confirming_amount      = State()


class AdminCreateLottery(StatesGroup):
    """Admin creates a new lottery."""
    title        = State()
    description  = State()
    price        = State()
    max_slots    = State()
    prize_pool   = State()
    payment_info = State()
    draw_date    = State()
    confirm      = State()


class AdminRejectReason(StatesGroup):
    """Admin provides rejection reason."""
    reason = State()


class AdminBroadcast(StatesGroup):
    """Admin global broadcast flow."""
    waiting_message = State()
