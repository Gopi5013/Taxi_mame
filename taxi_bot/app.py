from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from taxi_bot.config import BOT_TOKEN
from taxi_bot.database import init_db
from taxi_bot.handlers import chat, driver_panel, myid, start
from taxi_bot.handlers import admin_panel
from taxi_bot.menu import menu_callback


def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("Missing BOT_TOKEN. Set BOT_TOKEN in your .env file.")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("driver", driver_panel))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.LOCATION | (filters.TEXT & ~filters.COMMAND), chat))
    return app
