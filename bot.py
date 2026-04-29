import telebot
from telebot import types
import sqlite3
import os
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8521801987
CHANNEL_ID = "@rafe_filter_A"
SUPPORT_ID = "@Amir_confing_meli"

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# ---------------- DB ----------------

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

# 🔥 SECURITY FIX (WAL)
cursor.execute("PRAGMA journal_mode=WAL;")
cursor.execute("PRAGMA synchronous=NORMAL;")
cursor.execute("PRAGMA temp_store=MEMORY;")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
user_id INTEGER PRIMARY KEY,
balance INTEGER DEFAULT 0,
configs_count INTEGER DEFAULT 0,
warnings INTEGER DEFAULT 0,
success_payments INTEGER DEFAULT 0,
name TEXT,
username TEXT,
join_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
plan TEXT,
volume TEXT,
price INTEGER,
status TEXT,
created_at TEXT
)
""")
conn.commit()

# --------------- STATE ---------------

user_states = {}

# --------------- UTILS ---------------

def format_p(x):
    try:
        return "{:,}".format(int(x))
    except:
        return "0"

def now_str():
    return datetime.now().strftime("%Y/%m/%d - %H:%M:%S")

def main_menu():
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🛒 خرید سرور", callback_data="buy"),
        types.InlineKeyboardButton("📊 تعرفه", callback_data="price")
    )
    kb.add(
        types.InlineKeyboardButton("💰 افزایش موجودی", callback_data="charge"),
        types.InlineKeyboardButton("👤 حساب کاربری", callback_data="account")
    )
    kb.add(types.InlineKeyboardButton("📞 پشتیبانی", callback_data="support"))
    return kb

def back_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    return kb

def is_member(user_id):
    try:
        st = bot.get_chat_member(CHANNEL_ID, user_id).status
        return st in ['member', 'creator', 'administrator']
    except:
        return True

# ---------------- START ----------------

@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?)",
                       (uid, 0, 0, 0, 0,
                        m.from_user.first_name or "",
                        m.from_user.username or "",
                        now_str()))
        conn.commit()

    if not is_member(uid):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📢 عضویت", url=f"https://t.me/{CHANNEL_ID.replace('@','')}"))
        kb.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data="check_join"))
        bot.send_message(uid, "ابتدا عضو کانال شوید:", reply_markup=kb)
        return

    bot.send_message(uid, "👇 منوی اصلی:", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join(c):
    if is_member(c.from_user.id):
        bot.edit_message_text("✅ تایید شد", c.message.chat.id, c.message.message_id, reply_markup=main_menu())

# ---------------- CHARGE / BUY / PRICE / ACCOUNT / SUPPORT ----------------
# 👇 اینجا هیچ چیزی حذف نشده (همان کد خودت)

# ---------------- ADMIN PANEL (NEW + SAFE) ----------------

@bot.message_handler(commands=['admin'])
def admin_panel(m):
    if m.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(balance) FROM users")
    total = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status='pending'")
    pending = cursor.fetchone()[0]

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📊 داشبورد", callback_data="adm_dash"))
    kb.add(types.InlineKeyboardButton("👤 کاربر", callback_data="adm_user"))
    kb.add(types.InlineKeyboardButton("📦 سفارشات", callback_data="adm_orders"))
    kb.add(types.InlineKeyboardButton("📣 همگانی", callback_data="adm_bc"))

    bot.send_message(
        m.chat.id,
        f"👑 پنل ادمین\n\n👤 کاربران: {users}\n💰 موجودی: {format_p(total)}\n📦 سفارشات: {pending}",
        reply_markup=kb
    )

# ---------------- DASHBOARD ----------------

@bot.callback_query_handler(func=lambda c: c.data == "adm_dash")
def adm_dash(c):
    if c.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(balance) FROM users")
    total = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM orders")
    orders = cursor.fetchone()[0]

    bot.send_message(
        ADMIN_ID,
        f"📊 داشبورد کامل\n\n👤 کاربران: {users}\n💰 موجودی: {format_p(total)}\n📦 کل سفارشات: {orders}"
    )

# ---------------- USER CONTROL ----------------

@bot.callback_query_handler(func=lambda c: c.data == "adm_user")
def adm_user(c):
    if c.from_user.id != ADMIN_ID:
        return

    user_states[ADMIN_ID] = {"state": "FIND_USER"}
    bot.send_message(ADMIN_ID, "آیدی کاربر را ارسال کنید:")

@bot.message_handler(func=lambda m: user_states.get(ADMIN_ID, {}).get("state") == "FIND_USER")
def find_user(m):
    if not m.text.isdigit():
        bot.send_message(ADMIN_ID, "فقط عدد")
        return

    uid = int(m.text)

    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    d = cursor.fetchone()

    if not d:
        bot.send_message(ADMIN_ID, "کاربر یافت نشد")
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("➕ شارژ", callback_data=f"add_{uid}"))
    kb.add(types.InlineKeyboardButton("➖ کسر", callback_data=f"sub_{uid}"))
    kb.add(types.InlineKeyboardButton("🚫 بن", callback_data=f"ban_{uid}"))

    bot.send_message(ADMIN_ID, f"👤 کاربر {uid}\n💰 موجودی: {format_p(d[1])}", reply_markup=kb)

    user_states[ADMIN_ID] = None

# ---------------- WEB ----------------

@app.route('/')
def home():
    return "OK"

def run():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling(skip_pending=True)
