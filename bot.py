import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import psycopg
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
DATABASE_URL = os.environ["DATABASE_URL"].strip()

ADMIN_ID = 1773092768


# ============================================================
# DATABASE
# ============================================================

def get_db():
    return psycopg.connect(DATABASE_URL)


def init_database():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS listings (
                    id SERIAL PRIMARY KEY,
                    category VARCHAR(50) NOT NULL,
                    title TEXT NOT NULL,
                    location TEXT NOT NULL,
                    price TEXT NOT NULL,
                    contact TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()

    print("Database initialized successfully.")


def add_listing(category, title, location, price, contact, description):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO listings
                (category, title, location, price, contact, description)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    category,
                    title,
                    location,
                    price,
                    contact,
                    description,
                ),
            )

            listing_id = cur.fetchone()[0]

        conn.commit()

    return listing_id


def get_listings(category):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    title,
                    location,
                    price,
                    contact,
                    description
                FROM listings
                WHERE category = %s
                ORDER BY created_at DESC
                """,
                (category,),
            )

            return cur.fetchall()


def get_listing(listing_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    category,
                    title,
                    location,
                    price,
                    contact,
                    description
                FROM listings
                WHERE id = %s
                """,
                (listing_id,),
            )

            return cur.fetchone()


def update_listing(
    listing_id,
    title,
    location,
    price,
    contact,
    description,
):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE listings
                SET
                    title = %s,
                    location = %s,
                    price = %s,
                    contact = %s,
                    description = %s
                WHERE id = %s
                """,
                (
                    title,
                    location,
                    price,
                    contact,
                    description,
                    listing_id,
                ),
            )

        conn.commit()


def delete_listing(listing_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM listings
                WHERE id = %s
                """,
                (listing_id,),
            )

            deleted = cur.rowcount

        conn.commit()

    return deleted > 0


# ============================================================
# RENDER HEALTH SERVER
# ============================================================

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


# ============================================================
# CATEGORIES
# ============================================================

CATEGORY_NAMES = {
    "jobs": "💼 JOBS",
    "gigs": "💻 ONLINE GIGS",
    "business": "💰 BUSINESS OPPORTUNITIES",
    "cars": "🚗 CAR DEALS",
    "electronics": "📱 ELECTRONICS",
}


# ============================================================
# MAIN MENU
# ============================================================

def category_keyboard():

    return InlineKeyboardMarkup([
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
    ])


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🇰🇪 *Welcome to Kenya Jobs & Deals!*\n\n"
        "Find jobs, online gigs, business opportunities, "
        "car deals and electronics deals.\n\n"
        "Choose an option below:",
        reply_markup=category_keyboard(),
        parse_mode="Markdown",
    )


# ============================================================
# ADMIN MENU
# ============================================================

def admin_keyboard():

    return InlineKeyboardMarkup([
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
                "✏️ Edit Listing",
                callback_data="edit_listing"
            ),
            InlineKeyboardButton(
                "🗑️ Delete Listing",
                callback_data="delete_listing"
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
    ])


# ============================================================
# ADMIN COMMAND
# ============================================================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "⛔ You are not authorized to access the admin panel."
        )
        return

    await update.message.reply_text(
        "🔐 *ADMIN PANEL*\n\n"
        "Choose an action:",
        reply_markup=admin_keyboard(),
        parse_mode="Markdown",
    )


# ============================================================
# DISPLAY LISTINGS
# ============================================================

def format_listings(category):

    listings = get_listings(category)

    title = CATEGORY_NAMES.get(
        category,
        "LISTINGS"
    )

    if not listings:
        return (
            f"{title}\n\n"
            "No listings available yet."
        )

    text = f"{title}\n\n"

    for listing in listings:

        (
            listing_id,
            title_text,
            location,
            price,
            contact,
            description,
        ) = listing

        text += (
            f"🆔 *#{listing_id}*\n"
            f"📌 *{title_text}*\n"
            f"📍 {location}\n"
            f"💰 {price}\n"
            f"📞 {contact}\n"
            f"📝 {description}\n\n"
            "──────────────\n\n"
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


# ============================================================
# ADMIN TEXT INPUT
# ============================================================

async def admin_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    action = context.user_data.get("admin_action")

    if not action:
        return

    text = update.message.text.strip()

    # --------------------------------------------------------
    # ADD LISTING
    # --------------------------------------------------------

    if action == "add":

        category = context.user_data.get(
            "adding_category"
        )

        lines = text.split("\n")

        if len(lines) < 5:

            await update.message.reply_text(
                "❌ Please send 5 lines:\n\n"
                "Title\n"
                "Location\n"
                "Price/Salary\n"
                "Contact\n"
                "Description"
            )

            return

        title = lines[0].strip()
        location = lines[1].strip()
        price = lines[2].strip()
        contact = lines[3].strip()

        description = " ".join(
            line.strip()
            for line in lines[4:]
        )

        try:

            listing_id = add_listing(
                category,
                title,
                location,
                price,
                contact,
                description,
            )

        except Exception as e:

            print(f"Database error: {e}")

            await update.message.reply_text(
                "❌ Database error while saving listing."
            )

            return

        context.user_data.clear()

        await update.message.reply_text(
            "✅ *LISTING SAVED!*\n\n"
            f"🆔 #{listing_id}\n"
            f"📌 {title}\n"
            f"📍 {location}\n"
            f"💰 {price}\n"
            f"📞 {contact}",
            reply_markup=admin_keyboard(),
            parse_mode="Markdown",
        )

        return

    # --------------------------------------------------------
    # DELETE
    # --------------------------------------------------------

    if action == "delete":

        try:
            listing_id = int(text)
        except ValueError:

            await update.message.reply_text(
                "❌ Please enter the listing number only.\n\n"
                "Example:\n"
                "12"
            )

            return

        listing = get_listing(listing_id)

        if not listing:

            await update.message.reply_text(
                "❌ Listing not found."
            )

            return

        deleted = delete_listing(listing_id)

        context.user_data.clear()

        if deleted:

            await update.message.reply_text(
                f"🗑️ Listing #{listing_id} deleted successfully.",
                reply_markup=admin_keyboard(),
            )

        else:

            await update.message.reply_text(
                "❌ Could not delete the listing.",
                reply_markup=admin_keyboard(),
            )

        return

    # --------------------------------------------------------
    # EDIT
    # --------------------------------------------------------

    if action == "edit_id":

        try:
            listing_id = int(text)
        except ValueError:

            await update.message.reply_text(
                "❌ Enter the listing number only.\n\n"
                "Example:\n"
                "12"
            )

            return

        listing = get_listing(listing_id)

        if not listing:

            await update.message.reply_text(
                "❌ Listing not found."
            )

            return

        context.user_data["editing_id"] = listing_id
        context.user_data["admin_action"] = "edit_data"

        await update.message.reply_text(
            "✏️ *EDIT LISTING*\n\n"
            "Send the updated information using:\n\n"
            "Title\n"
            "Location\n"
            "Price/Salary\n"
            "Contact\n"
            "Description",
            parse_mode="Markdown",
        )

        return

    # --------------------------------------------------------
    # EDIT DATA
    # --------------------------------------------------------

    if action == "edit_data":

        listing_id = context.user_data.get(
            "editing_id"
        )

        lines = text.split("\n")

        if len(lines) < 5:

            await update.message.reply_text(
                "❌ Please send all 5 lines."
            )

            return

        title = lines[0].strip()
        location = lines[1].strip()
        price = lines[2].strip()
        contact = lines[3].strip()

        description = " ".join(
            line.strip()
            for line in lines[4:]
        )

        update_listing(
            listing_id,
            title,
            location,
            price,
            contact,
            description,
        )

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ Listing #{listing_id} updated successfully!",
            reply_markup=admin_keyboard(),
        )

        return


# ============================================================
# BUTTON HANDLER
# ============================================================

async def button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    # --------------------------------------------------------
    # HOME
    # --------------------------------------------------------

    if data == "home":

        context.user_data.clear()

        await query.edit_message_text(
            "🇰🇪 *Kenya Jobs & Deals*\n\n"
            "Choose a category below:",
            reply_markup=category_keyboard(),
            parse_mode="Markdown",
        )

        return

    # --------------------------------------------------------
    # ADD
    # --------------------------------------------------------

    if data.startswith("add_"):

        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text(
                "⛔ Unauthorized."
            )
            return

        category = data.replace(
            "add_",
            ""
        )

        context.user_data["admin_action"] = "add"
        context.user_data["adding_category"] = category

        await query.edit_message_text(
            f"➕ *ADD {CATEGORY_NAMES[category]}*\n\n"
            "Send:\n\n"
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

    # --------------------------------------------------------
    # DELETE
    # --------------------------------------------------------

    if data == "delete_listing":

        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text(
                "⛔ Unauthorized."
            )
            return

        context.user_data["admin_action"] = "delete"

        await query.edit_message_text(
            "🗑️ *DELETE LISTING*\n\n"
            "First use 📋 View Jobs/Gigs/etc. "
            "to find the listing ID.\n\n"
            "Then send only the listing number.\n\n"
            "Example:\n"
            "12",
            parse_mode="Markdown",
        )

        return

    # --------------------------------------------------------
    # EDIT
    # --------------------------------------------------------

    if data == "edit_listing":

        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text(
                "⛔ Unauthorized."
            )
            return

        context.user_data["admin_action"] = "edit_id"

        await query.edit_message_text(
            "✏️ *EDIT LISTING*\n\n"
            "First use 📋 View Jobs/Gigs/etc. "
            "to find the listing ID.\n\n"
            "Then send the listing number.\n\n"
            "Example:\n"
            "12",
            parse_mode="Markdown",
        )

        return

    # --------------------------------------------------------
    # VIEW
    # --------------------------------------------------------

    if data.startswith("view_"):

        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text(
                "⛔ Unauthorized."
            )
            return

        category = data.replace(
            "view_",
            ""
        )

        try:

            text = format_listings(
                category
            )

        except Exception as e:

            print(f"Database error: {e}")

            text = "❌ Unable to load listings."

        await query.edit_message_text(
            text,
            reply_markup=admin_keyboard(),
            parse_mode="Markdown",
        )

        return

    # --------------------------------------------------------
    # NORMAL CATEGORY
    # --------------------------------------------------------

    if data in CATEGORY_NAMES:

        try:

            text = format_listings(
                data
            )

        except Exception as e:

            print(f"Database error: {e}")

            text = "❌ Unable to load listings."

        await query.edit_message_text(
            text,
            reply_markup=listing_keyboard(),
            parse_mode="Markdown",
        )

        return

    # --------------------------------------------------------
    # PREMIUM
    # --------------------------------------------------------

    if data == "premium":

        await query.edit_message_text(
            "⭐ *PREMIUM MEMBERSHIP*\n\n"
            "Premium alerts and exclusive opportunities "
            "will be available soon.",
            reply_markup=listing_keyboard(),
            parse_mode="Markdown",
        )

        return

    # --------------------------------------------------------
    # ADVERTISE
    # --------------------------------------------------------

    if data == "advertise":

        await query.edit_message_text(
            "📢 *ADVERTISE WITH US*\n\n"
            "Contact the administrator to advertise "
            "your job, business, car or electronics listing.",
            reply_markup=listing_keyboard(),
            parse_mode="Markdown",
        )

        return


# ============================================================
# MAIN
# ============================================================

def main():

    threading.Thread(
        target=start_web_server,
        daemon=True
    ).start()

    init_database()

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "admin",
            admin
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            button
        )
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
    print("STARTING TELEGRAM POLLING...")
    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
