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

# --- Conversation States ---
# Trade Creation
ASK_COUNTERPARTY, ASK_DESCRIPTION, ASK_AMOUNT = range(3)
# Dispute Creation
ASK_DISPUTE_REASON, ASK_DISPUTE_PROOF = range(3, 5)

# --- Admin Filter ---
try:
    ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID"))
    admin_filter = filters.User(user_id=ADMIN_ID)
except (ValueError, TypeError):
    log.warning("ADMIN_CHAT_ID is not set. Admin commands will not be available.")
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

# --- Main Command & Menu Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the main menu and handles referral links."""
    session = DB.session()
    new_user = _get_or_create_user(session, update.effective_user)
    
    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0].split('_')[1])
            if referrer_id != new_user.telegram_id and not new_user.referral_received:
                referrer = session.query(User).filter_by(telegram_id=referrer_id).first()
                if referrer:
                    referral = Referral(referrer_id=referrer.id, referred_user_id=new_user.id)
                    session.add(referral)
                    session.commit()
                    await update.message.reply_text(f"Welcome! You were referred by @{referrer.username}.")
        except (ValueError, IndexError):
            pass # Ignore malformed referral links

    await update.message.reply_text(
        "Welcome to the Secure Escrow Bot! What would you like to do?",
        reply_markup=main_menu_keyboard()
    )
    session.close()

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button presses from the main menu."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "start_trade":
        await query.message.reply_text("Who is the buyer? Please reply to one of their messages to select them.")
        return ASK_COUNTERPARTY
    elif query.data == "view_profile":
        await query.message.delete() # Clean up the menu
        await profile(update, context)
        return ConversationHandler.END
    elif query.data == "connect_stripe":
        await query.message.delete()
        await connect_stripe(update, context)
        return ConversationHandler.END
    else:
        await query.message.reply_text("This feature is coming soon!")
        return ConversationHandler.END

# --- One-Time Trade Conversation ---
async def trade_ask_counterparty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Action cancelled. Please reply to a user's message to start a trade.")
        return ConversationHandler.END
        
    context.user_data['counterparty_tg'] = update.message.reply_to_message.from_user
    await update.message.reply_text("What are you selling? (e.g., 'Nike Dunks - Size 10')")
    return ASK_DESCRIPTION

async def trade_ask_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['description'] = update.message.text
    await update.message.reply_text("What is the amount in USD to hold in escrow?")
    return ASK_AMOUNT

async def trade_ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount <= 0: raise ValueError("Amount must be positive")
    except ValueError:
        await update.message.reply_text("Please enter a valid, positive number.")
        return ASK_AMOUNT

    session = DB.session()
    seller = _get_or_create_user(session, update.effective_user)
    buyer = _get_or_create_user(session, context.user_data['counterparty_tg'])

    deal = Deal(
        creator_id=seller.id,
        counterparty_id=buyer.id,
        title=context.user_data['description'],
        total_amount=amount,
        deal_type='trade',
        status='pending'
    )
    session.add(deal)
    session.commit()

    summary_text = (
        f"**Trade Offer Summary:**\n\n"
        f"**Item:** {deal.title}\n"
        f"**Amount:** ${deal.total_amount:.2f} USD\n"
        f"**Seller:** @{seller.username}\n"
        f"**Buyer:** @{buyer.username}\n\n"
        f"Please confirm to send this offer to the buyer."
    )
    await update.message.reply_text(
        summary_text,
        reply_markup=trade_confirmation_keyboard(deal.id),
        parse_mode='Markdown'
    )
    session.close()
    return ConversationHandler.END

# --- Dispute Conversation ---
async def dispute_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, deal_id_str = query.data.split(":")
    context.user_data['dispute_deal_id'] = int(deal_id_str)
    await query.answer()
    await query.message.reply_text("You have started the dispute process. Please describe the issue in a single message.")
    return ASK_DISPUTE_REASON

async def dispute_ask_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['dispute_reason'] = update.message.text
    await update.message.reply_text("Thank you. Now, please upload a single photo as proof (e.g., a screenshot of the item not working, or incorrect item).")
    return ASK_DISPUTE_PROOF

async def dispute_process_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = DB.session()
    deal_id = context.user_data['dispute_deal_id']
    deal = session.get(Deal, deal_id)
    
    if deal.auto_job_id:
        remove_job(context.job_queue, deal.auto_job_id)

    deal.status = 'disputed'
    deal.admin_notes = f"Dispute raised by @{update.effective_user.username}."
    
    dispute = Dispute(
        deal_id=deal.id,
        raised_by_id=update.effective_user.id,
        reason=context.user_data['dispute_reason'],
        proof_file_id=update.message.photo[-1].file_id
    )
    session.add(dispute)
    session.commit()

    await update.message.reply_text("✅ Dispute submitted. An admin has been notified and will review your case shortly. All actions on this deal are now locked.")

    admin_text = (
        f"‼️ **DISPUTE ALERT: Deal #{deal.id}** ‼️\n\n"
        f"**User:** @{update.effective_user.username}\n"
        f"**Reason:** {dispute.reason}\n\n"
        f"Proof is attached. Use admin commands to resolve."
    )
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=dispute.proof_file_id, caption=admin_text)
    
    context.user_data.clear()
    session.close()
    return ConversationHandler.END

# --- Lifecycle & Button Handlers ---
async def trade_lifecycle_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action, deal_id_str = query.data.split(":")
    deal_id = int(deal_id_str)

    session = DB.session()
    deal = session.get(Deal, deal_id)
    user = update.effective_user

    if not deal:
        await query.edit_message_text("This trade was not found.")
        session.close()
        return

    if action == "send_offer":
        if user.id != deal.creator.telegram_id:
            session.close()
            return await query.answer("Only the seller can send the offer.", show_alert=True)
        
        job_id = f"expire_offer_{deal.id}"
        deal.auto_job_id = job_id
        session.commit()
        schedule_job(context.job_queue, job_id, deal.id, "expire_offer", datetime.now() + timedelta(hours=24))
        
        invite_text = (
            f"You've been invited to a secure trade by @{deal.creator.username}!\n\n"
            f"**Item:** {deal.title}\n"
            f"**Price:** ${deal.total_amount:.2f} USD\n\n"
            f"Funds will be held in escrow until you confirm you've received the item."
        )
        await context.bot.send_message(
            chat_id=deal.counterparty.telegram_id,
            text=invite_text,
            reply_markup=trade_invite_keyboard(deal.id)
        )
        await query.edit_message_text("✅ Offer sent to the buyer!")

    elif action == "pay_trade":
        if user.id != deal.counterparty.telegram_id:
            session.close()
            return await query.answer("Only the buyer can pay for this trade.", show_alert=True)
        
        buyer = deal.counterparty
        application_fee_cents = 0
        platform_fee_percent = float(os.getenv("PLATFORM_FEE_PERCENT", "0"))

        completed_deals_count = session.query(Deal).filter(
            ((Deal.creator_id == buyer.id) | (Deal.counterparty_id == buyer.id)),
            Deal.status == 'completed'
        ).count()

        if completed_deals_count == 0: pass 
        elif buyer.free_trades_remaining > 0:
            buyer.free_trades_remaining -= 1
        elif platform_fee_percent > 0:
            fee_amount = deal.total_amount * (platform_fee_percent / 100)
            application_fee_cents = int(fee_amount * 100)

        stripe: StripeHelper = context.bot_data["stripe"]
        base_url = os.environ["BASE_URL"]
        checkout_url = stripe.create_checkout_session(
            deal.id, deal.title, deal.total_amount, deal.currency, 
            f"{base_url}/success.html", f"{base_url}/cancel.html",
            application_fee_cents
        )
        
        await query.message.reply_text(
            "Click the button below to securely fund the escrow.",
            reply_markup=checkout_keyboard(checkout_url)
        )

    elif action == "mark_shipped":
        if user.id != deal.creator.telegram_id:
            session.close()
            return await query.answer("Only the seller can mark the item as shipped.", show_alert=True)
        
        deal.trade_status = "shipped"
        job_id = f"auto_release_{deal.id}"
        deal.auto_job_id = job_id
        session.commit()
        schedule_job(context.job_queue, job_id, deal.id, "check_unconfirmed_deliveries", datetime.now() + timedelta(days=7))
        
        shipped_text = f"🚚 **Item Shipped!**\n\n@{deal.creator.username} has marked the item '{deal.title}' as shipped. Buyer, please confirm delivery once you receive it."
        await query.edit_message_text(shipped_text, reply_markup=trade_in_progress_keyboard(deal))
        await context.bot.send_message(chat_id=deal.counterparty.telegram_id, text=shipped_text)

    elif action == "confirm_delivery":
        if user.id != deal.counterparty.telegram_id:
            session.close()
            return await query.answer("Only the buyer can confirm delivery.", show_alert=True)
        
        if deal.auto_job_id:
            remove_job(context.job_queue, deal.auto_job_id)

        stripe: StripeHelper = context.bot_data["stripe"]
        stripe.transfer(deal.total_amount, deal.currency, deal.creator.stripe_account_id, f"deal-{deal.id}")
        
        deal.trade_status = "completed"
        deal.status = "completed"
        session.commit()

        completed_text = f"✅ **Trade Complete!**\n\nFunds for '{deal.title}' have been released to the seller. This trade is now complete."
        await query.edit_message_text(completed_text)
        await context.bot.send_message(chat_id=deal.creator.telegram_id, text=completed_text)
        await _prompt_for_ratings(context, deal)

    session.close()

async def rating_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    action = parts[0]

    if action == "skip_rating":
        await query.edit_message_text("Rating skipped.")
        return

    _, deal_id_str, reviewee_id_str, rating_str = parts
    session = DB.session()
    reviewer = _get_or_create_user(session, update.effective_user)
    existing_review = session.query(Review).filter_by(deal_id=int(deal_id_str), reviewer_id=reviewer.id).first()
    if existing_review:
        await query.edit_message_text("You have already left a review for this trade.")
        session.close()
        return

    new_review = Review(
        deal_id=int(deal_id_str),
        reviewer_id=reviewer.id,
        reviewee_id=int(reviewee_id_str),
        rating=int(rating_str)
    )
    session.add(new_review)
    session.commit()
    await query.edit_message_text(f"Thank you! You left a {'⭐'*int(rating_str)} rating.")
    session.close()

# --- Profile & Standalone Commands ---
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = DB.session()
    target_user = None
    message = update.message or update.callback_query.message

    if context.args:
        username_to_find = context.args[0].lstrip('@')
        target_user = session.query(User).filter(User.username.ilike(username_to_find)).first()
        if not target_user:
            await message.reply_text(f"User @{username_to_find} not found.")
            session.close()
            return
    else:
        target_user = _get_or_create_user(session, update.effective_user)

    completed_deals = session.query(Deal).filter(
        ((Deal.creator_id == target_user.id) | (Deal.counterparty_id == target_user.id)),
        Deal.status == 'completed'
    ).count()
    avg_rating, total_ratings = session.query(
        func.avg(Review.rating), func.count(Review.id)
    ).filter(Review.reviewee_id == target_user.id).first()
    recent_reviews = session.query(Review).filter(Review.reviewee_id == target_user.id).order_by(desc(Review.created)).limit(3).all()

    profile_text = f"**User Profile for @{target_user.username}**\n"
    if target_user.is_verified: profile_text += "✅ **Verified User**\n"
    profile_text += "-----------------------------------\n"
    profile_text += f"**Completed Trades:** {completed_deals}\n"
    profile_text += f"**Free Trades Remaining:** {target_user.free_trades_remaining}\n"
    profile_text += f"**Average Rating:** {f'{avg_rating:.2f} ⭐ ({total_ratings} ratings)' if total_ratings else 'No ratings yet.'}\n\n"
    profile_text += "**Recent Reviews:**\n"
    profile_text += '\n'.join([f"- {'⭐'*r.rating} from @{r.reviewer.username}" for r in recent_reviews]) if recent_reviews else "- No recent reviews.\n"

    await message.reply_text(profile_text, parse_mode='Markdown')
    session.close()

async def connect_stripe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = DB.session()
    user = _get_or_create_user(session, update.effective_user)
    message = update.message or update.callback_query.message

    if user.stripe_account_id:
        await message.reply_text("Your Stripe account is already connected.")
        session.close()
        return

    stripe: StripeHelper = context.bot_data["stripe"]
    base_url = os.environ["BASE_URL"]
    account_id = stripe.create_express_account()
    user.stripe_account_id = account_id
    session.commit()
    
    return_url = f"{base_url}/success.html"
    refresh_url = f"{base_url}/cancel.html"
    onboarding_link = stripe.onboarding_url(account_id, refresh_url, return_url)

    await message.reply_text(
        "Please connect your Stripe account to receive payments. Click the button below to get started.",
        reply_markup=onboarding_keyboard(onboarding_link)
    )
    session.close()

# --- Admin Commands ---
async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /admin_verify @username")
        return
    
    username = context.args[0].lstrip('@')
    session = DB.session()
    user = session.query(User).filter(User.username.ilike(username)).first()
    if not user:
        await update.message.reply_text(f"User @{username} not found.")
    else:
        user.is_verified = True
        session.commit()
        await update.message.reply_text(f"✅ User @{user.username} has been verified.")
        await context.bot.send_message(chat_id=user.telegram_id, text="Congratulations! You have been granted 'Verified' status by an admin.")
    session.close()

async def admin_split_funds(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        if seller_amount > 0:
            stripe.transfer(seller_amount, deal.currency, deal.creator.stripe_account_id, f"deal-{deal.id}")
        if buyer_refund_amount > 0:
            stripe.refund_payment(deal.payment_intent_id, int(buyer_refund_amount * 100))

        deal.status = "completed"
        deal.admin_notes = f"Dispute resolved by admin with a split. Seller gets ${seller_amount:.2f}, Buyer refunded ${buyer_refund_amount:.2f}."
        session.commit()

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