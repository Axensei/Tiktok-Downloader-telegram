import os
import time
from pathlib import Path
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ===================== CONFIG =====================
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("You must set the TOKEN environment variable with your BotFather token!")

ADMIN_ID = 217966398  # tuo ID Telegram per messaggi di errore/admin

# Directory temporanea per i download
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Statistiche semplici
STATS = {"total_downloads": 0}

# ===================== FUNZIONI =====================
async def download_video(url: str, outtmpl: str, cookies: str = None):
    """
    Scarica un video da TikTok senza watermark usando yt-dlp
    """
    ydl_opts = {
        "format": "mp4[ext=mp4]+bestaudio[ext=m4a]/mp4",
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }
    if cookies:
        ydl_opts["cookiefile"] = cookies

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename, info
    except Exception as e:
        raise e

# ===================== HANDLER START =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Send me a TikTok link and I will download the video for you (no watermark)."
    )

# ===================== HANDLER MESSAGGI =====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    text = msg.text.strip()
    private_chat = msg.chat.type == "private"

    # Verifica se il messaggio contiene un link TikTok
    if ("tiktok.com" in text) or ("vm.tiktok.com" in text):
        # Messaggi di stato solo in chat privata
        if private_chat:
            await msg.reply_text("🔗 Link received! Starting processing...")
            await msg.reply_text("⬇️ Downloading TikTok (no watermark, best quality)...")

        try:
            outtmpl = str(DOWNLOAD_DIR / f"video_{int(time.time())}.%(ext)s")
            cookies_file = "cookies.txt" if os.path.exists("cookies.txt") else None

            filepath, info = await download_video(text, outtmpl=outtmpl, cookies=cookies_file)

            # Controllo dimensione Telegram max 50MB
            if os.path.getsize(filepath) > 49 * 1024 * 1024:
                if private_chat:
                    await msg.reply_text("❌ The video is too large for Telegram (>50MB).")
                os.remove(filepath)
                return

            # Invio video
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
            # invio errore all'admin
            try:
                await context.bot.send_message(
                    ADMIN_ID, f"Error: {e}\nUser: {msg.from_user.id}\nMsg: {text}"
                )
            except:
                pass

    else:
        if private_chat:
            await msg.reply_text("⚠️ Please send a valid TikTok link (https://www.tiktok.com/...)")

# ===================== HANDLER ADMIN =====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.from_user.id != ADMIN_ID:
        await msg.reply_text("❌ You are not authorized to use this command.")
        return

    # Mostra statistiche
    await msg.reply_text(
        f"📊 Admin Panel\n\nTotal TikTok downloads: {STATS['total_downloads']}"
    )

# ===================== MAIN =====================
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()


