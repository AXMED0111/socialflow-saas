"""
SocialFlow Telegram Bot
Flow: /start -> login (once) -> upload media -> caption -> pick platforms -> schedule -> confirm
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

# Conversation states
AWAITING_EMAIL, AWAITING_PASSWORD, AWAITING_MEDIA, AWAITING_CAPTION, \
    CHOOSING_PLATFORMS, CHOOSING_SCHEDULE = range(6)

ALL_PLATFORMS = ["facebook", "instagram", "tiktok", "twitter"]

# Simple in-memory session store: telegram_user_id -> {token, workspace, draft_post}
# For production, persist this (Redis or DB) so it survives bot restarts.
SESSIONS: dict = {}


def get_session(user_id: int) -> dict:
    return SESSIONS.setdefault(user_id, {})


# ---------- /start & login ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(update.effective_user.id)

    if session.get("token"):
        await show_main_menu(update)
        return ConversationHandler.END

    await update.message.reply_text(
        "👋 Welcome to SocialFlow!\n\n"
        "Let's link your account first. What's your email?"
    )
    return AWAITING_EMAIL


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


async def show_main_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("📤 Upload Media", callback_data="menu_upload")],
        [InlineKeyboardButton("📚 My Recent Posts", callback_data="menu_posts")],
        [InlineKeyboardButton("🔗 Bot Share Link", callback_data="menu_share")],
        [InlineKeyboardButton("❓ Help", callback_data="menu_help")],
    ]
    await update.message.reply_text(
        "What would you like to do?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- Upload flow ----------

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu_upload":
        await query.message.reply_text("🎬 Send me the image or video you want to post.")
        return AWAITING_MEDIA
    elif query.data == "menu_share":
        session = get_session(update.effective_user.id)
        try:
            link_info = api.get_bot_share_link(session["token"])
            await query.message.reply_text(
                f"🔗 Share this bot with your team:\n{link_info['botLink']}\n\n{link_info['note']}"
            )
        except Exception:
            await query.message.reply_text("No bot link configured yet — set it up in the dashboard first.")
    elif query.data == "menu_help":
        await query.message.reply_text(
            "Commands:\n/start - Main menu\nJust send a photo/video anytime to start a new post."
        )
    return ConversationHandler.END


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
        await query.message.reply_text(f"❌ Failed to schedule post: {e}")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Cancelled. /start to begin again.")
    return ConversationHandler.END


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.PHOTO | filters.VIDEO, receive_media),
        ],
        states={
            AWAITING_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email)],
            AWAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)],
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
    app.add_handler(CallbackQueryHandler(menu_router, pattern="^menu_"))

    logger.info("SocialFlow bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
