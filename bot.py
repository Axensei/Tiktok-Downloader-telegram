import os
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# Token dal sistema (Heroku, Railway, Docker ecc.)
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("You must set the TOKEN environment variable with your BotFather token!")

# Messaggio di benvenuto
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! Send me any TikTok link and I will download the video WITHOUT watermark."
    )

# Gestione dei messaggi
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if "tiktok.com" in text or "vm.tiktok.com" in text:
        url = text

        await update.message.reply_text("🔗 Link received! Checking video...")

        try:
            ydl_opts = {
                "format": "mp4",
                "outtmpl": "video.%(ext)s",
                "quiet": True,
                "noplaylist": True,
                "merge_output_format": "mp4",
                "postprocessors": [],
                "extractor_args": {
                    "tiktok": {
                        "download_without_watermark": True
                    }
                }
            }

            await update.message.reply_text("⬇️ Downloading your TikTok video (no watermark)...")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_title = info.get("title", "tiktok_video")

            file_name = "video.mp4"

            # Controllo dimensione (Telegram max ~50MB)
            if os.path.getsize(file_name) > 49 * 1024 * 1024:
                await update.message.reply_text("❌ The video is too large for Telegram (>50MB).")
                os.remove(file_name)
                return

            await update.message.reply_text("📤 Uploading your video...")

            await update.message.reply_video(
                video=open(file_name, "rb"),
                filename=f"{video_title}.mp4",
                caption="✅ Here is your TikTok video (NO watermark)"
            )

            os.remove(file_name)

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
            if os.path.exists("video.mp4"):
                os.remove("video.mp4")

    else:
        await update.message.reply_text("⚠️ Please send a valid TikTok link.")

# Avvia il bot
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()

