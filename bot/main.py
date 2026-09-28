"""Catibot application entry point."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import settings, validate_settings
from bot.database.db import close_db, init_db
from bot.handlers import all_routers
from bot.services.cat_assets import CAT_ASSETS_ROOT
from bot.services.cat_preview import ASSET_ROUTE_PREFIX
from bot.services.notification_sweep import start_notification_sweep

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("catibot")


async def on_startup(bot: Bot) -> None:
    await init_db()
    if settings.webhook_base_url:
        await bot.set_webhook(settings.webhook_base_url + settings.webhook_path)
    start_notification_sweep(bot)
    logger.info("catibot started")


async def on_shutdown() -> None:
    await close_db()


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    for router in all_routers:
        dp.include_router(router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return dp


def _register_asset_routes(app: web.Application) -> None:
    app.router.add_static(
        f"{ASSET_ROUTE_PREFIX}/",
        path=str(CAT_ASSETS_ROOT),
        name="cat_assets",
        show_index=False,
        follow_symlinks=False,
    )


async def _run_polling(bot: Bot, dp: Dispatcher) -> None:
    runner: web.AppRunner | None = None
    if settings.public_asset_base_url:
        app = web.Application()
        _register_asset_routes(app)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=settings.port)
        await site.start()
        logger.info(
            "cat preview assets available at %s%s/",
            settings.public_asset_base_url,
            ASSET_ROUTE_PREFIX,
        )

    try:
        await dp.start_polling(bot)
    finally:
        if runner is not None:
            await runner.cleanup()


def main() -> None:
    validate_settings()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    if settings.webhook_base_url:
        app = web.Application()
        _register_asset_routes(app)
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(
            app,
            path=settings.webhook_path,
        )
        setup_application(app, dp, bot=bot)
        web.run_app(app, port=settings.port)
    else:
        asyncio.run(_run_polling(bot, dp))


if __name__ == "__main__":
    main()
