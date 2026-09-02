import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.environ["BOT_TOKEN"].strip()

# YOUR TELEGRAM ADMIN ID
ADMIN_ID = 1773092768


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
# LISTINGS
# =========================

LISTINGS = {
    "jobs": [],
    "gigs": [],
    "business": [],
    "cars": [],
    "electronics": [],
}


# =========================
# CATEGORY MENU
# =========================

def category_keyboard():

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
            InlineKeyboardButton(
                "📢 Advertise With Us",
                callback_data="advertise"
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🇰🇪 *Welcome to Kenya Jobs & Deals!*\n\n"
        "Find jobs, online gigs, business opportunities, "
        "car deals and electronics deals.\n\n"
        "Choose an option below:",
        reply_markup=category_keyboard(),
        parse_mode="Markdown",
    )


# =========================
# SHOW LISTINGS
# =========================

CATEGORY_NAMES = {
    "jobs": "💼 JOBS",
    "gigs": "💻 ONLINE GIGS",
    "business": "💰 BUSINESS OPPORTUNITIES",
    "cars": "🚗 CAR DEALS",
    "electronics": "📱 ELECTRONICS",
}


def get_listings_text(category):

    listings = LISTINGS.get(category, [])

    title = CATEGORY_NAMES.get(
        category,
        "LISTINGS"
    )

    if not listings:
        return (
            f"{title}\n\n"
            "No listings available yet.\n\n"
            "New opportunities will be posted here soon."
        )

    text = f"{title}\n\n"

    for number, listing in enumerate(listings, 1):

        text += (
            f"{number}️⃣ *{listing['title']}*\n"
            f"📍 {listing['location']}\n"
            f"💰 {listing['price']}\n"
            f"📞 {listing['contact']}\n"
            f"📝 {listing['description']}\n\n"
        )

    return text


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
# ADMIN MENU
# =========================

def admin_keyboard():

    keyboard = [
        [
            InlineKeyboardButton(
                "➕ Add Job",
                callback_data="add_jobs"
            ),
            InlineKeyboardButton(
                "➕ Add Gig",
                callback_data="add_gigs"
            ),
        ],
        [
            InlineKeyboardButton(
                "➕ Add Business",
                callback_data="add_business"
            ),
            InlineKeyboardButton(
                "➕ Add Car",
                callback_data="add_cars"
            ),
        ],
        [
            InlineKeyboardButton(
                "➕ Add Electronics",
                callback_data="add_electronics"
            ),
        ],
        [
            InlineKeyboardButton(
                "📋 View Jobs",
                callback_data="view_jobs"
            ),
            InlineKeyboardButton(
                "📋 View Gigs",
                callback_data="view_gigs"
            ),
        ],
        [
            InlineKeyboardButton(
                "📋 View Business",
                callback_data="view_business"
            ),
            InlineKeyboardButton(
                "📋 View Cars",
                callback_data="view_cars"
            ),
        ],
        [
            InlineKeyboardButton(
                "📋 View Electronics",
                callback_data="view_electronics"
            ),
        ],
        [
            InlineKeyboardButton(
                "🔙 Main Menu",
                callback_data="home"
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "⛔ You are not authorized to access the admin panel."
        )

        return

    await update.message.reply_text(
        "🔐 *ADMIN PANEL*\n\n"
        "Welcome, Admin.\n\n"
        "Choose an action:",
        reply_markup=admin_keyboard(),
        parse_mode="Markdown",
    )


# =========================
# ADMIN ADD LISTING
# =========================

async def admin_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    category = context.user_data.get("adding_category")

    if not category:
        return

    text = update.message.text.strip()

    lines = text.split("\n")

    if len(lines) < 5:

        await update.message.reply_text(
            "❌ Please provide all 5 lines.\n\n"
            "Use this format:\n\n"
            "Title\n"
            "Location\n"
            "Price/Salary\n"
            "Contact\n"
            "Description\n\n"
            "Example:\n\n"
            "Accountant\n"
            "Nairobi\n"
            "KSh 50,000\n"
            "0712345678\n"
            "Experienced accountant needed."
        )

        return

    listing = {
        "title": lines[0].strip(),
        "location": lines[1].strip(),
        "price": lines[2].strip(),
        "contact": lines[3].strip(),
        "description": " ".join(
            line.strip()
            for line in lines[4:]
        ),
    }

    LISTINGS[category].append(listing)

    context.user_data.pop("adding_category", None)

    await update.message.reply_text(
        "✅ *Listing added successfully!*\n\n"
        f"📌 {listing['title']}\n"
        f"📍 {listing['location']}\n"
        f"💰 {listing['price']}\n"
        f"📞 {listing['contact']}",
        reply_markup=admin_keyboard(),
        parse_mode="Markdown",
    )


# =========================
# BUTTON HANDLER
# =========================

async def button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    # -------------------------
    # MAIN MENU
    # -------------------------

    if data == "home":

        context.user_data.pop("adding_category", None)

        await query.edit_message_text(
            "🇰🇪 *Kenya Jobs & Deals*\n\n"
            "Choose a category below:",
            reply_markup=category_keyboard(),
            parse_mode="Markdown",
        )

        return

    # -------------------------
    # ADMIN PANEL
    # -------------------------

    if data == "admin_panel":

        if query.from_user.id != ADMIN_ID:

            await query.edit_message_text(
                "⛔ Unauthorized."
            )

            return

        await query.edit_message_text(
            "🔐 *ADMIN PANEL*\n\n"
            "Choose an action:",
            reply_markup=admin_keyboard(),
            parse_mode="Markdown",
        )

        return

    # -------------------------
    # ADD LISTING
    # -------------------------

    if data.startswith("add_"):

        if query.from_user.id != ADMIN_ID:

            await query.edit_message_text(
                "⛔ Unauthorized."
            )

            return

        category = data.replace("add_", "")

        context.user_data["adding_category"] = category

        await query.edit_message_text(
            f"➕ *ADD {CATEGORY_NAMES[category]}*\n\n"
            "Send the listing in this format:\n\n"
            "Title\n"
            "Location\n"
            "Price/Salary\n"
            "Contact\n"
            "Description\n\n"
            "Example:\n\n"
            "Accountant\n"
            "Nairobi\n"
            "KSh 50,000\n"
            "0712345678\n"
            "Experienced accountant needed.",
            parse_mode="Markdown",
        )

        return

    # -------------------------
    # VIEW LISTING
    # -------------------------

    if data.startswith("view_"):

        if query.from_user.id != ADMIN_ID:

            await query.edit_message_text(
                "⛔ Unauthorized."
            )

            return

        category = data.replace("view_", "")

        await query.edit_message_text(
            get_listings_text(category),
            reply_markup=admin_keyboard(),
            parse_mode="Markdown",
        )

        return

    # -------------------------
    # NORMAL CATEGORY
    # -------------------------

    if data in LISTINGS:

        await query.edit_message_text(
            get_listings_text(data),
            reply_markup=listing_keyboard(),
            parse_mode="Markdown",
        )

        return

    # -------------------------
    # PREMIUM
    # -------------------------

    if data == "premium":

        await query.edit_message_text(
            "⭐ *PREMIUM MEMBERSHIP*\n\n"
            "Get access to:\n\n"
            "✅ Early job alerts\n"
            "✅ Exclusive opportunities\n"
            "✅ Premium business listings\n"
            "✅ Special deals\n\n"
            "💳 Premium membership will be available soon.",
            reply_markup=listing_keyboard(),
            parse_mode="Markdown",
        )

        return

    # -------------------------
    # ADVERTISE
    # -------------------------

    if data == "advertise":

        await query.edit_message_text(
            "📢 *ADVERTISE WITH US*\n\n"
            "Do you have:\n\n"
            "💼 A job vacancy?\n"
            "💰 A business opportunity?\n"
            "🚗 A car for sale?\n"
            "📱 Electronics for sale?\n\n"
            "Contact the administrator to advertise.",
            reply_markup=listing_keyboard(),
            parse_mode="Markdown",
        )

        return


# =========================
# MAIN
# =========================

def main():

    threading.Thread(
        target=start_web_server,
        daemon=True
    ).start()

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("admin", admin)
    )

    app.add_handler(
        CallbackQueryHandler(button)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_input
        )
    )

    print(
        "🇰🇪 Kenya Jobs & Deals Bot is running..."
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
