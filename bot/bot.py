
import os, logging
from telegram.ext import ApplicationBuilder
from dotenv import load_dotenv
from database.database import DB
from stripe_utils.stripe_utils import StripeHelper
from .handlers import *
logging.basicConfig(level=logging.INFO)
def build_app():
    load_dotenv()
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    stripe_secret = os.environ["STRIPE_SECRET_KEY"]
    db_url = os.getenv("DATABASE_URL", "sqlite:///bot.db")
    DB.init(db_url)
    stripe = StripeHelper(stripe_secret)
    app = ApplicationBuilder().token(bot_token).build()
    app.bot_data["stripe"] = stripe
    return app
