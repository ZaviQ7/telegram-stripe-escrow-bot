from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import Deal

# --- Main Menu ---
def main_menu_keyboard():
    """Generates the main menu keyboard shown on /start."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Start One-Time Trade", callback_data="start_trade")],
        [InlineKeyboardButton("🏗️ Start Milestone Project", callback_data="start_milestone_project")],
        [InlineKeyboardButton("👤 My Profile & Deals", callback_data="view_profile")],
        [InlineKeyboardButton("🔗 Connect Stripe Account", callback_data="connect_stripe")],
    ])

# --- One-Time Trade Keyboards ---
def trade_confirmation_keyboard(deal_id: int):
    """Shown to the creator of the trade before sending the offer."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm & Send Offer", callback_data=f"send_offer:{deal_id}")],
        [InlineKeyboardButton("🚫 Cancel", callback_data=f"cancel_deal:{deal_id}")],
    ])

def trade_invite_keyboard(deal_id: int):
    """Shown to the buyer when they are invited to a trade."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pay via Stripe", callback_data=f"pay_trade:{deal_id}")],
        [InlineKeyboardButton("Decline", callback_data=f"decline_trade:{deal_id}")],
    ])

def trade_in_progress_keyboard(deal: Deal):
    """The main keyboard for a one-time trade, changes based on status."""
    keyboard = []
    if deal.status == 'disputed':
        keyboard.append([InlineKeyboardButton("‼️ Dispute Under Review", callback_data="noop")])
        return InlineKeyboardMarkup(keyboard)

    if deal.trade_status == "funded":
        keyboard.append([InlineKeyboardButton("🚚 Mark as Shipped", callback_data=f"mark_shipped:{deal.id}")])
    
    if deal.trade_status == "shipped":
        keyboard.append([InlineKeyboardButton("✅ Confirm Delivery", callback_data=f"confirm_delivery:{deal.id}")])

    if deal.trade_status in ["funded", "shipped"]:
         keyboard.append([InlineKeyboardButton("‼️ Raise Dispute", callback_data=f"dispute_deal:{deal.id}")])

    return InlineKeyboardMarkup(keyboard)

# --- Milestone Project Keyboard ---
def milestone_project_keyboard(deal: Deal):
    """Generates the entire text and keyboard for a milestone project dashboard."""
    status_emoji = {"pending": "⏳", "funded": "💰", "completed": "✅", "cancelled": "🚫", "disputed": "‼️"}
    deal_status = deal.status
    if deal.status == "pending" and any(m.payment_intent_id for m in deal.milestones):
        deal_status = "partially_funded"
        status_emoji["partially_funded"] = "💰"

    text = (
        f"**Project #{deal.id}: {deal.title}**\n"
        f"Status: {status_emoji.get(deal_status, '')} **{deal_status.replace('_', ' ').upper()}**\n"
        f"Client: @{deal.creator.username}\n"
        f"Contractor: @{deal.counterparty.username}\n"
        f"Total: ${deal.total_amount:.2f} {deal.currency.upper()}\n"
    )
    if deal.status == "disputed":
        text += f"\n**This project is currently in dispute. All actions are locked.**\n"

    text += "-----------------------------------\n**Milestones:**\n"
    keyboard = []
    has_funded_milestones = False

    for ms in sorted(deal.milestones, key=lambda m: m.id):
        button = None
        if ms.is_released:
            status = "✅ Released"
        elif ms.payment_intent_id:
            status = "💰 Funded"
            has_funded_milestones = True
            if deal.status != "disputed":
                button = InlineKeyboardButton(f"Release ${ms.amount:.2f}", callback_data=f"release_milestone:{ms.id}")
        else:
            status = "⏳ Pending"
            if deal.status != "disputed":
                button = InlineKeyboardButton(f"Deposit ${ms.amount:.2f}", callback_data=f"deposit_milestone:{ms.id}")
        
        text += f"- (ID: {ms.id}) {ms.name} (${ms.amount:.2f}): **{status}**\n"
        if button:
            keyboard.append([button])

    control_buttons = [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_deal:{deal.id}")]
    if deal.status not in ["completed", "cancelled", "disputed"] and has_funded_milestones:
        control_buttons.append(InlineKeyboardButton("‼️ Dispute Project", callback_data=f"dispute_deal:{deal.id}"))
    keyboard.append(control_buttons)
    
    return text, InlineKeyboardMarkup(keyboard)

# --- Other Keyboards ---
def rating_keyboard(deal_id: int, reviewee_id: int):
    """Generates a keyboard for leaving a 1-5 star rating."""
    star_buttons = [
        InlineKeyboardButton(f"{'⭐'*i}", callback_data=f"rate:{deal_id}:{reviewee_id}:{i}")
        for i in range(1, 6)
    ]
    return InlineKeyboardMarkup([star_buttons, [InlineKeyboardButton("Skip", callback_data=f"skip_rating:{deal_id}")]])

def checkout_keyboard(url: str):
    """A keyboard with a single button to the Stripe Checkout URL."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("💳 Proceed to Payment", url=url)]])

def onboarding_keyboard(url: str):
    """A keyboard with a single button to the Stripe onboarding URL."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Connect Stripe Account", url=url)]])
