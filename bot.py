import re
from urllib.parse import quote
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

ADMIN_ID = int(os.environ.get("ADMIN_ID", "1773092768"))
PORT = int(os.environ.get("PORT", 10000))
BOT_USERNAME = ""


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

            # NEW:
            # Listings submitted by users start as pending.
            cur.execute(
                """
                ALTER TABLE listings
                ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'approved'
                """
            )

            cur.execute(
                """
                ALTER TABLE listings
                ADD COLUMN IF NOT EXISTS user_id BIGINT
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    user_id BIGINT NOT NULL,
                    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, listing_id)
                )
                """
            )

        conn.commit()

    print("Database ready.")


# =========================================================
# ADD LISTING
# =========================================================

def add_listing(
    category,
    region,
    title,
    location,
    price,
    contact,
    description,
    photo=None,
    status="approved",
    user_id=None,
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
                    photo,
                    status,
                    user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    status,
                    user_id,
                ),
            )

            listing_id = cur.fetchone()[0]

        conn.commit()

    return listing_id



# =========================================================
# FAVOURITES
# =========================================================

def is_favorite(user_id, listing_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM favorites
                WHERE user_id = %s AND listing_id = %s
                """,
                (user_id, listing_id),
            )
            return cur.fetchone() is not None


def toggle_favorite(user_id, listing_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM favorites
                WHERE user_id = %s AND listing_id = %s
                """,
                (user_id, listing_id),
            )

            if cur.fetchone():
                cur.execute(
                    """
                    DELETE FROM favorites
                    WHERE user_id = %s AND listing_id = %s
                    """,
                    (user_id, listing_id),
                )
                saved = False
            else:
                cur.execute(
                    """
                    INSERT INTO favorites (user_id, listing_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (user_id, listing_id),
                )
                saved = True

        conn.commit()

    return saved


def get_favorite_listings(user_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    l.id,
                    l.category,
                    l.title,
                    l.location,
                    l.price,
                    l.contact,
                    l.description,
                    l.region,
                    l.photo,
                    l.status,
                    l.user_id
                FROM listings l
                INNER JOIN favorites f
                    ON f.listing_id = l.id
                WHERE f.user_id = %s
                  AND l.status = 'approved'
                ORDER BY f.created_at DESC
                LIMIT 30
                """,
                (user_id,),
            )
            return cur.fetchall()


# =========================================================
# GET ONE LISTING
# =========================================================

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
                    photo,
                    status,
                    user_id
                FROM listings
                WHERE id = %s
                """,
                (listing_id,),
            )

            return cur.fetchone()


# =========================================================
# GET LISTINGS
# =========================================================

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
                        photo,
                        status,
                        user_id
                    FROM listings
                    WHERE category = %s
                    AND region = %s
                    AND status = 'approved'
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
                        photo,
                        status,
                        user_id
                    FROM listings
                    WHERE category = %s
                    AND status = 'approved'
                    ORDER BY id DESC
                    """,
                    (category,),
                )

            return cur.fetchall()


# =========================================================
# SEARCH
# =========================================================

def search_listings(search_text):
    """
    Search approved listings using all meaningful words in the query.

    Examples:
      "accountant Nairobi" -> both words must appear somewhere in the listing.
      "Toyota Westlands" -> both Toyota and Westlands must appear.
      Exact phrases and title/location matches are ranked higher.
    """
    raw_query = " ".join(search_text.strip().split())
    if not raw_query:
        return []

    # Ignore common filler words so searches such as "jobs in Nairobi"
    # still work naturally.
    stop_words = {
        "a", "an", "and", "at", "for", "from", "in", "is",
        "near", "of", "on", "or", "the", "to", "with",
    }

    words = [
        word
        for word in re.findall(r"[^\s]+", raw_query.lower())
        if word not in stop_words and len(word) >= 2
    ]

    # If the query consists only of filler words, use the complete query.
    if not words:
        words = [raw_query.lower()]

    # Remove duplicate terms while preserving order.
    words = list(dict.fromkeys(words))

    searchable = """
        COALESCE(title, '') || ' ' ||
        COALESCE(location, '') || ' ' ||
        COALESCE(description, '') || ' ' ||
        COALESCE(category, '') || ' ' ||
        COALESCE(region, '') || ' ' ||
        COALESCE(price, '')
    """

    conditions = []
    params = []

    # Every meaningful search word must match somewhere in the listing.
    for word in words:
        conditions.append(f"{searchable} ILIKE %s")
        params.append(f"%{word}%")

    # Rank exact phrase matches first, then title/location/category matches.
    score_parts = [
        "CASE WHEN " + searchable + " ILIKE %s THEN 100 ELSE 0 END"
    ]
    score_params = [f"%{raw_query.lower()}%"]

    for word in words:
        score_parts.append(
            "CASE WHEN COALESCE(title, '') ILIKE %s THEN 20 ELSE 0 END"
        )
        score_params.append(f"%{word}%")

        score_parts.append(
            "CASE WHEN COALESCE(location, '') ILIKE %s THEN 15 ELSE 0 END"
        )
        score_params.append(f"%{word}%")

        score_parts.append(
            "CASE WHEN COALESCE(category, '') ILIKE %s THEN 10 ELSE 0 END"
        )
        score_params.append(f"%{word}%")

    score_sql = " + ".join(score_parts)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    category,
                    title,
                    location,
                    price,
                    contact,
                    description,
                    region,
                    photo,
                    status,
                    user_id
                FROM listings
                WHERE status = 'approved'
                AND (
                    {' AND '.join(conditions)}
                )
                ORDER BY ({score_sql}) DESC, id DESC
                LIMIT 30
                """,
                params + score_params,
            )

            return cur.fetchall()


# =========================================================
# GET PENDING LISTINGS
# =========================================================

def get_pending_listings():
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
                    photo,
                    status,
                    user_id
                FROM listings
                WHERE status = 'pending'
                ORDER BY id ASC
                """
            )

            return cur.fetchall()


# =========================================================
# APPROVE LISTING
# =========================================================

def approve_listing(listing_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE listings
                SET status = 'approved'
                WHERE id = %s
                  AND status = 'pending'
                RETURNING user_id
                """,
                (listing_id,),
            )
            row = cur.fetchone()

        conn.commit()

    return row[0] if row else None


# =========================================================
# REJECT LISTING
# =========================================================

def reject_listing(listing_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE listings
                SET status = 'rejected'
                WHERE id = %s
                  AND status = 'pending'
                RETURNING user_id
                """,
                (listing_id,),
            )
            row = cur.fetchone()

        conn.commit()

    return row[0] if row else None


# =========================================================
# UPDATE LISTING
# =========================================================

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


# =========================================================
# DELETE LISTING
# =========================================================

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
# HELPERS
# =========================================================

def is_admin(user_id):
    return user_id == ADMIN_ID


def clear_state(context):
    keys = [
        "admin_action",
        "category",
        "region",
        "listing_data",
        "editing_id",
        "editing_region",
        "editing_data",
        "delete_id",
        "searching",
        "advertising",
        "advertiser_category",
        "advertiser_region",
        "advertiser_data",
    ]

    for key in keys:
        context.user_data.pop(key, None)


def category_name(category):
    names = {
        "jobs": "💼 Jobs",
        "gigs": "💻 Online Gigs",
        "business": "💰 Business",
        "cars": "🚗 Car Deals",
        "electronics": "📱 Electronics",
    }

    return names.get(category, category.title())


# =========================================================
# LISTING DISPLAY
# =========================================================

def format_listing(row):
    listing_id = row[0]
    category = row[1]
    title = row[2]
    location = row[3]
    price = row[4]
    description = row[6]
    region = row[7] or "Other"

    return (
        f"🆔 Listing #{listing_id}\n\n"
        f"📌 {title}\n\n"
        f"🗂 Category: {category_name(category)}\n"
        f"🗺 Region: {region}\n"
        f"📍 Location: {location}\n"
        f"💰 Price/Salary: {price}\n\n"
        f"📝 Description:\n{description}"
    )


def normalize_phone_for_whatsapp(contact):
    """Return a WhatsApp-ready international phone number when possible."""
    if not contact:
        return None

    # Use the first phone-like number when contact contains extra text.
    match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", contact)
    if not match:
        return None

    number = re.sub(r"\D", "", match.group(0))

    # Kenya local mobile format: 07xxxxxxxx / 01xxxxxxxx -> 2547xxxxxxxx / 2541xxxxxxxx.
    if number.startswith("0") and len(number) == 10:
        number = "254" + number[1:]

    # Already international Kenya format without '+'.
    if number.startswith("254") and len(number) == 12:
        return number

    # If the contact is another international number, keep it if it is plausible.
    if 10 <= len(number) <= 15:
        return number

    return None


def listing_buttons(row, user_id=None):
    listing_id = row[0]
    category = row[1]
    contact = row[5]
    title = row[2]
    location = row[3]

    if category in ["jobs", "gigs"]:
        contact_text = "📞 Apply / Contact"
        whatsapp_text = "💬 Apply on WhatsApp"
    else:
        contact_text = "📞 Contact Seller"
        whatsapp_text = "💬 WhatsApp Seller"

    buttons = [
        InlineKeyboardButton(
            contact_text,
            callback_data=f"contact_{listing_id}",
        )
    ]

    whatsapp_number = normalize_phone_for_whatsapp(contact)
    if whatsapp_number:
        buttons.append(
            InlineKeyboardButton(
                whatsapp_text,
                url=f"https://wa.me/{whatsapp_number}",
            )
        )

    saved = False
    if user_id is not None:
        saved = is_favorite(user_id, listing_id)

    buttons.append(
        InlineKeyboardButton(
            "❤️ Saved" if saved else "🤍 Save",
            callback_data=f"favorite_{listing_id}",
        )
    )

    deep_link = f"https://t.me/{BOT_USERNAME}?start=listing_{listing_id}" if BOT_USERNAME else ""

    share_text = (
        f"🇰🇪 Kenya Jobs & Deals\n\n"
        f"📌 {title}\n"
        f"📍 {location}\n"
        f"💰 {row[4]}\n\n"
        f"🆔 Listing #{listing_id}"
    )

    buttons.append(
        InlineKeyboardButton(
            "📤 Share Listing",
            url=(
                f"https://t.me/share/url?url={quote(deep_link, safe="")}&text={quote(share_text)}"
                if deep_link
                else f"https://t.me/share/url?text={quote(share_text)}"
            ),
        )
    )

    return InlineKeyboardMarkup(
        [
            buttons[:2],
            buttons[2:],
        ] if len(buttons) >= 3 else [buttons]
    )


async def send_listing(message, row, user_id=None):
    text = format_listing(row)
    photo = row[8]
    buttons = listing_buttons(row, user_id)

    if photo:
        try:
            if len(text) <= 1000:
                await message.reply_photo(
                    photo=photo,
                    caption=text,
                    reply_markup=buttons,
                )
            else:
                await message.reply_photo(
                    photo=photo
                )

                await message.reply_text(
                    text,
                    reply_markup=buttons,
                )

        except Exception as e:
            print("Photo error:", e)

            await message.reply_text(
                text,
                reply_markup=buttons,
            )

    else:
        await message.reply_text(
            text,
            reply_markup=buttons,
        )


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
                "❤️ My Favourites",
                callback_data="favorites",
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
# ADMIN MENU
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
                "📥 Pending Ads",
                callback_data="pending_ads",
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
    clear_state(context)

    # Support shared listing deep links such as /start listing_123.
    if context.args:
        payload = context.args[0]
        if payload.startswith("listing_"):
            try:
                listing_id = int(payload.replace("listing_", "", 1))
            except ValueError:
                listing_id = None

            if listing_id is not None:
                listing = get_listing(listing_id)
                if listing and listing[9] == "approved":
                    await update.message.reply_text(
                        "📌 SHARED LISTING\n\n"
                        "Here is the listing that was shared with you:"
                    )
                    await send_listing(
                        update.message,
                        listing,
                        update.effective_user.id,
                    )
                    return

                await update.message.reply_text(
                    "❌ Sorry, this listing is no longer available.",
                    reply_markup=main_menu(),
                )
                return

    await update.message.reply_text(
        "🇰🇪 Welcome to Kenya Jobs & Deals Bot!\n\n"
        "Find jobs, online gigs, businesses, cars and electronics "
        "from different parts of Kenya.\n\n"
        "Choose a category or search for a listing:",
        reply_markup=main_menu(),
    )


# =========================================================
# ADMIN COMMAND
# =========================================================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "⛔ You are not authorized to use the admin panel."
        )
        return

    clear_state(context)

    await update.message.reply_text(
        "🔐 ADMIN PANEL\n\n"
        "Choose what you want to do:",
        reply_markup=admin_menu(),
    )


# =========================================================
# CANCEL
# =========================================================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(context)

    if is_admin(update.effective_user.id):
        await update.message.reply_text(
            "❌ Action cancelled.",
            reply_markup=admin_menu(),
        )
    else:
        await update.message.reply_text(
            "❌ Action cancelled.",
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
        clear_state(context)

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
        clear_state(context)

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
    # ADVERTISE WITH US
    # -----------------------------------------------------

    if data == "advertise":
        clear_state(context)

        context.user_data["advertising"] = True

        await query.edit_message_text(
            "📢 ADVERTISE WITH US\n\n"
            "Submit your job, business, car or electronics advert.\n\n"
            "Your advert will be reviewed by our admin before "
            "it becomes visible to everyone.\n\n"
            "Choose a category:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "💼 Jobs",
                            callback_data="advertise_jobs",
                        ),
                        InlineKeyboardButton(
                            "💻 Online Gigs",
                            callback_data="advertise_gigs",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "💰 Business",
                            callback_data="advertise_business",
                        ),
                        InlineKeyboardButton(
                            "🚗 Car Deals",
                            callback_data="advertise_cars",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "📱 Electronics",
                            callback_data="advertise_electronics",
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

    # -----------------------------------------------------
    # ADVERTISER CATEGORY
    # -----------------------------------------------------

    if data.startswith("advertise_"):
        category = data.replace(
            "advertise_",
            "",
        )

        context.user_data["advertiser_category"] = category

        await query.edit_message_text(
            f"📢 {category_name(category)}\n\n"
            "Choose the region:",
            reply_markup=admin_region_menu(
                "advertiseregion"
            ),
        )
        return

    # -----------------------------------------------------
    # ADVERTISER REGION
    # -----------------------------------------------------

    if data.startswith("advertiseregion_"):
        region_key = data.replace(
            "advertiseregion_",
            "",
        )

        region = REGIONS.get(
            region_key,
            "Other",
        )

        context.user_data["advertiser_region"] = region
        context.user_data["advertising"] = True

        await query.edit_message_text(
            f"🗺 Region: {region}\n\n"
            "Now send your advert details in EXACTLY 5 lines:\n\n"
            "1. Title\n"
            "2. Location\n"
            "3. Price or Salary\n"
            "4. Contact\n"
            "5. Description\n\n"
            "Example:\n\n"
            "Accountant Needed\n"
            "Westlands, Nairobi\n"
            "KSh 50,000 per month\n"
            "0712345678\n"
            "Looking for an experienced accountant."
        )
        return

    # -----------------------------------------------------
    # CONTACT / APPLY
    # -----------------------------------------------------

    if data.startswith("contact_"):
        listing_id_text = data.replace(
            "contact_",
            "",
        )

        try:
            listing_id = int(listing_id_text)

        except ValueError:
            await query.message.reply_text(
                "❌ Invalid listing."
            )
            return

        listing = get_listing(listing_id)

        if not listing:
            await query.message.reply_text(
                "❌ This listing is no longer available."
            )
            return

        category = listing[1]
        title = listing[2]
        contact = listing[5]

        if category in ["jobs", "gigs"]:
            heading = "📞 APPLY / CONTACT"
        else:
            heading = "📞 CONTACT SELLER"

        await query.message.reply_text(
            f"{heading}\n\n"
            f"📌 {title}\n\n"
            f"☎️ Contact:\n"
            f"{contact}\n\n"
            f"🆔 Listing #{listing_id}\n\n"
            "You can contact the advertiser directly or use the WhatsApp button on the listing."
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
                user_id,
            )

        await query.message.reply_text(
            "Choose what you want to do next:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔎 Another Region",
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
    # MY FAVOURITES
    # -----------------------------------------------------

    if data == "favorites":
        clear_state(context)

        listings = get_favorite_listings(user_id)

        if not listings:
            await query.edit_message_text(
                "❤️ MY FAVOURITES\n\n"
                "You have not saved any listings yet.\n\n"
                "Tap 🤍 Save on a listing to keep it here.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔎 Search Listings",
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

        await query.edit_message_text(
            f"❤️ MY FAVOURITES\n\n"
            f"You have {len(listings)} saved listing(s)."
        )

        for listing in listings:
            await send_listing(
                query.message,
                listing,
                user_id,
            )

        return

    # -----------------------------------------------------
    # SAVE / UNSAVE LISTING
    # -----------------------------------------------------

    if data.startswith("favorite_"):
        try:
            listing_id = int(data.replace("favorite_", "", 1))
        except ValueError:
            await query.message.reply_text("❌ Invalid listing.")
            return

        listing = get_listing(listing_id)

        if not listing or listing[9] != "approved":
            await query.message.reply_text(
                "❌ This listing is no longer available."
            )
            return

        saved = toggle_favorite(user_id, listing_id)

        try:
            await query.edit_message_reply_markup(
                reply_markup=listing_buttons(listing, user_id)
            )
        except Exception as e:
            print("Favourite button update error:", e)

        if saved:
            await query.message.reply_text(
                f"❤️ Saved: {listing[2]}\n\n"
                "You can find it under ❤️ My Favourites."
            )
        else:
            await query.message.reply_text(
                f"💔 Removed from favourites: {listing[2]}"
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
        clear_state(context)

        await query.edit_message_text(
            "❌ Action cancelled.\n\n"
            "🔐 ADMIN PANEL",
            reply_markup=admin_menu(),
        )
        return

    # -----------------------------------------------------
    # PENDING ADS
    # -----------------------------------------------------

    if data == "pending_ads":
        pending = get_pending_listings()

        if not pending:
            await query.edit_message_text(
                "📥 PENDING ADS\n\n"
                "There are no adverts waiting for approval.",
                reply_markup=admin_menu(),
            )
            return

        await query.edit_message_text(
            f"📥 PENDING ADS\n\n"
            f"{len(pending)} advert(s) waiting for approval."
        )

        for listing in pending:

            text = (
                "📥 NEW ADVERT\n\n"
                f"{format_listing(listing)}\n\n"
                "Choose an action:"
            )

            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Approve",
                            callback_data=f"approve_{listing[0]}",
                        ),
                        InlineKeyboardButton(
                            "❌ Reject",
                            callback_data=f"reject_{listing[0]}",
                        ),
                    ]
                ]
            )

            if listing[8]:
                try:
                    if len(text) <= 1000:
                        await query.message.reply_photo(
                            photo=listing[8],
                            caption=text,
                            reply_markup=buttons,
                        )
                    else:
                        await query.message.reply_photo(
                            photo=listing[8]
                        )

                        await query.message.reply_text(
                            text,
                            reply_markup=buttons,
                        )

                except Exception as e:
                    print("Pending photo error:", e)

                    await query.message.reply_text(
                        text,
                        reply_markup=buttons,
                    )

            else:
                await query.message.reply_text(
                    text,
                    reply_markup=buttons,
                )

        await query.message.reply_text(
            "🔐 Admin Panel",
            reply_markup=admin_menu(),
        )

        return

    # -----------------------------------------------------
    # APPROVE
    # -----------------------------------------------------

    if data.startswith("approve_"):
        listing_id_text = data.replace(
            "approve_",
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
            await query.edit_message_text(
                "❌ Listing not found."
            )
            return

        advertiser_user_id = approve_listing(listing_id)

        await query.edit_message_text(
            f"✅ Listing #{listing_id} APPROVED.\n\n"
            f"📌 {listing[2]}\n\n"
            "It is now visible to users."
        )

        if advertiser_user_id:
            try:
                await context.bot.send_message(
                    chat_id=advertiser_user_id,
                    text=(
                        "🎉 AD APPROVED!\n\n"
                        f"Your advert “{listing[2]}” has been approved "
                        "and is now live on Kenya Jobs & Deals Bot. 🇰🇪\n\n"
                        "Thank you for advertising with us!"
                    ),
                )
            except Exception as e:
                print("Advertiser approval notification error:", e)

        return

    # -----------------------------------------------------
    # REJECT
    # -----------------------------------------------------

    if data.startswith("reject_"):
        listing_id_text = data.replace(
            "reject_",
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
            await query.edit_message_text(
                "❌ Listing not found."
            )
            return

        advertiser_user_id = reject_listing(listing_id)

        await query.edit_message_text(
            f"❌ Listing #{listing_id} REJECTED.\n\n"
            f"📌 {listing[2]}\n\n"
            "It will not appear to users."
        )

        if advertiser_user_id:
            try:
                await context.bot.send_message(
                    chat_id=advertiser_user_id,
                    text=(
                        "❌ AD NOT APPROVED\n\n"
                        f"Unfortunately, your advert “{listing[2]}” "
                        "was not approved at this time.\n\n"
                        "Please contact the administrator if you need "
                        "more information."
                    ),
                )
            except Exception as e:
                print("Advertiser rejection notification error:", e)

        return

    # -----------------------------------------------------
    # ADMIN ADD
    # -----------------------------------------------------

    if data == "admin_add":
        clear_state(context)

        await query.edit_message_text(
            "➕ ADD LISTING\n\n"
            "Choose the category:",
            reply_markup=admin_category_menu(),
        )
        return

    # -----------------------------------------------------
    # ADMIN ADD CATEGORY
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
            reply_markup=admin_region_menu(
                "addregion"
            ),
        )
        return

    # -----------------------------------------------------
    # ADMIN ADD REGION
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
            "Send the listing details in EXACTLY 5 lines:\n\n"
            "1. Title\n"
            "2. Location\n"
            "3. Price or Salary\n"
            "4. Contact\n"
            "5. Description"
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
                user_id,
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
        clear_state(context)

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
            "Send the updated listing details in EXACTLY 5 lines:\n\n"
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
        clear_state(context)

        context.user_data["admin_action"] = "delete_id"

        await query.edit_message_text(
            "🗑 DELETE LISTING\n\n"
            "Send the ID number of the listing you want to delete.\n\n"
            "Example:\n"
            "3"
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
            await query.edit_message_text(
                "❌ Listing not found.",
                reply_markup=admin_menu(),
            )
            return

        delete_listing(listing_id)

        clear_state(context)

        await query.edit_message_text(
            f"✅ Listing #{listing_id} deleted successfully.",
            reply_markup=admin_menu(),
        )

        return


# =========================================================
# CLEAN FIVE-LINE INPUT
# =========================================================

def clean_input_line(line):
    """Remove optional field numbering such as '1.' or '1)'."""
    import re
    return re.sub(r"^\\s*[1-5][.)]\\s*", "", line).strip()


# =========================================================
# TEXT INPUT
# =========================================================

async def text_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = update.message.text.strip()

    # =====================================================
    # ADVERTISER SUBMISSION
    # =====================================================

    if context.user_data.get("advertising"):

        if context.user_data.get("admin_action") == "advertiser_photo":
            if text.lower() == "skip":
                await save_advertiser_submission(
                    update,
                    context,
                    None,
                )
            else:
                await update.message.reply_text(
                    "📸 Please send a photo or type skip."
                )
            return

        if not context.user_data.get(
            "advertiser_data"
        ):

            lines = text.splitlines()

            if len(lines) != 5:
                await update.message.reply_text(
                    "❌ Please send EXACTLY 5 lines:\n\n"
                    "1. Title\n"
                    "2. Location\n"
                    "3. Price or Salary\n"
                    "4. Contact\n"
                    "5. Description"
                )
                return

            context.user_data["advertiser_data"] = {
                "title": clean_input_line(lines[0]),
                "location": clean_input_line(lines[1]),
                "price": clean_input_line(lines[2]),
                "contact": clean_input_line(lines[3]),
                "description": clean_input_line(lines[4]),
            }

            context.user_data["admin_action"] = "advertiser_photo"

            await update.message.reply_text(
                "📸 PHOTO\n\n"
                "Send a photo for your advert.\n\n"
                "If you don't want a photo, type:\n\n"
                "skip"
            )

            return

    # =====================================================
    # SEARCH
    # =====================================================

    if context.user_data.get("searching"):

        context.user_data.pop(
            "searching",
            None,
        )

        try:
            listings = search_listings(text)

        except Exception as e:
            print("Search error:", e)

            await update.message.reply_text(
                "❌ Search database error."
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
                update.effective_user.id,
            )

        await update.message.reply_text(
            "What would you like to do next?",
            reply_markup=main_menu(),
        )

        return

    # =====================================================
    # ADMIN TEXT
    # =====================================================

    if not is_admin(update.effective_user.id):
        return

    action = context.user_data.get(
        "admin_action"
    )

    if not action:
        return

    # -----------------------------------------------------
    # ADMIN ADD DETAILS
    # -----------------------------------------------------

    if action == "add_details":

        lines = text.splitlines()

        if len(lines) != 5:
            await update.message.reply_text(
                "❌ Please send EXACTLY 5 lines."
            )
            return

        context.user_data["listing_data"] = {
            "title": clean_input_line(lines[0]),
            "location": clean_input_line(lines[1]),
            "price": clean_input_line(lines[2]),
            "contact": clean_input_line(lines[3]),
            "description": clean_input_line(lines[4]),
        }

        context.user_data["admin_action"] = "waiting_photo"

        await update.message.reply_text(
            "📸 PHOTO\n\n"
            "Send a photo for this listing.\n\n"
            "Or type:\n"
            "skip"
        )

        return

    # -----------------------------------------------------
    # ADMIN SKIP PHOTO
    # -----------------------------------------------------

    if action == "waiting_photo":

        if text.lower() == "skip":
            await save_admin_listing(
                update,
                context,
                None,
            )
        else:
            await update.message.reply_text(
                "📸 Please send a photo or type skip."
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
                "❌ Please send only the listing ID."
            )
            return

        listing = get_listing(listing_id)

        if not listing:
            await update.message.reply_text(
                "❌ Listing not found."
            )
            return

        context.user_data["editing_id"] = listing_id
        context.user_data["admin_action"] = "edit_region"

        await update.message.reply_text(
            f"✏️ Editing listing #{listing_id}\n\n"
            f"Current title: {listing[2]}\n"
            f"Current region: {listing[7] or 'Other'}\n\n"
            "Choose the new region:",
            reply_markup=admin_region_menu(
                "editregion"
            ),
        )

        return

    # -----------------------------------------------------
    # EDIT DETAILS
    # -----------------------------------------------------

    if action == "edit_details":

        lines = text.splitlines()

        if len(lines) != 5:
            await update.message.reply_text(
                "❌ Please send EXACTLY 5 lines."
            )
            return

        context.user_data["editing_data"] = {
            "title": clean_input_line(lines[0]),
            "location": clean_input_line(lines[1]),
            "price": clean_input_line(lines[2]),
            "contact": clean_input_line(lines[3]),
            "description": clean_input_line(lines[4]),
        }

        context.user_data["admin_action"] = "edit_photo"

        await update.message.reply_text(
            "📸 EDIT PHOTO\n\n"
            "Send a NEW photo, or type:\n\n"
            "keep\n\n"
            "to keep the current photo.\n\n"
            "Or type:\n\n"
            "remove\n\n"
            "to remove it."
        )

        return

    # -----------------------------------------------------
    # EDIT PHOTO
    # -----------------------------------------------------

    if action == "edit_photo":

        if text.lower() == "keep":

            listing_id = context.user_data.get(
                "editing_id"
            )

            listing = get_listing(
                listing_id
            )

            if not listing:
                await update.message.reply_text(
                    "❌ Listing not found."
                )
                return

            await save_edited_listing(
                update,
                context,
                listing[8],
            )

            return

        if text.lower() == "remove":

            await save_edited_listing(
                update,
                context,
                None,
            )

            return

        await update.message.reply_text(
            "❌ Send a new photo, or type keep or remove."
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
                "❌ Please send only the listing ID."
            )
            return

        listing = get_listing(listing_id)

        if not listing:
            await update.message.reply_text(
                "❌ Listing not found."
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
    photo_file_id = update.message.photo[-1].file_id

    # -----------------------------------------------------
    # ADVERTISER PHOTO
    # -----------------------------------------------------

    if context.user_data.get(
        "advertising"
    ):
        await save_advertiser_submission(
            update,
            context,
            photo_file_id,
        )

        return

    # -----------------------------------------------------
    # ADMIN PHOTO
    # -----------------------------------------------------

    if not is_admin(update.effective_user.id):
        return

    action = context.user_data.get(
        "admin_action"
    )

    if action == "waiting_photo":

        await save_admin_listing(
            update,
            context,
            photo_file_id,
        )

        return

    if action == "edit_photo":

        await save_edited_listing(
            update,
            context,
            photo_file_id,
        )

        return


# =========================================================
# SAVE ADMIN LISTING
# =========================================================

async def save_admin_listing(
    update,
    context,
    photo,
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
        clear_state(context)

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
            status="approved",
        )

    except Exception as e:
        print("Admin listing error:", e)

        await update.message.reply_text(
            "❌ Database error."
        )

        return

    clear_state(context)

    await update.message.reply_text(
        f"✅ LISTING ADDED SUCCESSFULLY!\n\n"
        f"🆔 Listing ID: #{listing_id}\n"
        f"📌 {data['title']}\n"
        f"🗺 Region: {region}\n"
        f"📸 Photo: {'Yes' if photo else 'No'}",
        reply_markup=admin_menu(),
    )


# =========================================================
# SAVE ADVERTISER SUBMISSION
# =========================================================

async def save_advertiser_submission(
    update,
    context,
    photo,
):
    category = context.user_data.get(
        "advertiser_category"
    )

    region = context.user_data.get(
        "advertiser_region"
    )

    data = context.user_data.get(
        "advertiser_data"
    )

    if not category or not region or not data:
        clear_state(context)

        await update.message.reply_text(
            "❌ Something went wrong.\n\n"
            "Please start again."
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
            status="pending",
            user_id=update.effective_user.id,
        )

    except Exception as e:
        print(
            "Advertiser submission error:",
            e,
        )

        await update.message.reply_text(
            "❌ There was a database error.\n\n"
            "Please try again later."
        )

        return

    # Send notification to admin
    try:

        admin_text = (
            "📥 NEW ADVERT SUBMITTED!\n\n"
            f"🆔 Listing #{listing_id}\n"
            f"🗂 Category: {category_name(category)}\n"
            f"🗺 Region: {region}\n"
            f"📌 {data['title']}\n"
            f"📍 {data['location']}\n"
            f"💰 {data['price']}\n"
            f"📞 {data['contact']}\n\n"
            f"📝 {data['description']}\n\n"
            "Please open /admin → Pending Ads to review."
        )

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
        )

    except Exception as e:
        print(
            "Admin notification error:",
            e,
        )

    clear_state(context)

    await update.message.reply_text(
        "✅ ADVERT SUBMITTED!\n\n"
        f"🆔 Submission #{listing_id}\n\n"
        "Your advert has been sent to our admin "
        "for approval.\n\n"
        "It will become visible to everyone after approval.",
        reply_markup=main_menu(),
    )


# =========================================================
# SAVE EDITED LISTING
# =========================================================

async def save_edited_listing(
    update,
    context,
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
        clear_state(context)

        await update.message.reply_text(
            "❌ Something went wrong.\n\n"
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
        print(
            "Edit listing error:",
            e,
        )

        await update.message.reply_text(
            "❌ Database error while editing."
        )

        return

    clear_state(context)

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
    update,
    context,
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

    # Prepare database
    init_database()

    # Render health server
    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True,
    )

    health_thread.start()

    # Telegram application
    async def post_init(application):
        global BOT_USERNAME
        bot_info = await application.bot.get_me()
        BOT_USERNAME = bot_info.username or ""
        print(f"Bot username: @{BOT_USERNAME}")

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
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

    # ONE text handler
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_input,
        )
    )

    # Errors
    app.add_error_handler(
        error_handler
    )

    print("Bot is running...")

    app.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# START BOT
# =========================================================

if __name__ == "__main__":
    main()
