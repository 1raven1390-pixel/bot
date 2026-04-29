import telebot
from telebot import types
import sqlite3
import os
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

# --- پیکربندی ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8521801987
CHANNEL_ID = "@rafe_filter_A"
SUPPORT_ID = "@Amir_confing_meli"

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- دیتابیس ---
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

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
    status TEXT, -- pending / done / canceled
    created_at TEXT
)
""")
conn.commit()

# --- وضعیت کاربر (States) ---
user_states = {}

# --- ابزارها ---
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

# --- شروع ربات ---
@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?)", 
                       (uid, 0, 0, 0, 0, m.from_user.first_name or "", m.from_user.username or "", now_str()))
        conn.commit()
    
    if not is_member(uid):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_ID.replace('@','')}"))
        kb.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data="check_join"))
        bot.send_message(uid, "برای استفاده ابتدا عضو کانال شوید:", reply_markup=kb)
        return
    bot.send_message(uid, "👇 منوی اصلی:", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join(c):
    if is_member(c.from_user.id):
        bot.edit_message_text("✅ تایید شد", c.message.chat.id, c.message.message_id, reply_markup=main_menu())
    else:
        bot.answer_callback_query(c.id, "هنوز عضو نشدی", show_alert=True)

# --- سیستم افزایش موجودی ---
@bot.callback_query_handler(func=lambda c: c.data == "charge")
def charge(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 کارت به کارت", callback_data="c2c"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    bot.edit_message_text("روش پرداخت:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "c2c")
def c2c(c):
    user_states[c.from_user.id] = {"state": "WAIT_AMOUNT"}
    bot.send_message(c.from_user.id, "💰 مبلغ (تومان) را وارد کنید:")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("state") == "WAIT_AMOUNT")
def get_amount(m):
    txt = (m.text or "").strip()
    if not txt.isdigit():
        bot.send_message(m.chat.id, "❌ فقط عدد وارد کنید")
        return
    amt = int(txt)
    user_states[m.from_user.id] = {"state": "WAIT_CARD", "amount": amt}
    bot.send_message(m.chat.id, "💳 شماره کارت مبدا را ارسال کنید:")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("state") == "WAIT_CARD")
def get_card(m):
    data = user_states.get(m.from_user.id, {})
    amt = data.get("amount", 0)
    expire_at = (datetime.now() + timedelta(minutes=30)).isoformat()
    user_states[m.from_user.id] = { "state": "WAIT_RECEIPT", "amount": amt, "card": m.text.strip(), "expire_at": expire_at }
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📸 ارسال رسید", callback_data="send_receipt"))
    bot.send_message(m.chat.id, f"✅ اطلاعات ثبت شد\n\n💰 مبلغ: {format_p(amt)} تومان\n💳 کارت مقصد:\n6221061233705260\n👤 به نام: افراس\n\n⚠️ فاکتور ۳۰ دقیقه معتبر است", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "send_receipt")
def send_receipt(c):
    bot.send_message(c.from_user.id, "📸 لطفاً تصویر رسید را ارسال کنید")

@bot.message_handler(content_types=['photo'])
def receipt(m):
    data = user_states.get(m.from_user.id)
    if not data or data.get("state") != "WAIT_RECEIPT": return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ تایید", callback_data=f"ok_{m.from_user.id}_{data['amount']}"),
           types.InlineKeyboardButton("❌ رد", callback_data=f"no_{m.from_user.id}"))
    bot.send_photo(ADMIN_ID, m.photo[-1].file_id, 
                   caption=f"💰 درخواست شارژ\n👤 کاربر: {m.from_user.id}\n💵 مبلغ: {format_p(data['amount'])}\n💳 کارت مبدا: {data['card']}", 
                   reply_markup=kb)
    bot.send_message(m.chat.id, "✅ رسید برای ادمین ارسال شد.")
    user_states[m.from_user.id] = None

@bot.callback_query_handler(func=lambda c: c.data.startswith("ok_"))
def ok_charge(c):
    _, uid, amt = c.data.split("_")
    uid, amt = int(uid), int(amt)
    cursor.execute("UPDATE users SET balance=balance+?, success_payments=success_payments+1 WHERE user_id=?", (amt, uid))
    conn.commit()
    bot.send_message(uid, f"✅ مبلغ {format_p(amt)} تومان به حساب شما اضافه شد")
    bot.answer_callback_query(c.id, "تایید شد")

@bot.callback_query_handler(func=lambda c: c.data.startswith("no_"))
def no_charge(c):
    uid = int(c.data.split("_")[1])
    cursor.execute("UPDATE users SET warnings=warnings+1 WHERE user_id=?", (uid,))
    conn.commit()
    bot.send_message(uid, "❌ رسید شما رد شد و اخطار دریافت کردید")
    bot.answer_callback_query(c.id, "رد شد")

# --- بخش تعرفه و خرید ---
PRICES_MONTH = {"1G":350000,"2G":699000,"3G":999000,"5G":1499000}
PRICES_VIP = {"1G":599000,"2G":1198000,"3G":1797000,"5G":2899000,"10G":5299000}

@bot.callback_query_handler(func=lambda c: c.data == "price")
def price_menu(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📅 ۱ ماهه", callback_data="price_month"),
           types.InlineKeyboardButton("♾ VIP بی محدودیت", callback_data="price_vip"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    bot.edit_message_text("📊 تعرفه خدمات:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "price_month")
def price_month(c):
    txt = "📅 تعرفه ۱ ماهه:\n\n" + "\n".join([f"{k}: {format_p(v)}" for k,v in PRICES_MONTH.items()])
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

@bot.callback_query_handler(func=lambda c: c.data == "price_vip")
def price_vip(c):
    txt = "♾ تعرفه VIP:\n\n" + "\n".join([f"{k}: {format_p(v)}" for k,v in PRICES_VIP.items()])
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

@bot.callback_query_handler(func=lambda c: c.data == "buy")
def buy(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📅 ۱ ماهه", callback_data="buy_month"),
           types.InlineKeyboardButton("♾ VIP", callback_data="buy_vip"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    bot.edit_message_text("🛒 انتخاب پلن:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy_plan(c):
    plan = c.data.split("_")[1].upper()
    user_states[c.from_user.id] = {"state":"SELECT_VOL", "plan":plan}
    kb = types.InlineKeyboardMarkup(row_width=3)
    vols = PRICES_MONTH.keys() if plan == "MONTH" else PRICES_VIP.keys()
    for v in vols:
        kb.add(types.InlineKeyboardButton(v, callback_data=f"vol_{v}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy"))
    bot.edit_message_text("📊 حجم مورد نظر را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("vol_"))
def select_volume(c):
    uid = c.from_user.id
    st = user_states.get(uid, {})
    plan = st.get("plan")
    vol = c.data.split("_")[1]
    price = PRICES_MONTH.get(vol) if plan == "MONTH" else PRICES_VIP.get(vol)
    
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    balance = cursor.fetchone()[0]
    if balance < price:
        bot.answer_callback_query(c.id, "❌ موجودی کافی نیست", show_alert=True); return

    user_states[uid] = {"state":"CONFIRM_BUY","plan":plan,"volume":vol,"price":price}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ تایید خرید", callback_data="final_buy"),
           types.InlineKeyboardButton("❌ لغو", callback_data="back"))
    bot.send_message(uid, f"🛍 تایید خرید {vol} ({plan})\n💵 مبلغ: {format_p(price)} تومان", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "final_buy")
def final_buy(c):
    uid = c.from_user.id
    data = user_states.get(uid, {})
    if data.get("state") != "CONFIRM_BUY": return
    
    price = data["price"]
    cursor.execute("UPDATE users SET balance=balance-?, configs_count=configs_count+1 WHERE user_id=?", (price, uid))
    cursor.execute("INSERT INTO orders (user_id,plan,volume,price,status,created_at) VALUES (?,?,?,?,?,?)", 
                   (uid, data["plan"], data["volume"], price, "pending", now_str()))
    order_id = cursor.lastrowid
    conn.commit()
    
    bot.send_message(uid, "⏳ سفارش ثبت شد. منتظر ارسال کانفیگ توسط ادمین باشید.")
    
    # --- دکمه اختصاصی ارسال کانفیگ برای ادمین ---
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📤 ارسال کانفیگ", callback_data=f"sendcfg_{order_id}"))
    
    bot.send_message(ADMIN_ID, f"🛒 سفارش جدید\n\n🆔 OrderID: {order_id}\n👤 کاربر: {uid}\n📦 پلن: {data['plan']}\n📊 حجم: {data['volume']}\n💵 مبلغ: {format_p(price)}", reply_markup=kb)
    user_states[uid] = None

# --- سیستم مدیریت کانفیگ توسط ادمین (جایگزین ریپلای) ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("sendcfg_"))
def start_send_config(c):
    if c.from_user.id != ADMIN_ID: return
    order_id = int(c.data.split("_")[1])
    cursor.execute("SELECT user_id, status FROM orders WHERE id=?", (order_id,))
    row = cursor.fetchone()
    
    if not row:
        bot.answer_callback_query(c.id, "سفارش پیدا نشد", show_alert=True); return
    if row[1] != "pending":
        bot.answer_callback_query(c.id, "این سفارش قبلا انجام شده", show_alert=True); return
        
    user_states[ADMIN_ID] = {"state": "SEND_CONFIG", "order_id": order_id, "user_id": row[0]}
    bot.send_message(ADMIN_ID, f"📤 لطفاً کانفیگ مربوط به سفارش {order_id} را ارسال کنید (متن یا لینک):")
    bot.answer_callback_query(c.id)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "SEND_CONFIG")
def send_config_to_user(m):
    data = user_states.get(ADMIN_ID)
    order_id = data["order_id"]
    user_id = data["user_id"]
    
    # ارسال به کاربر
    bot.send_message(user_id, f"✅ کانفیگ شما آماده شد:\n\n{m.text}")
    
    # بروزرسانی دیتابیس
    cursor.execute("UPDATE orders SET status='done' WHERE id=?", (order_id,))
    conn.commit()
    
    bot.send_message(ADMIN_ID, f"✅ کانفیگ با موفقیت برای کاربر {user_id} ارسال و سفارش {order_id} بسته شد.")
    user_states[ADMIN_ID] = None

# --- سایر بخش‌ها (اکانت، پشتیبانی، پنل ادمین) ---
@bot.callback_query_handler(func=lambda c: c.data == "account")
def account(c):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (c.from_user.id,))
    d = cursor.fetchone()
    text = f"👤 حساب کاربری:\n\n💰 موجودی: {format_p(d[1])} تومان\n🛍 سرویس‌ها: {d[2]}\n⚠️ اخطارها: {d[3]}\n⏰ عضویت: {d[7]}"
    bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

@bot.callback_query_handler(func=lambda c: c.data == "support")
def support(c):
    bot.edit_message_text(f"📞 پشتیبانی: {SUPPORT_ID}", c.message.chat.id, c.message.message_id, reply_markup=back_kb())

@bot.callback_query_handler(func=lambda c: c.data == "back")
def back(c):
    bot.edit_message_text("👇 منوی اصلی:", c.message.chat.id, c.message.message_id, reply_markup=main_menu())

@bot.message_handler(commands=['admin'])
def admin_panel(m):
    if m.from_user.id != ADMIN_ID: return
    cursor.execute("SELECT COUNT() FROM users"); users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT() FROM orders WHERE status='pending'"); pending = cursor.fetchone()[0]
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📦 سفارشات باز", callback_data="adm_orders"))
    bot.send_message(m.chat.id, f"👑 پنل مدیریت\n\n👤 کاربران: {users}\n📦 سفارشات معلق: {pending}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "adm_orders")
def adm_orders(c):
    if c.from_user.id != ADMIN_ID: return
    cursor.execute("SELECT id,user_id,plan,volume FROM orders WHERE status='pending' LIMIT 10")
    rows = cursor.fetchall()
    if not rows: bot.send_message(ADMIN_ID, "سفارش بازی نیست"); return
    for r in rows:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📤 ارسال کانفیگ", callback_data=f"sendcfg_{r[0]}"))
        bot.send_message(ADMIN_ID, f"ID: {r[0]} | User: {r[1]}\nPlan: {r[2]} | Vol: {r[3]}", reply_markup=kb)

# --- وب‌سرور و اجرا ---
@app.route('/')
def home(): return "Bot is Running!"

def run(): app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    Thread(target=run).start()
    print("Bot is started...")
    bot.infinity_polling(skip_pending=True)
