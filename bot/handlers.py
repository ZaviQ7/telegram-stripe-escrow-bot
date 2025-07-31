import os
import logging
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    ContextTypes, CommandHandler, ConversationHandler, MessageHandler, 
    CallbackQueryHandler, filters
)
from sqlalchemy.exc import NoResultFound
from sqlalchemy import func, desc

from database.database import DB
from database.models import User, Deal, Review, Referral, Dispute
from stripe_utils.stripe_utils import StripeHelper
from .keyboards import *
from scheduler import schedule_job, remove_job

log = logging.getLogger(__name__)

# --- Conversation States & Admin Filter (Same as before) ---
ASK_COUNTERPARTY, ASK_DESCRIPTION, ASK_AMOUNT = range(3)
ASK_DISPUTE_REASON, ASK_DISPUTE_PROOF = range(3, 5)
try:
    ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID"))
    admin_filter = filters.User(user_id=ADMIN_ID)
except (ValueError, TypeError):
    admin_filter = filters.User(user_id=0)

# --- Helper Functions ---
def _get_or_create_user(session, tg_user):
    try:
        user = session.query(User).filter_by(telegram_id=tg_user.id).one()
        if user.username != tg_user.username:
            user.username = tg_user.username
            session.commit()
        return user
    except NoResultFound:
        u = User(telegram_id=tg_user.id, username=tg_user.username)
        session.add(u)
        session.commit()
        return u

async def _prompt_for_ratings(context: ContextTypes.DEFAULT_TYPE, deal: Deal):
    """Sends rating prompts to both parties of a completed deal."""
    buyer_text = f"Trade complete! Please rate your experience with the seller, @{deal.creator.username}."
    await context.bot.send_message(
        chat_id=deal.counterparty.telegram_id,
        text=buyer_text,
        reply_markup=rating_keyboard(deal.id, deal.creator.id)
    )
    seller_text = f"Trade complete! Please rate your experience with the buyer, @{deal.counterparty.username}."
    await context.bot.send_message(
        chat_id=deal.creator.telegram_id,
        text=seller_text,
        reply_markup=rating_keyboard(deal.id, deal.counterparty.id)
    )

# --- Main Command & Menu Handlers (Same as before) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (Implementation from Phase 3)
    pass

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (Implementation from Phase 1)
    pass

# --- Trade & Dispute Conversations (Same as before) ---
# ... (trade_ask_counterparty, trade_ask_description, etc.)
# ... (dispute_start, dispute_ask_reason, etc.)

# --- Admin Commands ---
async def admin_split_funds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /admin_split [deal_id] [amount_to_seller]"""
    try:
        _, deal_id_str, seller_amount_str = context.args
        deal_id = int(deal_id_str)
        seller_amount = float(seller_amount_str)
    except (ValueError, IndexError):
        await update.message.reply_text("Usage: /admin_split [deal_id] [amount_to_seller]")
        return

    session = DB.session()
    deal = session.get(Deal, deal_id)

    if not deal or not deal.payment_intent_id:
        await update.message.reply_text("Deal not found or not funded.")
        session.close()
        return
    if seller_amount < 0 or seller_amount > deal.total_amount:
        await update.message.reply_text("Invalid amount. Must be between 0 and the total deal amount.")
        session.close()
        return

    stripe: StripeHelper = context.bot_data["stripe"]
    buyer_refund_amount = deal.total_amount - seller_amount
    
    try:
        # 1. Transfer funds to seller
        if seller_amount > 0:
            stripe.transfer(seller_amount, deal.currency, deal.creator.stripe_account_id, f"deal-{deal.id}")
        
        # 2. Refund the rest to the buyer
        if buyer_refund_amount > 0:
            stripe.refund_payment(deal.payment_intent_id, int(buyer_refund_amount * 100))

        # 3. Update deal status
        deal.status = "completed"
        deal.admin_notes = f"Dispute resolved by admin with a split. Seller gets ${seller_amount:.2f}, Buyer refunded ${buyer_refund_amount:.2f}."
        session.commit()

        # 4. Notify everyone
        resolution_text = (
            f"Dispute for Deal #{deal.id} has been resolved by an admin.\n"
            f"- The seller (@{deal.creator.username}) has been paid ${seller_amount:.2f}.\n"
            f"- The buyer (@{deal.counterparty.username}) has been refunded ${buyer_refund_amount:.2f}."
        )
        await update.message.reply_text(f"✅ Split successful. {resolution_text}")
        await context.bot.send_message(chat_id=deal.creator.telegram_id, text=resolution_text)
        await context.bot.send_message(chat_id=deal.counterparty.telegram_id, text=resolution_text)

    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")
    finally:
        session.close()

# ... (All other handlers from previous phases are here)