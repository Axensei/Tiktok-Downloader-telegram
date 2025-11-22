import os
import time
from pathlib import Path
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Configurazioni
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("You must set the TOKEN environment variable with your BotFather token!")

ADMIN_ID = 217966398  # ID Telegram dell'admin
DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Statistiche bot
STATS = {"total_downloads": 0}

# Funzione per il comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! Send me a TikTok link and I'll download it for you in high quality without watermark."
    )

# Funzione segreta per admin
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return

    await update.message.reply_text(
        f"🛠 Admin Panel\nTotal downloads: {STATS['total_downloads']}"
    )

# Funzione per scaricare video TikTok
async def download_video(url: str, outtmpl: str, cookies=None):
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4"
        }],
    }
    if cookies:
        ydl_opts["cookiefile"] = cookies

    loop = None
    try:
        loop = __import__("asyncio").get_running_loop()
    except RuntimeError:
        pass

    if loop and loop.is_running():
        # yt-dlp è sincrono, quindi esegui in thread pool per non bloccare il bot
        import asyncio
        from functools import partial
        ydl = yt_dlp.YoutubeDL(ydl_opts)
        info = await asyncio.to_thread(partial(ydl.extract_info, url, download=True))
    else:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

    filename = ydl.prepare_filename(info)
    return filename, info

# Funzione principale per gestire i messaggi
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    text = msg.text.strip()
    private_chat = msg.chat.type == "private"

    # Verifica se è link TikTok
    if ("tiktok.com" in text) or ("vm.tiktok.com" in text):

        try:
            outtmpl = str(DOWNLOAD_DIR / f"video_{int(time.time())}.%(ext)s")
            cookies_file = "cookies.txt" if os.path.exists("cookies.txt") else None

            # Messaggi di stato solo in chat privata
            if private_chat:
                await msg.reply_text("🔗 Link received! Starting processing...")
                await msg.reply_text("⬇️ Downloading TikTok (no watermark, best quality)...")

            filepath, info = await download_video(text, outtmpl=outtmpl, cookies=cookies_file)

            # Controllo dimensione max Telegram
            if os.path.getsize(filepath) > 49 * 1024 * 1024:
                if private_chat:
                    await msg.reply_text("❌ The video is too large for Telegram (>50MB).")
                os.remove(filepath)
                return

            # Invio video (sempre, sia gruppo che privato)
            await msg.reply_video(
                video=open(filepath, "rb"),
                caption="✅ Here's your TikTok video"
            )
            os.remove(filepath)

            # Aggiorna statistiche
            STATS["total_downloads"] += 1

        except Exception as e:
            if private_chat:
                await msg.reply_text(f"❌ Download failed: {e}")
            # Invio errore all'admin
            try:
                await context.bot.send_message(
                    ADMIN_ID, f"Error: {e}\nUser: {msg.from_user.id}\nMsg: {text}"
                )
            except:
                pass

    else:
        if private_chat:
            await msg.reply_text("⚠️ Please send a valid TikTok link (https://www.tiktok.com/...)")

# Creazione app bot
app = ApplicationBuilder().token(TOKEN).build()

# Comandi
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin_panel))

# Gestione messaggi
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Avvio bot
app.run_polling()


