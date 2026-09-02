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


# =========================
# CONFIGURATION
# =========================

TOKEN = os.environ["BOT_TOKEN"].strip()


# =========================
# RENDER HEALTH SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(
            b"Kenya Jobs & Deals Bot is running!"
        )

    def log_message(self, format, *args):
        pass


def start_web_server():
    port = int(os.environ.get("PORT", 10000))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    server.serve_forever()


# =========================
# CATEGORY MENU
# =========================

def category_keyboard():

    keyboard = [
        [
            InlineKeyboardButton(
                "💼 Jobs",
                callback_data="jobs"
            ),
            InlineKeyboardButton(
                "💻 Online Gigs",
                callback_data="gigs"
            ),
        ],
        [
            InlineKeyboardButton(
                "💰 Business",
                callback_data="business"
            ),
            InlineKeyboardButton(
                "🚗 Car Deals",
                callback_data="cars"
            ),
        ],
        [
            InlineKeyboardButton(
                "📱 Electronics",
                callback_data="electronics"
            ),
            InlineKeyboardButton(
                "⭐ Premium",
                callback_data="premium"
            ),
        ],
        [
            InlineKeyboardButton(
                "📢 Advertise With Us",
                callback_data="advertise"
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================
# START COMMAND
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🇰🇪 *Welcome to Kenya Jobs & Deals!*\n\n"
        "Find jobs, online gigs, business opportunities, "
        "car deals and electronics deals.\n\n"
        "Choose an option below:",
        reply_markup=category_keyboard(),
        parse_mode="Markdown",
    )


# =========================
# LISTING DATA
# =========================

LISTINGS = {

    "jobs": (
        "💼 *LATEST JOBS*\n\n"

        "1️⃣ *Sales Representative*\n"
        "📍 Nairobi\n"
        "💰 KSh 30,000 - 45,000\n"
        "📝 Full-time\n\n"

        "2️⃣ *Customer Service Agent*\n"
        "📍 Nairobi\n"
        "💰 KSh 25,000 - 35,000\n"
        "📝 Full-time\n\n"

        "3️⃣ *Office Administrator*\n"
        "📍 Mombasa\n"
        "💰 KSh 35,000 - 50,000\n"
        "📝 Full-time\n\n"

        "📌 More jobs will be added regularly."
    ),

    "gigs": (
        "💻 *ONLINE GIGS*\n\n"

        "1️⃣ *Data Entry*\n"
        "💰 KSh 500 - 2,000 per task\n"
        "🌍 Remote\n\n"

        "2️⃣ *Content Writing*\n"
        "💰 KSh 1,000 - 5,000 per article\n"
        "🌍 Remote\n\n"

        "3️⃣ *Social Media Management*\n"
        "💰 KSh 10,000 - 30,000/month\n"
        "🌍 Remote\n\n"

        "📌 New online opportunities coming soon."
    ),

    "business": (
        "💰 *BUSINESS OPPORTUNITIES*\n\n"

        "1️⃣ *Small Retail Business*\n"
        "📍 Nairobi\n"
        "💰 Starting from KSh 50,000\n\n"

        "2️⃣ *Food Business Opportunity*\n"
        "📍 Kiambu\n"
        "💰 Starting from KSh 30,000\n\n"

        "3️⃣ *Mobile Money Business*\n"
        "📍 Various locations\n"
        "💰 Investment varies\n\n"

        "📌 Contact the advertiser for details."
    ),

    "cars": (
        "🚗 *CAR DEALS*\n\n"

        "1️⃣ *Toyota Axio*\n"
        "📅 2018\n"
        "💰 KSh 1,450,000\n"
        "📍 Nairobi\n\n"

        "2️⃣ *Toyota Fielder*\n"
        "📅 2017\n"
        "💰 KSh 1,350,000\n"
        "📍 Nairobi\n\n"

        "3️⃣ *Mazda Demio*\n"
        "📅 2016\n"
        "💰 KSh 850,000\n"
        "📍 Mombasa\n\n"

        "📌 Always verify the vehicle before payment."
    ),

    "electronics": (
        "📱 *ELECTRONICS DEALS*\n\n"

        "1️⃣ *Samsung Galaxy Smartphone*\n"
        "💰 KSh 25,000\n"
        "📍 Nairobi\n\n"

        "2️⃣ *HP Laptop*\n"
        "💰 KSh 45,000\n"
        "📍 Nairobi\n\n"

        "3️⃣ *Bluetooth Speaker*\n"
        "💰 KSh 5,000\n"
        "📍 Nationwide delivery\n\n"

        "📌 Contact the seller for availability."
    ),

    "premium": (
        "⭐ *PREMIUM MEMBERSHIP*\n\n"

        "Get access to:\n\n"
        "✅ Early job alerts\n"
        "✅ Exclusive opportunities\n"
        "✅ Premium business listings\n"
        "✅ Special deals\n\n"

        "💳 Premium membership will be available soon."
    ),

    "advertise": (
        "📢 *ADVERTISE WITH US*\n\n"

        "Do you have:\n\n"
        "💼 A job vacancy?\n"
        "💰 A business opportunity?\n"
        "🚗 A car for sale?\n"
        "📱 Electronics for sale?\n\n"

        "You can advertise your listing to our audience.\n\n"

        "📩 Contact the administrator to get started."
    ),
}


# =========================
# LISTING BUTTONS
# =========================

def listing_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔙 Back to Categories",
                callback_data="home"
            )
        ]
    ])


# =========================
# BUTTON HANDLER
# =========================

async def button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    # Return to main menu
    if query.data == "home":

        await query.edit_message_text(
            "🇰🇪 *Kenya Jobs & Deals*\n\n"
            "Choose a category below:",
            reply_markup=category_keyboard(),
            parse_mode="Markdown",
        )

        return

    # Show selected category
    message = LISTINGS.get(
        query.data,
        "Please choose an option."
    )

    await query.edit_message_text(
        message,
        reply_markup=listing_keyboard(),
        parse_mode="Markdown",
    )


# =========================
# MAIN
# =========================

def main():

    # Start Render health server
    threading.Thread(
        target=start_web_server,
        daemon=True
    ).start()

    # Create Telegram application
    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler("start", start)
    )

    # Buttons
    app.add_handler(
        CallbackQueryHandler(button)
    )

    print("🇰🇪 Kenya Jobs & Deals Bot is running...")

    # Start Telegram polling
    app.run_polling(
        drop_pending_updates=True
    )


# =========================
# START PROGRAM
# =========================

if __name__ == "__main__":
    main()
