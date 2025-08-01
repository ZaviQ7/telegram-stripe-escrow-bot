import logging
from datetime import datetime
from telegram.ext import Application

from database.database import DB
from database.models import Deal
from stripe_utils.stripe_utils import StripeHelper

log = logging.getLogger(__name__)

def schedule_job(job_queue, job_id: str, deal_id: int, job_type: str, run_time: datetime):
    """Adds a job to the APScheduler queue."""
    job_queue.run_once(run_scheduled_job, run_time, context={'deal_id': deal_id, 'job_type': job_type}, name=job_id)
    log.info(f"Scheduled job '{job_id}' for deal {deal_id} to run at {run_time}.")

def remove_job(job_queue, job_id: str):
    """Removes a job from the queue by its name (ID)."""
    if not job_id: return
    jobs = job_queue.get_jobs_by_id(job_id)
    if jobs:
        for job in jobs:
            job.schedule_removal()
        log.info(f"Removed scheduled job '{job_id}'.")

async def run_scheduled_job(context: Application):
    """The callback function that APScheduler executes."""
    # THIS IS THE FIX: The import is moved inside the function to break the circular dependency.
    from bot.handlers import _prompt_for_ratings 

    job_context = context.job.context
    deal_id = job_context['deal_id']
    job_type = job_context['job_type']
    
    session = DB.session()
    try:
        deal = session.get(Deal, deal_id)
        if not deal:
            log.info(f"Scheduled job for deal {deal_id} is no longer relevant (deal not found).")
            return

        log.info(f"Running scheduled job '{job_type}' for deal {deal_id}.")
        stripe: StripeHelper = context.application.bot_data['stripe']

        if job_type == "expire_offer" and deal.status == 'pending':
            deal.status = 'cancelled'
            deal.admin_notes = 'Offer expired after 24 hours without payment.'
            session.commit()
            await context.bot.send_message(chat_id=deal.creator.telegram_id, text=f"Your trade offer for '{deal.title}' has expired as the buyer did not pay within 24 hours.")

        elif job_type == "check_unshipped_trades" and deal.trade_status == 'funded':
            stripe.refund_payment(deal.payment_intent_id)
            deal.status = 'cancelled'
            deal.trade_status = 'refunded'
            deal.admin_notes = 'Automatically refunded buyer as seller did not ship within 7 days.'
            session.commit()
            refund_text = f"Deal #{deal.id} for '{deal.title}' has been automatically cancelled and the buyer refunded because the seller did not mark it as shipped within 7 days."
            await context.bot.send_message(chat_id=deal.creator.telegram_id, text=refund_text)
            await context.bot.send_message(chat_id=deal.counterparty.telegram_id, text=refund_text)

        elif job_type == "check_unconfirmed_deliveries" and deal.trade_status == 'shipped':
            stripe.transfer(deal.total_amount, deal.currency, deal.creator.stripe_account_id, f"deal-{deal.id}")
            deal.status = 'completed'
            deal.trade_status = 'completed'
            deal.admin_notes = 'Automatically released funds to seller as buyer did not confirm delivery within 7 days.'
            session.commit()
            release_text = f"Funds for Deal #{deal.id} ('{deal.title}') have been automatically released to the seller because delivery was not confirmed within 7 days."
            await context.bot.send_message(chat_id=deal.creator.telegram_id, text=release_text)
            await context.bot.send_message(chat_id=deal.counterparty.telegram_id, text=release_text)
            await _prompt_for_ratings(context, deal)

    except Exception as e:
        log.error(f"Error in scheduled job for deal {deal_id}: {e}")
    finally:
        session.close()