import telebot
from telebot import types
import sqlite3
import os
from datetime import datetime
from flask import Flask
from threading import Thread

# --- تنظیمات اولیه ---
TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_ID = 8521801987
CHANNEL_ID = "@rafe_filter_A"
SUPPORT_ID = "@Amir_confing_meli"

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# دیکشنری برای مدیریت وضعیت کاربران
user_states = {}

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
conn.commit()

# --- توابع کمکی ---
def is_member(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'creator', 'administrator']
    except:
        return False

def format_p(amount):
    return "{:,}".format(int(amount))

def translate_to_english(text):
    persian_numbers = "۰۱۲۳۴۵۶۷۸۹"
    english_numbers = "0123456789"
    translation_table = str.maketrans(persian_numbers, english_numbers)
    return text.translate(translation_table)

# --- کیبورد اصلی ---
def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("🛒 خرید سرویس", callback_data="buy_main"),
           types.InlineKeyboardButton("📊 تعرفه", callback_data="price_list"))
    kb.add(types.InlineKeyboardButton("👤 حساب کاربری", callback_data="account"))
    kb.add(types.InlineKeyboardButton("💰 افزایش موجودی", callback_data="charge_start"))
    kb.add(types.InlineKeyboardButton("📞 پشتیبانی", callback_data="support"))
    return kb

# --- شروع ربات ---
@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    user_states[uid] = None
    
    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?)",
                       (uid, 0, 0, 0, 0, m.from_user.first_name, m.from_user.username, datetime.now().strftime("%Y/%m/%d")))
        conn.commit()

    if not is_member(uid):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_ID.replace('@','')}"))
        kb.add(types.InlineKeyboardButton("✅ عضو شدم (بررسی)", callback_data="check_join"))
        bot.send_message(m.chat.id, "❌ برای استفاده از ربات باید ابتدا عضو کانال ما شوید:", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, "👇 به پنل مدیریت خوش آمدید:", reply_markup=main_menu())

# --- مدیریت وضعیت‌های متنی (مبلغ و شماره کارت) ---
@bot.message_handler(func=lambda m: user_states.get(m.chat.id) in ['WAIT_AMT', 'WAIT_CARD'])
def handle_text_steps(m):
    uid = m.chat.id
    state = user_states.get(uid)
    
    if state == 'WAIT_AMT':
        text = translate_to_english(m.text)
        if text.isdigit():
            user_states[uid] = {'state': 'WAIT_CARD', 'amt': int(text)}
            bot.send_message(uid, f"✅ مبلغ {format_p(text)} تومان ثبت شد.\n\n💳 حالا شماره کارت 16 رقمی که با آن واریز می‌کنید را ارسال کنید:")
        else:
            bot.send_message(uid, "❌ لطفاً فقط عدد وارد کنید:")

    elif state == 'WAIT_CARD':
        if len(m.text) >= 2:
            data = user_states[uid]
            user_states[uid] = {'state': 'WAIT_PHOTO', 'amt': data['amt'], 'card': m.text}
            bot.send_message(uid, f"✅ شماره کارت ثبت شد.\n\n💰 مبلغ واریزی: {format_p(data['amt'])} تومان\n💳 شماره کارت مقصد: `6221061233705260` \n👤 بنام: افراس\n\n📸 لطفاً تصویر رسید واریز را ارسال کنید:")
        else:
            bot.send_message(uid, "❌ شماره کارت معتبر نیست!")

# --- دریافت عکس رسید و ارسال برای ادمین ---
@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    uid = m.chat.id
    data = user_states.get(uid)
    
    if isinstance(data, dict) and data.get('state') == 'WAIT_PHOTO':
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ تایید و شارژ", callback_data=f"adm_ok_{uid}_{data['amt']}"),
               types.InlineKeyboardButton("⚠️ رسید فیک (اخطار)", callback_data=f"adm_warn_{uid}"))
        
        bot.send_photo(ADMIN_ID, m.photo[-1].file_id, 
                       caption=f"💰 درخواست شارژ جدید\n\n👤 کاربر: {uid}\n💵 مبلغ: {format_p(data['amt'])} تومان\n💳 کارت مبدا: {data['card']}", 
                       reply_markup=kb)
        
        user_states[uid] = None
        bot.send_message(uid, "✅ رسید شما برای ادمین ارسال شد. لطفاً تا بررسی ادمین صبور باشید.")
    else:
        bot.send_message(uid, "❌ لطفاً ابتدا از منوی 'افزایش موجودی' اقدام کنید.")

# --- مدیریت کال‌بک‌ها (دکمه‌ها) ---
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    uid = c.from_user.id
    data = c.data

    if data == "check_join":
        if is_member(uid):
            bot.delete_message(c.message.chat.id, c.message.message_id)
            bot.send_message(c.message.chat.id, "✅ تایید شد!", reply_markup=main_menu())
        else:
            bot.answer_callback_query(c.id, "❌ هنوز عضو نشده‌اید!", show_alert=True)

    elif data == "account":
        cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        d = cursor.fetchone()
        text = f"👤 حساب کاربری:\n\n💰 موجودی: {format_p(d[1])} تومان\n🛍 تعداد سرویس: {d[2]}\n⚠️ اخطارها: {d[3]}"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb)

    elif data == "charge_start":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💳 کارت به کارت", callback_data="c2c"),
               types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
        bot.edit_message_text("روش افزایش موجودی:", c.message.chat.id, c.message.message_id, reply_markup=kb)

    elif data == "c2c":
        user_states[uid] = 'WAIT_AMT'
        bot.send_message(c.message.chat.id, "💰 مبلغ مورد نظر (تومان) را وارد کنید:")

    elif data.startswith("buy_main") or data == "price_list":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔹 1G (350,000T)", callback_data="order_350000_1G"),
               types.InlineKeyboardButton("🔹 2G (699,000T)", callback_data="order_699000_2G"))
        kb.add(types.InlineKeyboardButton("🔹 3G (999,000T)", callback_data="order_999000_3G"),
               types.InlineKeyboardButton("🔹 VIP (600,000T)", callback_data="order_600000_VIP"))
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
        bot.edit_message_text("🛒 لیست تعرفه و خرید سرویس:", c.message.chat.id, c.message.message_id, reply_markup=kb)

    elif data.startswith("order_"):
        _, price, name = data.split("_")
        price = int(price)
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        balance = cursor.fetchone()[0]
        if balance < price:
            bot.answer_callback_query(c.id, "❌ موجودی کافی نیست! لطفاً شارژ کنید.", show_alert=True)
        else:
            cursor.execute("UPDATE users SET balance = balance - ?, configs_count = configs_count + 1 WHERE user_id = ?", (price, uid))
            conn.commit()
            bot.send_message(ADMIN_ID, f"🛍 خرید جدید!\nکاربر: {uid}\nمحصول: {name}")
            bot.edit_message_text(f"✅ خرید {name} موفق بود. کانفیگ شما به زودی ارسال می‌شود.", c.message.chat.id, c.message.message_id)

    elif data.startswith("adm_"):
        p = data.split("_")
        target_id = int(p[2])
        if p[1] == "ok":
            amt = int(p[3])
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, target_id))
            conn.commit()
            bot.send_message(target_id, f"✅ رسید تایید شد! مبلغ {format_p(amt)} تومان به حساب شما اضافه شد.")
            bot.answer_callback_query(c.id, "حساب کاربر شارژ شد.")
        elif p[1] == "warn":
            cursor.execute("UPDATE users SET warnings = warnings + 1 WHERE user_id = ?", (target_id,))
            conn.commit()
            bot.send_message(target_id, "⚠️ رسید شما فیک تشخیص داده شد و اخطار دریافت کردید!")
            bot.answer_callback_query(c.id, "اخطار ثبت شد.")

    elif data == "support":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
        bot.edit_message_text(f"📞 پشتیبانی:\n{SUPPORT_ID}", c.message.chat.id, c.message.message_id, reply_markup=kb)

    elif data == "back_main":
        user_states[uid] = None
        bot.edit_message_text("👇 منوی اصلی:", c.message.chat.id, c.message.message_id, reply_markup=main_menu())

# --- تنظیمات وب‌سرور ---
@app.route('/')
def home(): return "Bot is Online"

def run(): app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
