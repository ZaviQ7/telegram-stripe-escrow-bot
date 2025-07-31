
import threading, os
from waitress import serve
from bot.bot import build_app
from webhooks.server import app as flask_app
from database.database import DB
def run_bot(app):
    app.run_polling()
def run_webhook():
    port = int(os.getenv("PORT", "8080"))
    serve(flask_app, host="0.0.0.0", port=port)
if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "sqlite:///bot.db")
    DB.init(db_url)
    app = build_app()
    threading.Thread(target=run_webhook, daemon=True).start()
    run_bot(app)
