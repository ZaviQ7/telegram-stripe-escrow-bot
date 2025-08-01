import os
import stripe
import logging
import asyncio
from flask import Flask, request, abort, Response
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from telegram import Bot

from database.database import DB
from database.models import User, Deal, Milestone, Review, Referral, Dispute
from bot.keyboards import trade_in_progress_keyboard, milestone_project_keyboard

log = logging.getLogger(__name__)

class AuthModelView(ModelView):
    """A ModelView protected by basic auth, for the admin panel."""
    def is_accessible(self):
        auth = request.authorization
        return auth and auth.username == os.getenv('ADMIN_USER') and auth.password == os.getenv('ADMIN_PASS')

    def inaccessible_callback(self, name, **kwargs):
        return Response('<h1>Login Required</h1>'
                        'Could not verify your access level for that page.', 401,
                        {'WWW-Authenticate': 'Basic realm="Login Required"'})

def create_flask_app():
    """Creates and configures the Flask application and its routes."""
    app = Flask(__name__)
    app.config['FLASK_ADMIN_SWATCH'] = 'cerulean'
    app.secret_key = os.getenv("SECRET_KEY", "super-secret-key-for-flask")

    # Initialize Stripe API key for this context
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

    # --- Admin Dashboard Setup ---
    admin = Admin(app, name='EscrowBot Admin', template_mode='bootstrap3')
    # This is now safe because DB.init() has already been called in main.py
    admin.add_view(AuthModelView(User, DB.session()))
    admin.add_view(AuthModelView(Deal, DB.session()))
    admin.add_view(AuthModelView(Milestone, DB.session()))
    admin.add_view(AuthModelView(Review, DB.session()))
    admin.add_view(AuthModelView(Referral, DB.session()))
    admin.add_view(AuthModelView(Dispute, DB.session()))

    # --- Stripe Webhook Handler ---
    @app.route("/stripe/webhook", methods=["POST"])
    def webhook():
        """Handles incoming events from Stripe."""
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
            metadata = pi["metadata"]
            bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

            if 'milestone_id' in metadata:
                milestone = session.get(Milestone, int(metadata['milestone_id']))
                if milestone and not milestone.payment_intent_id:
                    milestone.payment_intent_id = payment_intent_id
                    deal = milestone.deal
                    session.commit()
                    log.info("Milestone %s for Deal %s funded.", milestone.id, deal.id)
                    text, keyboard = milestone_project_keyboard(deal)
                    asyncio.run(bot.send_message(chat_id=deal.creator.telegram_id, text=text, reply_markup=keyboard, parse_mode='Markdown'))
                    asyncio.run(bot.send_message(chat_id=deal.counterparty.telegram_id, text=text, reply_markup=keyboard, parse_mode='Markdown'))

            elif 'deal_id' in metadata:
                deal = session.get(Deal, int(metadata['deal_id']))
                if deal and deal.status == 'pending':
                    deal.status = 'funded'
                    deal.trade_status = 'funded'
                    deal.payment_intent_id = payment_intent_id
                    session.commit()
                    log.info("One-Time Trade Deal %s funded.", deal.id)
                    funded_text = f"💰 **Trade Funded!**\n\nEscrow for '{deal.title}' is now funded. Seller, please ship the item and click 'Mark as Shipped'."
                    keyboard = trade_in_progress_keyboard(deal)
                    asyncio.run(bot.send_message(chat_id=deal.creator.telegram_id, text=funded_text, reply_markup=keyboard, parse_mode='Markdown'))
                    asyncio.run(bot.send_message(chat_id=deal.counterparty.telegram_id, text=funded_text, reply_markup=keyboard, parse_mode='Markdown'))

        session.close()
        return {"status": "ok"}

    # --- Static Pages for Stripe Redirects ---
    @app.route("/success.html")
    def success():
        return "<h1>Success!</h1><p>Your action was completed successfully. You can now return to Telegram.</p>"

    @app.route("/cancel.html")
    def cancel():
        return "<h1>Action Cancelled</h1><p>You have cancelled the action. You can close this window.</p>"

    return app