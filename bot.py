import os
import yt_dlp
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Token del bot dal sistema
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("You must set the TOKEN environment variable with your BotFather token!")

# Admin e configurazioni
ADMINS = [217966398]  # Inserisci il tuo ID Telegram
USERS_FILE = "users.json"
MAINTENANCE = False
LIMIT_PER_MINUTE = 5
ERROR_LOG = []

# Carica utenti registrati
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, "r") as f:
        USERS = json.load(f)
else:
    USERS = []

# Funzione /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in USERS:
        USERS.append(user_id)
        with open(USERS_FILE, "w") as f:
            json.dump(USERS, f)
    await update.message.reply_text(
        "👋 Welcome! Send me a TikTok link and I'll download it for you in high quality."
    )

# Funzione /stats
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    stats_msg = f"📊 Bot statistics:\n- Total users: {len(USERS)}\n- Maintenance mode: {'ON' if MAINTENANCE else 'OFF'}\n- Limit per minute: {LIMIT_PER_MINUTE}"
    await update.message.reply_text(stats_msg)

# Funzione /users
async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    await update.message.reply_text(f"👥 Registered users:\n{USERS}")

# Funzione /ban
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ Unauthorized.")
        return
    try:
        user_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason"
        if user_id not in USERS:
            await update.message.reply_text("❌ User not found.")
            return
        USERS.remove(user_id)
        with open(USERS_FILE, "w") as f:
            json.dump(USERS, f)
        await update.message.reply_text(f"✅ User {user_id} banned. Reason: {reason}")
    except:
        await update.message.reply_text("❌ Usage: /ban <user_id> [reason]")

# Funzione /unban
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ Unauthorized.")
        return
    try:
        user_id = int(context.args[0])
        if user_id in USERS:
            await update.message.reply_text("❌ User is already active.")
            return
        USERS.append(user_id)
        with open(USERS_FILE, "w") as f:
            json.dump(USERS, f)
        await update.message.reply_text(f"✅ User {user_id} unbanned.")
    except:
        await update.message.reply_text("❌ Usage: /unban <user_id>")

# Funzione /broadcast
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ Unauthorized.")
        return
    msg = " ".join(context.args)
    for uid in USERS:
        try:
            await context.bot.send_message(uid, msg)
        except:
            continue
    await update.message.reply_text("✅ Broadcast sent.")

# Funzione /maintenance
async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ Unauthorized.")
        return
    if context.args[0].lower() == "on":
        MAINTENANCE = True
        await update.message.reply_text("⚠️ Maintenance mode activated.")
    elif context.args[0].lower() == "off":
        MAINTENANCE = False
        await update.message.reply_text("✅ Maintenance mode deactivated.")
    else:
        await update.message.reply_text("❌ Usage: /maintenance on|off")

# Funzione /setlimit
async def setlimit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LIMIT_PER_MINUTE
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ Unauthorized.")
        return
    try:
        LIMIT_PER_MINUTE = int(context.args[0])
        await update.message.reply_text(f"✅ Limit set to {LIMIT_PER_MINUTE} requests per minute.")
    except:
        await update.message.reply_text("❌ Usage: /setlimit <n>")

# Funzione /errors
async def errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ Unauthorized.")
        return
    if ERROR_LOG:
        await update.message.reply_text("\n".join(ERROR_LOG[-10:]))
    else:
        await update.message.reply_text("✅ No errors logged.")

# Funzione principale per gestire i messaggi TikTok
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ERROR_LOG
    text = update.message.text
    chat_id = update.effective_chat.id
    is_private = update.effective_chat.type == "private"

    if MAINTENANCE:
        if is_private:
            await update.message.reply_text("⚠️ Bot is under maintenance. Try again later.")
        return

    if "tiktok.com" in text:
        url = text

        if is_private:
            await update.message.reply_text("🔗 Link received! Starting processing...")
            await update.message.reply_text("⬇️ Downloading video, please wait...")

        try:
            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": "video.mp4",
                "quiet": True,
                "noplaylist": True,
                "merge_output_format": "mp4",
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "tiktok_video")
                file_name = "video.mp4"

            if os.path.getsize(file_name) > 49 * 1024 * 1024:
                if is_private:
                    await update.message.reply_text("❌ The file is too big for Telegram (>50MB).")
                os.remove(file_name)
                return

            # Messaggio finale
            await update.message.reply_document(
                open(file_name, "rb"),
                filename=f"{title}.mp4",
                caption="✅ Here's your TikTok!" if not is_private else f"✅ Here's your TikTok: {title}"
            )
            os.remove(file_name)

        except Exception as e:
            ERROR_LOG.append(str(e))
            if len(ERROR_LOG) > 50:
                ERROR_LOG = ERROR_LOG[-50:]
            if is_private:
                await update.message.reply_text(f"❌ An error occurred: {str(e)}")
            if os.path.exists("video.mp4"):
                os.remove("video.mp4")
    else:
        if is_private:
            await update.message.reply_text(
                "⚠️ Please send a valid TikTok link and I will download it for you!"
            )

# Creazione applicazione
app = ApplicationBuilder().token(TOKEN).build()

# Handler comandi
app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("stats", stats_command))
app.add_handler(CommandHandler("users", users_command))
app.add_handler(CommandHandler("ban", ban_command))
app.add_handler(CommandHandler("unban", unban_command))
app.add_handler(CommandHandler("broadcast", broadcast_command))
app.add_handler(CommandHandler("maintenance", maintenance_command))
app.add_handler(CommandHandler("setlimit", setlimit_command))
app.add_handler(CommandHandler("errors", errors_command))

# Handler messaggi
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Avvio del bot
app.run_polling()




