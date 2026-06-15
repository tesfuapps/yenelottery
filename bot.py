"""
bot.py — Yene Lottery Bot Entry Point
Wires up all routers, initializes the database, and starts polling.

Usage:
    python bot.py
"""

import asyncio
import logging
import sys
import os  # <-- Added to read Render's port

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web  # <-- Added to handle Render's web health check

from config import cfg
from database.models import init_db
from database.connection import close_pool

# ── Routers ───────────────────────────────────────────────────────────────────
from handlers import user, lottery, payment, admin
from aiogram.types import BotCommand
from utils.automation import auto_execute_draw, spawn_from_templates
import database.queries as db

# ─────────────────────────────────────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO if not cfg.debug else logging.DEBUG,
    format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("bot")


# ─────────────────────────────────────────────────────────────────────────────
#  Background Tasks
# ─────────────────────────────────────────────────────────────────────────────

async def scheduler_loop(bot: Bot):
    """Periodically checks for expired lotteries and recurring tasks."""
    logger.info("⏰ Background scheduler started.")
    while True:
        try:
            # 1. Auto-Draw Expired Lotteries
            expired = await db.get_expired_lotteries()
            for lot in expired:
                logger.info(f"🎯 Auto-drawing expired lottery: {lot['title']} (ID: {lot['id']})")
                await auto_execute_draw(bot, lot['id'])
            
            # 2. Spawn Recurring Lotteries
            await spawn_from_templates(bot)
            
        except Exception as e:
            logger.error(f"❌ Error in scheduler_loop: {e}")
            
        await asyncio.sleep(60) # Check every minute

# ─────────────────────────────────────────────────────────────────────────────
#  Async Web Server to satisfy Render
# ─────────────────────────────────────────────────────────────────────────────

async def handle_health_check(request):
    """Answers Render's port checks to keep the service active."""
    return web.Response(text="Yene Lottery Bot is running and healthy!")

async def start_health_check_server():
    """Starts a lightweight async server bound to Render's dynamic port."""
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    
    # Read the environmental port provided by Render (defaults to 8080 locally)
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    await site.start()
    logger.info(f"🌐 Keep-alive server running on port {port}")

# ─────────────────────────────────────────────────────────────────────────────
#  Startup & Shutdown hooks
# ─────────────────────────────────────────────────────────────────────────────

async def setup_bot_commands(bot: Bot):
    """Set up the permanent 'Menu' button commands in Telegram."""
    commands = [
        BotCommand(command="start", description="🏠 Main Menu"),
        BotCommand(command="pay", description="💳 Join a Lottery"),
        BotCommand(command="mytickets", description="🎟️ View My Tickets"),
        BotCommand(command="history", description="📜 Draw History"),
    ]
    await bot.set_my_commands(commands)
    logger.info("✅ Bot commands menu updated.")

async def on_startup(bot: Bot) -> None:
    """Called once when the bot starts."""
    # Initialize database tables
    await init_db()
    
    # Set up commands menu
    await setup_bot_commands(bot)

    # Start background scheduler
    asyncio.create_task(scheduler_loop(bot))
    
    # Start the simple web server for Render health checks
    asyncio.create_task(start_health_check_server())

    # Log bot identity
    me = await bot.get_me()
    logger.info(f"🤖 Bot: @{me.username} (ID: {me.id})")
    logger.info(f"👑 Super Admins: {cfg.super_admin_ids}")
    logger.info(f"📢 Admin Group : {cfg.admin_group_id}")
    logger.info(f"🌐 Public Group: {cfg.public_group_id}")

    logger.info("✅ Bot is ready to accept connections.")
    logger.info("🚀 Yene Lottery Bot starting...")


async def on_shutdown(bot: Bot) -> None:
    """Called on graceful shutdown."""
    logger.info("🛑 Shutting down Yene Lottery Bot...")
    await close_pool()
    logger.info("👋 Goodbye!")


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    if not cfg.bot_token or cfg.bot_token == "your_bot_token_here":
        logger.error(
            "❌ BOT_TOKEN is not set!\n"
            "   Copy .env.example → .env and fill in your credentials."
        )
        sys.exit(1)

    # Create bot with HTML parse mode as default
    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Dispatcher with in-memory FSM storage
    # For production, use RedisStorage or PostgreSQL storage
    dp = Dispatcher(storage=MemoryStorage())

    # ── Register lifecycle hooks ──────────────────────────────────────────────
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # ── Register routers (order matters — more specific first) ────────────────
    dp.include_router(admin.router)    # Admin callbacks (approve/reject/draw)
    dp.include_router(payment.router)  # Payment screenshot flow
    dp.include_router(lottery.router)  # Lottery browsing
    dp.include_router(user.router)     # User registration and main menu

    # ── Start polling ─────────────────────────────────────────────────────────
    logger.info("📡 Starting long-polling...")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt).")