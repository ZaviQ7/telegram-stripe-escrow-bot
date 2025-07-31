# Telegram Escrow Payment Bot

This is a full-featured Telegram bot and web backend for secure peer-to-peer (P2P) payments, milestone-based project escrow, and one-time trades, powered by Stripe Connect. The system supports advanced workflows: milestone deals, automated edge-case handling (offer expiration, auto-release, auto-refund), disputes with admin resolution, and a web-based admin dashboard.

---

## **Project Structure**

```
telegram-stripe-bot/
├── bot/
│   ├── __init__.py
│   ├── bot.py
│   ├── handlers.py
│   └── keyboards.py
├── database/
│   ├── __init__.py
│   ├── database.py
│   └── models.py
├── stripe_utils/
│   ├── __init__.py
│   └── stripe_utils.py
├── webhooks/
│   ├── __init__.py
│   └── server.py
├── scheduler.py
├── requirements.txt
├── .env.example
└── main.py
```

---

## **1. Prerequisites**

- Python 3.10+
- A Stripe account ([get API keys](https://dashboard.stripe.com/apikeys))
- Telegram bot token ([@BotFather](https://t.me/BotFather))
- A server (or local machine for dev) **with a public HTTPS endpoint** (required for Stripe webhooks; use [ngrok](https://ngrok.com/) for local testing)
- Git (optional, for version control)

---

## **2. Installation & Setup**

### **A. Extract the ZIP**

Unzip the archive:
```bash
unzip telegram_stripe_bot_final.zip
cd telegram-stripe-bot
```

### **B. Python Environment**

Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### **C. Install Dependencies**

```bash
pip install -r requirements.txt
```

### **D. Configure Environment Variables**

Copy `.env.example` to `.env` and fill out your credentials:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
STRIPE_SECRET_KEY=sk_test_...   # Use your Stripe TEST key for dev
STRIPE_WEBHOOK_SECRET=whsec_... # Set this after creating your webhook endpoint in Stripe
BASE_URL=https://your-public-url.com  # MUST be public, e.g. your ngrok or production URL
DATABASE_URL=sqlite:///bot.db   # Or your Postgres/MySQL URI
ADMIN_CHAT_ID=123456789         # Your Telegram user ID
PLATFORM_FEE_PERCENT=2.5        # Platform fee (as percent, optional)
ADMIN_USER=admin                # Web dashboard login
ADMIN_PASS=your_secure_password # Web dashboard password
```

> **TIP:** To get your Stripe webhook secret, set up a webhook in your [Stripe dashboard](https://dashboard.stripe.com/webhooks) pointing to `https://your-public-url.com/stripe/webhook`, trigger a payment, and copy the secret from Stripe.

---

## **3. Running the Application**

### **A. Start the Bot and Web Server**

```bash
python main.py
```

- This will start **both** the Telegram bot (polling for messages) and a Flask web server.
- The web server exposes:
  - Stripe webhook at `/stripe/webhook`
  - Static success/cancel pages for Stripe
  - Admin dashboard at `/admin` (HTTP Basic Auth)

### **B. (Optional) Running with Ngrok for Local Testing**

If running locally, expose your Flask server to the public internet:

```bash
ngrok http 8080
```
Copy the HTTPS URL and use it as your `BASE_URL` in `.env`.

---

## **4. Stripe Setup Steps**

1. **Create a [Stripe Connect Express](https://dashboard.stripe.com/settings/connect) platform.**
2. Add your test API keys to `.env`.
3. Add a webhook in the Stripe dashboard for your `BASE_URL/stripe/webhook`.
   - Listen for at least: `checkout.session.completed`
4. Instruct users (contractors/sellers) to connect their Stripe account via `/connect_stripe` in the Telegram bot.

---

## **5. Telegram Bot Usage**

- **Start:** `/start` to see the menu.
- **New milestone deal:** `/newdeal` (reply to a user for counterparty, follow prompts for title and milestones).
- **One-time trade:** Choose from main menu or use `/start_trade` (if implemented in menu).
- **Fund milestone/trade:** Click the Deposit/Pay button, pay via Stripe.
- **Release:** Client releases payment per milestone or on trade completion.
- **Dispute:** Buyer/Seller can raise a dispute, upload photo proof, and describe the issue.
- **Admin:** Use `/admin_split`, `/admin_refund`, `/admin_resolve` for advanced manual control (see code for usage).

---

## **6. Admin Dashboard**

- Access at: `http(s)://<BASE_URL>/admin`
- Login with credentials set in `.env`
- View/manage all Users, Deals, Reviews, Disputes, Referrals

---

## **7. Scheduled Automation**

- **Offer Expiration:** Unfunded trade offers are auto-cancelled after 24h.
- **Auto-Refund:** If seller doesn't ship within 7 days, buyer is auto-refunded.
- **Auto-Release:** If buyer doesn't confirm delivery in 7 days, funds auto-release to seller.
- **All scheduler logic is managed via `scheduler.py` and APScheduler.**

---

## **8. Customization/Deployment Notes**

- Can swap out `sqlite` for Postgres/MySQL in `DATABASE_URL`.
- Use a production WSGI server (Waitress, Gunicorn) for deployment.
- SSL/HTTPS is **mandatory** for Stripe webhooks.
- Consider extra authentication for `/admin` if deploying publicly.

---

## **9. Security & Compliance**

- Platform fees are supported via `PLATFORM_FEE_PERCENT`.
- All payments go through Stripe; sensitive data is not stored.
- Admins can split funds, issue refunds, or resolve disputes via bot commands or the web panel.
- Make sure you comply with all legal requirements in your region for holding and releasing funds!

---

# **Requirements Table: Client PDF vs. Implementation**

| Requirement (from PDF/Brief)                  | Status      | Notes                                                                |
|-----------------------------------------------|-------------|----------------------------------------------------------------------|
| Secure peer-to-peer escrow (deals/trades)     | **✅**      | All logic for trade, milestone, and deal flows implemented           |
| Multi-milestone support                       | **✅**      | Each milestone independently funded and released                      |
| Stripe Connect onboarding                     | **✅**      | Sellers/contractors onboard via `/connect_stripe`                    |
| Payments/escrow held via Stripe               | **✅**      | All funds held in Stripe until released or refunded                   |
| Admin dashboard for all data                  | **✅**      | Flask-Admin at `/admin` with login                                   |
| Raise and resolve disputes (with file proof)  | **✅**      | Users describe problem, upload image; admins notified                 |
| Admin manual split/refund commands            | **✅**      | `/admin_split`, `/admin_refund`, `/admin_resolve` in Telegram        |
| Scheduler: Offer expiration                   | **✅**      | 24h deadline on all offers                                           |
| Scheduler: Auto-refund on unshipped trades    | **✅**      | 7-day deadline; triggers Stripe refund                               |
| Scheduler: Auto-release on unconfirmed trades | **✅**      | 7-day deadline; triggers Stripe transfer                             |
| Ratings and reviews after completion          | **✅**      | Both parties prompted for rating and comment                         |
| Referrals, verification, free trades          | **✅**      | As per database model and brief                                      |
| All Stripe logic (deposits, transfers, refund)| **✅**      | Real Stripe integration for deposit, payout, refund                  |
| All bot and dashboard environment config      | **✅**      | Managed via `.env`                                                   |
| Code is production-grade, maintainable        | **✅**      | Fully modular, upgradable, testable                                  |

---

## **Support**

If you encounter issues or have questions, please check the code comments, or reach out to the developer. For Stripe-specific errors, consult [Stripe’s API docs](https://stripe.com/docs/api).