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

# دیکشنری برای مدیریت وضعیت کاربران (جایگزین Next Step Handler)
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
    user_states[uid] = None # ریست کردن وضعیت
    
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

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join(c):
    if is_member(c.from_user.id):
        bot.delete_message(c.message.chat.id, c.message.message_id)
        bot.send_message(c.message.chat.id, "✅ عضویت تایید شد. خوش آمدید!", reply_markup=main_menu())
    else:
        bot.answer_callback_query(c.id, "❌ هنوز در کانال عضو نشده‌اید!", show_alert=True)

# --- مدیریت وضعیت‌های متنی (مبلغ و شماره کارت) ---
@bot.message_handler(func=lambda m: user_states.get(m.chat.id) in ['WAIT_AMT', 'WAIT_CARD'])
def handle_steps(m):
    uid = m.chat.id
    state = user_states.get(uid)
    
    if state == 'WAIT_AMT':
        text = translate_to_english(m.text)
        if text.isdigit():
            user_states[uid] = {'state': 'WAIT_CARD', 'amt': int(text)}
            bot.send_message(uid, f"✅ مبلغ {format_p(text)} تومان تایید شد.\n💳 حالا شماره کارت مبدا (شماره کارتی که با آن واریز می‌کنید) را ارسال کنید:")
        else:
            bot.send_message(uid, "❌ لطفاً فقط عدد وارد کنید:")

    elif state == 'WAIT_CARD':
        if len(m.text) > 2:
            data = user_states[uid]
            amt = data['amt']
            user_states[uid] = {'state': 'WAIT_PHOTO', 'amt': amt, 'card': m.text}
            
            text_info = f"لطفاً دقیقا مبلغ {format_p(amt)} تومان به شماره کارت زیر واریز کنید:\n\n💳 `6221061233705260` \n👤 بنام: افراس\n\n📸 پس از واریز، دکمه زیر را بزنید و تصویر رسید را بفرستید."
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("📤 ارسال تصویر رسید", callback_data="upload_photo"))
            bot.send_message(uid, text_info, reply_markup=kb, parse_mode="Markdown")
        else:
            bot.send_message(uid, "❌ شماره کارت معتبر وارد کنید:")

# --- مدیریت ارسال عکس رسید ---
@bot.message_handler(content_types=['photo'])
def handle_receipt(m):
    uid = m.chat.id
    if isinstance(user_states.get(uid), dict) and user_states[uid].get('state') == 'WAIT_PHOTO':
        d = user_states[uid]
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ تایید", callback_data=f"adm_ok_{uid}_{d['amt']}"),
               types.InlineKeyboardButton("⚠️ اخطار", callback_data=f"adm_warn_{uid}"))
        
        bot.send_photo(ADMIN_ID, m.photo[-1].file_id, 
                       caption=f"💰 رسید جدید\n👤 آیدی کاربر: {uid}\n💵 مبلغ: {format_p(d['amt'])}\n💳 کارت مبدا: {d['card']}", 
                       reply_markup=kb)
        
        user_states[uid] = None # ریست وضعیت
        bot.send_message(uid, "✅ رسید برای ادمین ارسال شد. پس از بررسی، حساب شما شارژ می‌شود.")
    else:
        # اگر کاربر همینطوری عکس فرستاد واکنشی نشان نده یا راهنمایی کن
        pass

# --- کال‌بک‌های مربوط به شارژ و آپلود ---
@bot.callback_query_handler(func=lambda c: c.data == "charge_start")
def charge_1(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 کارت به کارت", callback_data="c2c"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
    bot.edit_message_text("لطفاً روش پرداخت را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "c2c")
def charge_2(c):
    user_states[c.from_user.id] = 'WAIT_AMT'
    bot.edit_message_text("💰 مبلغ مورد نظر خود را به **تومان** وارد کنید:", c.message.chat.id, c.message.message_id, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "upload_photo")
def ask_photo(c):
    uid = c.from_user.id
    if isinstance(user_states.get(uid), dict):
        bot.send_message(c.message.chat.id, "🖼 حالا تصویر رسید واریزی خود را ارسال کنید:")
    else:
        bot.send_message(c.message.chat.id, "❌ زمان شما منقضی شده، دوباره تلاش کنید.")

# --- بقیه هندلرها (حساب، تعرفه، خرید و ...) ---
@bot.callback_query_handler(func=lambda c: c.data == "account")
def account(c):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (c.from_user.id,))
    d = cursor.fetchone()
    text = f"""📊 اطلاعات حساب کاربری شما:
    
🔢 آیدی عددی : {d[0]}
🔆 یوزرنیم : @{d[6] if d[6] else "ثبت نشده"}
💰 موجودی : {format_p(d[1])} تومان
🏦 پرداخت های موفق : {d[4]} عدد
🛍 تعداد سرویس ها : {d[2]} عدد
⚠️ تعداد اخطار ها : {d[3]} عدد
⏰ تاریخ عضویت : {d[7]}

🤖 | @rafe_filter"""
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
    bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["price_list", "buy_main"])
def tariffs(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("1️⃣ یک ماهه", callback_data="cat_1month"))
    kb.add(types.InlineKeyboardButton("💎 بدون محدودیت زمانی+VIP", callback_data="cat_vip"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
    bot.edit_message_text("لطفاً دسته بندی مورد نظر را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "cat_1month")
def cat_1m(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👤 تک کاربره", callback_data="list_1m_single"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_main"))
    bot.edit_message_text("سرویس‌های یک ماهه:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "list_1m_single")
def list_1m(c):
    prices = {"1G": 350000, "2G": 699000, "3G": 999000, "5G": 1499000}
    kb = types.InlineKeyboardMarkup()
    for k, v in prices.items():
        kb.add(types.InlineKeyboardButton(f"🔹 {k} : {format_p(v)} تومان", callback_data=f"order_{v}_{k}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="cat_1month"))
    bot.edit_message_text("💰 لیست قیمت سرویس‌های یک ماهه:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "cat_vip")
def list_vip(c):
    prices = {"1G": 600000, "2G": 1199000, "3G": 1799000, "5G": 2999000, "10G": 5499000}
    kb = types.InlineKeyboardMarkup()
    for k, v in prices.items():
        kb.add(types.InlineKeyboardButton(f"🔹 {k} : {format_p(v)} تومان", callback_data=f"order_{v}_{k}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_main"))
    bot.edit_message_text("💰 لیست قیمت (با تخفیف ویژه VIP):", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("order_"))
def confirm_buy(c):
    _, price, name = c.data.split("_")
    price = int(price)
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (c.from_user.id,))
    balance = cursor.fetchone()[0]

    if balance < price:
        bot.answer_callback_query(c.id, "❌ موجودی کافی نیست! لطفا حساب خود را شارژ کنید.", show_alert=True)
    else:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🟢 تایید خرید", callback_data=f"final_{price}_{name}"),
               types.InlineKeyboardButton("🔴 لغو", callback_data="back_main"))
        bot.edit_message_text(f"آیا از خرید سرویس {name} به مبلغ {format_p(price)} تومان اطمینان دارید؟", 
                              c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("final_"))
def final_buy(c):
    _, price, name = c.data.split("_")
    price = int(price)
    uid = c.from_user.id
    
    cursor.execute("UPDATE users SET balance = balance - ?, configs_count = configs_count + 1 WHERE user_id = ?", (price, uid))
    conn.commit()
    
    bot.edit_message_text("✅ در حال ساخت سرویس...", c.message.chat.id, c.message.message_id)
    bot.send_message(ADMIN_ID, f"🛒 سفارش جدید!\n👤 کاربر: {uid}\n📦 محصول: {name}\n💰 قیمت: {format_p(price)}")
    bot.send_message(uid, "🎉 خرید موفقیت‌آمیز بود! کانفیگ شما به زودی ارسال می‌شود.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_"))
def admin_p(c):
    p = c.data.split("_")
    uid = int(p[2])
    if p[1] == "ok":
        amt = int(p[3])
        cursor.execute("UPDATE users SET balance=balance+?, success_payments=success_payments+1 WHERE user_id=?", (amt, uid))
        conn.commit()
        bot.send_message(uid, f"✅ تراکنش شما تایید شد!\nمبلغ {format_p(amt)} تومان به حساب شما اضافه شد.")
    elif p[1] == "warn":
        cursor.execute("UPDATE users SET warnings=warnings+1 WHERE user_id=?", (uid,))
        conn.commit()
        bot.send_message(uid, "⚠️ اخطار! رسید ارسالی مورد تایید نبود. اخطار برای شما ثبت شد.")
    bot.answer_callback_query(c.id, "عملیات انجام شد")

@bot.callback_query_handler(func=lambda c: c.data == "support")
def support(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
    bot.edit_message_text(f"📞 برای پشتیبانی به آیدی زیر پیام دهید:\n\n{SUPPORT_ID}", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "back_main")
def back_main(c):
    user_states[c.from_user.id] = None
    bot.edit_message_text("👇 منوی اصلی:", c.message.chat.id, c.message.message_id, reply_markup=main_menu())

# --- تنظیمات آنلاین ماندن ---
@app.route('/')
def home(): return "Bot is running..."

def run(): app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.remove_webhook()
    print("Bot is starting...")
    bot.infinity_polling(skip_pending=True)
