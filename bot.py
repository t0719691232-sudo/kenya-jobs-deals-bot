import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.environ["BOT_TOKEN"]


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Kenya Jobs & Deals Bot is running!")

    def log_message(self, format, *args):
        pass


def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("💼 Jobs", callback_data="jobs"),
            InlineKeyboardButton("💻 Online Gigs", callback_data="gigs"),
        ],
        [
            InlineKeyboardButton("💰 Business", callback_data="business"),
            InlineKeyboardButton("🚗 Car Deals", callback_data="cars"),
        ],
        [
            InlineKeyboardButton("📱 Electronics", callback_data="electronics"),
            InlineKeyboardButton("⭐ Premium", callback_data="premium"),
        ],
        [
            InlineKeyboardButton("📢 Advertise With Us", callback_data="advertise"),
        ],
    ]

    await update.message.reply_text(
        "🇰🇪 *Welcome to Kenya Jobs & Deals!*\n\n"
        "Find jobs, online gigs, business opportunities, "
        "car deals and electronics deals.\n\n"
        "Choose an option below:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    messages = {
        "jobs": "💼 *JOBS*\n\nJob opportunities will be posted here soon.",
        "gigs": "💻 *ONLINE GIGS*\n\nOnline work opportunities will be posted here soon.",
        "business": "💰 *BUSINESS OPPORTUNITIES*\n\nBusiness opportunities will be posted here soon.",
        "cars": "🚗 *CAR DEALS*\n\nCar deals and prices will be posted here soon.",
        "electronics": "📱 *ELECTRONICS*\n\nElectronics deals will be posted here soon.",
        "premium": "⭐ *PREMIUM*\n\nPremium alerts and exclusive opportunities will be available here.",
        "advertise": "📢 *ADVERTISE WITH US*\n\nContact the administrator to advertise your business.",
    }

    await query.edit_message_text(
        messages.get(query.data, "Please choose an option."),
        parse_mode="Markdown",
    )


def main():
    threading.Thread(target=start_web_server, daemon=True).start()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    print("Bot is running...")
    app.run_polling()

                                                        
if __name__ == "__main__":
