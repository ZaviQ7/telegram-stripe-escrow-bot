import os
import logging
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ConversationHandler,
    CallbackQueryHandler, MessageHandler, filters
)
from dotenv import load_dotenv
from database.database import DB
from stripe_utils.stripe_utils import StripeHelper
from .handlers import (
    start, main_menu_handler, button_handler, rating_handler, profile,
    connect_stripe,
    admin_verify, admin_unverify, admin_split_funds, admin_refund, admin_resolve,
    admin_filter,
    trade_ask_counterparty, trade_ask_description, trade_ask_amount,
    ASK_COUNTERPARTY, ASK_DESCRIPTION, ASK_AMOUNT,
    milestone_ask_counterparty, milestone_ask_title, milestone_ask_loop, milestone_finish,
    ASK_MILESTONE_COUNTERPARTY, ASK_MILESTONE_TITLE, ASK_MILESTONES_LOOP,
    dispute_start, dispute_ask_reason, dispute_process_proof,
    ASK_DISPUTE_REASON, ASK_DISPUTE_PROOF
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def build_app():
    """
    Initializes the bot and registers conversation handlers, commands and callbacks.
    """
    load_dotenv()
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    stripe_secret = os.environ["STRIPE_SECRET_KEY"]
    db_url = os.getenv("DATABASE_URL", "sqlite:///bot.db")
    DB.init(db_url)
    stripe = StripeHelper(stripe_secret)

    app = ApplicationBuilder().token(bot_token).build()
    app.bot_data["stripe"] = stripe

    # Conversation handlers
    trade_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(main_menu_handler, pattern='^start_trade$')],
        states={
            ASK_COUNTERPARTY: [MessageHandler(filters.REPLY, trade_ask_counterparty)],
            ASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, trade_ask_description)],
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, trade_ask_amount)],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )
    milestone_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(main_menu_handler, pattern='^start_milestone_project$')],
        states={
            ASK_MILESTONE_COUNTERPARTY: [MessageHandler(filters.REPLY, milestone_ask_counterparty)],
            ASK_MILESTONE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, milestone_ask_title)],
            ASK_MILESTONES_LOOP: [
                CommandHandler("done", milestone_finish),
                MessageHandler(filters.TEXT & ~filters.COMMAND, milestone_ask_loop),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )
    dispute_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dispute_start, pattern='^dispute_deal:')],
        states={
            ASK_DISPUTE_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, dispute_ask_reason)],
            ASK_DISPUTE_PROOF: [MessageHandler(filters.PHOTO, dispute_process_proof)],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(trade_conv)
    app.add_handler(milestone_conv)
    app.add_handler(dispute_conv)

    # Standalone commands
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("connect", connect_stripe))

    # Admin commands
    app.add_handler(CommandHandler("admin_verify", admin_verify, filters=admin_filter))
    app.add_handler(CommandHandler("admin_unverify", admin_unverify, filters=admin_filter))
    app.add_handler(CommandHandler("admin_split", admin_split_funds, filters=admin_filter))
    app.add_handler(CommandHandler("admin_refund", admin_refund, filters=admin_filter))
    app.add_handler(CommandHandler("admin_resolve", admin_resolve, filters=admin_filter))

    # Callback query handlers
    app.add_handler(CallbackQueryHandler(rating_handler, pattern='^rate:|^skip_rating:'))
    app.add_handler(CallbackQueryHandler(button_handler))  # catch‑all for other buttons

    return app
