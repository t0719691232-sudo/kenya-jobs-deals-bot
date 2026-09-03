import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import psycopg

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# SETTINGS
# =========================================================

TOKEN = os.environ["BOT_TOKEN"].strip()
DATABASE_URL = os.environ["DATABASE_URL"].strip()

ADMIN_ID = 1773092768
PORT = int(os.environ.get("PORT", 10000))


# =========================================================
# REGIONS
# =========================================================

REGIONS = {
    "nairobi": "Nairobi",
    "mombasa": "Mombasa",
    "kisumu": "Kisumu",
    "nakuru": "Nakuru",
    "kiambu": "Kiambu",
    "machakos": "Machakos",
    "kajiado": "Kajiado",
    "uasin_gishu": "Uasin Gishu",
    "other": "Other",
}


# =========================================================
# DATABASE
# =========================================================

def get_connection():
    return psycopg.connect(DATABASE_URL)


def init_database():
    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
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
                """
            )

            cur.execute(
                """
                ALTER TABLE listings
                ADD COLUMN IF NOT EXISTS region TEXT DEFAULT 'Other'
                """
            )

            cur.execute(
                """
                ALTER TABLE listings
                ADD COLUMN IF NOT EXISTS photo TEXT
                """
            )

        conn.commit()

    print("Database ready.")


def add_listing(
    category,
    region,
    title,
    location,
    price,
    contact,
    description,
    photo=None,
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO listings
                (
                    category,
                    region,
                    title,
                    location,
                    price,
                    contact,
                    description,
                    photo
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    category,
                    region,
                    title,
                    location,
                    price,
                    contact,
                    description,
                    photo,
                ),
            )

            listing_id = cur.fetchone()[0]

        conn.commit()

    return listing_id


def get_listing(listing_id):
    with get_connection() as conn:
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
                    description,
                    region,
                    photo
                FROM listings
                WHERE id = %s
                """,
                (listing_id,),
            )

            return cur.fetchone()


def get_listings(category, region=None):
    with get_connection() as conn:
        with conn.cursor() as cur:

            if region:
                cur.execute(
                    """
                    SELECT
                        id,
                        category,
                        title,
                        location,
                        price,
                        contact,
                        description,
                        region,
                        photo
                    FROM listings
                    WHERE category = %s
                    AND region = %s
                    ORDER BY id DESC
                    """,
                    (category, region),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        id,
                        category,
                        title,
                        location,
                        price,
                        contact,
                        description,
                        region,
                        photo
                    FROM listings
                    WHERE category = %s
                    ORDER BY id DESC
                    """,
                    (category,),
                )

            return cur.fetchall()


def search_listings(search_text):
    search_pattern = f"%{search_text}%"

    with get_connection() as conn:
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
                    description,
                    region,
                    photo
                FROM listings
                WHERE
                    title ILIKE %s
                    OR location ILIKE %s
                    OR description ILIKE %s
                    OR category ILIKE %s
                    OR region ILIKE %s
                ORDER BY id DESC
                LIMIT 30
                """,
                (
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                ),
            )

            return cur.fetchall()


def update_listing(
    listing_id,
    region,
    title,
    location,
    price,
    contact,
    description,
    photo,
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE listings
                SET
                    region = %s,
                    title = %s,
                    location = %s,
                    price = %s,
                    contact = %s,
                    description = %s,
                    photo = %s
                WHERE id = %s
                """,
                (
                    region,
                    title,
                    location,
                    price,
                    contact,
                    description,
                    photo,
                    listing_id,
                ),
            )

        conn.commit()


def delete_listing(listing_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM listings
                WHERE id = %s
                """,
                (listing_id,),
            )

        conn.commit()


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def is_admin(user_id):
    return user_id == ADMIN_ID


def clear_admin_state(context):
    context.user_data.pop("admin_action", None)
    context.user_data.pop("category", None)
    context.user_data.pop("region", None)
    context.user_data.pop("listing_data", None)
    context.user_data.pop("editing_id", None)
    context.user_data.pop("editing_region", None)
    context.user_data.pop("editing_data", None)
    context.user_data.pop("delete_id", None)


def category_name(category):
    names = {
        "jobs": "💼 Jobs",
        "gigs": "💻 Online Gigs",
        "business": "💰 Business",
        "cars": "🚗 Car Deals",
        "electronics": "📱 Electronics",
    }

    return names.get(category, category.title())


def format_listing(row):
    (
        listing_id,
        category,
        title,
        location,
        price,
        contact,
        description,
        region,
        photo,
    ) = row

    region = region or "Other"

    return (
        f"🆔 Listing #{listing_id}\n\n"
        f"📌 {title}\n\n"
        f"🗂 Category: {category_name(category)}\n"
        f"🗺 Region: {region}\n"
        f"📍 Location: {location}\n"
        f"💰 Price/Salary: {price}\n"
        f"📞 Contact: {contact}\n\n"
        f"📝 Description:\n{description}"
    )


async def send_listing(message, row):
    text = format_listing(row)
    photo = row[8]

    if photo:
        try:
            if len(text) <= 1000:
                await message.reply_photo(
                    photo=photo,
                    caption=text,
                )
            else:
                await message.reply_photo(photo=photo)
                await message.reply_text(text)

        except Exception as e:
            print("Photo error:", e)
            await message.reply_text(text)

    else:
        await message.reply_text(text)


# =========================================================
# MAIN MENU
# =========================================================

def main_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "🔎 Search Listings",
                callback_data="search",
            )
        ],
        [
            InlineKeyboardButton(
                "💼 Jobs",
                callback_data="category_jobs",
            ),
            InlineKeyboardButton(
                "💻 Online Gigs",
                callback_data="category_gigs",
            ),
        ],
        [
            InlineKeyboardButton(
                "💰 Business",
                callback_data="category_business",
            ),
            InlineKeyboardButton(
                "🚗 Car Deals",
                callback_data="category_cars",
            ),
        ],
        [
            InlineKeyboardButton(
                "📱 Electronics",
                callback_data="category_electronics",
            )
        ],
        [
            InlineKeyboardButton(
                "⭐ Premium",
                callback_data="premium",
            )
        ],
        [
            InlineKeyboardButton(
                "📢 Advertise With Us",
                callback_data="advertise",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# REGION MENU
# =========================================================

def region_menu(category):
    keyboard = [
        [
            InlineKeyboardButton(
                "🇰🇪 All Kenya",
                callback_data=f"browse_{category}_all",
            )
        ],
        [
            InlineKeyboardButton(
                "Nairobi",
                callback_data=f"browse_{category}_nairobi",
            ),
            InlineKeyboardButton(
                "Mombasa",
                callback_data=f"browse_{category}_mombasa",
            ),
        ],
        [
            InlineKeyboardButton(
                "Kisumu",
                callback_data=f"browse_{category}_kisumu",
            ),
            InlineKeyboardButton(
                "Nakuru",
                callback_data=f"browse_{category}_nakuru",
            ),
        ],
        [
            InlineKeyboardButton(
                "Kiambu",
                callback_data=f"browse_{category}_kiambu",
            ),
            InlineKeyboardButton(
                "Machakos",
                callback_data=f"browse_{category}_machakos",
            ),
        ],
        [
            InlineKeyboardButton(
                "Kajiado",
                callback_data=f"browse_{category}_kajiado",
            ),
            InlineKeyboardButton(
                "Uasin Gishu",
                callback_data=f"browse_{category}_uasin_gishu",
            ),
        ],
        [
            InlineKeyboardButton(
                "Other",
                callback_data=f"browse_{category}_other",
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="main_menu",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# ADMIN MENUS
# =========================================================

def admin_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "➕ Add Listing",
                callback_data="admin_add",
            )
        ],
        [
            InlineKeyboardButton(
                "💼 View Jobs",
                callback_data="admin_view_jobs",
            ),
            InlineKeyboardButton(
                "💻 View Gigs",
                callback_data="admin_view_gigs",
            ),
        ],
        [
            InlineKeyboardButton(
                "💰 View Business",
                callback_data="admin_view_business",
            ),
            InlineKeyboardButton(
                "🚗 View Cars",
                callback_data="admin_view_cars",
            ),
        ],
        [
            InlineKeyboardButton(
                "📱 View Electronics",
                callback_data="admin_view_electronics",
            )
        ],
        [
            InlineKeyboardButton(
                "✏️ Edit Listing",
                callback_data="admin_edit",
            ),
            InlineKeyboardButton(
                "🗑 Delete Listing",
                callback_data="admin_delete",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="main_menu",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def admin_category_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "💼 Jobs",
                callback_data="add_jobs",
            ),
            InlineKeyboardButton(
                "💻 Online Gigs",
                callback_data="add_gigs",
            ),
        ],
        [
            InlineKeyboardButton(
                "💰 Business",
                callback_data="add_business",
            ),
            InlineKeyboardButton(
                "🚗 Car Deals",
                callback_data="add_cars",
            ),
        ],
        [
            InlineKeyboardButton(
                "📱 Electronics",
                callback_data="add_electronics",
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="cancel_action",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def admin_region_menu(prefix):
    keyboard = [
        [
            InlineKeyboardButton(
                "Nairobi",
                callback_data=f"{prefix}_nairobi",
            ),
            InlineKeyboardButton(
                "Mombasa",
                callback_data=f"{prefix}_mombasa",
            ),
        ],
        [
            InlineKeyboardButton(
                "Kisumu",
                callback_data=f"{prefix}_kisumu",
            ),
            InlineKeyboardButton(
                "Nakuru",
                callback_data=f"{prefix}_nakuru",
            ),
        ],
        [
            InlineKeyboardButton(
                "Kiambu",
                callback_data=f"{prefix}_kiambu",
            ),
            InlineKeyboardButton(
                "Machakos",
                callback_data=f"{prefix}_machakos",
            ),
        ],
        [
            InlineKeyboardButton(
                "Kajiado",
                callback_data=f"{prefix}_kajiado",
            ),
            InlineKeyboardButton(
                "Uasin Gishu",
                callback_data=f"{prefix}_uasin_gishu",
            ),
        ],
        [
            InlineKeyboardButton(
                "Other",
                callback_data=f"{prefix}_other",
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="cancel_action",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_admin_state(context)

    context.user_data.pop("searching", None)

    await update.message.reply_text(
        "🇰🇪 Welcome to Kenya Jobs & Deals Bot!\n\n"
        "Find jobs, online gigs, businesses, cars and electronics "
        "from different parts of Kenya.\n\n"
        "Choose a category or search for a listing:",
        reply_markup=main_menu(),
    )


# =========================================================
# ADMIN
# =========================================================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "⛔ You are not authorized to use the admin panel."
        )
        return

    clear_admin_state(context)

    await update.message.reply_text(
        "🔐 ADMIN PANEL\n\n"
        "Choose what you want to do:",
        reply_markup=admin_menu(),
    )


# =========================================================
# CANCEL
# =========================================================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_admin_state(context)
    context.user_data.pop("searching", None)

    if is_admin(update.effective_user.id):
        await update.message.reply_text(
            "❌ Action cancelled.",
            reply_markup=admin_menu(),
        )
    else:
        await update.message.reply_text(
            "❌ Search/action cancelled.",
            reply_markup=main_menu(),
        )


# =========================================================
# BUTTON HANDLER
# =========================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # -----------------------------------------------------
    # MAIN MENU
    # -----------------------------------------------------

    if data == "main_menu":
        clear_admin_state(context)
        context.user_data.pop("searching", None)

        await query.edit_message_text(
            "🇰🇪 Kenya Jobs & Deals Bot\n\n"
            "Choose a category or search:",
            reply_markup=main_menu(),
        )
        return

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    if data == "search":
        clear_admin_state(context)

        context.user_data["searching"] = True

        await query.edit_message_text(
            "🔎 SEARCH LISTINGS\n\n"
            "Type what you are looking for.\n\n"
            "Examples:\n"
            "• Accountant\n"
            "• Driver\n"
            "• Nairobi\n"
            "• Laptop\n"
            "• Toyota\n"
            "• Online work\n\n"
            "Type /cancel to stop."
        )
        return

    # -----------------------------------------------------
    # USER CATEGORY
    # -----------------------------------------------------

    if data.startswith("category_"):
        category = data.replace(
            "category_",
            "",
        )

        await query.edit_message_text(
            f"{category_name(category)}\n\n"
            "Choose a region:",
            reply_markup=region_menu(category),
        )
        return

    # -----------------------------------------------------
    # USER BROWSE
    # -----------------------------------------------------

    if data.startswith("browse_"):
        parts = data.split("_")

        category = parts[1]
        region_key = "_".join(parts[2:])

        if region_key == "all":
            listings = get_listings(category)
            region_display = "All Kenya"
        else:
            region_display = REGIONS.get(
                region_key,
                "Other",
            )

            listings = get_listings(
                category,
                region_display,
            )

        if not listings:
            await query.edit_message_text(
                f"{category_name(category)}\n"
                f"🗺 {region_display}\n\n"
                "No listings are available here yet.",
                reply_markup=region_menu(category),
            )
            return

        await query.edit_message_text(
            f"{category_name(category)}\n"
            f"🗺 {region_display}\n\n"
            f"Found {len(listings)} listing(s)."
        )

        for listing in listings:
            await send_listing(
                query.message,
                listing,
            )

        await query.message.reply_text(
            "Choose what you want to do next:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔎 Choose Another Region",
                            callback_data=f"category_{category}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🔎 Search",
                            callback_data="search",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 Main Menu",
                            callback_data="main_menu",
                        )
                    ],
                ]
            ),
        )

        return

    # -----------------------------------------------------
    # PREMIUM
    # -----------------------------------------------------

    if data == "premium":
        await query.edit_message_text(
            "⭐ PREMIUM\n\n"
            "Premium features are coming soon.\n\n"
            "Premium listings will receive more visibility.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🏠 Main Menu",
                            callback_data="main_menu",
                        )
                    ]
                ]
            ),
        )
        return

    # -----------------------------------------------------
    # ADVERTISE
    # -----------------------------------------------------

    if data == "advertise":
        await query.edit_message_text(
            "📢 ADVERTISE WITH US\n\n"
            "Businesses and advertisers will be able to submit "
            "their adverts here.\n\n"
            "This feature will be added next.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🏠 Main Menu",
                            callback_data="main_menu",
                        )
                    ]
                ]
            ),
        )
        return

    # =====================================================
    # ADMIN ONLY
    # =====================================================

    if not is_admin(user_id):
        await query.message.reply_text(
            "⛔ Admin access only."
        )
        return

    # -----------------------------------------------------
    # CANCEL ADMIN ACTION
    # -----------------------------------------------------

    if data == "cancel_action":
        clear_admin_state(context)

        await query.edit_message_text(
            "❌ Action cancelled.\n\n"
            "🔐 ADMIN PANEL",
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # ADD LISTING
    # -----------------------------------------------------

    if data == "admin_add":
        clear_admin_state(context)

        await query.edit_message_text(
            "➕ ADD LISTING\n\n"
            "Choose the category:",
            reply_markup=admin_category_menu(),
        )
        return

    # -----------------------------------------------------
    # SELECT ADD CATEGORY
    # -----------------------------------------------------

    if data.startswith("add_"):
        category = data.replace(
            "add_",
            "",
        )

        context.user_data["category"] = category
        context.user_data["admin_action"] = "add_region"

        await query.edit_message_text(
            f"➕ Add to {category_name(category)}\n\n"
            "Choose the region:",
            reply_markup=admin_region_menu("addregion"),
        )
        return

    # -----------------------------------------------------
    # SELECT ADD REGION
    # -----------------------------------------------------

    if data.startswith("addregion_"):
        region_key = data.replace(
            "addregion_",
            "",
        )

        region = REGIONS.get(
            region_key,
            "Other",
        )

        context.user_data["region"] = region
        context.user_data["admin_action"] = "add_details"

        await query.edit_message_text(
            f"🗺 Region: {region}\n\n"
            "Now send the listing details in EXACTLY 5 lines:\n\n"
            "1. Title\n"
            "2. Location\n"
            "3. Price or Salary\n"
            "4. Contact\n"
            "5. Description\n\n"
            "Example:\n\n"
            "Accountant\n"
            "Westlands, Nairobi\n"
            "KSh 50,000 per month\n"
            "0712345678\n"
            "Looking for an experienced accountant."
        )
        return

    # -----------------------------------------------------
    # ADMIN VIEW
    # -----------------------------------------------------

    if data.startswith("admin_view_"):
        category = data.replace(
            "admin_view_",
            "",
        )

        listings = get_listings(category)

        if not listings:
            await query.edit_message_text(
                f"{category_name(category)}\n\n"
                "No listings found.",
                reply_markup=admin_menu(),
            )
            return

        await query.edit_message_text(
            f"🔐 ADMIN — {category_name(category)}\n\n"
            f"Found {len(listings)} listing(s)."
        )

        for listing in listings:
            await send_listing(
                query.message,
                listing,
            )

        await query.message.reply_text(
            "🔐 Admin Panel",
            reply_markup=admin_menu(),
        )

        return

    # -----------------------------------------------------
    # EDIT
    # -----------------------------------------------------

    if data == "admin_edit":
        clear_admin_state(context)

        context.user_data["admin_action"] = "edit_id"

        await query.edit_message_text(
            "✏️ EDIT LISTING\n\n"
            "Send the ID number of the listing you want to edit.\n\n"
            "Example:\n"
            "3\n\n"
            "Use /cancel to cancel."
        )
        return

    # -----------------------------------------------------
    # EDIT REGION
    # -----------------------------------------------------

    if data.startswith("editregion_"):
        region_key = data.replace(
            "editregion_",
            "",
        )

        region = REGIONS.get(
            region_key,
            "Other",
        )

        context.user_data["editing_region"] = region
        context.user_data["admin_action"] = "edit_details"

        await query.edit_message_text(
            f"🗺 New region: {region}\n\n"
            "Now send the updated listing details in EXACTLY 5 lines:\n\n"
            "1. Title\n"
            "2. Location\n"
            "3. Price or Salary\n"
            "4. Contact\n"
            "5. Description"
        )
        return

    # -----------------------------------------------------
    # DELETE
    # -----------------------------------------------------

    if data == "admin_delete":
        clear_admin_state(context)

        context.user_data["admin_action"] = "delete_id"

        await query.edit_message_text(
            "🗑 DELETE LISTING\n\n"
            "Send the ID number of the listing you want to delete.\n\n"
            "Example:\n"
            "3\n\n"
            "Use /cancel to cancel."
        )
        return

    # -----------------------------------------------------
    # CONFIRM DELETE
    # -----------------------------------------------------

    if data.startswith("confirm_delete_"):
        listing_id_text = data.replace(
            "confirm_delete_",
            "",
        )

        try:
            listing_id = int(listing_id_text)

        except ValueError:
            await query.message.reply_text(
                "❌ Invalid listing ID."
            )
            return

        listing = get_listing(listing_id)

        if not listing:
            clear_admin_state(context)

            await query.edit_message_text(
                "❌ Listing not found.",
                reply_markup=admin_menu(),
            )
            return

        delete_listing(listing_id)

        clear_admin_state(context)

        await query.edit_message_text(
            f"✅ Listing #{listing_id} deleted successfully.",
            reply_markup=admin_menu(),
        )
        return


# =========================================================
# ADMIN TEXT INPUT
# =========================================================

async def admin_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update.effective_user.id):
        return

    # IMPORTANT:
    # This handles all normal text sent by the admin.
    text = update.message.text.strip()

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    if context.user_data.get("searching"):

        if text.lower() == "skip":
            return

        context.user_data.pop("searching", None)

        try:
            listings = search_listings(text)

        except Exception as e:
            print("Search error:", e)

            await update.message.reply_text(
                "❌ There was a database error while searching."
            )
            return

        if not listings:
            await update.message.reply_text(
                f"🔎 No listings found for:\n\n"
                f"“{text}”",
                reply_markup=main_menu(),
            )
            return

        await update.message.reply_text(
            f"🔎 Search results for:\n"
            f"“{text}”\n\n"
            f"Found {len(listings)} result(s)."
        )

        for listing in listings:
            await send_listing(
                update.message,
                listing,
            )

        await update.message.reply_text(
            "What would you like to do next?",
            reply_markup=main_menu(),
        )

        return

    # -----------------------------------------------------
    # ADMIN STATE
    # -----------------------------------------------------

    action = context.user_data.get("admin_action")

    if not action:
        return

    # -----------------------------------------------------
    # SKIP PHOTO
    # -----------------------------------------------------

    if (
        text.lower() == "skip"
        and action == "waiting_photo"
    ):
        await save_new_listing(
            update,
            context,
            photo=None,
        )
        return

    # -----------------------------------------------------
    # ADD DETAILS
    # -----------------------------------------------------

    if action == "add_details":
        lines = text.splitlines()

        if len(lines) != 5:
            await update.message.reply_text(
                "❌ Please send EXACTLY 5 lines.\n\n"
                "1. Title\n"
                "2. Location\n"
                "3. Price or Salary\n"
                "4. Contact\n"
                "5. Description\n\n"
                "Please try again."
            )
            return

        context.user_data["listing_data"] = {
            "title": lines[0].strip(),
            "location": lines[1].strip(),
            "price": lines[2].strip(),
            "contact": lines[3].strip(),
            "description": lines[4].strip(),
        }

        context.user_data["admin_action"] = "waiting_photo"

        await update.message.reply_text(
            "📸 PHOTO\n\n"
            "Now send a photo for this listing.\n\n"
            "If you do NOT want a photo, type:\n\n"
            "skip"
        )
        return

    # -----------------------------------------------------
    # WAITING FOR PHOTO
    # -----------------------------------------------------

    if action == "waiting_photo":
        await update.message.reply_text(
            "📸 Please send a photo.\n\n"
            "Or type:\n"
            "skip"
        )
        return

    # -----------------------------------------------------
    # EDIT ID
    # -----------------------------------------------------

    if action == "edit_id":
        try:
            listing_id = int(text)

        except ValueError:
            await update.message.reply_text(
                "❌ Please send only the listing ID number.\n\n"
                "Example:\n"
                "3"
            )
            return

        listing = get_listing(listing_id)

        if not listing:
            await update.message.reply_text(
                f"❌ Listing #{listing_id} was not found."
            )
            return

        context.user_data["editing_id"] = listing_id
        context.user_data["admin_action"] = "edit_region"

        current_region = listing[7] or "Other"

        await update.message.reply_text(
            f"✏️ Editing listing #{listing_id}\n\n"
            f"Current title: {listing[2]}\n"
            f"Current region: {current_region}\n\n"
            "Choose the new region:",
            reply_markup=admin_region_menu("editregion"),
        )
        return

    # -----------------------------------------------------
    # EDIT DETAILS
    # -----------------------------------------------------

    if action == "edit_details":
        lines = text.splitlines()

        if len(lines) != 5:
            await update.message.reply_text(
                "❌ Please send EXACTLY 5 lines.\n\n"
                "1. Title\n"
                "2. Location\n"
                "3. Price or Salary\n"
                "4. Contact\n"
                "5. Description"
            )
            return

        context.user_data["editing_data"] = {
            "title": lines[0].strip(),
            "location": lines[1].strip(),
            "price": lines[2].strip(),
            "contact": lines[3].strip(),
            "description": lines[4].strip(),
        }

        context.user_data["admin_action"] = "edit_photo"

        await update.message.reply_text(
            "📸 EDIT PHOTO\n\n"
            "Send a NEW photo, or type:\n\n"
            "keep\n\n"
            "to keep the existing photo.\n\n"
            "Or type:\n\n"
            "remove\n\n"
            "to remove the photo."
        )
        return

    # -----------------------------------------------------
    # EDIT PHOTO TEXT COMMAND
    # -----------------------------------------------------

    if action == "edit_photo":
        command = text.lower()

        if command == "keep":
            listing_id = context.user_data.get(
                "editing_id"
            )

            old_listing = get_listing(listing_id)

            if not old_listing:
                clear_admin_state(context)

                await update.message.reply_text(
                    "❌ Listing no longer exists.",
                    reply_markup=admin_menu(),
                )
                return

            old_photo = old_listing[8]

            await save_edited_listing(
                update,
                context,
                old_photo,
            )
            return

        if command == "remove":
            await save_edited_listing(
                update,
                context,
                None,
            )
            return

        await update.message.reply_text(
            "❌ Please send a new photo, or type "
            "keep or remove."
        )
        return

    # -----------------------------------------------------
    # DELETE ID
    # -----------------------------------------------------

    if action == "delete_id":
        try:
            listing_id = int(text)

        except ValueError:
            await update.message.reply_text(
                "❌ Please send only the listing ID number."
            )
            return

        listing = get_listing(listing_id)

        if not listing:
            await update.message.reply_text(
                f"❌ Listing #{listing_id} was not found."
            )
            return

        context.user_data["delete_id"] = listing_id

        await update.message.reply_text(
            f"⚠️ DELETE LISTING #{listing_id}?\n\n"
            f"📌 {listing[2]}\n"
            f"📍 {listing[3]}\n"
            f"💰 {listing[4]}\n\n"
            "This cannot be undone.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Yes, Delete",
                            callback_data=f"confirm_delete_{listing_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Cancel",
                            callback_data="cancel_action",
                        )
                    ],
                ]
            ),
        )
        return


# =========================================================
# PHOTO INPUT
# =========================================================

async def photo_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update.effective_user.id):
        return

    action = context.user_data.get("admin_action")

    if not update.message.photo:
        return

    photo_file_id = update.message.photo[-1].file_id

    # New listing
    if action == "waiting_photo":
        await save_new_listing(
            update,
            context,
            photo_file_id,
        )
        return

    # Edited listing
    if action == "edit_photo":
        await save_edited_listing(
            update,
            context,
            photo_file_id,
        )
        return

    await update.message.reply_text(
        "I am not waiting for a photo right now."
    )


# =========================================================
# SAVE NEW LISTING
# =========================================================

async def save_new_listing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    photo=None,
):
    category = context.user_data.get(
        "category"
    )

    region = context.user_data.get(
        "region"
    )

    data = context.user_data.get(
        "listing_data"
    )

    if not category or not region or not data:
        clear_admin_state(context)

        await update.message.reply_text(
            "❌ Something went wrong.\n\n"
            "Please start again with /admin."
        )
        return

    try:
        listing_id = add_listing(
            category=category,
            region=region,
            title=data["title"],
            location=data["location"],
            price=data["price"],
            contact=data["contact"],
            description=data["description"],
            photo=photo,
        )

    except Exception as e:
        print("Error adding listing:", e)

        await update.message.reply_text(
            "❌ Database error while saving the listing."
        )
        return

    clear_admin_state(context)

    await update.message.reply_text(
        f"✅ LISTING ADDED SUCCESSFULLY!\n\n"
        f"🆔 Listing ID: #{listing_id}\n"
        f"📌 {data['title']}\n"
        f"🗺 Region: {region}\n"
        f"📸 Photo: {'Yes' if photo else 'No'}",
        reply_markup=admin_menu(),
    )


# =========================================================
# SAVE EDITED LISTING
# =========================================================

async def save_edited_listing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    photo,
):
    listing_id = context.user_data.get(
        "editing_id"
    )

    region = context.user_data.get(
        "editing_region"
    )

    data = context.user_data.get(
        "editing_data"
    )

    if not listing_id or not region or not data:
        clear_admin_state(context)

        await update.message.reply_text(
            "❌ Something went wrong with the edit.\n\n"
            "Please start again with /admin."
        )
        return

    try:
        update_listing(
            listing_id=listing_id,
            region=region,
            title=data["title"],
            location=data["location"],
            price=data["price"],
            contact=data["contact"],
            description=data["description"],
            photo=photo,
        )

    except Exception as e:
        print("Error editing listing:", e)

        await update.message.reply_text(
            "❌ Database error while editing the listing."
        )
        return

    clear_admin_state(context)

    await update.message.reply_text(
        f"✅ Listing #{listing_id} updated successfully!",
        reply_markup=admin_menu(),
    )


# =========================================================
# RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header(
            "Content-type",
            "text/plain",
        )
        self.end_headers()

        self.wfile.write(
            b"Kenya Jobs & Deals Bot is running."
        )

    def log_message(self, format, *args):
        return


def run_health_server():
    server = HTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler,
    )

    print(
        f"Health server running on port {PORT}"
    )

    server.serve_forever()


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    print(
        "Telegram bot error:",
        context.error,
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "Starting Kenya Jobs & Deals Bot..."
    )

    # Database
    init_database()

    # Render health server
    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True,
    )

    health_thread.start()

    # Telegram application
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    app.add_handler(
        CommandHandler(
            "admin",
            admin,
        )
    )

    app.add_handler(
        CommandHandler(
            "cancel",
            cancel,
        )
    )

    # Buttons
    app.add_handler(
        CallbackQueryHandler(
            button_handler,
        )
    )

    # Photos
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            photo_input,
        )
    )

    # One text handler only
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_input,
        )
    )

    # Error handler
    app.add_error_handler(
        error_handler
    )

    print("Bot is running...")

    app.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
