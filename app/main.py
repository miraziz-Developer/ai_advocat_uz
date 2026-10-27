"""Entry point: webhook server on Render, long polling locally."""
import asyncio
import contextlib
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app import config, db
from app.bot import router

log = logging.getLogger("main")
WEBHOOK_PATH = "/tg/webhook"


async def keep_awake(url: str) -> None:
    """Render free web services sleep after 15 min without inbound traffic; pinging our own public
    URL every 10 min keeps it up (one service running 24/7 fits the free 750 h/month)."""
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(600)
            with contextlib.suppress(Exception):
                async with session.get(f"{url}/health", timeout=aiohttp.ClientTimeout(total=30)):
                    pass


DESCRIPTION = (
    "⚖️ O'zbekiston qonunlari bo'yicha AI huquqiy yordamchi.\n\n"
    "• Vaziyatingizni yozing yoki 🎙 ovozli xabar yuboring — qonun bo'yicha nima qilishni moddalar bilan aytaman.\n"
    "• 📄 Shartnoma rasmini yoki PDF yuboring — xavfli joylarini topaman.\n"
    "• 📝 Ariza, shikoyat, da'vo arizasini tayyorlab beraman.\n\n"
    "Manba: lex.uz rasmiy qonun matnlari."
)


async def setup_profile(bot: Bot) -> None:
    """Menu commands and the text users see before pressing Start. Failures here must not stop the bot."""
    try:
        await bot.set_my_commands([BotCommand(command="start", description="Bosh menyu"),
                                   BotCommand(command="new", description="Yangi suhbat")])
        await bot.set_my_description(DESCRIPTION)
        await bot.set_my_short_description("O'zbekiston qonunlari bo'yicha AI yordamchi: savol, ovoz, shartnoma tahlili.")
    except Exception:
        log.exception("could not set bot profile")


async def health(_: web.Request) -> web.Response:
    return web.Response(text="ok")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config.require("BOT_TOKEN", "DATABASE_URL", "GEMINI_API_KEY", "CARD_NUMBER", "CARD_HOLDER")
    bot = Bot(config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    if not config.WEBHOOK_BASE_URL:
        async def polling() -> None:
            await db.init()
            await setup_profile(bot)
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(bot)
        asyncio.run(polling())
        return

    config.require("WEBHOOK_SECRET")
    base = config.WEBHOOK_BASE_URL.rstrip("/")
    tasks: list[asyncio.Task] = []

    async def on_startup(bot: Bot) -> None:
        await db.init()
        await setup_profile(bot)
        await bot.set_webhook(f"{base}{WEBHOOK_PATH}", secret_token=config.WEBHOOK_SECRET,
                              allowed_updates=dp.resolve_used_update_types())
        tasks.append(asyncio.create_task(keep_awake(base)))

    dp.startup.register(on_startup)
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=config.WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    main()
