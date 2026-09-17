"""
SocialFlow Telegram Bot

Flows:
  /start -> Login or Sign Up
    Login:  email -> password -> main menu
    Sign Up: email -> password -> workspace name -> account created (pending_payment
             unless TRIAL_DAYS>0 on the backend) -> payment method menu -> claim
             submitted -> waits for admin approval
  Main menu: upload media -> caption -> platforms -> schedule -> confirm
             (blocked with a 402 from the backend until the subscription is active)
  Connect social account: platform -> username -> access token (manual entry —
             there's no OAuth app wired up yet, see NOTE in connect_account below)
  Payment: choose Monthly or Yearly -> price shown (with any live seasonal
             discount already applied) -> choose payment method -> claim submitted
  /status  -> show current subscription status and plan
  /pay     -> re-open the billing-plan menu (e.g. after a rejected claim)

  Admin-only (requires the caller's Telegram id to match ADMIN_TELEGRAM_ID):
  /pending -> list payment claims awaiting review
  /approve <claim_id> -> approve a claim, activates the workspace's subscription
  /reject <claim_id>  -> reject a claim
  /seasons -> pick a ready-made seasonal discount (New Year, Eid, Black Friday, ...)
              and turn it on with one tap
  /setpromo <percent> <monthly|yearly|both> <days|-> <name> -> start a custom discount
  /clearpromo -> turn off whatever discount is currently live
  /promo -> show what discount (if any) is currently live

  Temporary: /myid -> prints your numeric Telegram id, to help set ADMIN_TELEGRAM_ID.
"""
import os
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

from services import backend_service as api

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "")

# Conversation states
(AWAITING_EMAIL, AWAITING_PASSWORD, AWAITING_MEDIA, AWAITING_CAPTION,
 CHOOSING_PLATFORMS, CHOOSING_SCHEDULE,
 AWAITING_SIGNUP_EMAIL, AWAITING_SIGNUP_PASSWORD, AWAITING_SIGNUP_WORKSPACE,
 AWAITING_CLAIM_REFERENCE,
 AWAITING_CONNECT_USERNAME, AWAITING_CONNECT_TOKEN) = range(12)

ALL_PLATFORMS = ["facebook", "instagram", "tiktok", "twitter"]

# Simple in-memory session store: telegram_user_id -> {token, workspace, draft_post}
# For production, persist this (Redis or DB) so it survives bot restarts.
SESSIONS: dict = {}


def get_session(user_id: int) -> dict:
    return SESSIONS.setdefault(user_id, {})


def is_admin(update: Update) -> bool:
    return bool(ADMIN_TELEGRAM_ID) and str(update.effective_user.id) == str(ADMIN_TELEGRAM_ID)


# ---------- /start: login vs sign up ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(update.effective_user.id)

    if session.get("token"):
        await show_main_menu(update)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🔑 Log In", callback_data="auth_login")],
        [InlineKeyboardButton("🆕 Sign Up", callback_data="auth_signup")],
    ]
    await update.message.reply_text(
        "👋 Welcome to SocialFlow!\n\n"
        "Already have an account, or starting fresh?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


async def auth_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "auth_login":
        await query.message.reply_text("What's your email?")
        return AWAITING_EMAIL
    elif query.data == "auth_signup":
        await query.message.reply_text(
            "Let's create your account.\n\nWhat email should we use?"
        )
        return AWAITING_SIGNUP_EMAIL


# ---------- Login ----------

async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["email"] = update.message.text.strip()
    await update.message.reply_text("Got it. Now your password:")
    return AWAITING_PASSWORD


async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = context.user_data.get("email")
    password = update.message.text.strip()

    try:
        result = api.login(email, password)
    except Exception:
        await update.message.reply_text("❌ Login failed. Check your email/password and try /start again.")
        return ConversationHandler.END

    session = get_session(update.effective_user.id)
    session["token"] = result["token"]
    session["workspace"] = result["workspace"]

    await update.message.reply_text(f"✅ Linked! Welcome, you're a {result['workspace']['role']} here.")
    await show_main_menu(update)
    return ConversationHandler.END


# ---------- Sign up ----------

async def receive_signup_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["signup_email"] = update.message.text.strip()
    await update.message.reply_text("Choose a password (6+ characters):")
    return AWAITING_SIGNUP_PASSWORD


async def receive_signup_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["signup_password"] = update.message.text.strip()
    await update.message.reply_text("What should we call your workspace (e.g. your business name)?")
    return AWAITING_SIGNUP_WORKSPACE


async def receive_signup_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    workspace_name = update.message.text.strip()
    email = context.user_data.get("signup_email")
    password = context.user_data.get("signup_password")

    try:
        result = api.signup(email, password, workspace_name)
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 409:
            await update.message.reply_text(
                "That email is already registered. Try /start and choose Log In instead."
            )
        else:
            await update.message.reply_text(f"❌ Sign up failed: {e}")
        return ConversationHandler.END

    session = get_session(update.effective_user.id)
    session["token"] = result["token"]
    session["workspace"] = result["workspace"]

    sub_status = result.get("subscription", {}).get("status", "pending_payment")
    await update.message.reply_text(f"✅ Account created for {workspace_name}!")

    if sub_status == "trial":
        await update.message.reply_text("You're on a free trial — jump right in!")
        await show_main_menu(update)
    else:
        await update.message.reply_text(
            "One more step: this account unlocks after a payment is confirmed. "
            "Let's set that up now."
        )
        await show_cycle_menu(update)
    return ConversationHandler.END


# ---------- Main menu ----------

async def show_main_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("📤 Upload Media", callback_data="menu_upload")],
        [InlineKeyboardButton("🔌 Connect Social Account", callback_data="menu_connect")],
        [InlineKeyboardButton("💳 Payment / Subscription", callback_data="menu_pay")],
        [InlineKeyboardButton("🔗 Bot Share Link", callback_data="menu_share")],
        [InlineKeyboardButton("❓ Help", callback_data="menu_help")],
    ]
    await update.message.reply_text(
        "What would you like to do?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session(update.effective_user.id)

    if not session.get("token") and query.data != "menu_help":
        await query.message.reply_text("Please link your account first with /start")
        return ConversationHandler.END

    if query.data == "menu_upload":
        await query.message.reply_text("🎬 Send me the image or video you want to post.")
        return AWAITING_MEDIA
    elif query.data == "menu_connect":
        return await start_connect_account(update, context)
    elif query.data == "menu_pay":
        await show_cycle_menu(update)
    elif query.data == "menu_share":
        try:
            link_info = api.get_bot_share_link(session["token"])
            await query.message.reply_text(
                f"🔗 Share this bot with your team:\n{link_info['botLink']}\n\n{link_info['note']}"
            )
        except Exception:
            await query.message.reply_text("No bot link configured yet — set it up in the dashboard first.")
    elif query.data == "menu_help":
        await query.message.reply_text(
            "Commands:\n"
            "/start - Main menu\n"
            "/status - Check your subscription status\n"
            "/pay - Submit or re-submit a payment\n"
            "Just send a photo/video anytime to start a new post."
        )
    return ConversationHandler.END


# ---------- Connect social account (manual token entry) ----------
# NOTE: there's no OAuth app wired up for Facebook/Instagram/TikTok/Twitter yet
# (those app credentials in backend/.env.example are blank, and the actual
# posting functions in backend/services/socialPlatforms.js are stubbed —
# they log and report success but don't call the real platform APIs). Until
# that's built, "connecting" here just stores a username + optional token you
# already have, and posting is simulated end-to-end for testing.

async def start_connect_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(p.title(), callback_data=f"connectplat_{p}")] for p in ALL_PLATFORMS]
    await update.callback_query.message.reply_text(
        "Which platform do you want to connect?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


async def choose_connect_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    platform = query.data.replace("connectplat_", "")
    context.user_data["connect_platform"] = platform
    await query.message.reply_text(f"What's your {platform.title()} username or page name?")
    return AWAITING_CONNECT_USERNAME


async def receive_connect_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["connect_username"] = update.message.text.strip()
    await update.message.reply_text(
        "If you already have an access token for this account, paste it now. "
        "Otherwise just send \"skip\" — you can still test the scheduling flow without one."
    )
    return AWAITING_CONNECT_TOKEN


async def receive_connect_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(update.effective_user.id)
    text = update.message.text.strip()
    token_value = None if text.lower() == "skip" else text

    try:
        api.connect_account(
            session["token"],
            context.user_data["connect_platform"],
            context.user_data["connect_username"],
            token_value
        )
        await update.message.reply_text(
            f"✅ {context.user_data['connect_platform'].title()} account "
            f"\"{context.user_data['connect_username']}\" saved."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Couldn't save that account: {e}")

    context.user_data.pop("connect_platform", None)
    context.user_data.pop("connect_username", None)
    return ConversationHandler.END


# ---------- Payment / billing ----------

def payment_instructions(method: str) -> str:
    if method == "local_manual":
        return os.getenv(
            "LOCAL_PAYMENT_INSTRUCTIONS",
            "⚠️ Local payment details aren't configured yet — ask the admin to set "
            "LOCAL_PAYMENT_INSTRUCTIONS in the bot's environment."
        )
    elif method == "crypto":
        address = os.getenv("CRYPTO_WALLET_ADDRESS", "")
        network = os.getenv("CRYPTO_NETWORK", "")
        if not address:
            return "⚠️ Crypto wallet address isn't configured yet — ask the admin to set it up."
        return f"Send payment to this {network or 'crypto'} address:\n`{address}`"
    elif method == "international":
        return os.getenv(
            "INTERNATIONAL_PAYMENT_INSTRUCTIONS",
            "⚠️ International payment details aren't configured yet — ask the admin to set "
            "INTERNATIONAL_PAYMENT_INSTRUCTIONS in the bot's environment."
        )
    return "Unknown payment method."


def format_price_line(quote: dict) -> str:
    price = f"{quote['finalPrice']} {quote['currency']}"
    if quote.get("discountPercent"):
        base = f"{quote['basePrice']} {quote['currency']}"
        promo = quote.get("promoName") or "Discount"
        return f"~{base}~ *{price}* — {quote['discountPercent']}% off ({promo}) 🎉"
    return f"*{price}*"


async def show_cycle_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("🗓️ Monthly", callback_data="cycle_monthly")],
        [InlineKeyboardButton("📆 Yearly (best value)", callback_data="cycle_yearly")],
    ]
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text("Choose a billing plan:", reply_markup=InlineKeyboardMarkup(keyboard))


async def choose_billing_cycle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cycle = query.data.replace("cycle_", "")
    context.user_data["claim_cycle"] = cycle
    session = get_session(update.effective_user.id)

    try:
        quote = api.get_pricing(session["token"], cycle)
    except Exception as e:
        await query.message.reply_text(f"❌ Couldn't fetch pricing: {e}")
        return ConversationHandler.END

    period = "month" if cycle == "monthly" else "year"
    await query.message.reply_text(
        f"{cycle.title()} plan: {format_price_line(quote)} / {period}",
        parse_mode="Markdown"
    )
    await show_payment_menu(update)
    return ConversationHandler.END


async def show_payment_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("🏦 Local Payment", callback_data="pay_local_manual")],
        [InlineKeyboardButton("₿ Crypto", callback_data="pay_crypto")],
        [InlineKeyboardButton("🌍 International", callback_data="pay_international")],
    ]
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text("How would you like to pay?", reply_markup=InlineKeyboardMarkup(keyboard))


async def choose_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.replace("pay_", "")
    context.user_data["claim_method"] = method

    await query.message.reply_text(payment_instructions(method), parse_mode="Markdown")
    await query.message.reply_text(
        "Once you've paid, send me a reference: a transaction ID, screenshot caption, "
        "or any note that helps us confirm it."
    )
    return AWAITING_CLAIM_REFERENCE


async def receive_claim_reference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(update.effective_user.id)
    method = context.user_data.get("claim_method", "local_manual")
    cycle = context.user_data.get("claim_cycle", "monthly")
    reference = update.message.text.strip()

    try:
        api.submit_claim(
            session["token"], method, billing_cycle=cycle, reference=reference,
            telegram_chat_id=str(update.effective_user.id)
        )
        await update.message.reply_text(
            "✅ Got it! Your payment is pending review. You'll be able to use the system "
            "as soon as it's approved — check anytime with /status."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Couldn't submit that claim: {e}")

    context.user_data.pop("claim_method", None)
    context.user_data.pop("claim_cycle", None)
    return ConversationHandler.END


async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(update.effective_user.id)
    if not session.get("token"):
        await update.message.reply_text("Please link your account first with /start")
        return
    await show_cycle_menu(update)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(update.effective_user.id)
    if not session.get("token"):
        await update.message.reply_text("Please link your account first with /start")
        return

    try:
        status = api.get_billing_status(session["token"])
    except Exception as e:
        await update.message.reply_text(f"❌ Couldn't fetch your status: {e}")
        return

    lines = [f"Subscription: *{status['status']}*"]
    if status.get("billingCycle"):
        lines.append(f"Plan: {status['billingCycle']}")
    if status.get("trialEndsAt"):
        lines.append(f"Trial ends: {status['trialEndsAt']}")
    if status.get("currentPeriodEnd"):
        lines.append(f"Renews/expires: {status['currentPeriodEnd']}")
    if status.get("pendingClaim"):
        c = status["pendingClaim"]
        lines.append(f"Pending claim: #{c['id']} ({c['method']}, {c.get('billing_cycle', 'monthly')}), submitted {c['created_at']}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ---------- Admin commands ----------

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: `{update.effective_user.id}`", parse_mode="Markdown")


# Quick-pick seasonal templates for /seasons — tap one to activate it instantly.
# Edit this dict any time to change what shows up (name, percent, cycle, days).
SEASONAL_PRESETS = {
    "newyear": ("New Year Sale", 20, "both", 14),
    "eid": ("Eid Sale", 20, "both", 7),
    "blackfriday": ("Black Friday Sale", 30, "both", 3),
    "ramadan": ("Ramadan Special", 15, "both", 30),
    "summer": ("Summer Sale", 15, "both", 30),
    "independence": ("Independence Day Sale", 15, "both", 5),
}


async def seasons_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Not authorized.")
        return
    keyboard = [
        [InlineKeyboardButton(f"{label} — {pct}% off", callback_data=f"preset_{key}")]
        for key, (label, pct, cycle, days) in SEASONAL_PRESETS.items()
    ]
    keyboard.append([InlineKeyboardButton("✏️ Something else (use /setpromo)", callback_data="preset_custom")])
    await update.message.reply_text(
        "Pick a seasonal promotion to turn on right now:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def apply_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update):
        await query.message.reply_text("Not authorized.")
        return
    key = query.data.replace("preset_", "")
    if key == "custom":
        await query.message.reply_text(
            "Use /setpromo <percent> <monthly|yearly|both> <days|-> <name>\n"
            "Example: /setpromo 25 both 10 Ramadan Kareem Offer"
        )
        return
    preset = SEASONAL_PRESETS.get(key)
    if not preset:
        await query.message.reply_text("Unknown preset.")
        return
    name, pct, cycle, days = preset
    try:
        result = api.set_promotion(name, pct, cycle, days)
        promo = result["promotion"]
        await query.message.reply_text(
            f"🎉 \"{promo['name']}\" is live: {promo['discountPercent']}% off ({promo['billingCycle']}) "
            f"for {days} days.\nCustomers see this automatically when they choose a plan. "
            "Use /clearpromo to end it early."
        )
    except Exception as e:
        await query.message.reply_text(f"❌ Couldn't activate promotion: {e}")


async def setpromo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Not authorized.")
        return
    if len(context.args) < 4:
        await update.message.reply_text(
            "Usage: /setpromo <percent> <monthly|yearly|both> <days|-> <name>\n"
            "Example: /setpromo 20 both 14 New Year Sale\n"
            "Use - for days to run until you /clearpromo it manually.\n"
            "Tip: /seasons shows ready-made options you can turn on with one tap."
        )
        return

    percent_str, cycle, days_str, *name_parts = context.args
    name = " ".join(name_parts)
    try:
        percent = int(percent_str)
    except ValueError:
        await update.message.reply_text("percent must be a whole number, e.g. 20")
        return
    if cycle not in ("monthly", "yearly", "both"):
        await update.message.reply_text("cycle must be monthly, yearly, or both")
        return
    days = None if days_str == "-" else int(days_str)

    try:
        result = api.set_promotion(name, percent, cycle, days)
    except Exception as e:
        await update.message.reply_text(f"❌ Couldn't set promotion: {e}")
        return

    promo = result["promotion"]
    ends_text = f" until {promo['endsAt']}" if promo.get("endsAt") else " (no end date — use /clearpromo to end it)"
    await update.message.reply_text(
        f"🎉 \"{promo['name']}\" is live: {promo['discountPercent']}% off ({promo['billingCycle']}){ends_text}\n"
        "Customers will see this automatically when they choose a plan."
    )


async def clearpromo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Not authorized.")
        return
    try:
        api.clear_promotion()
        await update.message.reply_text("Promotion cleared. Standard pricing is back in effect.")
    except Exception as e:
        await update.message.reply_text(f"❌ Couldn't clear promotion: {e}")


async def promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Not authorized.")
        return
    try:
        promos = api.list_promotions()
    except Exception as e:
        await update.message.reply_text(f"❌ Couldn't fetch promotions: {e}")
        return

    active = [p for p in promos if p.get("active")]
    if not active:
        await update.message.reply_text("No active promotion right now. /seasons for quick options, or /setpromo for a custom one.")
        return

    lines = ["Active promotion(s):"]
    for p in active:
        ends = f", ends {p['ends_at']}" if p.get("ends_at") else " (no end date set)"
        lines.append(f"#{p['id']} \"{p['name']}\" — {p['discount_percent']}% off ({p['billing_cycle']}){ends}")
    await update.message.reply_text("\n".join(lines))


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Not authorized.")
        return
    try:
        claims = api.list_pending_claims()
    except Exception as e:
        await update.message.reply_text(f"❌ Couldn't fetch claims: {e}")
        return

    if not claims:
        await update.message.reply_text("No pending claims.")
        return

    lines = ["Pending claims:"]
    for c in claims:
        lines.append(
            f"#{c['id']} — {c['workspace_name']} ({c.get('submitted_by_email', '?')}) "
            f"via {c['method']}, ref: {c.get('reference') or '—'}"
        )
    lines.append("\nApprove with /approve <id>, reject with /reject <id>.")
    await update.message.reply_text("\n".join(lines))


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve <claim_id>")
        return
    try:
        result = api.approve_claim(context.args[0])
        await update.message.reply_text(f"✅ Claim #{context.args[0]} approved. Subscription is now active.")
        chat_id = result.get("telegramChatId")
        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text="🎉 Your payment was confirmed! Your subscription is now active — /start to continue."
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Couldn't approve claim: {e}")


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /reject <claim_id>")
        return
    try:
        result = api.reject_claim(context.args[0])
        await update.message.reply_text(f"Claim #{context.args[0]} rejected.")
        chat_id = result.get("telegramChatId")
        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Your payment claim couldn't be confirmed. Please double-check and try /pay again, "
                     "or contact support."
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Couldn't reject claim: {e}")


# ---------- Upload / caption / platforms / schedule (paid action) ----------

async def receive_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(update.effective_user.id)
    if not session.get("token"):
        await update.message.reply_text("Please link your account first with /start")
        return ConversationHandler.END

    file_obj = None
    mime_type = "image/jpeg"
    if update.message.photo:
        file_obj = await update.message.photo[-1].get_file()
    elif update.message.video:
        file_obj = await update.message.video.get_file()
        mime_type = "video/mp4"
    else:
        await update.message.reply_text("Please send a photo or video file.")
        return AWAITING_MEDIA

    local_path = f"/tmp/{file_obj.file_unique_id}"
    await file_obj.download_to_drive(local_path)

    try:
        result = api.upload_media(session["token"], local_path, mime_type)
    except Exception as e:
        await update.message.reply_text(f"❌ Upload failed: {e}")
        return ConversationHandler.END

    context.user_data["draft_media_ids"] = [result["id"]]
    await update.message.reply_text(
        f"✓ Media received ({result['fileType']}).\n\nNow send me the caption (with hashtags if you want):"
    )
    return AWAITING_CAPTION


async def receive_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["draft_caption"] = update.message.text
    context.user_data["draft_platforms"] = []

    await update.message.reply_text(
        "✓ Caption saved!\n\nNow select platforms (tap all that apply, then Done):",
        reply_markup=platform_keyboard([])
    )
    return CHOOSING_PLATFORMS


def platform_keyboard(selected: list) -> InlineKeyboardMarkup:
    rows = []
    for p in ALL_PLATFORMS:
        label = f"✅ {p.title()}" if p in selected else p.title()
        rows.append([InlineKeyboardButton(label, callback_data=f"platform_{p}")])
    rows.append([InlineKeyboardButton("➡️ Done", callback_data="platforms_done")])
    return InlineKeyboardMarkup(rows)


async def toggle_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected = context.user_data.setdefault("draft_platforms", [])
    platform = query.data.replace("platform_", "")

    if platform in selected:
        selected.remove(platform)
    else:
        selected.append(platform)

    await query.edit_message_reply_markup(reply_markup=platform_keyboard(selected))
    return CHOOSING_PLATFORMS


async def platforms_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get("draft_platforms"):
        await query.message.reply_text("Select at least one platform first.")
        return CHOOSING_PLATFORMS

    keyboard = [
        [InlineKeyboardButton("🚀 Post Now", callback_data="schedule_now")],
        [InlineKeyboardButton("⏰ In 1 hour", callback_data="schedule_1h")],
        [InlineKeyboardButton("📅 Tomorrow 9 AM", callback_data="schedule_tomorrow9")],
    ]
    await query.message.reply_text("When should this go out?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_SCHEDULE


async def finalize_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session(update.effective_user.id)

    now = datetime.utcnow()
    if query.data == "schedule_now":
        scheduled_time = None
    elif query.data == "schedule_1h":
        scheduled_time = (now + timedelta(hours=1)).isoformat()
    else:  # schedule_tomorrow9
        tomorrow_9am = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0)
        scheduled_time = tomorrow_9am.isoformat()

    try:
        result = api.create_post(
            token=session["token"],
            caption=context.user_data.get("draft_caption", ""),
            platforms=context.user_data.get("draft_platforms", []),
            media_ids=context.user_data.get("draft_media_ids", []),
            scheduled_time=scheduled_time
        )
        when_text = "right now" if not scheduled_time else f"at {scheduled_time}"
        await query.message.reply_text(
            f"✅ Post #{result['id']} scheduled for {when_text} "
            f"on {', '.join(context.user_data.get('draft_platforms', []))}!"
        )
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 402:
            await query.message.reply_text(
                "💳 Your subscription isn't active yet, so posts can't be scheduled. "
                "Use /pay to submit a payment, or /status to check where things stand."
            )
        else:
            await query.message.reply_text(f"❌ Failed to schedule post: {e}")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Cancelled. /start to begin again.")
    return ConversationHandler.END


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # NOTE on structure: every button that can be tapped from a "cold" screen
    # (the main menu, or a screen shown after a previous flow ended) has to be
    # an entry_point, not just a handler nested under states — a
    # ConversationHandler only looks at `states` while a conversation is
    # already active for that chat, and each of our sub-flows (login, signup,
    # connect-account, payment) explicitly ends the conversation before
    # showing the next menu. So auth_/menu_/connectplat_/pay_ callbacks are
    # entry points, and only what follows them (typed replies) lives in states.
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.PHOTO | filters.VIDEO, receive_media),
            CallbackQueryHandler(auth_router, pattern="^auth_"),
            CallbackQueryHandler(menu_router, pattern="^menu_"),
            CallbackQueryHandler(choose_connect_platform, pattern="^connectplat_"),
            CallbackQueryHandler(choose_billing_cycle, pattern="^cycle_"),
            CallbackQueryHandler(choose_payment_method, pattern="^pay_"),
        ],
        states={
            AWAITING_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email)],
            AWAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)],
            AWAITING_SIGNUP_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_signup_email)],
            AWAITING_SIGNUP_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_signup_password)],
            AWAITING_SIGNUP_WORKSPACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_signup_workspace)],
            AWAITING_CLAIM_REFERENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_claim_reference)],
            AWAITING_CONNECT_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_connect_username)],
            AWAITING_CONNECT_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_connect_token)],
            AWAITING_MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO, receive_media)],
            AWAITING_CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_caption)],
            CHOOSING_PLATFORMS: [
                CallbackQueryHandler(platforms_done, pattern="^platforms_done$"),
                CallbackQueryHandler(toggle_platform, pattern="^platform_"),
            ],
            CHOOSING_SCHEDULE: [CallbackQueryHandler(finalize_schedule, pattern="^schedule_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)

    # Seasonal-promo presets are a plain (stateless) callback: tapping one just
    # fires an admin API call, nothing follows it, so it doesn't need to be
    # part of the conversation.
    app.add_handler(CallbackQueryHandler(apply_preset, pattern="^preset_"))

    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("pay", pay_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("pending", pending_command))
    app.add_handler(CommandHandler("approve", approve_command))
    app.add_handler(CommandHandler("reject", reject_command))
    app.add_handler(CommandHandler("seasons", seasons_command))
    app.add_handler(CommandHandler("setpromo", setpromo_command))
    app.add_handler(CommandHandler("clearpromo", clearpromo_command))
    app.add_handler(CommandHandler("promo", promo_command))

    logger.info("SocialFlow bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
