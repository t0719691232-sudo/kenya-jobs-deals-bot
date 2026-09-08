import re
from urllib.parse import quote
import os
from datetime import datetime, timedelta
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
PREMIUM_CONTACT = "M-Pesa: 0719691232 — Samuel Kimani"


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

            # Featured / premium listing fields.
            cur.execute(
                """
                ALTER TABLE listings
                ADD COLUMN IF NOT EXISTS featured BOOLEAN DEFAULT FALSE
                """
            )

            cur.execute(
                """
                ALTER TABLE listings
                ADD COLUMN IF NOT EXISTS featured_until TIMESTAMP
                """
            )

            # Manual premium requests. Admin approves after confirming payment.
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS premium_requests (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
                    duration_days INTEGER NOT NULL,
                    price INTEGER NOT NULL,
                    mpesa_reference TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                "ALTER TABLE premium_requests ADD COLUMN IF NOT EXISTS mpesa_reference TEXT"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS analytics_events (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    event_type TEXT NOT NULL,
                    listing_id INTEGER REFERENCES listings(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                "ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS search_query TEXT"
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                    l.user_id,
                    l.featured,
                    l.featured_until
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
                    user_id,
                    featured,
                    featured_until
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
                        user_id,
                        featured,
                        featured_until
                    FROM listings
                    WHERE category = %s
                    AND region = %s
                    AND status = 'approved'
                    ORDER BY (featured = TRUE AND (featured_until IS NULL OR featured_until > CURRENT_TIMESTAMP)) DESC, id DESC
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
                        user_id,
                        featured,
                        featured_until
                    FROM listings
                    WHERE category = %s
                    AND status = 'approved'
                    ORDER BY (featured = TRUE AND (featured_until IS NULL OR featured_until > CURRENT_TIMESTAMP)) DESC, id DESC
                    """,
                    (category,),
                )

            return cur.fetchall()


# =========================================================
# FEATURED LISTINGS
# =========================================================

def get_featured_listings():
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
                    user_id,
                    featured,
                    featured_until
                FROM listings
                WHERE status = 'approved'
                  AND featured = TRUE
                  AND (featured_until IS NULL OR featured_until > CURRENT_TIMESTAMP)
                ORDER BY featured_until ASC NULLS LAST, id DESC
                LIMIT 30
                """
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
                    user_id,
                    featured,
                    featured_until
                FROM listings
                WHERE status = 'approved'
                AND (
                    {' AND '.join(conditions)}
                )
                ORDER BY (featured = TRUE AND (featured_until IS NULL OR featured_until > CURRENT_TIMESTAMP)) DESC, ({score_sql}) DESC, id DESC
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
                    user_id,
                    featured,
                    featured_until
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
        "advertiser_photo",
        "premium_listing_id",
        "premium_duration_days",
        "premium_waiting_receipt",
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
# PREMIUM / FEATURED LISTINGS
# =========================================================

PREMIUM_PRICES = {
    7: 200,
    14: 350,
    30: 600,
}


def is_featured_active(row):
    """Return True when a listing is currently featured."""
    if len(row) <= 11 or not row[11]:
        return False
    featured_until = row[12] if len(row) > 12 else None
    return featured_until is None or featured_until > datetime.now()


def get_user_listings(user_id):
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
                    user_id,
                    featured,
                    featured_until
                FROM listings
                WHERE user_id = %s
                  AND status = 'approved'
                ORDER BY id DESC
                LIMIT 30
                """,
                (user_id,),
            )
            return cur.fetchall()


def create_premium_request(user_id, listing_id, duration_days, mpesa_reference):
    price = PREMIUM_PRICES[duration_days]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO premium_requests
                    (user_id, listing_id, duration_days, price, mpesa_reference, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
                RETURNING id
                """,
                (user_id, listing_id, duration_days, price, mpesa_reference),
            )
            request_id = cur.fetchone()[0]
        conn.commit()
    return request_id


def get_pending_premium_requests():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pr.id,
                    pr.user_id,
                    pr.listing_id,
                    pr.duration_days,
                    pr.price,
                    pr.mpesa_reference,
                    pr.status,
                    pr.created_at,
                    l.title,
                    l.category
                FROM premium_requests pr
                INNER JOIN listings l ON l.id = pr.listing_id
                WHERE pr.status = 'pending'
                ORDER BY pr.id ASC
                """
            )
            return cur.fetchall()


def approve_premium_request(request_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, listing_id, duration_days
                FROM premium_requests
                WHERE id = %s AND status = 'pending'
                """,
                (request_id,),
            )
            request = cur.fetchone()
            if not request:
                return None

            user_id, listing_id, duration_days = request
            cur.execute(
                """
                SELECT featured_until
                FROM listings
                WHERE id = %s AND status = 'approved'
                """,
                (listing_id,),
            )
            listing_row = cur.fetchone()
            if not listing_row:
                return None

            current_until = listing_row[0]
            now = datetime.now()
            base = current_until if current_until and current_until > now else now
            new_until = base + timedelta(days=duration_days)

            cur.execute(
                """
                UPDATE listings
                SET featured = TRUE, featured_until = %s
                WHERE id = %s AND status = 'approved'
                """,
                (new_until, listing_id),
            )
            cur.execute(
                """
                UPDATE premium_requests
                SET status = 'approved'
                WHERE id = %s
                """,
                (request_id,),
            )

        conn.commit()

    return user_id, listing_id, new_until


def reject_premium_request(request_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE premium_requests
                SET status = 'rejected'
                WHERE id = %s AND status = 'pending'
                RETURNING user_id, listing_id
                """,
                (request_id,),
            )
            row = cur.fetchone()
        conn.commit()
    return row


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

    featured_label = "⭐ FEATURED\n\n" if is_featured_active(row) else ""

    return (
        f"🆔 Listing #{listing_id}\n\n"
        f"{featured_label}"
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
    if user_id and user_id != ADMIN_ID:
        track_analytics_event(
            "listing_view",
            user_id=user_id,
            listing_id=row[0],
        )

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
                "⭐ Featured Listings",
                callback_data="featured_listings",
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


def register_user(user):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO bot_users (user_id, username, first_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_seen = CURRENT_TIMESTAMP
                    """,
                    (user.id, user.username, user.first_name),
                )
            conn.commit()
    except Exception as e:
        print("User registration tracking error:", e)


def track_analytics_event(
    event_type,
    user_id=None,
    listing_id=None,
    search_query=None,
):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analytics_events
                        (user_id, event_type, listing_id, search_query)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, event_type, listing_id, search_query),
                )
            conn.commit()
    except Exception as e:
        print("Analytics tracking error:", e)


def get_analytics():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE event_type = 'listing_view') AS listing_views,
                    COUNT(*) FILTER (WHERE event_type = 'search') AS searches,
                    COUNT(DISTINCT user_id) FILTER (WHERE user_id IS NOT NULL) AS active_users,
                    COUNT(*) FILTER (
                        WHERE event_type = 'listing_view'
                          AND created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
                    ) AS views_7_days,
                    COUNT(*) FILTER (
                        WHERE event_type = 'search'
                          AND created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
                    ) AS searches_7_days
                FROM analytics_events
                """
            )
            row = cur.fetchone()

            cur.execute(
                """
                SELECT
                    l.id,
                    l.title,
                    COUNT(a.id) AS views
                FROM listings l
                LEFT JOIN analytics_events a
                    ON a.listing_id = l.id
                   AND a.event_type = 'listing_view'
                WHERE l.status = 'approved'
                GROUP BY l.id, l.title
                ORDER BY views DESC, l.id DESC
                LIMIT 5
                """
            )
            top_listings = cur.fetchall()

            cur.execute(
                """
                SELECT
                    COUNT(*) AS registered_users,
                    COUNT(*) FILTER (
                        WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '1 day'
                    ) AS new_users_today,
                    COUNT(*) FILTER (
                        WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
                    ) AS new_users_7_days
                FROM bot_users
                """
            )
            user_stats = cur.fetchone()

            cur.execute(
                """
                SELECT
                    search_query,
                    COUNT(*) AS search_count
                FROM analytics_events
                WHERE event_type = 'search'
                  AND search_query IS NOT NULL
                  AND TRIM(search_query) <> ''
                GROUP BY search_query
                ORDER BY search_count DESC, MAX(created_at) DESC
                LIMIT 5
                """
            )
            top_searches = cur.fetchall()

    return {
        "listing_views": row[0] or 0,
        "searches": row[1] or 0,
        "active_users": row[2] or 0,
        "views_7_days": row[3] or 0,
        "searches_7_days": row[4] or 0,
        "top_listings": top_listings,
        "registered_users": user_stats[0] or 0,
        "new_users_today": user_stats[1] or 0,
        "new_users_7_days": user_stats[2] or 0,
        "top_searches": top_searches,
    }


def get_admin_notifications():
    """Return pending counts and the latest pending items for the admin."""
    pending_ads = get_pending_listings()
    pending_premium = get_pending_premium_requests()

    return {
        "pending_ads": pending_ads,
        "pending_premium": pending_premium,
    }


def get_admin_dashboard():
    """Return key business metrics for the admin dashboard."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_listings,
                    COUNT(*) FILTER (WHERE status = 'approved') AS approved_listings,
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending_listings,
                    COUNT(*) FILTER (
                        WHERE featured = TRUE
                          AND (featured_until IS NULL OR featured_until > CURRENT_TIMESTAMP)
                    ) AS active_featured
                FROM listings
                """
            )
            listing_stats = cur.fetchone()

            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending_premium,
                    COUNT(*) FILTER (WHERE status = 'approved') AS approved_premium,
                    COALESCE(SUM(price) FILTER (WHERE status = 'approved'), 0) AS premium_revenue
                FROM premium_requests
                """
            )
            premium_stats = cur.fetchone()

            # The bot does not maintain a separate users table.
            # Count unique Telegram IDs recorded in listings, premium requests,
            # and favourites as "recorded users".
            cur.execute(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM (
                    SELECT user_id FROM listings WHERE user_id IS NOT NULL
                    UNION
                    SELECT user_id FROM premium_requests
                    UNION
                    SELECT user_id FROM favorites
                ) AS recorded_users
                """
            )
            recorded_users = cur.fetchone()[0]

    return {
        "total_listings": listing_stats[0] or 0,
        "approved_listings": listing_stats[1] or 0,
        "pending_listings": listing_stats[2] or 0,
        "active_featured": listing_stats[3] or 0,
        "pending_premium": premium_stats[0] or 0,
        "approved_premium": premium_stats[1] or 0,
        "premium_revenue": premium_stats[2] or 0,
        "recorded_users": recorded_users or 0,
    }


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
                "📊 Dashboard",
                callback_data="admin_dashboard",
            ),
            InlineKeyboardButton(
                "📈 Analytics",
                callback_data="admin_analytics",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔔 Notifications",
                callback_data="admin_notifications",
            )
        ],
        [
            InlineKeyboardButton(
                "💎 Premium Requests",
                callback_data="premium_requests",
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
    register_user(update.effective_user)

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

    if data == "featured_listings":
        listings = get_featured_listings()

        if not listings:
            await query.edit_message_text(
                "⭐ FEATURED LISTINGS\n\n"
                "There are no Featured Listings available right now.",
                reply_markup=main_menu(),
            )
            return

        await query.edit_message_text(
            "⭐ FEATURED LISTINGS\n\n"
            f"Showing {len(listings)} promoted listing(s).\n\n"
            "These listings are currently featured by advertisers."
        )

        for listing in listings:
            await send_listing(
                query.message,
                listing,
                user_id,
            )

        await query.message.reply_text(
            "What would you like to do next?",
            reply_markup=main_menu(),
        )
        return

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
    # ADVERTISER PREVIEW CONFIRM / CANCEL
    # -----------------------------------------------------

    if data == "advertiser_cancel":
        clear_state(context)
        await query.edit_message_text(
            "❌ Advert cancelled.\n\n"
            "No listing was submitted.",
            reply_markup=main_menu(),
        )
        return

    if data == "advertiser_confirm":
        if not context.user_data.get("advertising"):
            await query.message.reply_text("❌ This advert session has expired. Please start again.")
            return

        photo = context.user_data.get("advertiser_photo")
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⏳ Submitting your advert...")
        await save_advertiser_submission(query, context, photo)
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
        listings = get_user_listings(user_id)

        if not listings:
            await query.edit_message_text(
                "⭐ PREMIUM / FEATURED\n\n"
                "You do not have any approved adverts to feature yet.\n\n"
                "First submit an advert through 📢 Advertise With Us.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
                ),
            )
            return

        buttons = []
        for listing in listings:
            status_text = "⭐ Featured" if is_featured_active(listing) else "📌 Feature"
            buttons.append([
                InlineKeyboardButton(
                    f"{status_text}: #{listing[0]} {listing[2][:28]}",
                    callback_data=f"premium_listing_{listing[0]}",
                )
            ])

        buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])

        await query.edit_message_text(
            "⭐ PREMIUM / FEATURED\n\n"
            "Choose one of your approved adverts to promote.\n\n"
            "Featured adverts appear first in listings and show a ⭐ FEATURED label.\n\n"
            "Pricing:\n"
            "📌 7 days — KSh 200\n"
            "📌 14 days — KSh 350\n"
            "📌 30 days — KSh 600\n\n"
            "Payment is confirmed manually by admin.\n\n"
            f"💳 {PREMIUM_CONTACT}",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("premium_listing_"):
        try:
            listing_id = int(data.replace("premium_listing_", "", 1))
        except ValueError:
            await query.message.reply_text("❌ Invalid listing.")
            return

        listing = get_listing(listing_id)
        if not listing or listing[9] != "approved" or listing[10] != user_id:
            await query.message.reply_text("❌ This listing is not available for your account.")
            return

        await query.edit_message_text(
            "⭐ FEATURE THIS LISTING\n\n"
            f"🆔 Listing #{listing_id}\n"
            f"📌 {listing[2]}\n\n"
            "Choose a promotion period:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📌 7 days — KSh 200", callback_data=f"premium_duration_{listing_id}_7")],
                [InlineKeyboardButton("📌 14 days — KSh 350", callback_data=f"premium_duration_{listing_id}_14")],
                [InlineKeyboardButton("📌 30 days — KSh 600", callback_data=f"premium_duration_{listing_id}_30")],
                [InlineKeyboardButton("⬅️ Back", callback_data="premium")],
            ]),
        )
        return

    if data.startswith("premium_duration_"):
        parts = data.split("_")
        try:
            listing_id = int(parts[2])
            duration_days = int(parts[3])
        except (ValueError, IndexError):
            await query.message.reply_text("❌ Invalid premium option.")
            return

        if duration_days not in PREMIUM_PRICES:
            await query.message.reply_text("❌ Invalid premium period.")
            return

        listing = get_listing(listing_id)
        if not listing or listing[9] != "approved" or listing[10] != user_id:
            await query.message.reply_text("❌ This listing is not available for your account.")
            return

        price = PREMIUM_PRICES[duration_days]

        context.user_data["premium_listing_id"] = listing_id
        context.user_data["premium_duration_days"] = duration_days
        context.user_data["premium_waiting_receipt"] = True

        await query.edit_message_text(
            "💳 M-PESA PAYMENT\n\n"
            f"📌 Listing: {listing[2]}\n"
            f"⭐ Duration: {duration_days} days\n"
            f"💰 Amount: KSh {price}\n\n"
            f"Send KSh {price} to:\n"
            f"📱 {PREMIUM_CONTACT}\n\n"
            "After payment, send the M-Pesa transaction code here.\n"
            "Example: QABC123XYZ\n\n"
            "Your request will be sent to admin for payment verification."
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
    # PREMIUM REQUESTS
    # -----------------------------------------------------

    if data == "admin_analytics":
        stats = get_analytics()

        lines = [
            "📈 BOT ANALYTICS",
            "",
            "👥 USER GROWTH",
            f"👤 Registered Users: {stats['registered_users']}",
            f"🆕 New Today: {stats['new_users_today']}",
            f"📅 New Last 7 Days: {stats['new_users_7_days']}",
            "",
            "📊 ENGAGEMENT",
            f"👀 Total Listing Views: {stats['listing_views']}",
            f"🔎 Total Searches: {stats['searches']}",
            f"👥 Users Tracked: {stats['active_users']}",
            "",
            "📅 LAST 7 DAYS",
            f"👀 Listing Views: {stats['views_7_days']}",
            f"🔎 Searches: {stats['searches_7_days']}",
            "",
            "🔎 TOP 5 SEARCHES",
        ]

        if stats["top_searches"]:
            for position, (search_query, count) in enumerate(
                stats["top_searches"], start=1
            ):
                lines.append(
                    f"{position}. {search_query[:40]} — {count} search(es)"
                )
        else:
            lines.append("No searches recorded yet.")

        lines.append("")
        lines.append("🏆 TOP 5 LISTINGS BY VIEWS")

        if stats["top_listings"]:
            for position, (listing_id, title, views) in enumerate(
                stats["top_listings"], start=1
            ):
                lines.append(
                    f"{position}. #{listing_id} {title[:35]} — {views} view(s)"
                )
        else:
            lines.append("No listing views recorded yet.")

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="admin_analytics")],
                [InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")],
                [InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_menu")],
            ]),
        )
        return

    if data == "admin_notifications":
        notifications = get_admin_notifications()
        pending_ads = notifications["pending_ads"]
        pending_premium = notifications["pending_premium"]

        lines = [
            "🔔 ADMIN NOTIFICATIONS",
            "",
            f"📥 Pending Adverts: {len(pending_ads)}",
            f"💎 Pending Premium Payments: {len(pending_premium)}",
            "",
            "📌 RECENT ITEMS",
        ]

        shown = 0

        for listing in pending_ads[:5]:
            lines.append(
                f"📥 Advert #{listing[0]} — {listing[2]}"
            )
            shown += 1

        for request in pending_premium[:5]:
            request_id, requester_id, listing_id, duration_days, price, mpesa_reference, status, created_at, title, category = request
            lines.append(
                f"💎 Premium #{request_id} — #{listing_id} {title}"
            )
            lines.append(
                f"   🧾 {mpesa_reference or 'No reference'} • KSh {price}"
            )
            shown += 1

        if shown == 0:
            lines.append("No pending items right now. ✅")

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="admin_notifications")],
                [InlineKeyboardButton("📥 Pending Ads", callback_data="pending_ads")],
                [InlineKeyboardButton("💎 Premium Requests", callback_data="premium_requests")],
                [InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_menu")],
            ]),
        )
        return

    if data == "admin_menu":
        await query.edit_message_text(
            "🔐 ADMIN PANEL",
            reply_markup=admin_menu(),
        )
        return

    if data == "admin_dashboard":
        stats = get_admin_dashboard()

        await query.edit_message_text(
            "📊 ADMIN DASHBOARD\n\n"
            f"👥 Recorded Users: {stats['recorded_users']}\n"
            f"📋 Total Listings: {stats['total_listings']}\n"
            f"✅ Approved Listings: {stats['approved_listings']}\n"
            f"⏳ Pending Ads: {stats['pending_listings']}\n"
            f"⭐ Active Featured: {stats['active_featured']}\n\n"
            f"💎 Pending Premium: {stats['pending_premium']}\n"
            f"🏆 Approved Premium: {stats['approved_premium']}\n"
            f"💰 Premium Revenue: KSh {stats['premium_revenue']:,}\n\n"
            "ℹ️ Revenue counts approved Premium requests only.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="admin_dashboard")],
                [InlineKeyboardButton("💎 Premium Requests", callback_data="premium_requests")],
                [InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_menu")],
            ]),
        )
        return

    if data == "premium_requests":
        requests = get_pending_premium_requests()

        if not requests:
            await query.edit_message_text(
                "💎 PREMIUM REQUESTS\n\n"
                "There are no premium requests waiting for approval.",
                reply_markup=admin_menu(),
            )
            return

        await query.edit_message_text(
            f"💎 PREMIUM REQUESTS\n\n"
            f"{len(requests)} request(s) waiting for payment confirmation."
        )

        for req in requests:
            request_id, requester_id, listing_id, duration_days, price, mpesa_reference, status, created_at, title, category = req
            buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"premium_approve_{request_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"premium_reject_{request_id}"),
                ]
            ])
            await query.message.reply_text(
                "💎 PREMIUM REQUEST\n\n"
                f"Request #{request_id}\n"
                f"🆔 Listing #{listing_id}\n"
                f"📌 {title}\n"
                f"🗂 {category_name(category)}\n"
                f"👤 User ID: {requester_id}\n"
                f"📌 Duration: {duration_days} days\n"
                f"💰 Price: KSh {price}\n"
                f"🧾 M-Pesa Reference: {mpesa_reference or 'Not provided'}\n"
                f"🕐 Requested: {created_at}\n\n"
                "Verify the M-Pesa payment before approving.",
                reply_markup=buttons,
            )

        await query.message.reply_text("🔐 Admin Panel", reply_markup=admin_menu())
        return

    if data.startswith("premium_approve_"):
        try:
            request_id = int(data.replace("premium_approve_", "", 1))
        except ValueError:
            await query.message.reply_text("❌ Invalid request ID.")
            return

        result = approve_premium_request(request_id)
        if not result:
            await query.message.reply_text("❌ Request not found, already processed, or listing unavailable.")
            return

        requester_id, listing_id, featured_until = result
        await query.edit_message_text(
            f"✅ Premium request #{request_id} approved.\n\n"
            f"🆔 Listing #{listing_id}\n"
            f"⭐ Featured until: {featured_until}"
        )

        try:
            await context.bot.send_message(
                chat_id=requester_id,
                text=(
                    "🎉 PREMIUM ACTIVATED!\n\n"
                    f"Your listing #{listing_id} is now ⭐ FEATURED.\n"
                    f"It will remain featured until {featured_until}."
                ),
            )
        except Exception as e:
            print("Premium approval notification error:", e)
        return

    if data.startswith("premium_reject_"):
        try:
            request_id = int(data.replace("premium_reject_", "", 1))
        except ValueError:
            await query.message.reply_text("❌ Invalid request ID.")
            return

        result = reject_premium_request(request_id)
        if not result:
            await query.message.reply_text("❌ Request not found or already processed.")
            return

        requester_id, listing_id = result
        await query.edit_message_text(
            f"❌ Premium request #{request_id} rejected.\n\n"
            f"🆔 Listing #{listing_id}"
        )

        try:
            await context.bot.send_message(
                chat_id=requester_id,
                text=(
                    "❌ PREMIUM REQUEST NOT APPROVED\n\n"
                    f"Your Featured request for listing #{listing_id} was not approved."
                ),
            )
        except Exception as e:
            print("Premium rejection notification error:", e)
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
    # PREMIUM M-PESA RECEIPT
    # =====================================================

    if context.user_data.get("premium_waiting_receipt"):
        receipt = text.replace(" ", "").upper()

        if not re.fullmatch(r"[A-Z0-9]{6,20}", receipt):
            await update.message.reply_text(
                "❌ Invalid M-Pesa transaction code.\n\n"
                "Please send the transaction code only, using 6–20 letters/numbers.\n"
                "Example: QABC123XYZ"
            )
            return

        listing_id = context.user_data.get("premium_listing_id")
        duration_days = context.user_data.get("premium_duration_days")

        if not listing_id or duration_days not in PREMIUM_PRICES:
            context.user_data.pop("premium_waiting_receipt", None)
            await update.message.reply_text(
                "❌ Your Premium payment session expired. Please start again from 💎 Premium."
            )
            return

        listing = get_listing(listing_id)
        if not listing or listing[9] != "approved" or listing[10] != update.effective_user.id:
            clear_state(context)
            await update.message.reply_text(
                "❌ This listing is no longer available for your account.",
                reply_markup=main_menu(),
            )
            return

        price = PREMIUM_PRICES[duration_days]
        request_id = create_premium_request(
            update.effective_user.id,
            listing_id,
            duration_days,
            receipt,
        )

        context.user_data.pop("premium_waiting_receipt", None)
        context.user_data.pop("premium_listing_id", None)
        context.user_data.pop("premium_duration_days", None)

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "💎 PREMIUM REQUEST\n\n"
                    f"Request #{request_id}\n"
                    f"🆔 Listing #{listing_id}\n"
                    f"📌 {listing[2]}\n"
                    f"👤 User ID: {update.effective_user.id}\n"
                    f"📌 Duration: {duration_days} days\n"
                    f"💰 Price: KSh {price}\n"
                    f"🧾 M-Pesa Reference: {receipt}\n\n"
                    "Verify the M-Pesa payment, then approve from "
                    "/admin → Premium Requests."
                ),
            )
        except Exception as e:
            print("Premium admin notification error:", e)

        await update.message.reply_text(
            "💎 PREMIUM REQUEST SENT\n\n"
            f"📌 Listing: {listing[2]}\n"
            f"⭐ Duration: {duration_days} days\n"
            f"💰 Amount: KSh {price}\n"
            f"🧾 M-Pesa Reference: {receipt}\n\n"
            "Your payment reference has been sent to admin for verification. "
            "Once payment is confirmed, your Featured listing will be activated.",
            reply_markup=main_menu(),
        )
        return

    # =====================================================
    # ADVERTISER SUBMISSION
    # =====================================================

    if context.user_data.get("advertising"):

        if context.user_data.get("admin_action") == "advertiser_photo":
            if text.lower() == "skip":
                await show_advertiser_preview(update, context, None)
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

        track_analytics_event(
            "search",
            user_id=update.effective_user.id,
            search_query=text,
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

    if context.user_data.get("advertising"):
        if context.user_data.get("admin_action") == "advertiser_photo":
            await show_advertiser_preview(update, context, photo_file_id)
        else:
            await update.message.reply_text(
                "❌ Please use the buttons on the preview to submit or cancel."
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
# ADVERTISER PREVIEW
# =========================================================

async def show_advertiser_preview(update, context, photo=None):
    data = context.user_data.get("advertiser_data")
    category = context.user_data.get("advertiser_category")
    region = context.user_data.get("advertiser_region")

    if not data or not category or not region:
        clear_state(context)
        await update.message.reply_text("❌ Something went wrong. Please start again.")
        return

    preview = (
        "👀 ADVERT PREVIEW\n\n"
        f"🗂 Category: {category_name(category)}\n"
        f"🗺 Region: {region}\n"
        f"📌 {data['title']}\n"
        f"📍 {data['location']}\n"
        f"💰 {data['price']}\n"
        f"☎️ {data['contact']}\n\n"
        f"📝 {data['description']}\n\n"
        "Please check everything carefully.\n"
        "Your advert will be sent to admin for approval."
    )

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Submit Advert", callback_data="advertiser_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="advertiser_cancel"),
        ]
    ])

    context.user_data["advertiser_photo"] = photo
    context.user_data["admin_action"] = "advertiser_confirm"

    if photo:
        await update.message.reply_photo(
            photo=photo,
            caption=preview,
            reply_markup=markup,
        )
    else:
        await update.message.reply_text(
            preview + "\n\n📸 Photo: None",
            reply_markup=markup,
        )


# =========================================================
# SAVE ADVERTISER SUBMISSION
# =========================================================

async def save_advertiser_submission(
    query,
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

        await query.message.reply_text(
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
            user_id=query.from_user.id,
        )

    except Exception as e:
        print(
            "Advertiser submission error:",
            e,
        )

        await query.message.reply_text(
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

    await query.message.reply_text(
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
