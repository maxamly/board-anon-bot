from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import get_settings
from app.db.session import init_db
from app.handlers import admin, callbacks, user
from app.utils.logging import setup_logging


async def run_bot() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    setup_logging(settings.log_level)
    init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dispatcher = Dispatcher()
    dispatcher.include_router(admin.router)
    dispatcher.include_router(callbacks.router)
    dispatcher.include_router(user.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(
        bot,
        allowed_updates=dispatcher.resolve_used_update_types(),
        polling_timeout=settings.polling_timeout,
    )


def run() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    run()
