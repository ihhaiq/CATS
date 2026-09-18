"""
Entry point. Boots the aiogram dispatcher on a webhook (aiohttp) for Railway.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import settings, validate_settings
from bot.database.db import init_db
from bot.handlers import all_routers
from bot.handlers.errors import on_error
from bot.services.notification_sweep import start_notification_sweep, stop_notification_sweep

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("catibot")


async def on_startup(bot: Bot) -> None:
    await init_db()
    if settings.webhook_base_url:
        await bot.set_webhook(settings.webhook_base_url + settings.webhook_path)
    start_notification_sweep(bot)
    logger.info("catibot started")


async def on_shutdown() -> None:
    await stop_notification_sweep()
    logger.info("catibot stopped")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    for router in all_routers:
        dp.include_router(router)
    dp.errors.register(on_error)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return dp


def main() -> None:
    validate_settings()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    if settings.webhook_base_url:
        app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.webhook_path)
        setup_application(app, dp, bot=bot)
        web.run_app(app, port=settings.port)
    else:
        # local dev fallback: long polling
        asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
