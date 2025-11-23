import os
import yt_dlp
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ==========================
# Configurazioni generali
# ==========================
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("You must set the TOKEN environment variable with your BotFather token!")

ADMINS = [217966398]  # Inserisci il tuo ID Telegram
USERS_FILE = "users.json"
MAINTENANCE = False
LIMIT_PER_MINUTE = 5
ERROR_LOG = []

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)
VIDEO_CACHE = {}
MAX_CACHE_FILES = 50  # massimo numero di video in cache

# ==========================
# Funzioni di supporto
# ==========================
def clean_cache():
    """Rimuove i file più vecchi se ci sono troppi file nella cache"""
    files = [os.path.join(CACHE_DIR, f) for f in os.listdir(CACHE_DIR)]
    if len(files) <= MAX_CACHE_FILES:
        return
    files.sort(key=lambda x: os.path.getmtime(x))
    while len(files) > MAX_CACHE_FILES:
        try:
            os.remove(files[0])
            for k, v in list(VIDEO_CACHE.items()):
                if v == files[0]:
                    del VIDEO_CACHE[k]
            files.pop(0)
        except:
            break

# ==========================
# Caricamento utenti
# ==========================
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, "r") as f:
        USERS = json.load(f)
else:
    USERS = []

# ==========================
# Comando /start
# ==========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in USERS:
        USERS.append(user_id)
        with open(USERS_FILE, "w") as f:
            json.dump(USERS, f)
    await update.message.reply_text(
        "👋 Welcome! Send me a TikTok link and I'll download it for you in high quality."
    )

# ==========================
# Comandi Admin
# ==========================
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized.")
        return
    stats_msg = f"📊 Bot statistics:\n- Total users: {len(USERS)}\n- Maintenance mode: {'ON' if MAINTENANCE else 'OFF'}\n- Limit per minute: {LIMIT_PER_MINUTE}"
    await update.message.reply_text(stats_msg)

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ Unauthorized.")
        return
    await update.message.reply_text(f"👥 Registered users:\n{USERS}")

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

async def errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ Unauthorized.")
        return
    if ERROR_LOG:
        await update.message.reply_text("\n".join(ERROR_LOG[-10:]))
    else:
        await update.message.reply_text("✅ No errors logged.")

# ==========================
# Gestione messaggi TikTok
# ==========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ERROR_LOG
    text = update.message.text
    is_private = update.effective_chat.type == "private"

    if MAINTENANCE:
        if is_private:
            await update.message.reply_text("⚠️ Bot is under maintenance. Try again later.")
        return

    if "tiktok.com" in text:
        url = text

        # Controllo caching
        if url in VIDEO_CACHE:
            file_name = VIDEO_CACHE[url]
            if os.path.exists(file_name):
                await update.message.reply_document(open(file_name, "rb"))
                return

        if is_private:
            await update.message.reply_text("🔗 Link received! Downloading...")

        try:
            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": os.path.join(CACHE_DIR, "tiktok_%(id)s.%(ext)s"),
                "quiet": True,
                "noplaylist": True,
                "merge_output_format": "mp4",
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_name = os.path.join(CACHE_DIR, f"tiktok_{info['id']}.mp4")

            clean_cache()
            VIDEO_CACHE[url] = file_name

            if os.path.getsize(file_name) > 49 * 1024 * 1024:
                if is_private:
                    await update.message.reply_text("❌ The file is too big for Telegram (>50MB).")
                return

            # INVIO SOLO VIDEO SENZA TESTO
            await update.message.reply_document(open(file_name, "rb"))

        except Exception as e:
            ERROR_LOG.append(str(e))
            if len(ERROR_LOG) > 50:
                ERROR_LOG = ERROR_LOG[-50:]
            if is_private:
                await update.message.reply_text(f"❌ An error occurred.")

    else:
        if is_private:
            await update.message.reply_text("⚠️ Please send a valid TikTok link!")

# ==========================
# Avvio applicazione
# ==========================
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

# Avvio bot
app.run_polling()









