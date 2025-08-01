import os
import threading
from dotenv import load_dotenv

# 1. Load environment variables from .env file FIRST.
load_dotenv()

# 2. Initialize the database SECOND.
from database.database import DB
db_url = os.getenv("DATABASE_URL", "sqlite:///bot.db")
DB.init(db_url)

# 3. NOW, it's safe to import the rest of the application components.
from waitress import serve
from bot.bot import build_app
from webhooks.server import create_flask_app

def run_bot(app):
    """Starts the Telegram bot's polling loop."""
    print("Bot is polling for messages...")
    app.run_polling()

def run_webhook_server(app):
    """Starts the web server for Stripe webhooks and the admin panel."""
    port = int(os.getenv("PORT", "8080"))
    print(f"Webhook server and admin dashboard running on http://0.0.0.0:{port}")
    serve(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    # Build the Telegram bot application.
    # The Application object automatically creates and starts its own job_queue.
    app = build_app()
    
    # Create the Flask web application
    flask_app = create_flask_app()
    
    # NOTE: We no longer create a separate scheduler.
    # The `app` object's built-in `job_queue` is automatically passed to all handlers
    # via the `context` object (as `context.job_queue`).
    # Our existing code in `handlers.py` and `scheduler.py` already uses this correctly.

    # Run the Flask web server in a separate thread
    threading.Thread(target=run_webhook_server, args=(flask_app,), daemon=True).start()
    
    # Run the bot in the main thread
    run_bot(app)