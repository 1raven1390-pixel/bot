import telebot
from telebot import types
from pymongo import MongoClient
import os
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8521801987
CHANNEL_ID = "@rafe_filter_A"
GROUP_ID = "@GP_config_A"
SUPPORT_ID = "@Amir_confing_meli"

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# ---------------- DB ----------------

MONGO_URI = "mongodb+srv://1raven1390_db_user:iOlmB4Azr3SrrkVZ@bot.te88ask.mongodb.net/?retryWrites=true&w=majority&appName=Bot"
client = MongoClient(MONGO_URI)
db = client['telegram_bot']

users_col = db['users']
orders_col = db['orders']
settings_col = db['settings']
fjoin_col = db['force_join']

for s in ['sale_month', 'sale_vip', 'sale_napsterv', 'sale_napsterv_unlim', 'sale_wireguard', 'charge_status', 'ref_status']:
    if not settings_col.find_one({"key": s}):
        settings_col.insert_one({"key": s, "value": 1})

if fjoin_col.count_documents({}) == 0:
    fjoin_col.insert_one({"type": "channel", "chat_id": CHANNEL_ID})
    fjoin_col.insert_one({"type": "group", "chat_id": GROUP_ID})

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
    return res['value'] if res else default_prices.get(p_type, {})

# --------------- STATE ---------------
user_states = {}

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
    kb.add(types.InlineKeyboardButton("🛒 خرید سرور", callback_data="buy"), types.InlineKeyboardButton("📊 تعرفه", callback_data="price"))
    kb.add(types.InlineKeyboardButton("💰 افزایش موجودی", callback_data="charge"), types.InlineKeyboardButton("👤 حساب کاربری", callback_data="account"))
    kb.add(types.InlineKeyboardButton("👥 زیرمجموعه‌گیری", callback_data="referral"), types.InlineKeyboardButton("📞 پشتیبانی", callback_data="support"))
    kb.add(types.InlineKeyboardButton("🖥 وضعیت سرورها", callback_data="server_status"), types.InlineKeyboardButton("📢 اطلاعیه‌ها", callback_data="announcements"))
    kb.add(types.InlineKeyboardButton("📚 آموزش اتصال", callback_data="tutorial"))
    return kb

def back_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
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
            "invited_count": 0, "is_banned": False,
            "last_activity": datetime.now()
        })
        if ref_by and get_setting('ref_status'):
            inviter = users_col.find_one({"user_id": ref_by})
            if inviter and inviter.get('invited_count', 0) < 4:
                users_col.update_one({"user_id": ref_by}, {"$inc": {"balance": 5000, "invited_count": 1}})
                bot.send_message(ref_by, "🎉 تبریک! یک کاربر با لینک شما عضو شد و ۵,۰۰۰ تومان به موجودی شما اضافه شد.")
    else:
        users_col.update_one({"user_id": uid}, {"$set": {"last_activity": datetime.now()}})

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
    kb.add(types.InlineKeyboardButton("🖥 وضعیت سرورها", callback_data="adm_server_status"))
    kb.add(types.InlineKeyboardButton("📢 اطلاعیه هوشمند", callback_data="adm_smart_announce"))
    kb.add(types.InlineKeyboardButton("📊 آمار کاربران فعال", callback_data="adm_active_stats"))
    kb.add(types.InlineKeyboardButton("📚 مدیریت آموزش اتصال", callback_data="adm_tutorial_mgr"))
    bot.send_message(m.chat.id, f"👑 پنل ادمین \n\n👤 تعداد کاربران: {users_count}\n💰 مجموع موجودی: {format_p(total)}\n📦 سفارشات باز: {pending}", reply_markup=kb)

# تابع کمکی برای نمایش پنل ادمین از طریق callback
def show_admin_panel(chat_id):
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
    kb.add(types.InlineKeyboardButton("🖥 وضعیت سرورها", callback_data="adm_server_status"))
    kb.add(types.InlineKeyboardButton("📢 اطلاعیه هوشمند", callback_data="adm_smart_announce"))
    kb.add(types.InlineKeyboardButton("📊 آمار کاربران فعال", callback_data="adm_active_stats"))
    kb.add(types.InlineKeyboardButton("📚 مدیریت آموزش اتصال", callback_data="adm_tutorial_mgr"))
    bot.send_message(chat_id, f"👑 پنل ادمین \n\n👤 تعداد کاربران: {users_count}\n💰 مجموع موجودی: {format_p(total)}\n📦 سفارشات باز: {pending}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join(c):
    if is_member(c.from_user.id):
        bot.edit_message_text("✅ تایید شد", c.message.chat.id, c.message.message_id, reply_markup=main_menu())
    else: bot.answer_callback_query(c.id, "هنوز عضو کانال یا گروه نشدی", show_alert=True)

# --------------- ADMIN SETTINGS ---------------

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

# FIX: دکمه بازگشت پنل ادمین - حالا پیام جدید می‌فرسته
@bot.callback_query_handler(func=lambda c: c.data == "admin_back")
def admin_back(c):
    if c.from_user.id != ADMIN_ID: return
    show_admin_panel(c.message.chat.id)

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
    user_states[m.from_user.id] = {"state": "WAIT_RECEIPT", "amount": amt, "card": m.text.strip(), "expire_at": expire_at}
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
    # ذخیره order_id در دیتابیس برای جلوگیری از تایید/رد چندباره
    order_res = orders_col.insert_one({
        "user_id": m.from_user.id,
        "type": "charge",
        "amount": data['amount'],
        "card": data['card'],
        "status": "pending",
        "created_at": now_str()
    })
    charge_order_id = str(order_res.inserted_id)

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ تایید", callback_data=f"ok_{m.from_user.id}_{data['amount']}_{charge_order_id}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"no_{m.from_user.id}_{charge_order_id}")
    )
    bot.send_photo(ADMIN_ID, m.photo[-1].file_id,
        caption=f"💰 درخواست شارژ\n\n👤 کاربر: {m.from_user.id}\n💵 مبلغ: {format_p(data['amount'])}\n💳 کارت مبدا: {data['card']}",
        reply_markup=kb)
    bot.send_message(m.chat.id, "✅ رسید برای ادمین ارسال شد، لطفاً منتظر بمانید 🙏")
    user_states[m.from_user.id] = None

# FIX: تایید شارژ - جلوگیری از تایید چندباره با بررسی وضعیت در دیتابیس
@bot.callback_query_handler(func=lambda c: c.data.startswith("ok_"))
def ok(c):
    from bson.objectid import ObjectId
    parts = c.data.split("_")
    uid = int(parts[1])
    amt = int(parts[2])
    charge_order_id = parts[3] if len(parts) > 3 else None

    if charge_order_id:
        order = orders_col.find_one({"_id": ObjectId(charge_order_id)})
        if not order or order.get("status") != "pending":
            bot.answer_callback_query(c.id, "⚠️ این درخواست قبلاً پردازش شده است.", show_alert=True)
            # ویرایش کپشن برای نمایش وضعیت
            try:
                current_caption = c.message.caption or ""
                bot.edit_message_caption(
                    caption=current_caption + "\n\n✅ قبلاً تایید شده بود",
                    chat_id=c.message.chat.id,
                    message_id=c.message.message_id
                )
            except: pass
            return
        orders_col.update_one({"_id": ObjectId(charge_order_id)}, {"$set": {"status": "approved"}})

    users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt, "success_payments": 1}})
    bot.send_message(uid, f"✅ مبلغ {format_p(amt)} تومان به حساب شما اضافه شد")
    bot.answer_callback_query(c.id, "✅ تایید شد")
    # ویرایش کپشن پیام ادمین برای نشان دادن وضعیت
    try:
        current_caption = c.message.caption or ""
        bot.edit_message_caption(
            caption=current_caption + "\n\n✅ رسید با موفقیت تایید شد",
            chat_id=c.message.chat.id,
            message_id=c.message.message_id
        )
    except: pass

# FIX: رد شارژ - جلوگیری از رد و اخطار چندباره
@bot.callback_query_handler(func=lambda c: c.data.startswith("no_"))
def no(c):
    from bson.objectid import ObjectId
    parts = c.data.split("_")
    uid = int(parts[1])
    charge_order_id = parts[2] if len(parts) > 2 else None

    if charge_order_id:
        order = orders_col.find_one({"_id": ObjectId(charge_order_id)})
        if not order or order.get("status") != "pending":
            bot.answer_callback_query(c.id, "⚠️ این درخواست قبلاً پردازش شده است.", show_alert=True)
            try:
                current_caption = c.message.caption or ""
                bot.edit_message_caption(
                    caption=current_caption + "\n\n❌ قبلاً رد شده بود",
                    chat_id=c.message.chat.id,
                    message_id=c.message.message_id
                )
            except: pass
            return
        orders_col.update_one({"_id": ObjectId(charge_order_id)}, {"$set": {"status": "rejected"}})

    users_col.update_one({"user_id": uid}, {"$inc": {"warnings": 1}})
    u_data = users_col.find_one({"user_id": uid})
    warns = u_data.get("warnings", 0)
    if warns >= 3:
        users_col.update_one({"user_id": uid}, {"$set": {"is_banned": True}})
        bot.send_message(uid, "❌ شما ۳ اخطار دریافت کردید و دسترسی شما به ربات برای همیشه مسدود شد.")
    else:
        bot.send_message(uid, f"❌ رسید شما رد شد و اخطار دریافت کردید. (تعداد اخطار: {warns} از ۳)")

    bot.answer_callback_query(c.id, "❌ رد شد")
    # ویرایش کپشن پیام ادمین
    try:
        current_caption = c.message.caption or ""
        bot.edit_message_caption(
            caption=current_caption + f"\n\n❌ رسید با موفقیت رد شد (اخطار کاربر: {warns} از ۳)",
            chat_id=c.message.chat.id,
            message_id=c.message.message_id
        )
    except: pass

# --------------- PRICE ---------------

@bot.callback_query_handler(func=lambda c: c.data == "price")
def price_menu(c):
    uid = c.from_user.id
    kb = types.InlineKeyboardMarkup()
    if get_setting('sale_month'):
        kb.add(types.InlineKeyboardButton("📅 ۱ ماهه", callback_data="price_month"))
    if get_setting('sale_vip'):
        kb.add(types.InlineKeyboardButton("♾ بدون محدودیت زمانی + ساب + VIP", callback_data="price_vip"))
    if get_setting('sale_napsterv'):
        kb.add(types.InlineKeyboardButton("🔮 سرور نپستر", callback_data="price_napsterv"))
    if get_setting('sale_napsterv_unlim'):
        kb.add(types.InlineKeyboardButton("🌀 سرور نامحدود نپستر", callback_data="price_napsterv_unlim"))
    if get_setting('sale_wireguard'):
        kb.add(types.InlineKeyboardButton("🔴 سرور وایرگارد", callback_data="price_wireguard"))
    # FIX: سرور اختصاصی VIP حذف شد از اینجا - فقط در صورت فعال بودن sale_vip و VIP بودن کاربر نشون داده میشه
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

@bot.callback_query_handler(func=lambda c: c.data == "buy")
def buy(c):
    kb = types.InlineKeyboardMarkup()
    if get_setting('sale_month'):
        kb.add(types.InlineKeyboardButton("📅 ۱ ماهه", callback_data="buy_month"))
    if get_setting('sale_vip'):
        kb.add(types.InlineKeyboardButton("♾ بدون محدودیت + VIP", callback_data="buy_vip"))
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
    bot.send_message(ADMIN_ID, "📤 کانفیگ رو ارسال کن:\n(می‌توانید متن، فایل .conf یا هر نوع فایلی ارسال کنید)")

@bot.message_handler(content_types=['document'], func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "SEND_CONFIG")
def send_config_file_to_user(m):
    from bson.objectid import ObjectId
    data = user_states.get(ADMIN_ID)
    if not data: return
    order_id = data["order_id"]
    user_id = data["user_id"]
    caption = m.caption or "✅ فایل کانفیگ شما آماده است"
    bot.send_document(user_id, m.document.file_id, caption=f"✅ کانفیگ سفارش شما:\n\n{caption}")
    orders_col.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "done"}})
    bot.send_message(ADMIN_ID, f"✅ فایل کانفیگ برای سفارش {order_id} ارسال شد")
    user_states[ADMIN_ID] = None

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "SEND_CONFIG")
def send_config_to_user(m):
    from bson.objectid import ObjectId
    if m.text == "/admin":
        user_states[ADMIN_ID] = None
        admin_panel(m); return
    data = user_states.get(ADMIN_ID)
    order_id = data["order_id"]; user_id = data["user_id"]
    bot.send_message(user_id, f"✅ کانفیگ شما:\n\n{m.text}")
    orders_col.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "done"}})
    bot.send_message(ADMIN_ID, f"✅ کانفیگ برای سفارش {order_id} ارسال شد")
    user_states[ADMIN_ID] = None

# --------------- ACCOUNT ---------------

@bot.callback_query_handler(func=lambda c: c.data == "account")
def account(c):
    d = users_col.find_one({"user_id": c.from_user.id})
    username = f"@{c.from_user.username}" if c.from_user.username else "❌ ندارد"
    status = "🚫 مسدود" if d.get("is_banned") or d.get("warnings", 0) >= 3 else "✅ فعال"
    level = get_user_level(d.get("success_payments", 0))
    text = f"📊 اطلاعات حساب کاربری شما در ربات: \n\n🔢 آیدی عددی : {c.from_user.id}\n🔆 یوزرنیم : {username}\n📱 وضعیت : {status}\n🏅 سطح کاربری : {level}\n💰 موجودی : {format_p(d['balance'])} تومان\n🏦 پرداخت های موفق : {d['success_payments']} عدد\n🛍 تعداد سرویس ها : {d['configs_count']} عدد\n⚠️ تعداد اخطار ها : {d['warnings']} عدد\n⏰ تاریخ عضویت : {d['join_date']}\n\n🤖 | @rafe_filter_GB_bot"
    bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

# --------------- SUPPORT - FIX: مستقیم به پیوی ادمین ---------------

@bot.callback_query_handler(func=lambda c: c.data == "support")
def support(c):
    uid = c.from_user.id
    user = users_col.find_one({"user_id": uid})
    username_display = f"@{c.from_user.username}" if c.from_user.username else "ندارد"
    # ارسال اطلاعات کاربر به ادمین
    try:
        bot.send_message(ADMIN_ID,
            f"📞 درخواست پشتیبانی\n\n"
            f"👤 نام: {c.from_user.first_name or ''}\n"
            f"🔆 یوزرنیم: {username_display}\n"
            f"🔢 آیدی: {uid}\n"
            f"💰 موجودی: {format_p(user['balance'] if user else 0)} تومان")
    except: pass
    # FIX: دکمه مستقیم برای باز کردن پیوی ادمین
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💬 ارتباط با پشتیبانی", url=f"https://t.me/{SUPPORT_ID.replace('@', '')}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    bot.edit_message_text("📞 برای ارتباط با پشتیبانی روی دکمه زیر کلیک کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

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

# --------------- مدیریت قیمت‌ها ---------------

@bot.callback_query_handler(func=lambda c: c.data == "adm_change_prices")
def adm_change_prices(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📅 قیمت ۱ ماهه", callback_data="FIXEDsetp_MONTH"),
           types.InlineKeyboardButton("♾ قیمت VIP", callback_data="FIXEDsetp_VIP"))
    kb.add(types.InlineKeyboardButton("🔮 قیمت نپستر", callback_data="FIXEDsetp_NAPSTERV"),
           types.InlineKeyboardButton("🌀 قیمت نپستر نامحدود", callback_data="FIXEDsetp_NAPSTERV_UNLIM"))
    kb.add(types.InlineKeyboardButton("🔴 قیمت وایرگارد", callback_data="FIXEDsetp_WIREGUARD"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back"))
    bot.edit_message_text("⚙️ مدیریت تعرفه‌ها و حجم سرورها:\nکدام دسته‌بندی را مدیریت می‌کنید؟", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("FIXEDsetp_"))
def FIXED_adm_setp_plan(c):
    plan = c.data.replace("FIXEDsetp_", "")
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
    c.data = f"FIXEDsetp_{plan}"
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

# --------------- مدیریت عضویت اجباری ---------------

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

# =====================================================================
# ویژگی‌های اضافه‌شده
# =====================================================================

announcements_col = db['announcements']
tutorial_col = db['tutorials']

for s_new in ['tutorial_status']:
    if not settings_col.find_one({"key": s_new}):
        settings_col.insert_one({"key": s_new, "value": 1})

if not settings_col.find_one({"key": "server_status_text"}):
    settings_col.insert_one({"key": "server_status_text", "value": "🟢 همه سرورها آنلاین هستند."})

# ==================== FIX: ساختار جدید آموزش‌ها با سه سرور برای هر OS ====================
# مقداردهی اولیه آموزش‌های پیش‌فرض با ساختار جدید
default_tutorials = [
    {"os": "android", "label": "📱 اندروید", "type": "text"},
    {"os": "ios", "label": "🍎 iOS (آیفون)", "type": "text"},
    {"os": "windows", "label": "💻 ویندوز", "type": "text"},
    {"os": "mac", "label": "🖥 مک", "type": "text"},
]
for tut in default_tutorials:
    if not tutorial_col.find_one({"os": tut["os"]}):
        tutorial_col.insert_one(tut)

# مقداردهی اولیه محتوای سه سرور برای هر OS (اگر وجود نداشت)
server_types = ["v2ray", "npv", "wireguard"]
server_labels = {"v2ray": "🔵 سرور V2ray", "npv": "🟣 سرور Npv", "wireguard": "🔴 سرور Wireguard"}
default_os_list = ["android", "ios", "windows", "mac"]
for os_key in default_os_list:
    for srv in server_types:
        key = f"tut_content_{os_key}_{srv}"
        if not settings_col.find_one({"key": key}):
            settings_col.insert_one({
                "key": key,
                "value": {
                    "type": "text",
                    "content": f"آموزش اتصال {srv} برای {os_key} هنوز تنظیم نشده است.",
                    "file_id": None
                }
            })

# ==================== ویژگی ۱: سیستم ضد اسپم ====================
import time
spam_tracker = {}
spam_muted = {}

def check_spam(uid):
    now_ts = time.time()
    if uid in spam_muted:
        if now_ts < spam_muted[uid]:
            return True
        else:
            del spam_muted[uid]
            spam_tracker[uid] = []
    if uid not in spam_tracker:
        spam_tracker[uid] = []
    spam_tracker[uid] = [t for t in spam_tracker[uid] if now_ts - t < 5]
    spam_tracker[uid].append(now_ts)
    if len(spam_tracker[uid]) > 4:
        spam_muted[uid] = now_ts + 30
        spam_tracker[uid] = []
        return True
    return False

_orig_process_new_updates = bot.process_new_updates

def patched_process_new_updates(updates):
    for update in updates:
        if update.callback_query:
            uid = update.callback_query.from_user.id
            if uid != ADMIN_ID and check_spam(uid):
                remaining = int(spam_muted.get(uid, time.time()) - time.time())
                if remaining < 0: remaining = 0
                try:
                    bot.answer_callback_query(update.callback_query.id, f"⛔ اسپم شناسایی شد!\nلطفاً {remaining} ثانیه صبر کنید.", show_alert=True)
                except: pass
                updates = [u for u in updates if u != update]
    _orig_process_new_updates(updates)

bot.process_new_updates = patched_process_new_updates
# ================================================================

# ==================== ویژگی ۲: وضعیت سرورها ====================
@bot.callback_query_handler(func=lambda c: c.data == "server_status")
def server_status(c):
    res = settings_col.find_one({"key": "server_status_text"})
    status_text = res['value'] if res else "وضعیت سرورها در دسترس نیست."
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔄 بروزرسانی", callback_data="server_status"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    bot.edit_message_text(f"🖥 وضعیت سرورها:\n\n{status_text}", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "adm_server_status")
def adm_server_status(c):
    if c.from_user.id != ADMIN_ID: return
    res = settings_col.find_one({"key": "server_status_text"})
    current = res['value'] if res else ""
    user_states[ADMIN_ID] = {"state": "ADM_SET_SERVER_STATUS"}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back"))
    bot.edit_message_text(f"🖥 وضعیت فعلی سرورها:\n\n{current}\n\n✏️ متن جدید را ارسال کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "ADM_SET_SERVER_STATUS")
def save_server_status(m):
    settings_col.update_one({"key": "server_status_text"}, {"$set": {"value": m.text.strip()}})
    bot.send_message(ADMIN_ID, "✅ وضعیت سرورها بروزرسانی شد.")
    user_states[ADMIN_ID] = None
# ================================================================

# ==================== ویژگی ۳: اطلاعیه هوشمند ====================
@bot.callback_query_handler(func=lambda c: c.data == "announcements")
def announcements_list(c):
    items = list(announcements_col.find({}).sort("_id", -1).limit(10))
    if not items:
        bot.edit_message_text("📢 اطلاعیه‌ای موجود نیست.", c.message.chat.id, c.message.message_id, reply_markup=back_kb())
        return
    txt = "📢 آخرین اطلاعیه‌ها:\n\n"
    for item in items:
        txt += f"🔹 {item.get('date','')}\n{item.get('text','')}\n\n"
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

@bot.callback_query_handler(func=lambda c: c.data == "adm_smart_announce")
def adm_smart_announce(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state": "ADM_SMART_ANNOUNCE"}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back"))
    bot.edit_message_text("📢 اطلاعیه هوشمند:\n\nمتن اطلاعیه را ارسال کنید.\nپیام پس از ۶۰ ثانیه از چت کاربران حذف خواهد شد و در تاریخچه ذخیره می‌شود.", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "ADM_SMART_ANNOUNCE")
def do_smart_announce(m):
    text = m.text
    date_str = now_str()
    announcements_col.insert_one({"text": text, "date": date_str})
    users = list(users_col.find({}, {"user_id": 1}))
    sent_messages = []
    ok = 0
    for u in users:
        try:
            sent = bot.send_message(u['user_id'], f"📢 اطلاعیه مهم:\n\n{text}\n\n⏱ این پیام پس از ۶۰ ثانیه حذف می‌شود")
            sent_messages.append({"uid": u['user_id'], "mid": sent.message_id})
            ok += 1
        except: pass
    user_states[ADMIN_ID] = None
    bot.send_message(ADMIN_ID, f"✅ اطلاعیه برای {ok} نفر ارسال شد. پس از ۶۰ ثانیه حذف می‌شود.")

    def delete_after_60(messages):
        time.sleep(60)
        for item in messages:
            try:
                bot.delete_message(item['uid'], item['mid'])
            except: pass

    Thread(target=delete_after_60, args=(sent_messages,), daemon=True).start()
# =============================================================================

# ==================== ویژگی ۴: سطح‌بندی کاربران ====================
def get_user_level(success_payments):
    if success_payments >= 15:
        return "💎 VIP"
    elif success_payments >= 7:
        return "🥇 طلایی"
    elif success_payments >= 4:
        return "🥈 نقره‌ای"
    else:
        return "🥉 برنزی"

# FIX: حذف callback سرور اختصاصی VIP از price_menu - نگه داشتیم handler رو در صورت نیاز
@bot.callback_query_handler(func=lambda c: c.data == "price_vip_exclusive")
def price_vip_exclusive(c):
    uid = c.from_user.id
    user = users_col.find_one({"user_id": uid})
    if not user or get_user_level(user.get("success_payments", 0)) != "💎 VIP":
        bot.answer_callback_query(c.id, "❌ این بخش فقط برای کاربران VIP قابل دسترس است.", show_alert=True)
        return
    txt = "💎 سرور اختصاصی VIP\n\nبرای دریافت اطلاعات سرور اختصاصی VIP با پشتیبانی تماس بگیرید."
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📞 تماس با پشتیبانی", url=f"https://t.me/{SUPPORT_ID.replace('@','')}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="price"))
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=kb)
# ===========================================================================

# ==================== ویژگی ۵: آمار کاربران فعال ====================
@bot.callback_query_handler(func=lambda c: c.data == "adm_active_stats")
def adm_active_stats(c):
    if c.from_user.id != ADMIN_ID: return
    now_dt = datetime.now()
    today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now_dt - timedelta(days=7)
    month_start = now_dt - timedelta(days=30)
    today_count = users_col.count_documents({"last_activity": {"$gte": today_start}})
    week_count = users_col.count_documents({"last_activity": {"$gte": week_start}})
    month_count = users_col.count_documents({"last_activity": {"$gte": month_start}})
    total_count = users_col.count_documents({})
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"📅 امروز: {today_count} نفر", callback_data="adm_active_stats"))
    kb.add(types.InlineKeyboardButton(f"📆 هفته گذشته: {week_count} نفر", callback_data="adm_active_stats"))
    kb.add(types.InlineKeyboardButton(f"🗓 ماه گذشته: {month_count} نفر", callback_data="adm_active_stats"))
    kb.add(types.InlineKeyboardButton(f"👥 کل کاربران: {total_count} نفر", callback_data="adm_active_stats"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back"))
    bot.edit_message_text(
        f"📊 آمار کاربران فعال:\n\n"
        f"📅 امروز: {today_count} نفر\n"
        f"📆 هفته گذشته: {week_count} نفر\n"
        f"🗓 ماه گذشته: {month_count} نفر\n"
        f"👥 کل کاربران: {total_count} نفر",
        c.message.chat.id, c.message.message_id, reply_markup=kb
    )
# =====================================================================

# ==================== ویژگی ۶: آموزش اتصال با سه سرور و سیستم ثبت محتوا ====================

@bot.callback_query_handler(func=lambda c: c.data == "tutorial")
def tutorial_menu(c):
    res = settings_col.find_one({"key": "tutorial_status"})
    if res and res['value'] == 0:
        bot.answer_callback_query(c.id, "⚠️ بخش آموزش در حال حاضر توسط ادمین بسته شده است.", show_alert=True)
        return
    items = list(tutorial_col.find({}))
    kb = types.InlineKeyboardMarkup()
    for item in items:
        kb.add(types.InlineKeyboardButton(item['label'], callback_data=f"tut_os_{item['os']}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    bot.edit_message_text("📚 آموزش اتصال\n\nسیستم‌عامل خود را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

# FIX: نمایش سه دکمه سرور برای هر OS
@bot.callback_query_handler(func=lambda c: c.data.startswith("tut_os_"))
def tutorial_os_servers(c):
    os_key = c.data.replace("tut_os_", "")
    item = tutorial_col.find_one({"os": os_key})
    if not item:
        bot.answer_callback_query(c.id, "سیستم‌عامل یافت نشد", show_alert=True)
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔵 سرور V2ray", callback_data=f"tut_show_{os_key}_v2ray"))
    kb.add(types.InlineKeyboardButton("🟣 سرور Npv", callback_data=f"tut_show_{os_key}_npv"))
    kb.add(types.InlineKeyboardButton("🔴 سرور Wireguard", callback_data=f"tut_show_{os_key}_wireguard"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="tutorial"))
    bot.edit_message_text(f"📚 آموزش {item['label']}\n\nنوع سرور را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

# FIX: نمایش محتوای آموزش برای OS + نوع سرور مشخص
@bot.callback_query_handler(func=lambda c: c.data.startswith("tut_show_"))
def show_tutorial_content(c):
    parts = c.data.replace("tut_show_", "").rsplit("_", 1)
    if len(parts) != 2:
        bot.answer_callback_query(c.id, "خطا در دریافت اطلاعات", show_alert=True)
        return
    os_key, srv_type = parts
    content_key = f"tut_content_{os_key}_{srv_type}"
    content_data = settings_col.find_one({"key": content_key})
    os_item = tutorial_col.find_one({"os": os_key})
    os_label = os_item['label'] if os_item else os_key
    srv_label = {"v2ray": "🔵 V2ray", "npv": "🟣 Npv", "wireguard": "🔴 Wireguard"}.get(srv_type, srv_type)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"tut_os_{os_key}"))

    if not content_data or not content_data.get('value'):
        bot.edit_message_text(f"📚 {os_label} - {srv_label}\n\nآموزش هنوز تنظیم نشده است.", c.message.chat.id, c.message.message_id, reply_markup=kb)
        return

    val = content_data['value']
    content_type = val.get("type", "text")
    content_text = val.get("content", "")
    file_id = val.get("file_id")
    header = f"📚 آموزش {os_label} - {srv_label}\n\n"

    if content_type == "text":
        bot.edit_message_text(header + content_text, c.message.chat.id, c.message.message_id, reply_markup=kb)
    elif content_type == "photo" and file_id:
        bot.send_photo(c.from_user.id, file_id, caption=header + content_text, reply_markup=kb)
    elif content_type == "video" and file_id:
        bot.send_video(c.from_user.id, file_id, caption=header + content_text, reply_markup=kb)
    elif content_type == "document" and file_id:
        bot.send_document(c.from_user.id, file_id, caption=header + content_text, reply_markup=kb)
    else:
        bot.edit_message_text(header + content_text, c.message.chat.id, c.message.message_id, reply_markup=kb)

# ==================== مدیریت آموزش‌ها توسط ادمین ====================

@bot.callback_query_handler(func=lambda c: c.data == "adm_tutorial_mgr")
def adm_tutorial_mgr(c):
    if c.from_user.id != ADMIN_ID: return
    res = settings_col.find_one({"key": "tutorial_status"})
    status = "✅ باز" if (res and res['value'] == 1) else "❌ بسته"
    items = list(tutorial_col.find({}))
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"بخش آموزش: {status}", callback_data="tog_tutorial_status_adm"))
    kb.add(types.InlineKeyboardButton("➕ افزودن سیستم‌عامل جدید", callback_data="tut_adm_add_os"))
    for item in items:
        kb.add(
            types.InlineKeyboardButton(f"✏️ {item['label']}", callback_data=f"tut_adm_manage_{item['os']}"),
            types.InlineKeyboardButton(f"🗑 حذف {item['label']}", callback_data=f"tut_adm_del_os_{item['os']}")
        )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back"))
    bot.edit_message_text("📚 مدیریت آموزش اتصال:", c.message.chat.id, c.message.message_id, reply_markup=kb)

# FIX: حذف سیستم‌عامل از پنل ادمین
@bot.callback_query_handler(func=lambda c: c.data.startswith("tut_adm_del_os_"))
def tut_adm_del_os(c):
    if c.from_user.id != ADMIN_ID: return
    os_key = c.data.replace("tut_adm_del_os_", "")
    item = tutorial_col.find_one({"os": os_key})
    if not item:
        bot.answer_callback_query(c.id, "یافت نشد", show_alert=True)
        return
    # حذف سیستم‌عامل از tutorial_col
    tutorial_col.delete_one({"os": os_key})
    # حذف محتوای سرورهای مرتبط
    for srv in ["v2ray", "npv", "wireguard"]:
        settings_col.delete_one({"key": f"tut_content_{os_key}_{srv}"})
    bot.answer_callback_query(c.id, f"✅ {item['label']} با موفقیت حذف شد", show_alert=True)
    adm_tutorial_mgr(c)

# FIX: مدیریت محتوای سه سرور برای هر OS
@bot.callback_query_handler(func=lambda c: c.data.startswith("tut_adm_manage_"))
def tut_adm_manage_os(c):
    if c.from_user.id != ADMIN_ID: return
    os_key = c.data.replace("tut_adm_manage_", "")
    item = tutorial_col.find_one({"os": os_key})
    if not item: return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔵 ثبت آموزش V2ray", callback_data=f"tut_adm_set_{os_key}_v2ray"))
    kb.add(types.InlineKeyboardButton("🟣 ثبت آموزش Npv", callback_data=f"tut_adm_set_{os_key}_npv"))
    kb.add(types.InlineKeyboardButton("🔴 ثبت آموزش Wireguard", callback_data=f"tut_adm_set_{os_key}_wireguard"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_tutorial_mgr"))
    bot.edit_message_text(f"📚 مدیریت آموزش‌های {item['label']}:\nکدام سرور را ویرایش می‌کنید؟", c.message.chat.id, c.message.message_id, reply_markup=kb)

# FIX: شروع فرایند ثبت آموزش با دکمه تایید - نه ثبت خودکار
@bot.callback_query_handler(func=lambda c: c.data.startswith("tut_adm_set_"))
def tut_adm_set_content(c):
    if c.from_user.id != ADMIN_ID: return
    parts = c.data.replace("tut_adm_set_", "").rsplit("_", 1)
    if len(parts) != 2: return
    os_key, srv_type = parts
    srv_label = {"v2ray": "V2ray", "npv": "Npv", "wireguard": "Wireguard"}.get(srv_type, srv_type)
    os_item = tutorial_col.find_one({"os": os_key})
    os_label = os_item['label'] if os_item else os_key
    user_states[ADMIN_ID] = {
        "state": "TUT_COLLECTING_CONTENT",
        "os": os_key,
        "srv": srv_type,
        "collected": [],  # لیست محتواها
        "os_label": os_label,
        "srv_label": srv_label
    }
    bot.send_message(ADMIN_ID,
        f"📝 ثبت آموزش {os_label} - {srv_label}\n\n"
        f"محتوای آموزش را ارسال کنید:\n"
        f"• می‌توانید متن، عکس، ویدیو، یا فایل ارسال کنید\n"
        f"• می‌توانید چندین محتوا ارسال کنید\n\n"
        f"وقتی آماده بودید، دکمه زیر را بزنید:"
    )
    # ارسال دکمه ثبت آموزش
    kb2 = types.InlineKeyboardMarkup()
    kb2.add(types.InlineKeyboardButton("✅ ثبت آموزش", callback_data=f"tut_adm_save_{os_key}_{srv_type}"))
    kb2.add(types.InlineKeyboardButton("❌ لغو", callback_data=f"tut_adm_manage_{os_key}"))
    bot.send_message(ADMIN_ID, "👆 محتوا را ارسال کنید، سپس دکمه ثبت را بزنید:", reply_markup=kb2)

# جمع‌آوری محتوای آموزش (متن)
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "TUT_COLLECTING_CONTENT", content_types=['text'])
def tut_collect_text(m):
    data = user_states.get(ADMIN_ID, {})
    if data.get("state") != "TUT_COLLECTING_CONTENT": return
    data["collected"].append({"type": "text", "content": m.text.strip(), "file_id": None})
    bot.send_message(ADMIN_ID, f"✅ متن دریافت شد. می‌توانید محتوای بیشتری ارسال کنید یا دکمه ثبت را بزنید.")

# جمع‌آوری محتوای آموزش (عکس)
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "TUT_COLLECTING_CONTENT", content_types=['photo'])
def tut_collect_photo(m):
    data = user_states.get(ADMIN_ID, {})
    if data.get("state") != "TUT_COLLECTING_CONTENT": return
    data["collected"].append({"type": "photo", "content": m.caption or "", "file_id": m.photo[-1].file_id})
    bot.send_message(ADMIN_ID, f"✅ عکس دریافت شد. می‌توانید محتوای بیشتری ارسال کنید یا دکمه ثبت را بزنید.")

# جمع‌آوری محتوای آموزش (ویدیو)
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "TUT_COLLECTING_CONTENT", content_types=['video'])
def tut_collect_video(m):
    data = user_states.get(ADMIN_ID, {})
    if data.get("state") != "TUT_COLLECTING_CONTENT": return
    data["collected"].append({"type": "video", "content": m.caption or "", "file_id": m.video.file_id})
    bot.send_message(ADMIN_ID, f"✅ ویدیو دریافت شد. می‌توانید محتوای بیشتری ارسال کنید یا دکمه ثبت را بزنید.")

# جمع‌آوری محتوای آموزش (فایل) - فقط اگر state صحیح باشه
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "TUT_COLLECTING_CONTENT", content_types=['document'])
def tut_collect_document(m):
    data = user_states.get(ADMIN_ID, {})
    if data.get("state") != "TUT_COLLECTING_CONTENT": return
    data["collected"].append({"type": "document", "content": m.caption or "", "file_id": m.document.file_id})
    bot.send_message(ADMIN_ID, f"✅ فایل دریافت شد. می‌توانید محتوای بیشتری ارسال کنید یا دکمه ثبت را بزنید.")

# FIX: ذخیره محتوا فقط وقتی دکمه ثبت آموزش زده میشه
@bot.callback_query_handler(func=lambda c: c.data.startswith("tut_adm_save_"))
def tut_adm_save_content(c):
    if c.from_user.id != ADMIN_ID: return
    parts = c.data.replace("tut_adm_save_", "").rsplit("_", 1)
    if len(parts) != 2: return
    os_key, srv_type = parts
    data = user_states.get(ADMIN_ID, {})
    if data.get("state") != "TUT_COLLECTING_CONTENT":
        bot.answer_callback_query(c.id, "هیچ محتوایی برای ثبت وجود ندارد", show_alert=True)
        return
    collected = data.get("collected", [])
    if not collected:
        bot.answer_callback_query(c.id, "⚠️ ابتدا محتوایی ارسال کنید", show_alert=True)
        return
    content_key = f"tut_content_{os_key}_{srv_type}"
    # اگر فقط یک آیتم بود، به‌صورت تکی ذخیره می‌کنیم
    # اگر چندین آیتم بود، به‌صورت لیست ذخیره می‌کنیم
    if len(collected) == 1:
        save_value = collected[0]
    else:
        save_value = {"type": "multi", "items": collected}
    settings_col.update_one({"key": content_key}, {"$set": {"value": save_value}}, upsert=True)
    bot.answer_callback_query(c.id, "✅ آموزش با موفقیت ذخیره شد", show_alert=True)
    os_label = data.get("os_label", os_key)
    srv_label = data.get("srv_label", srv_type)
    bot.send_message(ADMIN_ID, f"✅ آموزش {os_label} - {srv_label} با {len(collected)} محتوا ذخیره شد.")
    user_states[ADMIN_ID] = None

@bot.callback_query_handler(func=lambda c: c.data == "tog_tutorial_status_adm")
def tog_tutorial_status(c):
    if c.from_user.id != ADMIN_ID: return
    res = settings_col.find_one({"key": "tutorial_status"})
    current_val = res['value'] if res else 1
    settings_col.update_one({"key": "tutorial_status"}, {"$set": {"value": 0 if current_val == 1 else 1}})
    adm_tutorial_mgr(c)

@bot.callback_query_handler(func=lambda c: c.data == "tut_adm_add_os")
def tut_adm_add_os(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state": "TUT_WAIT_NEW_OS_NAME"}
    bot.send_message(ADMIN_ID, "نام کلید سیستم‌عامل را وارد کنید (مثل: linux یا router):")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "TUT_WAIT_NEW_OS_NAME")
def tut_save_new_os_name(m):
    os_key = m.text.strip().lower().replace(" ", "_")
    user_states[ADMIN_ID] = {"state": "TUT_WAIT_NEW_OS_LABEL", "os": os_key}
    bot.send_message(ADMIN_ID, f"کلید: {os_key}\nحالا نام نمایشی را با ایموجی وارد کنید (مثل: 🐧 لینوکس):")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "TUT_WAIT_NEW_OS_LABEL")
def tut_save_new_os_label(m):
    label = m.text.strip()
    os_key = user_states[ADMIN_ID]["os"]
    # اضافه کردن OS جدید به دیتابیس
    tutorial_col.insert_one({"os": os_key, "label": label, "type": "text"})
    # مقداردهی اولیه محتوای سه سرور
    for srv in ["v2ray", "npv", "wireguard"]:
        key = f"tut_content_{os_key}_{srv}"
        if not settings_col.find_one({"key": key}):
            settings_col.insert_one({
                "key": key,
                "value": {"type": "text", "content": f"آموزش {srv} برای {label} هنوز تنظیم نشده است.", "file_id": None}
            })
    bot.send_message(ADMIN_ID, f"✅ سیستم‌عامل '{label}' با کلید '{os_key}' اضافه شد.\nحالا می‌توانید از پنل مدیریت آموزش‌ها محتوا تنظیم کنید.")
    user_states[ADMIN_ID] = None

# FIX: نمایش محتوای چند آیتمی
def send_multi_content(user_id, items, header, back_cb):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb))
    for i, item in enumerate(items):
        t = item.get("type", "text")
        content = item.get("content", "")
        file_id = item.get("file_id")
        caption = header + content if i == 0 else content
        if t == "text":
            bot.send_message(user_id, caption, reply_markup=kb if i == len(items)-1 else None)
        elif t == "photo" and file_id:
            bot.send_photo(user_id, file_id, caption=caption, reply_markup=kb if i == len(items)-1 else None)
        elif t == "video" and file_id:
            bot.send_video(user_id, file_id, caption=caption, reply_markup=kb if i == len(items)-1 else None)
        elif t == "document" and file_id:
            bot.send_document(user_id, file_id, caption=caption, reply_markup=kb if i == len(items)-1 else None)

# بازنویسی show_tutorial_content برای پشتیبانی از multi
@bot.callback_query_handler(func=lambda c: c.data.startswith("tut_show_"))
def show_tutorial_content_v2(c):
    parts = c.data.replace("tut_show_", "").rsplit("_", 1)
    if len(parts) != 2:
        bot.answer_callback_query(c.id, "خطا در دریافت اطلاعات", show_alert=True)
        return
    os_key, srv_type = parts
    content_key = f"tut_content_{os_key}_{srv_type}"
    content_data = settings_col.find_one({"key": content_key})
    os_item = tutorial_col.find_one({"os": os_key})
    os_label = os_item['label'] if os_item else os_key
    srv_label = {"v2ray": "🔵 V2ray", "npv": "🟣 Npv", "wireguard": "🔴 Wireguard"}.get(srv_type, srv_type)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"tut_os_{os_key}"))
    header = f"📚 آموزش {os_label} - {srv_label}\n\n"

    if not content_data or not content_data.get('value'):
        bot.send_message(c.from_user.id, header + "آموزش هنوز تنظیم نشده است.", reply_markup=kb)
        return

    val = content_data['value']
    content_type = val.get("type", "text")

    if content_type == "multi":
        items = val.get("items", [])
        send_multi_content(c.from_user.id, items, header, f"tut_os_{os_key}")
    else:
        content_text = val.get("content", "")
        file_id = val.get("file_id")
        if content_type == "text":
            bot.send_message(c.from_user.id, header + content_text, reply_markup=kb)
        elif content_type == "photo" and file_id:
            bot.send_photo(c.from_user.id, file_id, caption=header + content_text, reply_markup=kb)
        elif content_type == "video" and file_id:
            bot.send_video(c.from_user.id, file_id, caption=header + content_text, reply_markup=kb)
        elif content_type == "document" and file_id:
            bot.send_document(c.from_user.id, file_id, caption=header + content_text, reply_markup=kb)
        else:
            bot.send_message(c.from_user.id, header + content_text, reply_markup=kb)

# =========================================================================

# به‌روزرسانی last_activity در هر callback
_original_process = bot.process_new_updates

def update_activity_middleware(updates):
    for update in updates:
        if update.callback_query:
            uid = update.callback_query.from_user.id
            users_col.update_one({"user_id": uid}, {"$set": {"last_activity": datetime.now()}})
        elif update.message:
            uid = update.message.from_user.id
            users_col.update_one({"user_id": uid}, {"$set": {"last_activity": datetime.now()}})
    patched_process_new_updates(updates)

bot.process_new_updates = update_activity_middleware

# --------------- WEB ---------------

@app.route('/')
def home(): return "OK - MongoDB Active"

def run(): app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling(skip_pending=True)
