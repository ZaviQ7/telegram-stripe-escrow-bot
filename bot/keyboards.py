
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
def checkout_keyboard(url: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton("💳 Proceed to Payment", url=url)]])
def onboarding_keyboard(url: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Connect Stripe Account", url=url)]])
