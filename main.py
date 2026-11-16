"""
Telegram Join-Request Bot
Does NOT approve join requests. They stay pending so YOU approve manually
Sends welcome DM (text + image + button) as soon as the request arrives
Saves every user in SQLite (stays even if they leave the channel)
/broadcast (reply to any message) -> sends to all saved users
/stats -> user counts
Run:
pip install python-telegram-bot==21.6
export BOT_TOKEN="123:ABC"
export ADMIN_IDS="111111111,222222222"
python bot.py
"""
import asyncio
import logging
import os
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import (
Application,
ChatJoinRequestHandler,
CommandHandler,
ContextTypes,
)
---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_TOKEN_HERE")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
WELCOME_TEXT = (
"👋 Welcome {name}!\n\n"
"Aapki join request mil gayi hai ✅\n"
"Jaldi approve hogi. Tab tak neeche button dekho 👇"
)
WELCOME_IMAGE = ""  # image URL ya file name (e.g. "welcome.jpg"). Khali = no image
WELCOME_VIDEO = ""  # video URL ya file name (e.g. "welcome.mp4"). Video ho to image ignore hoti hai
Channel post se welcome copy karna (image/video/text sab chalta hai):
link https://t.me/c/2122174869/30385 -> chat id -1002122174869, message id 30385
Bot us channel ka admin/member hona chahiye. 0 = off
WELCOME_FROM_CHAT = 0
WELCOME_FROM_MSG = 0
BUTTON_TEXT = "GET VIP FILE LINK"
BUTTON_URL = "https://t.me/+W5mDdrIhzNIyMGE1"
----------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")
DB = os.getenv("DB_PATH", "users.db")
def db():
return sqlite3.connect(DB)
def init_db():
with db() as c:
c.execute(
"""CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
name TEXT,
username TEXT,
active INTEGER DEFAULT 1,
joined_at TEXT DEFAULT CURRENT_TIMESTAMP
)"""
)
def save_user(u):
with db() as c:
c.execute(
"INSERT INTO users(user_id,name,username,active) VALUES(?,?,?,1) "
"ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, "
"username=excluded.username, active=1",
(u.id, u.full_name, u.username),
)
def set_inactive(user_id):
with db() as c:
c.execute("UPDATE users SET active=0 WHERE user_id=?", (user_id,))
def all_active_ids():
with db() as c:
return [r[0] for r in c.execute("SELECT user_id FROM users WHERE active=1")]
---------- 1 + 2: auto accept + welcome DM ----------
async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
req = update.chat_join_request
user = req.from_user
save_user(user)
# NOTE: no req.approve() here. Request stays pending until you accept it.

markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXT, url=BUTTON_URL)]])
text = WELCOME_TEXT.format(name=user.first_name)
chat = req.user_chat_id
try:
    if WELCOME_FROM_CHAT and WELCOME_FROM_MSG:
        await context.bot.copy_message(
            chat, WELCOME_FROM_CHAT, WELCOME_FROM_MSG, reply_markup=markup
        )
    elif WELCOME_VIDEO:
        if WELCOME_VIDEO.startswith("http"):
            await context.bot.send_video(
                chat, WELCOME_VIDEO, caption=text, reply_markup=markup,
                supports_streaming=True,
            )
        else:
            with open(WELCOME_VIDEO, "rb") as f:
                await context.bot.send_video(
                    chat, f, caption=text, reply_markup=markup,
                    supports_streaming=True,
                )
    elif WELCOME_IMAGE:
        if WELCOME_IMAGE.startswith("http"):
            await context.bot.send_photo(
                chat, WELCOME_IMAGE, caption=text, reply_markup=markup
            )
        else:
            with open(WELCOME_IMAGE, "rb") as f:
                await context.bot.send_photo(
                    chat, f, caption=text, reply_markup=markup
                )
    else:
        await context.bot.send_message(chat, text, reply_markup=markup)
except Forbidden:
    set_inactive(user.id)
except TelegramError as e:
    log.warning("welcome DM failed for %s: %s", user.id, e)
---------- /start (user bot ko start kare to bhi save) ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
save_user(update.effective_user)
await update.message.reply_text("✅ Bot connected! Updates yahin milenge.")
---------- 3 + 4: broadcast ----------
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
if update.effective_user.id not in ADMIN_IDS:
return
msg = update.message.reply_to_message
if not msg:
await update.message.reply_text(
"Pehle jo message bhejna hai (text/photo/video) wo bhejo, "
"phir us par reply karke /broadcast likho."
)
return
ids = all_active_ids()
status = await update.message.reply_text(f"📣 Sending to {len(ids)} users...")
ok = fail = 0
for uid in ids:
    try:
        await context.bot.copy_message(uid, msg.chat_id, msg.message_id)
        ok += 1
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        try:
            await context.bot.copy_message(uid, msg.chat_id, msg.message_id)
            ok += 1
        except TelegramError:
            fail += 1
    except (Forbidden, BadRequest):
        set_inactive(uid)  # user ne bot block kiya / account deleted
        fail += 1
    except TelegramError:
        fail += 1
    await asyncio.sleep(0.05)  # ~20 msg/sec, limit se safe

await status.edit_text(f"✅ Done\nSent: {ok}\nFailed/Blocked: {fail}")
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
if update.effective_user.id not in ADMIN_IDS:
return
with db() as c:
total = c.execute("SELECT COUNT() FROM users").fetchone()[0]
active = c.execute("SELECT COUNT() FROM users WHERE active=1").fetchone()[0]
await update.message.reply_text(f"👥 Total: {total}\n✅ Active: {active}\n🚫 Blocked: {total - active}")
def main():
init_db()
app = Application.builder().token(BOT_TOKEN).build()
app.add_handler(ChatJoinRequestHandler(on_join_request))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("stats", stats))
app.run_polling(allowed_updates=Update.ALL_TYPES)
if name == "main":
main()
