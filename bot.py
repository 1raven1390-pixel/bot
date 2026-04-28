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
    try:
        return "{:,}".format(int(amount))
    except:
        return amount

def translate_to_english(text):
    persian_numbers = "۰۱۲۳۴۵۶۷۸۹"
    english_numbers = "0123456789"
    translation_table = str.maketrans(persian_numbers, english_numbers)
    return text.translate(translation_table)

# --- کیبوردها ---
def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("🛒 خرید سرویس", callback_data="buy_main"),
           types.InlineKeyboardButton("📊 تعرفه", callback_data="price_list"))
    kb.add(types.InlineKeyboardButton("👤 حساب کاربری", callback_data="account"))
    kb.add(types.InlineKeyboardButton("💰 افزایش موجودی", callback_data="charge_start"))
    kb.add(types.InlineKeyboardButton("📞 پشتیبانی", callback_data="support"))
    return kb

# --- هندلرهای اصلی ---
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
@bot.message_handler(func=lambda m: user_states.get(m.chat.id) is not None and not isinstance(user_states.get(m.chat.id), dict) or (isinstance(user_states.get(m.chat.id), dict) and user_states[m.chat.id].get('state') == 'WAIT_CARD'))
def handle_steps(m):
    uid = m.chat.id
    current_state = user_states.get(uid)
    
    # مرحله دریافت مبلغ
    if current_state == 'WAIT_AMT':
        text = translate_to_english(m.text)
        if text.isdigit():
            user_states[uid] = {'state': 'WAIT_CARD', 'amt': int(text)}
            bot.send_message(uid, f"✅ مبلغ {format_p(text)} تومان تایید شد.\n\n💳 حالا **شماره کارت مبدا** (کارتی که با آن واریز می‌کنید) را ارسال کنید:")
        else:
            bot.send_message(uid, "❌ لطفاً فقط عدد به تومان وارد کنید:")

    # مرحله دریافت شماره کارت
    elif isinstance(current_state, dict) and current_state.get('state') == 'WAIT_CARD':
        if len(m.text) >= 2:
            amt = current_state['amt']
            user_states[uid] = {'state': 'WAIT_PHOTO', 'amt': amt, 'card': m.text}
            
            text_info = f"💰 مبلغ: {format_p(amt)} تومان\n💳 شماره کارت مقصد:\n\n`6221061233705260` \n👤 بنام: افراس\n\n✅ پس از واریز، **تصویر رسید** را همینجا ارسال کنید:"
            bot.send_message(uid, text_info, parse_mode="Markdown")
        else:
            bot.send_message(uid, "❌ شماره کارت معتبر نیست. دوباره ارسال کنید:")

# --- مدیریت ارسال عکس رسید ---
@bot.message_handler(content_types=['photo'])
def handle_receipt(m):
    uid = m.chat.id
    state_data = user_states.get(uid)
    
    if isinstance(state_data, dict) and state_data.get('state') == 'WAIT_PHOTO':
        d = state_data
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ تایید و شارژ", callback_data=f"adm_ok_{uid}_{d['amt']}"),
               types.InlineKeyboardButton("⚠️ فیک (اخطار)", callback_data=f"adm_warn_{uid}"))
        
        # ارسال برای ادمین
        bot.send_photo(ADMIN_ID, m.photo[-1].file_id, 
                       caption=f"💰 رسید جدید رسید!\n\n👤 آیدی کاربر: `{uid}`\n💵 مبلغ: {format_p(d['amt'])} تومان\n💳 کارت مبدا: {d['card']}", 
                       reply_markup=kb, parse_mode="Markdown")
        
        user_states[uid] = None # ریست وضعیت
        bot.send_message(uid, "✅ رسید و اطلاعات شما برای ادمین ارسال شد. پس از تایید، حساب شما شارژ می‌شود.")
    else:
        bot.send_message(uid, "❌ ابتدا از منو گزینه افزایش موجودی را انتخاب کنید.")

# --- کال‌بک‌ها ---
@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(c):
    uid = c.from_user.id
    
    if c.data == "check_join":
        if is_member(uid):
            bot.delete_message(c.message.chat.id, c.message.message_id)
            bot.send_message(c.message.chat.id, "✅ عضویت تایید شد!", reply_markup=main_menu())
        else:
            bot.answer_callback_query(c.id, "❌ هنوز عضو نشده‌اید!", show_alert=True)

    elif c.data == "charge_start":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💳 کارت به کارت", callback_data="c2c"),
               types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
        bot.edit_message_text("لطفاً روش پرداخت را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

    elif c.data == "c2c":
        user_states[uid] = 'WAIT_AMT'
        bot.edit_message_text("💰 مبلغ مورد نظر خود را به **تومان** وارد کنید:", c.message.chat.id, c.message.message_id, parse_mode="Markdown")

    elif c.data == "account":
        cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        d = cursor.fetchone()
        text = f"📊 حساب کاربری:\n\n💰 موجودی: {format_p(d[1])} تومان\n🛍 سرویس‌ها: {d[2]}\n⚠️ اخطارها: {d[3]}"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb)

    elif c.data == "back_main":
        user_states[uid] = None
        bot.edit_message_text("👇 منوی اصلی:", c.message.chat.id, c.message.message_id, reply_markup=main_menu())

    elif c.data.startswith("adm_"):
        p = c.data.split("_")
        target_uid = int(p[2])
        if p[1] == "ok":
            amt = int(p[3])
            cursor.execute("UPDATE users SET balance=balance+?, success_payments=success_payments+1 WHERE user_id=?", (amt, target_uid))
            conn.commit()
            bot.send_message(target_uid, f"✅ حساب شما مبلغ {format_p(amt)} تومان شارژ شد.")
            bot.answer_callback_query(c.id, "حساب کاربر شارژ شد.")
        elif p[1] == "warn":
            cursor.execute("UPDATE users SET warnings=warnings+1 WHERE user_id=?", (target_uid,))
            conn.commit()
            bot.send_message(target_uid, "⚠️ اخطار! رسید شما معتبر نبود.")
            bot.answer_callback_query(c.id, "اخطار ثبت شد.")

# --- آنلاین ماندن ---
@app.route('/')
def home(): return "Bot is Online!"

def run(): app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
