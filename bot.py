import os
import json
import time
import asyncio
from pathlib import Path
import yt_dlp
from functools import wraps

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIG ----------------
ADMIN_ID = 217966398              # il tuo Telegram user id (già impostato)
TOKEN = os.environ.get("TOKEN")   # MUST be set as env var
if not TOKEN:
    raise ValueError("You must set the TOKEN environment variable with your BotFather token!")

DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.json"
BANS_FILE = DATA_DIR / "bans.json"
STATE_FILE = DATA_DIR / "state.json"
ERROR_LOG = DATA_DIR / "errors.log"

# flood control (default)
DEFAULT_LIMIT_PER_MIN = 5  # requests per minute per user

# create data dir
DATA_DIR.mkdir(exist_ok=True)

# ---------------- persistence helpers ----------------
def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

users = load_json(USERS_FILE, {})      # user_id -> {first_name, last_name, username, count}
bans = load_json(BANS_FILE, {})        # user_id -> reason/timestamp
state = load_json(STATE_FILE, {"maintenance": False, "limit_per_min": DEFAULT_LIMIT_PER_MIN})

# in-memory rate limiter map: user_id -> [timestamps]
rate_map = {}

# error logging
def log_error(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    ERROR_LOG.parent.mkdir(exist_ok=True)
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")

# admin-only decorator
def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        uid = update.effective_user.id if update.effective_user else None
        if uid != ADMIN_ID:
            if update.effective_chat:
                await update.message.reply_text("❌ You are not authorized to use this command.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ---------------- utility ----------------
def register_user(u):
    if not u:
        return
    uid = str(u.id)
    if uid not in users:
        users[uid] = {
            "first_name": u.first_name,
            "last_name": u.last_name,
            "username": u.username,
            "count": 0,
            "first_seen": int(time.time())
        }
        save_json(USERS_FILE, users)

def increment_user_count(uid):
    s = str(uid)
    if s not in users:
        users[s] = {"first_name": "", "last_name": "", "username": "", "count": 0, "first_seen": int(time.time())}
    users[s]["count"] = users[s].get("count", 0) + 1
    save_json(USERS_FILE, users)

def is_banned(uid):
    return str(uid) in bans

def ban_user(uid, reason="manual"):
    bans[str(uid)] = {"reason": reason, "ts": int(time.time())}
    save_json(BANS_FILE, bans)

def unban_user(uid):
    bans.pop(str(uid), None)
    save_json(BANS_FILE, bans)

def check_rate(uid):
    now = time.time()
    arr = rate_map.setdefault(str(uid), [])
    # remove older than 60s
    arr[:] = [t for t in arr if now - t < 60]
    limit = state.get("limit_per_min", DEFAULT_LIMIT_PER_MIN)
    if len(arr) >= limit:
        return False
    arr.append(now)
    return True

# ---------------- yt-dlp download helper (non-blocking) ----------------
async def download_tiktok(url: str, outtmpl="video.%(ext)s", cookies=None):
    """
    Runs yt-dlp in threadpool to avoid blocking event loop.
    Returns (filepath, info) or raises exception.
    """
    loop = asyncio.get_running_loop()
    def run():
        ydl_opts = {
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            "quiet": True,
            "noplaylist": True,
            "no_warnings": True,
            "extractor_args": {
                "tiktok": {"download_without_watermark": True}
            }
        }
        if cookies and os.path.exists(cookies):
            ydl_opts["cookiefile"] = cookies
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # normalize mp4 extension
            if not filename.lower().endswith(".mp4"):
                filename = os.path.splitext(filename)[0] + ".mp4"
            return filename, info
    return await loop.run_in_executor(None, run)

# ---------------- Bot Handlers ----------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    await update.message.reply_text(
        "👋 Hello! I'm your TikTok downloader bot.\n"
        "Send me a TikTok link and I'll download the video WITHOUT watermark.\n\n"
        "I work in private chats and in groups (if added)."
    )

@admin_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = len(users)
    total_banned = len(bans)
    total_requests = sum(u.get("count",0) for u in users.values())
    text = (
        f"📊 Bot statistics:\n\n"
        f"Users: {total_users}\n"
        f"Total download requests: {total_requests}\n"
        f"Banned users: {total_banned}\n"
        f"Maintenance: {'ON' if state.get('maintenance') else 'OFF'}\n"
        f"Limit per minute: {state.get('limit_per_min')}\n"
    )
    await update.message.reply_text(text)

@admin_only
async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not users:
        await update.message.reply_text("No users recorded yet.")
        return
    lines = []
    for uid, info in users.items():
        lines.append(f"{uid} — @{info.get('username') or ''} ({info.get('first_name')}) reqs:{info.get('count')}")
    text = "Users:\n" + "\n".join(lines[:200])
    await update.message.reply_text(text)

@admin_only
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /ban <user_id> [reason]")
        return
    target = args[0]
    reason = " ".join(args[1:]) if len(args) > 1 else "manual"
    ban_user(target, reason)
    await update.message.reply_text(f"User {target} banned. Reason: {reason}")

@admin_only
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    target = args[0]
    unban_user(target)
    await update.message.reply_text(f"User {target} unbanned.")

@admin_only
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /broadcast your message here")
        return
    message = " ".join(context.args)
    send_count = 0
    await update.message.reply_text("Broadcast started...")
    for uid in list(users.keys()):
        try:
            await context.bot.send_message(int(uid), message)
            send_count += 1
            await asyncio.sleep(0.05)  # small throttle
        except Exception as e:
            log_error(f"Broadcast failed to {uid}: {e}")
    await update.message.reply_text(f"Broadcast finished. Sent to {send_count} users.")

@admin_only
async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /maintenance on|off")
        return
    mode = args[0].lower()
    if mode in ("on","1","true"):
        state["maintenance"] = True
        save_json(STATE_FILE, state)
        await update.message.reply_text("Maintenance mode ON. Bot will respond only to admins.")
    else:
        state["maintenance"] = False
        save_json(STATE_FILE, state)
        await update.message.reply_text("Maintenance mode OFF.")

@admin_only
async def setlimit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /setlimit <requests_per_minute>")
        return
    try:
        val = int(args[0])
        state["limit_per_min"] = max(1, val)
        save_json(STATE_FILE, state)
        await update.message.reply_text(f"Limit per minute set to {state['limit_per_min']}")
    except:
        await update.message.reply_text("Invalid number.")

@admin_only
async def errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ERROR_LOG.exists():
        await update.message.reply_text("No errors logged yet.")
        return
    text = ERROR_LOG.read_text(encoding="utf-8").splitlines()[-200:]
    await update.message.reply_text("Last errors:\n" + "\n".join(text))

# ---------------- main message handler ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    uid = update.effective_user.id if update.effective_user else None
    # register user
    if update.effective_user:
        register_user(update.effective_user)

    # admin bypasses bans and maintenance
    if uid != ADMIN_ID:
        if is_banned(uid):
            await msg.reply_text("❌ You are banned from using this bot.")
            return
        if state.get("maintenance", False):
            await msg.reply_text("⚠️ Bot is in maintenance. Try later.")
            return
        if not check_rate(uid):
            await msg.reply_text("⏳ Rate limit exceeded. Try again in a moment.")
            return

    text = msg.text.strip()
    # accept different tiktok link types
    if ("tiktok.com" in text) or ("vm.tiktok.com" in text):
        await msg.reply_text("🔗 Link received! Starting processing...")

        # run download (non-blocking)
        try:
            # download to a unique filename to avoid race
            outtmpl = f"downloads/video_{uid}_{int(time.time())}.%(ext)s"
            Path("downloads").mkdir(exist_ok=True)
            cookies_file = "cookies.txt" if os.path.exists("cookies.txt") else None

            await msg.reply_text("⬇️ Downloading TikTok (no watermark, best available)...")

            try:
                filepath, info = await download_tiktok(text, outtmpl=outtmpl, cookies=cookies_file)
            except Exception as ex:
                log_error(f"Download failed for {text} by {uid}: {ex}")
                await msg.reply_text(f"❌ Download failed: {ex}")
                return

            # increment counters
            increment_user_count(uid)

            # ensure mp4 extension
            if not filepath.lower().endswith(".mp4"):
                newpath = os.path.splitext(filepath)[0] + ".mp4"
                try:
                    os.rename(filepath, newpath)
                    filepath = newpath
                except:
                    pass

            # file size check
            size = os.path.getsize(filepath)
            if size > 49 * 1024 * 1024:
                await msg.reply_text("❌ The video is too large for Telegram (>50MB).")
                try:
                    os.remove(filepath)
                except:
                    pass
                return

            await msg.reply_text("📤 Uploading video now...")
            # send to same chat (works in groups and private)
            try:
                await msg.reply_video(video=open(filepath, "rb"), caption=f"✅ Here is your TikTok video")
            except Exception as e:
                # fallback to send_document if reply_video fails
                await msg.reply_document(document=open(filepath, "rb"), caption=f"✅ Here is your TikTok video")
            finally:
                try:
                    os.remove(filepath)
                except:
                    pass

        except Exception as e:
            log_error(f"Unexpected error in handler: {e}")
            await msg.reply_text("❌ Unexpected error occurred. The admin has been notified.")
            # notify admin
            try:
                await context.bot.send_message(ADMIN_ID, f"Error: {e}\nUser: {uid}\nMsg: {text}")
            except:
                pass
    else:
        # optional: in private hint
        if msg.chat.type == "private":
            await msg.reply_text("⚠️ Please send a valid TikTok link (https://www.tiktok.com/...).")

# ---------------- Startup ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("maintenance", maintenance_command))
    app.add_handler(CommandHandler("setlimit", setlimit_command))
    app.add_handler(CommandHandler("errors", errors_command))

    # message handler (works in groups too)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()


