import os
import stripe
import logging
import asyncio
from flask import Flask, request, abort, Response
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from dotenv import load_dotenv
from telegram import Bot

from database.database import DB
from database.models import User, Deal, Milestone, Review, Referral, Dispute
from bot.keyboards import trade_in_progress_keyboard
from scheduler import remove_job

# --- Setup ---
load_dotenv()
app = Flask(__name__)
app.config['FLASK_ADMIN_SWATCH'] = 'cerulean'
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key-for-flask")
log = logging.getLogger(__name__)

# --- Admin Dashboard Setup (Same as before, but included for completeness) ---
class AuthModelView(ModelView):
    def is_accessible(self):
        auth = request.authorization
        return auth and auth.username == os.getenv('ADMIN_USER') and auth.password == os.getenv('ADMIN_PASS')
    def inaccessible_callback(self, name, **kwargs):
        return Response('Login Required', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

admin = Admin(app, name='EscrowBot Admin', template_mode='bootstrap3')
admin.add_view(AuthModelView(User, DB.session()))
admin.add_view(AuthModelView(Deal, DB.session()))
admin.add_view(AuthModelView(Review, DB.session()))
admin.add_view(AuthModelView(Referral, DB.session()))
admin.add_view(AuthModelView(Dispute, DB.session()))

# --- Async Helper ---
async def send_telegram_message_with_keyboard(bot, chat_id: int, text: str, keyboard):
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode='Markdown')

# --- Stripe Webhook Handler ---
@app.route("/stripe/webhook", methods=["POST"])
def webhook():
    try:
        event = stripe.Webhook.construct_event(
            request.data, request.headers.get("stripe-signature", ""), os.getenv("STRIPE_WEBHOOK_SECRET")
        )
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        log.error("Webhook signature verification failed: %s", e)
        return abort(400, "Invalid signature")

    session = DB.session()
    
    if event["type"] == "checkout.session.completed":
        session_data = event["data"]["object"]
        payment_intent_id = session_data.get("payment_intent")
        
        pi = stripe.PaymentIntent.retrieve(payment_intent_id)
        deal_id = int(pi["metadata"]["deal_id"])
        
        deal = session.get(Deal, deal_id)
        if deal and deal.status == 'pending':
            # Remove offer expiration job
            if deal.auto_job_id:
                # This requires access to the job queue, handled in the bot for simplicity
                pass

            deal.status = 'funded'
            deal.trade_status = 'funded'
            deal.payment_intent_id = payment_intent_id # SAVE THE PAYMENT INTENT ID
            session.commit()
            log.info("One-Time Trade Deal %s successfully funded.", deal_id)

            bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
            funded_text = f"💰 **Trade Funded!**\n\nEscrow for '{deal.title}' is now funded. Seller, please ship the item and click 'Mark as Shipped'."
            keyboard = trade_in_progress_keyboard(deal)
            asyncio.run(send_telegram_message_with_keyboard(bot, deal.creator.telegram_id, funded_text, keyboard))
            asyncio.run(send_telegram_message_with_keyboard(bot, deal.counterparty.telegram_id, funded_text, keyboard))

    session.close()
    return {"status": "ok"}

# --- Static Pages for Redirects ---
@app.route("/success.html")
def success(): return "<h1>Success!</h1><p>You can return to Telegram.</p>"
@app.route("/cancel.html")
def cancel(): return "<h1>Cancelled</h1><p>You can return to Telegram.</p>"
