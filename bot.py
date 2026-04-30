import telebot
from telebot import types
from pymongo import MongoClient # تغییر یافت
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

# ---------------- DB (Changed to MongoDB) ----------------

# اتصال به دیتابیس ابری شما
MONGO_URI = "mongodb+srv://1raven1390_db_user:iOlmB4Azr3SrrkVZ@bot.te88ask.mongodb.net/?retryWrites=true&w=majority&appName=Bot"
client = MongoClient(MONGO_URI)
db = client['telegram_bot']

users_col = db['users']
orders_col = db['orders']
settings_col = db['settings']

# مقداردهی اولیه تنظیمات (اگر وجود نداشته باشند)
for s in ['sale_month', 'sale_vip', 'charge_status', 'ref_status']: # ref_status اضافه شد
    if not settings_col.find_one({"key": s}):
        settings_col.insert_one({"key": s, "value": 1})

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
    return kb

def back_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    return kb

def is_member(user_id):
    try:
        st = bot.get_chat_member(CHANNEL_ID, user_id).status
        return st in ['member', 'creator', 'administrator']
    except: return True

# --------------- START & ADMIN COMMAND ---------------

@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    
    # سیستم بن خودکار و دستی
    user_check = users_col.find_one({"user_id": uid})
    if user_check and (user_check.get("is_banned") or user_check.get("warnings", 0) >= 3):
        bot.send_message(uid, "❌ حساب شما به دلیل تخلف (یا دریافت ۳ اخطار) مسدود شده است.")
        return

    # سیستم زیرمجموعه گیری
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
            "invited_count": 0, "is_banned": False
        })
        # اهدای پاداش دعوت
        if ref_by and get_setting('ref_status'):
            inviter = users_col.find_one({"user_id": ref_by})
            if inviter and inviter.get('invited_count', 0) < 4:
                users_col.update_one({"user_id": ref_by}, {"$inc": {"balance": 5000, "invited_count": 1}})
                bot.send_message(ref_by, "🎉 تبریک! یک کاربر با لینک شما عضو شد و ۵,۰۰۰ تومان به موجودی شما اضافه شد.")

    if not is_member(uid):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_ID.replace('@','')}"))
        kb.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data="check_join"))
        bot.send_message(uid, "برای استفاده ابتدا عضو کانال شوید:", reply_markup=kb)
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
    bot.send_message(m.chat.id, f"👑 پنل ادمین \n\n👤 تعداد کاربران: {users_count}\n💰 مجموع موجودی: {format_p(total)}\n📦 سفارشات باز: {pending}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join(c):
    if is_member(c.from_user.id):
        bot.edit_message_text("✅ تایید شد", c.message.chat.id, c.message.message_id, reply_markup=main_menu())
    else: bot.answer_callback_query(c.id, "هنوز عضو نشدی", show_alert=True)

# --------------- ADMIN SETTINGS (MANAGEMENT) ---------------

@bot.callback_query_handler(func=lambda c: c.data == "adm_settings")
def adm_settings(c):
    if c.from_user.id != ADMIN_ID: return
    m_status = "✅ باز" if get_setting('sale_month') else "❌ بسته"
    v_status = "✅ باز" if get_setting('sale_vip') else "❌ بسته"
    c_status = "✅ باز" if get_setting('charge_status') else "❌ بسته"
    r_status = "✅ باز" if get_setting('ref_status') else "❌ بسته"
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"فروش ۱ ماهه: {m_status}", callback_data="tog_sale_month"))
    kb.add(types.InlineKeyboardButton(f"فروش VIP: {v_status}", callback_data="tog_sale_vip"))
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
    # بن خودکار در صورت رسیدن اخطار به ۳
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
    kb.add(types.InlineKeyboardButton("📅 ۱ ماهه", callback_data="price_month"), types.InlineKeyboardButton("♾ بدون محدودیت زمانی + ساب + VIP", callback_data="price_vip"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    bot.edit_message_text("📊 تعرفه:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "price_month")
def price_month(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👤 تک کاربره", callback_data="show_month_prices"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="price"))
    bot.edit_message_text("۱ ماهه:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "show_month_prices")
def show_month_prices(c):
    txt = "📅 ۱ ماهه (تک کاربره)\n\n1گیگ : ۳۵۰,۰۰۰\n2گیگ : ۶۹۹,۰۰۰\n3گیگ : ۹۹۹,۰۰۰\n5گیگ : ۱,۴۹۹,۰۰۰"
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

@bot.callback_query_handler(func=lambda c: c.data == "price_vip")
def price_vip(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("♾ بدون محدودیت کاربری", callback_data="show_vip_prices"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="price"))
    bot.edit_message_text("VIP:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "show_vip_prices")
def show_vip_prices(c):
    txt = "♾ بدون محدودیت + VIP (تخفیف)\n\n1گیگ : ۵۹۹,۰۰۰\n2گیگ : ۱,۱۹۸,۰۰۰\n3گیگ : ۱,۷۹۷,۰۰۰\n5گیگ : ۲,۸۹۹,۰۰۰\n10گیگ : ۵,۲۹۹,۰۰۰"
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

# --------------- BUY ---------------

PRICES_MONTH = {"1G":350000,"2G":699000,"3G":999000,"5G":1499000}
PRICES_VIP = {"1G":599000,"2G":1198000,"3G":1797000,"5G":2899000,"10G":5299000}

@bot.callback_query_handler(func=lambda c: c.data == "buy")
def buy(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📅 ۱ ماهه", callback_data="buy_month"), types.InlineKeyboardButton("♾ بدون محدودیت + VIP", callback_data="buy_vip"))
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
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in ["1G","2G","3G","5G"]: kb.add(types.InlineKeyboardButton(v, callback_data=f"vol_{v}"))
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
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in ["1G","2G","3G","5G","10G"]: kb.add(types.InlineKeyboardButton(v, callback_data=f"vol_{v}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_vip"))
    bot.edit_message_text("حجم را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("vol_"))
def select_volume(c):
    uid = c.from_user.id
    st = user_states.get(uid, {})
    plan = st.get("plan")
    volume = c.data.split("_")[1]
    price = PRICES_MONTH.get(volume) if plan=="MONTH" else PRICES_VIP.get(volume)
    user = users_col.find_one({"user_id": uid})
    balance = user['balance'] if user else 0
    if balance < price:
        bot.answer_callback_query(c.id, "❌ موجودی کافی نمی‌باشد", show_alert=True); return
    user_states[uid] = {"state":"CONFIRM_BUY","plan":plan,"volume":volume,"price":price}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ تایید", callback_data="final_buy"), types.InlineKeyboardButton("❌ لغو", callback_data="back"))
    bot.send_message(uid, f"آیا از خرید {volume} به مبلغ {format_p(price)} اطمینان دارید؟", reply_markup=kb)

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
    bot.send_message(ADMIN_ID, "📤 کانفیگ رو ارسال کن:")

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
    status = "🚫 مسدود" if d.get("is_banned") else "✅ فعال"
    text = f"📊 اطلاعات حساب کاربری شما در ربات: \n\n🔢 آیدی عددی : {c.from_user.id}\n🔆 یوزرنیم : {username}\n📱 وضعیت : {status}\n💰 موجودی : {format_p(d['balance'])} تومان\n🏦 پرداخت های موفق : {d['success_payments']} عدد\n🛍 تعداد سرویس ها : {d['configs_count']} عدد\n⚠️ تعداد اخطار ها : {d['warnings']} عدد\n⏰ تاریخ عضویت : {d['join_date']}\n\n🤖 | @rafe_filter_GB_bot"
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
    
    ban_txt = "🔓 آن‌بن کردن" if d.get("is_banned") else "🚫 بن کردن"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("➕ افزودن موجودی", callback_data=f"adm_add_{uid}"), types.InlineKeyboardButton("➖ کسر موجودی", callback_data=f"adm_sub_{uid}"))
    kb.add(types.InlineKeyboardButton("⚠️ اخطار", callback_data=f"adm_warn_{uid}"), types.InlineKeyboardButton(ban_txt, callback_data=f"adm_ban_{uid}"))
    
    bot.send_message(ADMIN_ID, f"👤 کاربر {uid} \n\n💰 موجودی: {format_p(d['balance'])}\n🏦 پرداخت موفق: {d['success_payments']}\n🛍 سرویس‌ها: {d['configs_count']}\n⚠️ اخطار: {d['warnings']}\n🚫 وضعیت: {'مسدود' if d.get('is_banned') else 'آزاد'}\n⏰ عضویت: {d['join_date']}", reply_markup=kb)
    user_states[ADMIN_ID] = None

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_ban_"))
def adm_ban_toggle(c):
    if c.from_user.id != ADMIN_ID: return
    uid = int(c.data.split("_")[2])
    user = users_col.find_one({"user_id": uid})
    new_status = not user.get("is_banned", False)
    users_col.update_one({"user_id": uid}, {"$set": {"is_banned": new_status}})
    txt = "مسدود شد" if new_status else "آزاد شد"
    bot.answer_callback_query(c.id, f"کاربر {txt}")
    bot.send_message(uid, f"⚠️ حساب شما توسط مدیریت {'مسدود' if new_status else 'آزاد'} شد.")

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

# --------------- WEB ---------------

@app.route('/')
def home(): return "OK - MongoDB Active"

def run(): app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling(skip_pending=True)
