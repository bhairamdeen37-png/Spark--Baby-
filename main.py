import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiohttp import web

import config
from storage.database import init_db, close_db
from services import bot_state

from handlers import start, help, settings, study, messages, quiz, notes, payment, admin

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("spark_baby.main")


async def _start_health_server():
    """Render Web Services need something bound to $PORT — this is just a
    health check, it has nothing to do with the bot's actual logic."""
    app = web.Application()
    app.router.add_get("/", lambda req: web.Response(text="Spark Baby is alive."))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"Health server listening on :{port}")


async def main():
    config.validate_startup()
    await init_db()
    log.info("Database ready.")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=None),
    )
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(help.router)
    dp.include_router(settings.router)
    dp.include_router(study.router)
    dp.include_router(quiz.router)
    dp.include_router(notes.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)
    dp.include_router(messages.router)  # generic text/photo handler LAST — it's the catch-all

    me = await bot.get_me()
    bot_state.set_identity(me.username, me.id)
    log.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info(f"🚀 SPARK BABY STARTED — @{me.username}")
    log.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    await _start_health_server()

    try:
        await dp.start_polling(bot)
    finally:
        await close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
