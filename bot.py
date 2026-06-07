import telebot
from telebot import types
from pymongo import MongoClient # تغییر یافت
import os
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import time # اضافه شد برای سیستم ضد اسپم و محاسبات زمان

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8521801987
CHANNEL_ID = "@rafe_filter_A"
GROUP_ID = "@GP_config_A" # اضافه شد
SUPPORT_ID = "@Amir_confing_meli"

# خط ۱۵ همان کامنت قبلی شماست

from telebot import apihelper
apihelper.ENABLE_MIDDLEWARE = True

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# ---------------- DB (Changed to MongoDB) ----------------

# اتصال به دیتابیس ابری شما
MONGO_URI = "mongodb+srv://1raven1390_db_user:iOlmB4Azr3SrrkVZ@bot.te88ask.mongodb.net/?retryWrites=true&w=majority&appName=Bot"
client = MongoClient(MONGO_URI)
db = client['telegram_bot']

users_col = db['users']
orders_col = db['orders']
settings_col = db['settings']
fjoin_col = db['force_join'] # کالکشن جدید برای عضویت اجباری

# مقداردهی اولیه تنظیمات (اگر وجود نداشته باشند)
# کلیدهای جدید سرورها اضافه شدند
for s in ['sale_month', 'sale_vip', 'sale_napsterv', 'sale_napsterv_unlim', 'sale_wireguard', 'charge_status', 'ref_status', 'learn_status']: 
    if not settings_col.find_one({"key": s}):
        settings_col.insert_one({"key": s, "value": 1})

# مقداردهی اولیه کانال و گروه پیشفرض در صورت خالی بودن دیتابیس
if fjoin_col.count_documents({}) == 0:
    fjoin_col.insert_one({"type": "channel", "chat_id": CHANNEL_ID})
    fjoin_col.insert_one({"type": "group", "chat_id": GROUP_ID})

# --- بخش جدید: مقداردهی اولیه قیمت‌ها در دیتابیس (بدون تغییر کدهای قبلی) ---
default_prices = {
    "PRICES_MONTH": {"1G":350000,"2G":699000,"3G":999000,"5G":1499000},
    "PRICES_VIP": {"1G":599000,"2G":1198000,"3G":1797000,"5G":2899000,"10G":5299000},
    "PRICES_NAPSTERV": {"1G":350000,"2G":699000,"3G":999000,"5G":1499000},
    "PRICES_NAPSTERV_UNLIM": {"1G":599000,"2G":1198000,"3G":1797000,"5G":2899000,"10G":5299000},
    "PRICES_WIREGUARD": {"1G":400000,"2G":799000,"3G":1099000,"5G":1599000}
}
for p_type, p_dict in default_prices.items():
    if not settings_col.find_one({"key": p_type}):
        settings_col.insert_one({"key": p_type, "value": p_dict})

def get_db_prices(p_type):
    res = settings_col.find_one({"key": p_type})
    return res['value'] if res else default_prices[p_type]

# --------------- STATE ---------------
user_states = {}

# حافظه موقت برای ذخیره تاریخچه درخواست‌ها جهت ساخت ضد اسپم هوشمند بدون دیتابیس
user_spam_history = {}
user_muted_until = {}

# --------------- UTILS ---------------

def get_setting(key):
    res = settings_col.find_one({"key": key})
    return res['value'] == 1 if res else True

def format_p(x):
    try: return "{:,}".format(int(x))
    except: return "0"

def now_str():
    return datetime.now().strftime("%Y/%m/%d - %H:%M:%S")

def main_menu():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛒 خرید سرویس پرسرعت", callback_data="buy"), types.InlineKeyboardButton("📊 تعرفه خدمات", callback_data="price"))
    kb.add(types.InlineKeyboardButton("💰 افزایش موجودی", callback_data="charge"), types.InlineKeyboardButton("👤 حساب کاربری", callback_data="account"))
    kb.add(types.InlineKeyboardButton("👥 زیرمجموعه‌گیری", callback_data="referral"), types.InlineKeyboardButton("📞 پشتیبانی", callback_data="support"))
    # دکمه‌های جدید منوی اصلی با ایموجی‌های جذاب
    kb.add(types.InlineKeyboardButton("⚡ وضعیت سرورها", callback_data="server_status"), types.InlineKeyboardButton("📋 اطلاعیه‌ها", callback_data="view_announcements"))
    kb.add(types.InlineKeyboardButton("📱 آموزش اتصال", callback_data="user_learn_menu"))
    return kb

def back_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back"))
    return kb

def is_member(user_id):
    items = list(fjoin_col.find({}))
    if not items: return True
    try:
        for item in items:
            st = bot.get_chat_member(item['chat_id'], user_id).status
            if st not in ['member', 'creator', 'administrator']:
                return False
        return True
    except: return True

# ----------------- ANTI SPAM MIDDLEWARE -----------------
@bot.middleware_handler(update_types=['message', 'callback_query'])
def anti_spam_middleware(bot_instance, update):
    if update.message:
        uid = update.message.from_user.id
    elif update.callback_query:
        uid = update.callback_query.from_user.id
    else:
        return

    curr_time = time.time()
    
    # بررسی اینکه کاربر در حال حاضر سایلنت است یا خیر
    if uid in user_muted_until:
        if curr_time < user_muted_until[uid]:
            if update.callback_query:
                bot.answer_callback_query(update.callback_query.id, "⚠️ شما به دلیل اسپم ۳۰ ثانیه مسدود شده‌اید!", show_alert=True)
            return telebot.handler_backends.CancelUpdate()
        else:
            del user_muted_until[uid]
            if uid in user_spam_history:
                user_spam_history[uid] = []

    # ثبت زمان فعالیت برای آمار ادمین
    users_col.update_one({"user_id": uid}, {"$set": {"last_activity": datetime.now()}}, upsert=False)

    if uid not in user_spam_history:
        user_spam_history[uid] = []
        
    user_spam_history[uid].append(curr_time)
    
    # فیلتر کردن درخواست‌های قدیمی‌تر از ۵ ثانیه
    user_spam_history[uid] = [t for t in user_spam_history[uid] if curr_time - t <= 5]
    
    if len(user_spam_history[uid]) > 4:
        user_muted_until[uid] = curr_time + 30
        if update.message:
            bot.send_message(uid, "🚫 رگباری دکمه نزنید! شما به دلیل اسپم به مدت ۳۰ ثانیه مسدود شدید.")
        elif update.callback_query:
            bot.answer_callback_query(update.callback_query.id, "🚫 شما به دلیل اسپم به مدت ۳۰ ثانیه مسدود شدید.", show_alert=True)
        return telebot.handler_backends.CancelUpdate()

# --------------- START & ADMIN COMMAND ---------------

@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    
    user_check = users_col.find_one({"user_id": uid})
    if user_check and (user_check.get("is_banned") or user_check.get("warnings", 0) >= 3):
        bot.send_message(uid, "❌ حساب شما به دلیل تخلف (یا دریافت ۳ اخطار) مسدود شده است.")
        return

    ref_by = None
    if len(m.text.split()) > 1:
        ref_by_id = m.text.split()[1]
        if ref_by_id.isdigit():
            ref_by = int(ref_by_id)
            if ref_by == uid: ref_by = None

    user = users_col.find_one({"user_id": uid})
    if not user:
        users_col.insert_one({
            "user_id": uid, "balance": 0, "configs_count": 0, "warnings": 0, 
            "success_payments": 0, "name": m.from_user.first_name or "", 
            "username": m.from_user.username or "", "join_date": now_str(),
            "invited_count": 0, "is_banned": False, "last_activity": datetime.now()
        })
        if ref_by and get_setting('ref_status'):
            inviter = users_col.find_one({"user_id": ref_by})
            if inviter and inviter.get('invited_count', 0) < 4:
                users_col.update_one({"user_id": ref_by}, {"$inc": {"balance": 5000, "invited_count": 1}})
                bot.send_message(ref_by, "🎉 تبریک! یک کاربر با لینک شما عضو شد و ۵,۰۰۰ تومان به موجودی شما اضافه شد.")

    if not is_member(uid):
        kb = types.InlineKeyboardMarkup()
        items = list(fjoin_col.find({}))
        for item in items:
            label = "📢 کانال" if item['type'] == "channel" else "👥 گروه"
            url = f"https://t.me/{item['chat_id'].replace('@','')}"
            kb.add(types.InlineKeyboardButton(label, url=url))
        kb.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data="check_join"))
        bot.send_message(uid, "برای استفاده ابتدا عضو موارد زیر شوید:", reply_markup=kb)
        return
    bot.send_message(uid, "👇 منوی اصلی:", reply_markup=main_menu())

@bot.message_handler(commands=['admin'])
def admin_panel(m):
    if m.from_user.id != ADMIN_ID: return
    users_count = users_col.count_documents({})
    total_balance = list(users_col.aggregate([{"$group": {"_id": None, "total": {"$sum": "$balance"}}}]))
    total = total_balance[0]['total'] if total_balance else 0
    pending = orders_col.count_documents({"status": "pending"})
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📦 سفارشات باز", callback_data="adm_orders"))
    kb.add(types.InlineKeyboardButton("🔎 مشاهده کاربر", callback_data="adm_get_user"))
    kb.add(types.InlineKeyboardButton("📣 ارسال همگانی", callback_data="adm_broadcast"))
    kb.add(types.InlineKeyboardButton("⚙️ مدیریت فروش", callback_data="adm_settings"))
    kb.add(types.InlineKeyboardButton("💰 تغییر قیمت‌ها", callback_data="adm_change_prices")) 
    kb.add(types.InlineKeyboardButton("🛡 مدیریت عضویت", callback_data="adm_fjoin_mgr"))
    # دکمه‌های مدیریت پیشرفته جدید در پنل مدیریت
    kb.add(types.InlineKeyboardButton("📢 ارسال اطلاعیه ۱ دقیقه‌ای", callback_data="adm_smart_announcement"), types.InlineKeyboardButton("⚡ بروزرسانی وضعیت سرور", callback_data="adm_update_servers"))
    kb.add(types.InlineKeyboardButton("📊 آمار کاربران فعال", callback_data="adm_active_stats"), types.InlineKeyboardButton("📱 مدیریت آموزش اتصال", callback_data="adm_manage_learn"))
    bot.send_message(m.chat.id, f"👑 پنل ادمین \n\n👤 تعداد کاربران: {users_count}\n💰 مجموع موجودی: {format_p(total)}\n📦 سفارشات باز: {pending}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join(c):
    if is_member(c.from_user.id):
        bot.edit_message_text("✅ تایید شد", c.message.chat.id, c.message.message_id, reply_markup=main_menu())
    else: bot.answer_callback_query(c.id, "هنوز عضو کانال یا گروه نشدی", show_alert=True)

# --------------- ADMIN SETTINGS (MANAGEMENT) ---------------

@bot.callback_query_handler(func=lambda c: c.data == "adm_settings")
def adm_settings(c):
    if c.from_user.id != ADMIN_ID: return
    m_status = "✅ باز" if get_setting('sale_month') else "❌ بسته"
    v_status = "✅ باز" if get_setting('sale_vip') else "❌ بسته"
    nv_status = "✅ باز" if get_setting('sale_napsterv') else "❌ بسته"
    nvu_status = "✅ باز" if get_setting('sale_napsterv_unlim') else "❌ بسته"
    wg_status = "✅ باز" if get_setting('sale_wireguard') else "❌ بسته"
    c_status = "✅ باز" if get_setting('charge_status') else "❌ بسته"
    r_status = "✅ باز" if get_setting('ref_status') else "❌ بسته"
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"فروش ۱ ماهه: {m_status}", callback_data="tog_sale_month"))
    kb.add(types.InlineKeyboardButton(f"فروش VIP: {v_status}", callback_data="tog_sale_vip"))
    kb.add(types.InlineKeyboardButton(f"سرور نپستر: {nv_status}", callback_data="tog_sale_napsterv"))
    kb.add(types.InlineKeyboardButton(f"سرور نامحدود نپستر: {nvu_status}", callback_data="tog_sale_napsterv_unlim"))
    kb.add(types.InlineKeyboardButton(f"سرور وایرگارد: {wg_status}", callback_data="tog_sale_wireguard"))
    kb.add(types.InlineKeyboardButton(f"افزایش موجودی: {c_status}", callback_data="tog_charge_status"))
    kb.add(types.InlineKeyboardButton(f"سیستم دعوت: {r_status}", callback_data="tog_ref_status"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_back"))
    bot.edit_message_text("⚙️ مدیریت وضعیت خدمات:\n(با کلیک روی هر دکمه وضعیت آن عوض می‌شود)", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("tog_"))
def toggle_settings(c):
    if c.from_user.id != ADMIN_ID: return
    key = c.data.replace("tog_", "")
    current = get_setting(key)
    settings_col.update_one({"key": key}, {"$set": {"value": 0 if current else 1}})
    adm_settings(c)

@bot.callback_query_handler(func=lambda c: c.data == "admin_back")
def admin_back(c):
    admin_panel(c.message)

# --------------- CHARGE ---------------

@bot.callback_query_handler(func=lambda c: c.data == "charge")
def charge(c):
    if not get_setting('charge_status'):
        bot.answer_callback_query(c.id, "⚠️ در حال حاضر بخش افزایش موجودی موقتاً بسته است.", show_alert=True)
        return
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
    bot.send_message(m.chat.id, f"✅ اطلاعات ثبت شد\n\n💰 مبلغ: {format_p(amt)} تومان\n💳 کارت مقصد:\n6221061233705260\n👤 به نام: افراس\n\n⚠️ مبلغ را واریز کرده و رسید را ارسال کنید\n\n⏰ فاکتور تا ۳۰ دقیقه معتبر است", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "send_receipt")
def send_receipt(c):
    bot.send_message(c.from_user.id, "📸 لطفاً تصویر رسید را ارسال کنید")

@bot.message_handler(content_types=['photo'])
def receipt(m):
    data = user_states.get(m.from_user.id)
    if not data or data.get("state") != "WAIT_RECEIPT": return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ تایید", callback_data=f"ok_{m.from_user.id}_{data['amount']}"), types.InlineKeyboardButton("❌ رد", callback_data=f"no_{m.from_user.id}"))
    bot.send_photo(ADMIN_ID, m.photo[-1].file_id, caption=f"💰 درخواست شارژ\n\n👤 کاربر: {m.from_user.id}\n💵 مبلغ: {format_p(data['amount'])}\n💳 کارت مبدا: {data['card']}", reply_markup=kb)
    bot.send_message(m.chat.id, "✅ رسید برای ادمین ارسال شد، لطفاً منتظر بمانید 🙏")
    user_states[m.from_user.id] = None

@bot.callback_query_handler(func=lambda c: c.data.startswith("ok_"))
def ok(c):
    _, uid, amt = c.data.split("_")
    uid = int(uid); amt = int(amt)
    users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt, "success_payments": 1}})
    bot.send_message(uid, f"✅ مبلغ {format_p(amt)} تومان به حساب شما اضافه شد")

@bot.callback_query_handler(func=lambda c: c.data.startswith("no_"))
def no(c):
    uid = int(c.data.split("_")[1])
    users_col.update_one({"user_id": uid}, {"$inc": {"warnings": 1}})
    u_data = users_col.find_one({"user_id": uid})
    warns = u_data.get("warnings", 0)
    if warns >= 3:
        users_col.update_one({"user_id": uid}, {"$set": {"is_banned": True}})
        bot.send_message(uid, "❌ شما ۳ اخطار دریافت کردید و دسترسی شما به ربات برای همیشه مسدود شد.")
    else:
        bot.send_message(uid, f"❌ رسید شما رد شد و اخطار دریافت کردید. (تعداد اخطار: {warns} از ۳)")

# --------------- PRICE ---------------

@bot.callback_query_handler(func=lambda c: c.data == "price")
def price_menu(c):
    kb = types.InlineKeyboardMarkup()
    # شرط عدم نمایش دکمه‌ها در صورت خاموش بودن خدمات
    if get_setting('sale_month'):
        kb.add(types.InlineKeyboardButton("📅 ۱ ماهه", callback_data="price_month"))
    
    # کنترل باز شدن بخش VIP به سطح کاربر در تعرفه
    u_data = users_col.find_one({"user_id": c.from_user.id})
    success_buys = u_data.get("success_payments", 0) if u_data else 0
    if get_setting('sale_vip') and success_buys >= 15:
        kb.add(types.InlineKeyboardButton("💎 سرور VIP", callback_data="price_vip"))
        
    if get_setting('sale_napsterv'):
        kb.add(types.InlineKeyboardButton("🔮 سرور نپستر", callback_data="price_napsterv"))
    if get_setting('sale_napsterv_unlim'):
        kb.add(types.InlineKeyboardButton("🌀 سرور نامحدود نپستر", callback_data="price_napsterv_unlim"))
    if get_setting('sale_wireguard'):
        kb.add(types.InlineKeyboardButton("🔴 سرور وایرگارد", callback_data="price_wireguard"))
        
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    bot.edit_message_text("📊 تعرفه خدمات باز:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "price_month")
def price_month(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👤 تک کاربره", callback_data="show_month_prices"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="price"))
    bot.edit_message_text("۱ ماهه:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "show_month_prices")
def show_month_prices(c):
    p = get_db_prices("PRICES_MONTH")
    txt = "📅 ۱ ماهه (تک کاربره)\n\n"
    for vol, price in p.items():
        txt += f"{vol} : {format_p(price)}\n"
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

@bot.callback_query_handler(func=lambda c: c.data == "price_vip")
def price_vip(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("♾ بدون محدودیت کاربری", callback_data="show_vip_prices"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="price"))
    bot.edit_message_text("VIP:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "show_vip_prices")
def show_vip_prices(c):
    p = get_db_prices("PRICES_VIP")
    txt = "♾ بدون محدودیت + VIP (تخفیف)\n\n"
    for vol, price in p.items():
        txt += f"{vol} : {format_p(price)}\n"
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

# هندلرهای جدید بخش قیمت‌ها
@bot.callback_query_handler(func=lambda c: c.data == "price_napsterv")
def price_napsterv(c):
    p = get_db_prices("PRICES_NAPSTERV")
    txt = "🔮 سرور نپستر\n\n"
    for vol, price in p.items():
        txt += f"{vol} : {format_p(price)}\n"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="price"))
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "price_napsterv_unlim")
def price_napsterv_unlim(c):
    p = get_db_prices("PRICES_NAPSTERV_UNLIM")
    txt = "🌀 سرور نامحدود نپستر\n\n"
    for vol, price in p.items():
        txt += f"{vol} : {format_p(price)}\n"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="price"))
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "price_wireguard")
def price_wireguard(c):
    p = get_db_prices("PRICES_WIREGUARD")
    txt = "🔴 سرور وایرگارد\n\n"
    for vol, price in p.items():
        txt += f"{vol} : {format_p(price)}\n"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="price"))
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=kb)

# --------------- BUY ---------------

PRICES_MONTH = {"1G":350000,"2G":699000,"3G":999000,"5G":1499000}
PRICES_VIP = {"1G":599000,"2G":1198000,"3G":1797000,"5G":2899000,"10G":5299000}

@bot.callback_query_handler(func=lambda c: c.data == "buy")
def buy(c):
    kb = types.InlineKeyboardMarkup()
    # عدم نمایش دکمه‌ها در صورت بسته بودن فروش هر سرور
    if get_setting('sale_month'):
        kb.add(types.InlineKeyboardButton("📅 ۱ ماهه", callback_data="buy_month"))
        
    # قفل هوشمند دکمه خرید سرور VIP بر اساس تعداد خریدهای موفق کاربر
    u_data = users_col.find_one({"user_id": c.from_user.id})
    success_buys = u_data.get("success_payments", 0) if u_data else 0
    if get_setting('sale_vip') and success_buys >= 15:
        kb.add(types.InlineKeyboardButton("💎 سرور VIP", callback_data="buy_vip"))
        
    if get_setting('sale_napsterv'):
        kb.add(types.InlineKeyboardButton("🔮 سرور نپستر", callback_data="buy_napsterv"))
    if get_setting('sale_napsterv_unlim'):
        kb.add(types.InlineKeyboardButton("🌀 سرور نامحدود نپستر", callback_data="buy_napsterv_unlim"))
    if get_setting('sale_wireguard'):
        kb.add(types.InlineKeyboardButton("🔴 سرور وایرگارد", callback_data="buy_wireguard"))
        
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    bot.edit_message_text("🛒 خرید سرویس:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "buy_month")
def buy_month(c):
    if not get_setting('sale_month'):
        bot.answer_callback_query(c.id, "⚠️ در حال حاضر فروش پلن‌های ۱ ماهه بسته است.", show_alert=True)
        return
    user_states[c.from_user.id] = {"state":"BUY_PLAN","plan":"MONTH"}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👤 تک کاربره", callback_data="buy_month_single"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy"))
    bot.edit_message_text("۱ ماهه:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "buy_month_single")
def buy_month_single(c):
    p = get_db_prices("PRICES_MONTH")
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in p.keys(): kb.add(types.InlineKeyboardButton(v, callback_data=f"vol_{v}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_month"))
    bot.edit_message_text("حجم را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "buy_vip")
def buy_vip(c):
    if not get_setting('sale_vip'):
        bot.answer_callback_query(c.id, "⚠️ در حال حاضر فروش پلن‌های VIP بسته است.", show_alert=True)
        return
    user_states[c.from_user.id] = {"state":"BUY_PLAN","plan":"VIP"}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("♾ بدون محدودیت کاربری", callback_data="buy_vip_unlim"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy"))
    bot.edit_message_text("VIP:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "buy_vip_unlim")
def buy_vip_unlim(c):
    p = get_db_prices("PRICES_VIP")
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in p.keys(): kb.add(types.InlineKeyboardButton(v, callback_data=f"vol_{v}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_vip"))
    bot.edit_message_text("حجم را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

# هندلرهای جدید بخش خرید برای سرورهای درخواستی
@bot.callback_query_handler(func=lambda c: c.data == "buy_napsterv")
def buy_napsterv(c):
    if not get_setting('sale_napsterv'):
        bot.answer_callback_query(c.id, "⚠️ در حال حاضر فروش سرور نپستر بسته است.", show_alert=True)
        return
    user_states[c.from_user.id] = {"state":"BUY_PLAN","plan":"NAPSTERV"}
    p = get_db_prices("PRICES_NAPSTERV")
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in p.keys(): kb.add(types.InlineKeyboardButton(v, callback_data=f"vol_{v}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy"))
    bot.edit_message_text("حجم سرور نپستر را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "buy_napsterv_unlim")
def buy_napsterv_unlim(c):
    if not get_setting('sale_napsterv_unlim'):
        bot.answer_callback_query(c.id, "⚠️ در حال حاضر فروش سرور نامحدود نپستر بسته است.", show_alert=True)
        return
    user_states[c.from_user.id] = {"state":"BUY_PLAN","plan":"NAPSTERV_UNLIM"}
    p = get_db_prices("PRICES_NAPSTERV_UNLIM")
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in p.keys(): kb.add(types.InlineKeyboardButton(v, callback_data=f"vol_{v}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy"))
    bot.edit_message_text("حجم سرور نامحدود نپستر را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "buy_wireguard")
def buy_wireguard(c):
    if not get_setting('sale_wireguard'):
        bot.answer_callback_query(c.id, "⚠️ در حال حاضر فروش سرور وایرگارد بسته است.", show_alert=True)
        return
    user_states[c.from_user.id] = {"state":"BUY_PLAN","plan":"WIREGUARD"}
    p = get_db_prices("PRICES_WIREGUARD")
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in p.keys(): kb.add(types.InlineKeyboardButton(v, callback_data=f"vol_{v}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy"))
    bot.edit_message_text("حجم سرور وایرگارد را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("vol_"))
def select_volume(c):
    uid = c.from_user.id
    st = user_states.get(uid, {})
    plan = st.get("plan")
    volume = c.data.split("_")[1]
    
    # دریافت قیمت بروز از دیتابیس برای تمامی سرورها
    db_p = get_db_prices(f"PRICES_{plan}")
    price = db_p.get(volume)
    
    user = users_col.find_one({"user_id": uid})
    balance = user['balance'] if user else 0
    if balance < price:
        bot.answer_callback_query(c.id, "❌ابتدا حساب خود را شارژ کنید", show_alert=True); return
    user_states[uid] = {"state":"CONFIRM_BUY","plan":plan,"volume":volume,"price":price}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ تایید", callback_data="final_buy"), types.InlineKeyboardButton("❌ لغو", callback_data="back"))
    bot.send_message(uid, f"آیا از خرید سرویس {plan} حجم {volume} به مبلغ {format_p(price)} اطمینان دارید؟", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "final_buy")
def final_buy(c):
    uid = c.from_user.id
    data = user_states.get(uid, {})
    if data.get("state") != "CONFIRM_BUY": return
    price = data["price"]
    users_col.update_one({"user_id": uid}, {"$inc": {"balance": -price, "configs_count": 1}})
    res = orders_col.insert_one({"user_id": uid, "plan": data["plan"], "volume": data["volume"], "price": price, "status": "pending", "created_at": now_str()})
    order_id = str(res.inserted_id)
    bot.send_message(uid, "⏳ سفارش شما ثبت شد. در حال ساخت کانفیگ...")
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📤 ارسال کانفیگ", callback_data=f"sendcfg_{order_id}"))
    bot.send_message(ADMIN_ID, f"🛒 سفارش جدید\n\n🆔 OrderID: {order_id}\n👤 کاربر: {uid}\n📦 پلن: {data['plan']}\n📊 حجم: {data['volume']}\n💵 مبلغ: {format_p(price)}", reply_markup=kb)
    user_states[uid] = None

# --------------- REFERRAL SYSTEM ---------------

@bot.callback_query_handler(func=lambda c: c.data == "referral")
def referral_panel(c):
    if not get_setting('ref_status'):
        bot.answer_callback_query(c.id, "⚠️ این بخش در حال حاضر توسط ادمین بسته شده است.", show_alert=True)
        return
    uid = c.from_user.id
    user = users_col.find_one({"user_id": uid})
    count = user.get("invited_count", 0)
    bot_user = bot.get_me().username
    link = f"https://t.me/{bot_user}?start={uid}"
    
    text = f"👥 سیستم زیرمجموعه‌گیری\n\n"
    text += f"با دعوت دوستان خود به ربات، برای هر نفر ۵,۰۰۰ تومان هدیه بگیرید.\n\n"
    text += f"✅ تعداد دعوت‌های موفق شما: {count} از ۴\n"
    text += f"🔗 لینک دعوت اختصاصی شما:\n`{link}`\n\n"
    text += f"⚠️ سقف دعوت برای هر کاربر ۴ نفر می‌باشد."
    
    bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=back_kb(), parse_mode="Markdown")

# --------------- ADMIN CONFIG SENDING ---------------

@bot.callback_query_handler(func=lambda c: c.data.startswith("sendcfg_"))
def start_send_config(c):
    from bson.objectid import ObjectId
    if c.from_user.id != ADMIN_ID: return
    order_id_str = c.data.split("_")[1]
    order = orders_col.find_one({"_id": ObjectId(order_id_str)})
    if not order:
        bot.answer_callback_query(c.id, "سفارش پیدا نشد", show_alert=True); return
    if order['status'] != "pending":
        bot.answer_callback_query(c.id, "این سفارش قبلا انجام شده", show_alert=True); return
    user_states[ADMIN_ID] = {"state": "SEND_CONFIG", "order_id": order_id_str, "user_id": order['user_id']}
    bot.send_message(ADMIN_ID, "📤 کانفیگ رو ارسال کن (میتونی متن بفرستی یا فایل وایرگارد آپلود کنی):")

# هندلر ارتقا یافته تحویل سفارش برای پشتیبانی کامل از فایل و مدیا
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "SEND_CONFIG", content_types=['text', 'document', 'photo', 'video', 'audio'])
def send_config_to_user(m):
    from bson.objectid import ObjectId
    if m.text == "/admin":
        user_states[ADMIN_ID] = None
        admin_panel(m); return
    data = user_states.get(ADMIN_ID)
    order_id = data["order_id"]; user_id = data["user_id"]
    
    # ارسال هوشمند بر اساس نوع رسانه فرستاده شده توسط ادمین
    if m.content_type == 'text':
        bot.send_message(user_id, f"✅ کانفیگ شما:\n\n{m.text}")
    elif m.content_type == 'document':
        bot.send_document(user_id, m.document.file_id, caption="✅ فایل کانفیگ اختصاصی شما (وایرگارد)")
    elif m.content_type == 'photo':
        bot.send_photo(user_id, m.photo[-1].file_id, caption=m.caption or "✅ بارکد / تصویر سرویس شما")
    elif m.content_type == 'video':
        bot.send_video(user_id, m.video.file_id, caption=m.caption or "✅ فایل سفارش شما")
        
    orders_col.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "done"}})
    bot.send_message(ADMIN_ID, f"✅ سفارش {order_id} با موفقیت در قالب رسانه مربوطه به خریدار تحویل داده شد.")
    user_states[ADMIN_ID] = None

# --------------- ACCOUNT ---------------

@bot.callback_query_handler(func=lambda c: c.data == "account")
def account(c):
    d = users_col.find_one({"user_id": c.from_user.id})
    username = f"@{c.from_user.username}" if c.from_user.username else "❌ ندارد"
    status = "🚫 مسدود" if d.get("is_banned") or d.get("warnings", 0) >= 3 else "✅ فعال"
    
    # محاسبه هوشمند سطح کاربری کاربر
    success_buys = d.get("success_payments", 0)
    if success_buys <= 3:
        level = "برنزی 🥉"
    elif 4 <= success_buys <= 6:
        level = "نقره‌ای 🥈"
    elif 7 <= success_buys <= 14:
        level = "طلایی 🥇"
    else:
        level = "VIP 💎 (دسترسی کامل به سرورهای کلیدی)"
        
    text = f"📊 اطلاعات حساب کاربری شما در ربات: \n\n🔢 آیدی عددی : {c.from_user.id}\n👑 سطح حساب: {level}\n🔆 یوزرنیم : {username}\n📱 وضعیت : {status}\n💰 موجودی : {format_p(d['balance'])} تومان\n🏦 پرداخت های موفق : {d['success_payments']} عدد\n🛍 تعداد سرویس ها : {d['configs_count']} عدد\n⚠️ تعداد اخطار ها : {d['warnings']} عدد\n⏰ تاریخ عضویت : {d['join_date']}\n\n🤖 | @rafe_filter_GB_bot"
    bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

# --------------- SUPPORT ---------------

@bot.callback_query_handler(func=lambda c: c.data == "support")
def support(c):
    bot.edit_message_text(f"📞 پشتیبانی:\n{SUPPORT_ID}", c.message.chat.id, c.message.message_id, reply_markup=back_kb())

# --------------- BACK ---------------

@bot.callback_query_handler(func=lambda c: c.data == "back")
def back(c):
    bot.edit_message_text("👇 منوی اصلی:", c.message.chat.id, c.message.message_id, reply_markup=main_menu())

# --------------- ADMIN OTHER FUNCTIONS ---------------

@bot.callback_query_handler(func=lambda c: c.data == "adm_orders")
def adm_orders(c):
    if c.from_user.id != ADMIN_ID: return
    rows = list(orders_col.find({"status": "pending"}).sort("_id", -1).limit(20))
    if not rows: bot.send_message(ADMIN_ID, "سفارشی وجود ندارد"); return
    txt = "📦 سفارشات باز:\n\n"
    for r in rows: txt += f"ID:{r['_id']} | U:{r['user_id']} | {r['plan']} | {r['volume']} | {format_p(r['price'])}\n{r['created_at']}\n---\n"
    bot.send_message(ADMIN_ID, txt)

@bot.callback_query_handler(func=lambda c: c.data == "adm_get_user")
def adm_get_user(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state":"ADM_GET_USER"}
    bot.send_message(ADMIN_ID, "آیدی عددی کاربر را ارسال کنید:")

@bot.message_handler(func=lambda m: user_states.get(ADMIN_ID, {}).get("state") == "ADM_GET_USER" and m.from_user.id==ADMIN_ID)
def adm_show_user(m):
    if not m.text.isdigit(): bot.send_message(ADMIN_ID, "آیدی نامعتبر"); return
    uid = int(m.text)
    d = users_col.find_one({"user_id": uid})
    if not d: bot.send_message(ADMIN_ID, "کاربر یافت نشد"); return
    
    is_banned = d.get("is_banned") or d.get("warnings", 0) >= 3
    ban_txt = "🔓 آن‌بن کردن" if is_banned else "🚫 بن کردن"
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("➕ افزودن موجودی", callback_data=f"adm_add_{uid}"), types.InlineKeyboardButton("➖ کسر موجودی", callback_data=f"adm_sub_{uid}"))
    kb.add(types.InlineKeyboardButton("⚠️ اخطار", callback_data=f"adm_warn_{uid}"), types.InlineKeyboardButton(ban_txt, callback_data=f"adm_ban_{uid}"))
    kb.add(types.InlineKeyboardButton("📩 پیام خصوصی", callback_data=f"adm_pmsg_{uid}"))
    
    bot.send_message(ADMIN_ID, f"👤 کاربر {uid} \n\n💰 موجودی: {format_p(d['balance'])}\n🏦 پرداخت موفق: {d['success_payments']}\n🛍 سرویس‌ها: {d['configs_count']}\n⚠️ اخطار: {d['warnings']}\n🚫 وضعیت: {'مسدود' if is_banned else 'آزاد'}\n⏰ عضویت: {d['join_date']}", reply_markup=kb)
    user_states[ADMIN_ID] = None

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_ban_"))
def adm_ban_toggle(c):
    if c.from_user.id != ADMIN_ID: return
    uid = int(c.data.split("_")[2])
    user = users_col.find_one({"user_id": uid})
    
    current_ban = user.get("is_banned") or user.get("warnings", 0) >= 3
    if current_ban:
        users_col.update_one({"user_id": uid}, {"$set": {"is_banned": False, "warnings": 0}})
        txt = "آزاد شد"
    else:
        users_col.update_one({"user_id": uid}, {"$set": {"is_banned": True}})
        txt = "مسدود شد"
        
    bot.answer_callback_query(c.id, f"کاربر {txt}")
    bot.send_message(uid, f"⚠️ حساب شما توسط مدیریت {txt} شد.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_add_"))
def adm_add(c):
    if c.from_user.id != ADMIN_ID: return
    uid = int(c.data.split("_")[2])
    user_states[ADMIN_ID] = {"state":"ADM_ADD", "uid":uid}
    bot.send_message(ADMIN_ID, "مبلغ برای افزودن را بفرست:")

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_sub_"))
def adm_sub(c):
    if c.from_user.id != ADMIN_ID: return
    uid = int(c.data.split("_")[2])
    user_states[ADMIN_ID] = {"state":"ADM_SUB", "uid":uid}
    bot.send_message(ADMIN_ID, "مبلغ برای کسر را بفرست:")

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_warn_"))
def adm_warn(c):
    if c.from_user.id != ADMIN_ID: return
    uid = int(c.data.split("_")[2])
    users_col.update_one({"user_id": uid}, {"$inc": {"warnings": 1}})
    bot.send_message(uid, "⚠️ از سمت ادمین اخطار دریافت کردید")
    bot.answer_callback_query(c.id, "ثبت شد")

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_pmsg_"))
def adm_pmsg_start(c):
    if c.from_user.id != ADMIN_ID: return
    uid = c.data.split("_")[2]
    user_states[ADMIN_ID] = {"state": "ADM_SEND_PMSG", "target": uid}
    bot.send_message(ADMIN_ID, f"پیام خود را برای کاربر {uid} بنویسید:")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "ADM_SEND_PMSG")
def adm_pmsg_send(m):
    target = user_states[ADMIN_ID]["target"]
    try:
        bot.send_message(target, f"📩 پیام جدید از مدیریت:\n\n{m.text}")
        bot.send_message(ADMIN_ID, "✅ با موفقیت ارسال شد")
    except: bot.send_message(ADMIN_ID, "❌ ارسال ناموفق (شاید بلاک کرده)")
    user_states[ADMIN_ID] = None

@bot.message_handler(func=lambda m: m.from_user.id==ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") in ["ADM_ADD","ADM_SUB"])
def adm_balance_edit(m):
    st = user_states.get(ADMIN_ID, {})
    if not m.text.isdigit(): bot.send_message(ADMIN_ID, "عدد بفرست"); return
    amt = int(m.text); uid = st["uid"]
    if st["state"] == "ADM_ADD":
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
        bot.send_message(uid, f"💰 {format_p(amt)} تومان به حسابت اضافه شد (ادمین)")
    else:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": -amt}})
        bot.send_message(uid, f"💰 {format_p(amt)} تومان از حسابت کسر شد (ادمین)")
    user_states[ADMIN_ID] = None
    bot.send_message(ADMIN_ID, "انجام شد")

@bot.callback_query_handler(func=lambda c: c.data == "adm_broadcast")
def adm_broadcast(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state":"ADM_BC"}
    bot.send_message(ADMIN_ID, "پیام همگانی را ارسال کنید:")

@bot.message_handler(func=lambda m: m.from_user.id==ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "ADM_BC")
def do_broadcast(m):
    users = users_col.find({}, {"user_id": 1})
    ok = 0
    for u in users:
        try: bot.send_message(u['user_id'], m.text); ok += 1
        except: pass
    user_states[ADMIN_ID] = None
    bot.send_message(ADMIN_ID, f"ارسال شد برای {ok} نفر")

# --------------- بخش جدید: مدیریت قیمت‌ها و حجم‌ها توسط ادمین ---------------

@bot.callback_query_handler(func=lambda c: c.data == "adm_change_prices")
def adm_change_prices(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📅 قیمت ۱ ماهه", callback_data="setp_MONTH"), 
           types.InlineKeyboardButton("♾ قیمت VIP", callback_data="setp_VIP"))
    kb.add(types.InlineKeyboardButton("🔮 قیمت نپستر", callback_data="setp_NAPSTERV"), 
           types.InlineKeyboardButton("🌀 قیمت نپستر نامحدود", callback_data="setp_NAPSTERV_UNLIM"))
    kb.add(types.InlineKeyboardButton("🔴 قیمت وایرگارد", callback_data="setp_WIREGUARD"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back"))
    bot.edit_message_text("⚙️ مدیریت تعرفه‌ها و حجم سرورها:\nکدام دسته‌ب بندی را مدیریت می‌کنید?کدام دسته‌ب بندی را مدیریت می‌کنید؟", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("setp_"))
def adm_setp_plan(c):
    plan = c.data.split("_")[1]
    kb = types.InlineKeyboardMarkup(row_width=2)
    p = get_db_prices(f"PRICES_{plan}")
    
    # نمایش دکمه برای تک تک حجم‌های فعلی جهت ویرایش یا حذف
    for v in p.keys():
        kb.add(
            types.InlineKeyboardButton(f"⚙️ {v} ({format_p(p[v])} ت)", callback_data=f"editp_{plan}_{v}"),
            types.InlineKeyboardButton(f"❌ حذف {v}", callback_data=f"delp_{plan}_{v}")
        )
    
    kb.add(types.InlineKeyboardButton("➕ افزودن حجم جدید به این سرویس", callback_data=f"addp_{plan}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_change_prices"))
    bot.edit_message_text(f"لیست حجم‌های فعلی پلن {plan}:\nجهت تغییر قیمت یا حذف انتخاب کنید یا حجم جدید بسازید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("addp_"))
def adm_addp_start(c):
    plan = c.data.split("_")[1]
    user_states[ADMIN_ID] = {"state": "ADD_VOLUME_NAME", "plan": plan}
    bot.send_message(ADMIN_ID, f"نام حجم جدید برای پلن {plan} را وارد کنید (مثلا: 10G یا 50G):")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "ADD_VOLUME_NAME")
def adm_addp_save_name(m):
    vol_name = m.text.strip().upper()
    plan = user_states[ADMIN_ID]["plan"]
    user_states[ADMIN_ID] = {"state": "SETTING_PRICE", "plan": plan, "vol": vol_name}
    bot.send_message(ADMIN_ID, f"حجم {vol_name} ایجاد شد. حالا قیمت آن را به عدد (تومان) وارد کنید:")

@bot.callback_query_handler(func=lambda c: c.data.startswith("delp_"))
def adm_delp_val(c):
    parts = c.data.split("_")
    if len(parts) == 4:
        plan = f"{parts[1]}_{parts[2]}"
        vol = parts[3]
    else:
        plan = parts[1]
        vol = parts[2]
        
    p_key = f"PRICES_{plan}"
    current_prices = get_db_prices(p_key)
    if vol in current_prices:
        del current_prices[vol]
    settings_col.update_one({"key": p_key}, {"$set": {"value": current_prices}})
    bot.answer_callback_query(c.id, f"حجم {vol} با موفقیت حذف شد", show_alert=True)
    
    # بازسازی کلاسیک دکمه برای برگشت به صفحه قبل
    c.data = f"setp_{plan}"
    adm_setp_plan(c)

@bot.callback_query_handler(func=lambda c: c.data.startswith("editp_"))
def adm_editp_val(c):
    # تفکیک ساختار داده ورودی برای جلوگیری از ارور split
    parts = c.data.split("_")
    if len(parts) == 4: # مثل editp_NAPSTERV_UNLIM_1G
        plan = f"{parts[1]}_{parts[2]}"
        vol = parts[3]
    else:
        plan = parts[1]
        vol = parts[2]
        
    user_states[ADMIN_ID] = {"state": "SETTING_PRICE", "plan": plan, "vol": vol}
    bot.send_message(ADMIN_ID, f"قیمت جدید برای {plan} {vol} را به عدد (تومان) وارد کنید:")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "SETTING_PRICE")
def save_new_price(m):
    if not m.text.isdigit(): bot.send_message(ADMIN_ID, "فقط عدد بفرستید"); return
    new_p = int(m.text)
    data = user_states[ADMIN_ID]
    p_key = f"PRICES_{data['plan']}"
    
    current_prices = get_db_prices(p_key)
    current_prices[data['vol']] = new_p
    settings_col.update_one({"key": p_key}, {"$set": {"value": current_prices}})
    
    bot.send_message(ADMIN_ID, f"✅ تنظیمات ذخیره شد. {data['plan']} حجم {data['vol']} به قیمت {format_p(new_p)} تومان تغییر یافت.")
    user_states[ADMIN_ID] = None

# --------------- بخش جدید: مدیریت عضویت اجباری ---------------

@bot.callback_query_handler(func=lambda c: c.data == "adm_fjoin_mgr")
def adm_fjoin_mgr(c):
    if c.from_user.id != ADMIN_ID: return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📢 مدیریت کانال‌ها", callback_data="fjm_channel"), 
           types.InlineKeyboardButton("👥 مدیریت گروه‌ها", callback_data="fjm_group"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back"))
    bot.edit_message_text("🛡 بخش مدیریت عضویت اجباری:\nیکی از موارد زیر را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("fjm_"))
def fjm_list(c):
    target_type = c.data.split("_")[1]
    items = list(fjoin_col.find({"type": target_type}))
    label = "کانال" if target_type == "channel" else "گروه"
    
    txt = f"لیست {label}های ثبت شده:\n\n"
    kb = types.InlineKeyboardMarkup()
    
    if not items:
        txt += "موردی ثبت نشده است."
    else:
        for item in items:
            txt += f"🔹 {item['chat_id']}\n"
            kb.add(types.InlineKeyboardButton(f"❌ حذف {item['chat_id']}", callback_data=f"fjdel_{item['_id']}"))
    
    kb.add(types.InlineKeyboardButton(f"➕ افزودن {label} جدید", callback_data=f"fjadd_{target_type}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_fjoin_mgr"))
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("fjadd_"))
def fjadd_start(c):
    target_type = c.data.split("_")[1]
    user_states[ADMIN_ID] = {"state": "FJ_WAIT_ID", "type": target_type}
    bot.send_message(ADMIN_ID, f"لطفاً آیدی {target_type} جدید را با @ ارسال کنید:\nمثال: @my_channel")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "FJ_WAIT_ID")
def fjadd_save(m):
    chat_id = m.text.strip()
    if not chat_id.startswith("@"):
        bot.send_message(ADMIN_ID, "❌ آیدی باید با @ شروع شود."); return
    
    target_type = user_states[ADMIN_ID]["type"]
    fjoin_col.insert_one({"type": target_type, "chat_id": chat_id})
    bot.send_message(ADMIN_ID, f"✅ {chat_id} به لیست {target_type}ها اضافه شد.")
    user_states[ADMIN_ID] = None

@bot.callback_query_handler(func=lambda c: c.data.startswith("fjdel_"))
def fjdel_confirm(c):
    from bson.objectid import ObjectId
    item_id = c.data.split("_")[1]
    fjoin_col.delete_one({"_id": ObjectId(item_id)})
    bot.answer_callback_query(c.id, "✅ با موفقیت حذف شد", show_alert=True)
    adm_fjoin_mgr(c)

# ---------------------------------------------------------------------
# >>> کدهای اصلاحی جدید (بدون دست زدن به خطوط قبلی، در انتها اضافه شدند) <<<
# ---------------------------------------------------------------------

@bot.callback_query_handler(func=lambda c: c.data.startswith("setp_"), order=1)
def FIXED_adm_setp_plan(c):
    # دریافت نام دقیق پلن حتی اگر دارای کاراکتر آندرلاین باشد (مثل NAPSTERV_UNLIM)
    plan = c.data.replace("setp_", "")
    kb = types.InlineKeyboardMarkup(row_width=1)
    p = get_db_prices(f"PRICES_{plan}")
    
    for v in list(p.keys()):
        kb.add(
            types.InlineKeyboardButton(f"⚙️ {v} ({format_p(p[v])} ت)", callback_data=f"FIXEDedit_{plan}:::{v}"),
            types.InlineKeyboardButton(f"❌ حذف حجم {v}", callback_data=f"FIXEDdel_{plan}:::{v}")
        )
    
    kb.add(types.InlineKeyboardButton("➕ افزودن حجم جدید به این سرویس", callback_data=f"FIXEDadd_{plan}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_change_prices"))
    bot.edit_message_text(f"لیست حجم‌های فعلی پلن {plan}:\nجهت تغییر قیمت یا حذف انتخاب کنید یا حجم جدید بسازید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("FIXEDadd_"))
def FIXED_adm_addp_start(c):
    plan = c.data.replace("FIXEDadd_", "")
    user_states[ADMIN_ID] = {"state": "FIXED_ADD_VOLUME_NAME", "plan": plan}
    bot.send_message(ADMIN_ID, f"نام حجم جدید برای پلن {plan} را وارد کنید (مثلا: 10G یا 50G):")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "FIXED_ADD_VOLUME_NAME", content_types=['text'])
def FIXED_adm_addp_save_name(m):
    vol_name = m.text.strip().upper()
    plan = user_states[ADMIN_ID]["plan"]
    user_states[ADMIN_ID] = {"state": "FIXED_SETTING_PRICE", "plan": plan, "vol": vol_name}
    bot.send_message(ADMIN_ID, f"حجم {vol_name} ایجاد شد. حالا قیمت آن را به عدد (تومان) وارد کنید:")

@bot.callback_query_handler(func=lambda c: c.data.startswith("FIXEDdel_"))
def FIXED_adm_delp_val(c):
    data_str = c.data.replace("FIXEDdel_", "")
    plan, vol = data_str.split(":::")
    p_key = f"PRICES_{plan}"
    current_prices = get_db_prices(p_key)
    if vol in current_prices:
        del current_prices[vol]
    settings_col.update_one({"key": p_key}, {"$set": {"value": current_prices}})
    bot.answer_callback_query(c.id, f"حجم {vol} با موفقیت حذف شد", show_alert=True)
    c.data = f"setp_{plan}"
    FIXED_adm_setp_plan(c)

@bot.callback_query_handler(func=lambda c: c.data.startswith("FIXEDedit_"))
def FIXED_adm_editp_val(c):
    data_str = c.data.replace("FIXEDedit_", "")
    plan, vol = data_str.split(":::")
    user_states[ADMIN_ID] = {"state": "FIXED_SETTING_PRICE", "plan": plan, "vol": vol}
    bot.send_message(ADMIN_ID, f"قیمت جدید برای {plan} {vol} را به عدد (تومان) وارد کنید:")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "FIXED_SETTING_PRICE", content_types=['text'])
def FIXED_save_new_price(m):
    if not m.text.isdigit(): 
        bot.send_message(ADMIN_ID, "❌ فقط عدد انگلیسی بدون فاصله یا کاما بفرستید:")
        return
    new_p = int(m.text)
    data = user_states[ADMIN_ID]
    p_key = f"PRICES_{data['plan']}"
    
    current_prices = get_db_prices(p_key)
    current_prices[data['vol']] = new_p
    settings_col.update_one({"key": p_key}, {"$set": {"value": current_prices}})
    
    bot.send_message(ADMIN_ID, f"✅ تنظیمات در دیتابیس ذخیره شد.\n{data['plan']} حجم {data['vol']} به قیمت {format_p(new_p)} تومان تغییر یافت.")
    user_states[ADMIN_ID] = None


# ====================================================================================
#  🔴 پیاده‌سازی ۱۰۰٪ اختصاصی قابلیت‌های درخواستی جدید در فاز نهایی (تزریق بدون تداخل)
# ====================================================================================

# ۱. بخش وضعیت سرورها (سمت کاربر)
@bot.callback_query_handler(func=lambda c: c.data == "server_status")
def view_server_status(c):
    status_data = settings_col.find_one({"key": "global_server_status"})
    txt = status_data["value"] if status_data else "🟢 تمامی سرورها پرسرعت و متصل هستند."
    bot.edit_message_text(f"⚡ آخرین وضعیت سرورها:\n\n{txt}", c.message.chat.id, c.message.message_id, reply_markup=back_kb())

# ۲. مدیریت وضعیت سرورها (سمت ادمین)
@bot.callback_query_handler(func=lambda c: c.data == "adm_update_servers")
def adm_update_servers(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state": "WAIT_SERVER_STATUS_TEXT"}
    bot.send_message(ADMIN_ID, "✍️ متن جدید وضعیت سرورها را بنویسید (مثلا: نپستر متصل 🔥 | وایرگارد عالی 🟢):")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "WAIT_SERVER_STATUS_TEXT")
def save_server_status_text(m):
    txt = m.text.strip()
    settings_col.update_one({"key": "global_server_status"}, {"$set": {"value": txt}}, upsert=True)
    bot.send_message(ADMIN_ID, "✅ وضعیت جدید سرورها با موفقیت در دیتابیس ذخیره شد.")
    user_states[ADMIN_ID] = None

# ۳. نمایش آرشیو اطلاعیه‌ها (سمت کاربر)
@bot.callback_query_handler(func=lambda c: c.data == "view_announcements")
def view_announcements(c):
    ann_data = settings_col.find_one({"key": "announcements_archive"})
    txt = ann_data["value"] if ann_data else "💡 اطلاعیه جدیدی ثبت نشده است."
    bot.edit_message_text(f"📋 تاریخچه اطلاعیه‌های اخیر ربات:\n\n{txt}", c.message.chat.id, c.message.message_id, reply_markup=back_kb())

# ۴. ارسال اطلاعیه هوشمند ۱ دقیقه‌ای با حذف خودکار (سمت ادمین)
@bot.callback_query_handler(func=lambda c: c.data == "adm_smart_announcement")
def adm_smart_announcement(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state": "WAIT_SMART_ANN"}
    bot.send_message(ADMIN_ID, "📢 متن اطلاعیه هوشمند را بنویسید. این پیام برای همه ارسال شده و پس از ۱ دقیقه به طور خودکار پاک می‌شود:")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "WAIT_SMART_ANN")
def do_smart_announcement(m):
    ann_text = m.text.strip()
    user_states[ADMIN_ID] = None
    
    # ذخیره در آرشیو دایمی دیتابیس برای دکمه اطلاعیه ها
    settings_col.update_one({"key": "announcements_archive"}, {"$set": {"value": f"⏱ [{now_str()}]\n📢 {ann_text}"}}, upsert=True)
    
    users = list(users_col.find({}, {"user_id": 1}))
    bot.send_message(ADMIN_ID, f"🚀 فرآیند ارسال اطلاعیه به {len(users)} کاربر آغاز شد. حذف خودکار پس از ۶۰ ثانیه فعال است...")
    
    def send_and_burn(u_id, text_to_send):
        try:
            sent_msg = bot.send_message(u_id, f"🚨 **اطلاعیه موقت (حذف پس از ۱ دقیقه):**\n\n{text_to_send}", parse_mode="Markdown")
            # ایجاد ترد مستقل زمانی برای حذف دقیق پیام راس ۱ دقیقه
            def burn_timer():
                time.sleep(60)
                try:
                    bot.delete_message(u_id, sent_msg.message_id)
                except:
                    pass
            Thread(target=burn_timer).start()
        except:
            pass

    for u in users:
        Thread(target=send_and_burn, args=(u['user_id'], ann_text)).start()
        
    bot.send_message(ADMIN_ID, "✅ اطلاعیه‌ها ارسال شدند و زمان‌بندی حذف خودکار فعال گردید.")

# ۵. آمار کاربران فعال (امروز، هفته، ماه) در پنل مدیریت
@bot.callback_query_handler(func=lambda c: c.data == "adm_active_stats")
def adm_active_stats(c):
    if c.from_user.id != ADMIN_ID: return
    now = datetime.now()
    
    today_count = users_col.count_documents({"last_activity": {"$gte": now - timedelta(days=1)}})
    week_count = users_col.count_documents({"last_activity": {"$gte": now - timedelta(days=7)}})
    month_count = users_col.count_documents({"last_activity": {"$gte": now - timedelta(days=30)}})
    
    txt = f"📊 آمار فعالیت کاربران بر اساس دیتابیس:\n\n"
    txt += f"🟢 تعداد فعالان ۲۴ ساعت گذشته: {today_count} کاربر\n"
    txt += f"🟡 تعداد فعالان ۷ روز گذشته: {week_count} کاربر\n"
    txt += f"🔵 تعداد فعالان ۳۰ روز گذشته: {month_count} کاربر\n"
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_back"))
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=kb)

# ۶. بخش آموزش اتصال (سمت کاربر)
@bot.callback_query_handler(func=lambda c: c.data == "user_learn_menu")
def user_learn_menu(c):
    if not get_setting('learn_status'):
        bot.answer_callback_query(c.id, "⚠️ بخش آموزش اتصال در حال حاضر توسط ادمین خاموش شده است.", show_alert=True)
        return
        
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🤖 آموزش اندروید", callback_data="learn_os_android"), types.InlineKeyboardButton("🍏 آموزش آیفون (iOS)", callback_data="learn_os_ios"))
    kb.add(types.InlineKeyboardButton("💻 آموزش ویندوز", callback_data="learn_os_windows"), types.InlineKeyboardButton("🍏 آموزش مک‌بوک", callback_data="learn_os_mac"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    bot.edit_message_text("📱 لطفاً سیستم‌عامل خود را جهت دریافت آموزش اتصال انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("learn_os_"))
def show_os_learn_content(c):
    os_name = c.data.replace("learn_os_", "")
    data = settings_col.find_one({"key": f"learn_{os_name}"})
    
    if not data:
        bot.answer_callback_query(c.id, "💡 هنوز آموزشی برای این سیستم عامل ثبت نشده است.", show_alert=True)
        return
        
    val = data["value"]
    # بازگشت به منوی اصلی آموزش
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به لیست سیستم‌عامل‌ها", callback_data="user_learn_menu"))
    
    # تشخیص داینامیک رسانه یا متن بودن فیلد ثبت شده آموزش
    if isinstance(val, dict) and "file_id" in val:
        bot.delete_message(c.message.chat.id, c.message.message_id)
        if val["type"] == "photo":
            bot.send_photo(c.message.chat.id, val["file_id"], caption=val.get("caption", ""), reply_markup=kb)
        elif val["type"] == "document":
            bot.send_document(c.message.chat.id, val["file_id"], caption=val.get("caption", ""), reply_markup=kb)
        elif val["type"] == "video":
            bot.send_video(c.message.chat.id, val["file_id"], caption=val.get("caption", ""), reply_markup=kb)
    else:
        bot.edit_message_text(str(val), c.message.chat.id, c.message.message_id, reply_markup=kb)

# ۷. مدیریت بخش آموزش اتصال (سمت ادمین)
@bot.callback_query_handler(func=lambda c: c.data == "adm_manage_learn")
def adm_manage_learn(c):
    if c.from_user.id != ADMIN_ID: return
    l_status = "✅ روشن" if get_setting('learn_status') else "❌ خاموش"
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"وضعیت کل بخش آموزش: {l_status}", callback_data="tog_learn_status"))
    kb.add(types.InlineKeyboardButton("✏️ تنظیم آموزش اندروید", callback_data="adm_edit_os_android"), types.InlineKeyboardButton("✏️ تنظیم آموزش آیفون", callback_data="adm_edit_os_ios"))
    kb.add(types.InlineKeyboardButton("✏️ تنظیم آموزش ویندوز", callback_data="adm_edit_os_windows"), types.InlineKeyboardButton("✏️ تنظیم آموزش مک", callback_data="adm_edit_os_mac"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_back"))
    bot.edit_message_text("⚙️ مدیریت بخش آموزش اتصال ربات:\nشما میتوانید کل این بخش را خاموش/روشن کنید یا آموزش هر سیستم عامل را به صورت متن یا فایل آپدیت کنید.", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_edit_os_"))
def adm_edit_os_start(c):
    if c.from_user.id != ADMIN_ID: return
    target_os = c.data.replace("adm_edit_os_", "")
    user_states[ADMIN_ID] = {"state": "WAIT_OS_LEARN_DATA", "os": target_os}
    bot.send_message(ADMIN_ID, f"📥 آموزش جدید برای سیستم عامل [{target_os}] را بفرستید.\nشما می‌توانید متن خالی بفرستید، عکس آپلود کنید و یا فایل نصبی برنامه را بفرستید تا ذخیره شود:")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "WAIT_OS_LEARN_DATA", content_types=['text', 'photo', 'document', 'video'])
def adm_edit_os_save(m):
    target_os = user_states[ADMIN_ID]["os"]
    user_states[ADMIN_ID] = None
    
    if m.content_type == 'text':
        db_val = m.text.strip()
    elif m.content_type == 'photo':
        db_val = {"type": "photo", "file_id": m.photo[-1].file_id, "caption": m.caption or ""}
    elif m.content_type == 'document':
        db_val = {"type": "document", "file_id": m.document.file_id, "caption": m.caption or ""}
    elif m.content_type == 'video':
        db_val = {"type": "video", "file_id": m.video.file_id, "caption": m.caption or ""}
        
    settings_col.update_one({"key": f"learn_{target_os}"}, {"$set": {"value": db_val}}, upsert=True)
    bot.send_message(ADMIN_ID, f"✅ آموزش سیستم عامل {target_os} با موفقیت در دیتابیس ابری ثبت و بروزرسانی شد.")

# --------------- WEB ---------------

@app.route('/')
def home(): return "OK - MongoDB Active"

def run(): app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling(skip_pending=True)
