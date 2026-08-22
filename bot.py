import telebot
from telebot import types
from pymongo import MongoClient
import os
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import time
import random
import string

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
test_accounts_col = db['test_accounts']  # مخزن اکانت‌های تست
test_used_col = db['test_used']  # ثبت کاربرانی که تست گرفتن

# مجموعه‌های جدید دیتابیس برای قابلیت‌های درخواستی
coupons_col = db['coupons']
subadmins_col = db['subadmins']
waiting_list_col = db['waiting_list']
reviews_col = db['reviews']

for s in ['sale_month', 'sale_vip', 'sale_napsterv', 'sale_napsterv_unlim', 'sale_wireguard', 'charge_status',
          'ref_status', 'test_status', 'coupon_system_status', 'subadmin_system_status', 'review_system_status',
          'reminder_system_status', 'fake_messages_status']:
    if not settings_col.find_one({"key": s}):
        settings_col.insert_one({"key": s, "value": 1})

if fjoin_col.count_documents({}) == 0:
    fjoin_col.insert_one({"type": "channel", "chat_id": CHANNEL_ID})
    fjoin_col.insert_one({"type": "group", "chat_id": GROUP_ID})

# مقداردهی اولیه دکمه‌های تست (اگه نبود)
if not settings_col.find_one({"key": "test_buttons"}):
    settings_col.insert_one({"key": "test_buttons", "value": []})

default_prices = {
    "PRICES_MONTH": {"1G": 350000, "2G": 699000, "3G": 999000, "5G": 1499000},
    "PRICES_VIP": {"1G": 599000, "2G": 1198000, "3G": 1797000, "5G": 2899000, "10G": 5299000},
    "PRICES_NAPSTERV": {"1G": 350000, "2G": 699000, "3G": 999000, "5G": 1499000},
    "PRICES_NAPSTERV_UNLIM": {"1G": 599000, "2G": 1198000, "3G": 1797000, "5G": 2899000, "10G": 5299000},
    "PRICES_WIREGUARD": {"1G": 400000, "2G": 799000, "3G": 1099000, "5G": 1599000}
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
    try:
        return "{:,}".format(int(x))
    except:
        return "0"


def now_str():
    return datetime.now().strftime("%Y/%m/%d - %H:%M:%S")


def mask_user_id(uid):
    uid_str = str(uid)
    if len(uid_str) > 4:
        return f"{uid_str[:2]}****{uid_str[-2:]}"
    return uid_str


def send_to_channels(text):
    try:
        bot.send_message(CHANNEL_ID, text)
        bot.send_message(GROUP_ID, text)
    except:
        pass


def generate_track_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def generate_coupon_code():
    """تولید خودکار کد تخفیف ۸ کاراکتری یکتا (حروف بزرگ انگلیسی + اعداد)"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not coupons_col.find_one({"code": code}):
            return code


def parse_duration_text(txt):
    """پارس کردن متن مدت اعتبار به فرمت 7d / 24h / 30m / 0
    خروجی: (timedelta, label) یا ("ERROR", None)"""
    txt = (txt or "").strip().lower()
    if txt == "0":
        return None, "نامحدود"
    if len(txt) < 2:
        return "ERROR", None
    unit = txt[-1]
    num_part = txt[:-1]
    if not num_part.isdigit():
        return "ERROR", None
    num = int(num_part)
    if num <= 0:
        return "ERROR", None
    if unit == "d":
        return timedelta(days=num), f"{num} روز"
    elif unit == "h":
        return timedelta(hours=num), f"{num} ساعت"
    elif unit == "m":
        return timedelta(minutes=num), f"{num} دقیقه"
    else:
        return "ERROR", None


def register_coupon_usage(code, uid):
    """ثبت استفاده موفق از کوپن: افزایش used_count و اضافه‌شدن uid به used_by"""
    coupons_col.update_one({"code": code}, {"$inc": {"used_count": 1}, "$addToSet": {"used_by": uid}})


def check_coupon_valid(code, uid):
    """بررسی امنیتی کامل کوپن سمت کاربر. خروجی: (True, coupon_doc) یا (False, error_message)"""
    code = (code or "").strip().upper()
    if len(code) != 8 or not code.isalnum():
        return False, "❌ کد تخفیف باید دقیقاً ۸ کاراکتر الفبایی/عددی باشد."
    cp = coupons_col.find_one({"code": code})
    if not cp:
        return False, "❌ کد تخفیف یافت نشد."
    if not cp.get("active", True):
        return False, "❌ این کد تخفیف غیرفعال است."
    expire_at = cp.get("expire_at")
    if expire_at:
        try:
            exp_dt = datetime.fromisoformat(expire_at)
            if datetime.now() > exp_dt:
                return False, "❌ این کد تخفیف منقضی شده است."
        except:
            pass
    if uid in cp.get("used_by", []):
        return False, "❌ شما قبلاً از این کد تخفیف استفاده کرده‌اید (هر کاربر فقط یک بار مجاز است)."
    max_uses = cp.get("max_uses", 0)
    if max_uses > 0 and cp.get("used_count", 0) >= max_uses:
        return False, "❌ ظرفیت استفاده از این کد تخفیف به اتمام رسیده است."
    return True, cp


# --------------- تقویم جلالی (بدون کتابخانه خارجی) ---------------
def jalali_to_gregorian(jy, jm, jd):
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0):
        g_days_in_month[1] = 29
    gm = 0
    while gm < 12 and gd > g_days_in_month[gm]:
        gd -= g_days_in_month[gm]
        gm += 1
    gm += 1
    return gy, gm, gd


def gregorian_to_jalali(gy, gm, gd):
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    for i in range(gm2):
        g_day_no += g_days_in_month[i]
    if gm2 > 1 and ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)):
        g_day_no += 1
    g_day_no += gd2
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    jm = 0
    while jm < 11 and j_day_no >= j_days_in_month[jm]:
        j_day_no -= j_days_in_month[jm]
        jm += 1
    jm += 1
    jd = j_day_no + 1
    return jy, jm, jd


PERSIAN_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def get_current_time_both_calendars():
    now = datetime.now()
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    weekday_fa = PERSIAN_WEEKDAYS[now.weekday()]
    time_str = now.strftime("%H:%M:%S")
    txt = (f"🕐 زمان دقیق سرور:\n\n"
           f"📅 شمسی: {jy:04d}/{jm:02d}/{jd:02d}\n"
           f"📅 میلادی: {now.year:04d}/{now.month:02d}/{now.day:02d}\n"
           f"📆 روز هفته: {weekday_fa}\n"
           f"⏰ ساعت: {time_str}")
    return txt


def add_row(kb, *buttons):
    """تابع کمکی مشترک برای افزودن یک ردیف دکمه"""
    kb.add(*buttons)
    return kb


def btn(text, callback_data=None, url=None, style=None):
    """تابع کمکی ساخت دکمه با پشتیبانی از style (primary / success / danger)"""
    kwargs = {}
    if url:
        kwargs["url"] = url
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if style is not None:
        kwargs["style"] = style
    return types.InlineKeyboardButton(text, **kwargs)


def main_menu():
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("🛒 خرید سرور", "buy", style="primary"))
    kb.add(btn("📊 تعرفه", "price", style="primary"), btn("👤 حساب کاربری", "account", style="primary"))
    kb.add(btn("💰 افزایش موجودی", "charge", style="primary"), btn("👥 زیرمجموعه‌گیری", "referral", style="primary"))
    kb.add(btn("🖥 وضعیت سرورها", "server_status", style="primary"), btn("📢 اطلاعیه‌ها", "announcements", style="primary"))
    kb.add(btn("📚 آموزش اتصال", "tutorial", style="primary"),
           btn("🔍 پیگیری سفارش", "track_order", style="primary"),
           btn("📞 پشتیبانی", "support", style="primary"))
    if get_setting('test_status'):
        kb.add(btn("🎁 اکانت تست", "test_account", style="success"))
    return kb


def back_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("🔙 بازگشت", "back", style="danger"))
    return kb


def is_member(user_id):
    items = list(fjoin_col.find({}))
    if not items:
        return True
    try:
        for item in items:
            st = bot.get_chat_member(item['chat_id'], user_id).status
            if st not in ['member', 'creator', 'administrator']:
                return False
        return True
    except:
        return True


# --------------- ADMIN PANEL (یکپارچه‌شده - رفع تکرار کد) ---------------
def admin_panel_text():
    """متن پنل ادمین - جدا شده تا در همه جا یکسان استفاده شود"""
    users_count = users_col.count_documents({})
    total_balance = list(users_col.aggregate([{"$group": {"_id": None, "total": {"$sum": "$balance"}}}]))
    total = total_balance[0]['total'] if total_balance else 0
    pending = orders_col.count_documents({"status": "pending"})
    return f"👑 پنل ادمین \n\n👤 تعداد کاربران: {users_count}\n💰 مجموع موجودی: {format_p(total)}\n📦 سفارشات باز: {pending}"


def build_admin_kb():
    """کیبورد پنل ادمین - جدا شده تا در همه جا یکسان استفاده شود"""
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("📦 سفارشات باز", "adm_orders", style="primary"))
    kb.add(btn("🔎 مشاهده کاربر", "adm_get_user", style="primary"))
    kb.add(btn("📣 ارسال همگانی", "adm_broadcast", style="primary"))
    kb.add(btn("⚙️ مدیریت فروش", "adm_settings", style="primary"))
    kb.add(btn("💰 تغییر قیمت‌ها", "adm_change_prices", style="primary"))
    kb.add(btn("🛡 مدیریت عضویت", "adm_fjoin_mgr", style="primary"))
    kb.add(btn("🖥 وضعیت سرورها", "adm_server_status", style="primary"))
    kb.add(btn("📢 اطلاعیه هوشمند", "adm_smart_announce", style="primary"))
    kb.add(btn("📊 آمار کاربران فعال", "adm_active_stats", style="primary"))
    kb.add(btn("📚 مدیریت آموزش اتصال", "adm_tutorial_mgr", style="primary"))
    kb.add(btn("🎁 مدیریت اکانت تست", "adm_test_mgr", style="primary"))
    kb.add(btn("📋 گزارش خریداران", "adm_buyers_report", style="primary"))
    kb.add(btn("🏷 مدیریت کدهای تخفیف", "adm_coupon_mgr", style="primary"))
    kb.add(btn("👥 مدیریت ادمین‌های فرعی", "adm_subadmin_mgr", style="primary"))
    kb.add(btn("⭐ تنظیمات نظرسنجی و یادآوری", "adm_extra_systems", style="primary"))
    return kb


def render_admin_panel(chat_id, message_id=None):
    """تابع واحد نمایش پنل ادمین - جایگزین admin_panel و show_admin_panel قبلی"""
    text = admin_panel_text()
    kb = build_admin_kb()
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
            return
        except:
            pass
    bot.send_message(chat_id, text, reply_markup=kb)


def build_subadmin_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("📦 مشاهده سفارشات فعال", "sub_view_orders", style="primary"))
    kb.add(btn("📤 ارسال کانفیگ با کد سفارش", "sub_send_config_by_id", style="primary"))
    return kb


def subadmin_panel_text(sub_data):
    return (f"👥 پنل ادمین فرعی\nدسترسی‌های شما:\n"
            f"تایید/رد رسید: {'✅' if sub_data['receipt_access'] else '❌'}\n"
            f"ارسال کانفیگ: {'✅' if sub_data['config_access'] else '❌'}")


def render_subadmin_panel(chat_id, message_id=None):
    sub_data = subadmins_col.find_one({"user_id": chat_id})
    if not sub_data:
        return
    text = subadmin_panel_text(sub_data)
    kb = build_subadmin_kb()
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
            return
        except:
            pass
    bot.send_message(chat_id, text, reply_markup=kb)


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
            if ref_by == uid:
                ref_by = None
    user = users_col.find_one({"user_id": uid})
    if not user:
        users_col.insert_one({
            "user_id": uid,
            "balance": 0,
            "configs_count": 0,
            "warnings": 0,
            "success_payments": 0,
            "name": m.from_user.first_name or "",
            "username": m.from_user.username or "",
            "join_date": now_str(),
            "invited_count": 0,
            "is_banned": False,
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
            url = f"https://t.me/{item['chat_id'].replace('@', '')}"
            kb.add(btn(label, url=url, style="primary"))
        kb.add(btn("✅ عضو شدم", "check_join", style="primary"))
        bot.send_message(uid, "برای استفاده ابتدا عضو موارد زیر شوید:", reply_markup=kb)
        return
    bot.send_message(uid, "👇 منوی اصلی:", reply_markup=main_menu())


@bot.message_handler(commands=['admin'])
def admin_panel(m):
    uid = m.from_user.id
    is_sub = subadmins_col.find_one({"user_id": uid})
    is_system_on = get_setting('subadmin_system_status')

    if uid != ADMIN_ID:
        if is_sub and is_system_on:
            render_subadmin_panel(uid)
        return

    render_admin_panel(m.chat.id)


@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join(c):
    if is_member(c.from_user.id):
        bot.edit_message_text("✅ تایید شد", c.message.chat.id, c.message.message_id, reply_markup=main_menu())
    else:
        bot.answer_callback_query(c.id, "هنوز عضو کانال یا گروه نشدی", show_alert=True)


# --------------- ADMIN SETTINGS (توگل‌های مستقل مدیریت فروش) ---------------
SALE_TOGGLE_KEYS = ['sale_month', 'sale_vip', 'sale_napsterv', 'sale_napsterv_unlim', 'sale_wireguard',
                     'charge_status', 'ref_status', 'test_status']

SALE_PLAN_MAP = {
    "sale_month": ("MONTH", "۱ ماهه"),
    "sale_vip": ("VIP", "VIP"),
    "sale_napsterv": ("NAPSTERV", "نپستر"),
    "sale_napsterv_unlim": ("NAPSTERV_UNLIM", "نامحدود نپستر"),
    "sale_wireguard": ("WIREGUARD", "وایرگارد"),
}


@bot.callback_query_handler(func=lambda c: c.data == "adm_settings")
def adm_settings(c):
    if c.from_user.id != ADMIN_ID:
        return
    labels = {
        'sale_month': "فروش ۱ ماهه", 'sale_vip': "فروش VIP", 'sale_napsterv': "سرور نپستر",
        'sale_napsterv_unlim': "سرور نامحدود نپستر", 'sale_wireguard': "سرور وایرگارد",
        'charge_status': "افزایش موجودی", 'ref_status': "سیستم دعوت", 'test_status': "اکانت تست"
    }
    kb = types.InlineKeyboardMarkup()
    for key in SALE_TOGGLE_KEYS:
        status = "✅ باز" if get_setting(key) else "❌ بسته"
        kb.add(btn(f"{labels[key]}: {status}", f"SALE_TOG_{key}", style="primary"))
    kb.add(btn("🔙 بازگشت به پنل", "admin_back", style="danger"))
    bot.edit_message_text("⚙️ مدیریت وضعیت خدمات:\n(با کلیک روی هر دکمه وضعیت آن عوض می‌شود)", c.message.chat.id,
                           c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("SALE_TOG_"))
def sale_toggle_settings(c):
    if c.from_user.id != ADMIN_ID:
        return
    key = c.data.replace("SALE_TOG_", "")
    if key not in SALE_TOGGLE_KEYS:
        return
    current = get_setting(key)
    settings_col.update_one({"key": key}, {"$set": {"value": 0 if current else 1}})

    # اگر سرور از بسته به باز تغییر کرد -> اطلاع‌رسانی لیست انتظار در Thread جدید
    if not current and key in SALE_PLAN_MAP:
        plan_key, plan_title = SALE_PLAN_MAP[key]
        Thread(target=check_and_notify_waiting_list, args=(plan_key, plan_title), daemon=True).start()

    adm_settings(c)


@bot.callback_query_handler(func=lambda c: c.data == "admin_back")
def admin_back(c):
    uid = c.from_user.id
    is_sub = subadmins_col.find_one({"user_id": uid})
    is_system_on = get_setting('subadmin_system_status')

    if uid != ADMIN_ID:
        if is_sub and is_system_on:
            render_subadmin_panel(uid, c.message.message_id)
        return

    render_admin_panel(c.message.chat.id, c.message.message_id)


# --------------- CHARGE ---------------
@bot.callback_query_handler(func=lambda c: c.data == "charge")
def charge(c):
    if not get_setting('charge_status'):
        bot.answer_callback_query(c.id, "⚠️ در حال حاضر بخش افزایش موجودی موقتاً بسته است.", show_alert=True)
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("💳 کارت به کارت", "c2c", style="primary"))
    kb.add(btn("🔙 بازگشت", "back", style="danger"))
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
    user_states[m.from_user.id] = {"state": "WAIT_RECEIPT", "amount": amt, "card": m.text.strip(),
                                    "expire_at": expire_at, "invoice_time": datetime.now(), "is_expired": False}
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("📸 ارسال رسید", "send_receipt", style="success"))
    bot.send_message(m.chat.id,
                      f"✅ اطلاعات ثبت شد\n\n💰 مبلغ: {format_p(amt)} تومان\n💳 کارت مقصد:\n6221061233705260\n👤 به نام: افراس\n\n⚠️ مبلغ را واریز کرده و رسید را ارسال کنید\n\n⏰ فاکتور تا ۳۰ دقیقه معتبر است",
                      reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "send_receipt")
def send_receipt(c):
    uid = c.from_user.id
    data = user_states.get(uid)

    # حذف فوری دکمه بعد از کلیک تا کاربر نتواند دوباره کلیک کند
    try:
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
    except:
        pass

    if not data or data.get("state") not in ["WAIT_RECEIPT", "RECEIPT_SUBMITTED"]:
        bot.send_message(uid, "❌ هیچ فاکتور فعالی یافت نشد یا فاکتور منقضی شده است.")
        return

    if data.get("is_expired"):
        bot.send_message(uid, "❌ این فاکتور منقضی شده است.")
        return

    if data.get("state") == "RECEIPT_SUBMITTED":
        bot.send_message(uid, "❌ رسید قبلاً ارسال شده")
        return

    bot.send_message(uid, "📸 لطفاً تصویر رسید را ارسال کنید")


@bot.message_handler(content_types=['photo'])
def receipt(m):
    uid = m.from_user.id
    data = user_states.get(uid)
    if not data or data.get("state") != "WAIT_RECEIPT":
        if data and data.get("state") == "RECEIPT_SUBMITTED":
            bot.send_message(uid, "❌ رسید قبلاً ارسال شده")
        return

    if data.get("is_expired"):
        bot.send_message(uid, "❌ فاکتور منقضی شد")
        return

    order_res = orders_col.insert_one({
        "user_id": uid,
        "type": "charge",
        "amount": data['amount'],
        "card": data['card'],
        "status": "pending",
        "created_at": now_str()
    })
    charge_order_id = str(order_res.inserted_id)

    data["state"] = "RECEIPT_SUBMITTED"

    kb = types.InlineKeyboardMarkup()
    kb.add(
        btn("✅ تایید", f"ok_{uid}_{data['amount']}_{charge_order_id}", style="success"),
        btn("❌ رد", f"no_{uid}_{charge_order_id}", style="danger")
    )

    bot.send_photo(ADMIN_ID, m.photo[-1].file_id,
                    caption=f"💰 درخواست شارژ\n\n👤 کاربر: {uid}\n💵 مبلغ: {format_p(data['amount'])}\n💳 کارت مبدا: {data['card']}",
                    reply_markup=kb)

    is_sub_system = get_setting('subadmin_system_status')
    if is_sub_system:
        subs = subadmins_col.find({"receipt_access": True})
        for sub in subs:
            try:
                bot.send_photo(sub["user_id"], m.photo[-1].file_id,
                                caption=f"💰 درخواست شارژ (ادمین فرعی)\n\n👤 کاربر: {uid}\n💵 مبلغ: {format_p(data['amount'])}\n💳 کارت مبدا: {data['card']}",
                                reply_markup=kb)
            except:
                pass

    bot.send_message(m.chat.id, "✅ رسید برای ادمین ارسال شد، لطفاً منتظر بمانید 🙏")


@bot.callback_query_handler(func=lambda c: c.data.startswith("ok_"))
def ok(c):
    from bson.objectid import ObjectId
    parts = c.data.split("_")
    uid = int(parts[1])
    amt = int(parts[2])
    charge_order_id = parts[3] if len(parts) > 3 else None

    clicker_id = c.from_user.id
    if clicker_id != ADMIN_ID:
        sub_check = subadmins_col.find_one({"user_id": clicker_id})
        if not sub_check or not get_setting('subadmin_system_status') or not sub_check['receipt_access']:
            bot.answer_callback_query(c.id, "❌ شما دسترسی تایید رسید را ندارید.", show_alert=True)
            return

    if charge_order_id:
        order = orders_col.find_one({"_id": ObjectId(charge_order_id)})
        if not order or order.get("status") != "pending":
            bot.answer_callback_query(c.id, "⚠️ این درخواست قبلاً پردازش شده است.", show_alert=True)
            try:
                current_caption = c.message.caption or ""
                bot.edit_message_caption(caption=current_caption + "\n\n✅ قبلاً تایید شده بود",
                                          chat_id=c.message.chat.id, message_id=c.message.message_id)
            except:
                pass
            return

        orders_col.update_one({"_id": ObjectId(charge_order_id)}, {"$set": {"status": "approved"}})

        if uid in user_states:
            user_states[uid] = None

        users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt, "success_payments": 1}})

        u_data = users_col.find_one({"user_id": uid})
        new_payments = u_data.get("success_payments", 0)
        old_level = get_user_level(new_payments - 1)
        new_level = get_user_level(new_payments)

        if old_level != new_level:
            bot.send_message(uid, f"تبریک! به سطح {new_level} ارتقا یافتید ❤️‍🔥")
            if new_level == "💎 VIP":
                kb_gift = types.InlineKeyboardMarkup()
                kb_gift.add(btn("🎁 ارسال هدیه VIP", f"gift_vip_{uid}", style="success"))
                bot.send_message(ADMIN_ID, f"🏅 کاربر {uid} به سطح VIP رسید!", reply_markup=kb_gift)

        bot.send_message(uid, f"✅ مبلغ {format_p(amt)} تومان به حساب شما اضافه شد")

        masked = mask_user_id(uid)
        charge_alert = f"💳 شارژ حساب انجام شد\n━━━━━━━━━━━━━━━━\n💰 مبلغ واریزی: {format_p(amt)} تومان\n👤 کاربر: {masked}\n⌛ {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}\n━━━━━━━━━━━━━━━━\n🔒 AmirPlus | سرویس مطمئن"
        send_to_channels(charge_alert)

        bot.answer_callback_query(c.id, "✅ تایید شد")
        try:
            current_caption = c.message.caption or ""
            bot.edit_message_caption(caption=current_caption + "\n\n✅ رسید با موفقیت تایید شد",
                                      chat_id=c.message.chat.id, message_id=c.message.message_id)
        except:
            pass

        # نوتیف به ادمین اصلی در صورت تایید توسط ادمین فرعی
        if clicker_id != ADMIN_ID:
            try:
                bot.send_message(ADMIN_ID,
                                  f"✅ ادمین فرعی [{clicker_id}] رسید کاربر [{uid}] به مبلغ {format_p(amt)} تومان را تأیید کرد.")
            except:
                pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("no_"))
def no(c):
    from bson.objectid import ObjectId
    parts = c.data.split("_")
    uid = int(parts[1])
    charge_order_id = parts[2] if len(parts) > 2 else None

    clicker_id = c.from_user.id
    if clicker_id != ADMIN_ID:
        sub_check = subadmins_col.find_one({"user_id": clicker_id})
        if not sub_check or not get_setting('subadmin_system_status') or not sub_check['receipt_access']:
            bot.answer_callback_query(c.id, "❌ شما دسترسی رد رسید را ندارید.", show_alert=True)
            return

    if charge_order_id:
        order = orders_col.find_one({"_id": ObjectId(charge_order_id)})
        if not order or order.get("status") != "pending":
            bot.answer_callback_query(c.id, "⚠️ این درخواست قبلاً پردازش شده است.", show_alert=True)
            try:
                current_caption = c.message.caption or ""
                bot.edit_message_caption(caption=current_caption + "\n\n❌ قبلاً رد شده بود",
                                          chat_id=c.message.chat.id, message_id=c.message.message_id)
            except:
                pass
            return

        orders_col.update_one({"_id": ObjectId(charge_order_id)}, {"$set": {"status": "rejected"}})

        if uid in user_states:
            user_states[uid] = None

        users_col.update_one({"user_id": uid}, {"$inc": {"warnings": 1}})
        u_data = users_col.find_one({"user_id": uid})
        warns = u_data.get("warnings", 0)
        if warns >= 3:
            users_col.update_one({"user_id": uid}, {"$set": {"is_banned": True}})
            bot.send_message(uid, "❌ شما ۳ اخطار دریافت کردید و دسترسی شما به ربات برای همیشه مسدود شد.")
        else:
            bot.send_message(uid, f"❌ رسید شما رد شد و اخطار دریافت کردید. (تعداد اخطار: {warns} از ۳)")
        bot.answer_callback_query(c.id, "❌ رد شد")
        try:
            current_caption = c.message.caption or ""
            bot.edit_message_caption(caption=current_caption + f"\n\n❌ رسید با موفقیت رد شد (اخطار کاربر: {warns} از ۳)",
                                      chat_id=c.message.chat.id, message_id=c.message.message_id)
        except:
            pass

        # نوتیف به ادمین اصلی در صورت رد توسط ادمین فرعی
        if clicker_id != ADMIN_ID:
            try:
                bot.send_message(ADMIN_ID, f"❌ ادمین فرعی [{clicker_id}] رسید کاربر [{uid}] را رد کرد.")
            except:
                pass


# --------------- PRICE ---------------
@bot.callback_query_handler(func=lambda c: c.data == "price")
def price_menu(c):
    kb = types.InlineKeyboardMarkup()
    if get_setting('sale_month'):
        kb.add(btn("📅 ۱ ماهه", "price_month", style="primary"))
    if get_setting('sale_vip'):
        kb.add(btn("♾ بدون محدودیت زمانی + ساب + VIP", "price_vip", style="primary"))
    if get_setting('sale_napsterv'):
        kb.add(btn("🔮 سرور نپستر", "price_napsterv", style="primary"))
    if get_setting('sale_napsterv_unlim'):
        kb.add(btn("🌀 سرور نامحدود نپستر", "price_napsterv_unlim", style="primary"))
    if get_setting('sale_wireguard'):
        kb.add(btn("🔴 سرور وایرگارد", "price_wireguard", style="primary"))
    kb.add(btn("🔙 بازگشت", "back", style="danger"))
    bot.edit_message_text("📊 تعرفه خدمات باز:", c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "price_month")
def price_month(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("👤 تک کاربره", "show_month_prices", style="primary"))
    kb.add(btn("🔙 بازگشت", "price", style="danger"))
    bot.edit_message_text("۱ ماهه:", c.message.chat.id, c.message.message_id, reply_markup=kb)


def price_plan_kb(plan_key, prices_dict, back_cb, buy_cb=None):
    """تابع کمکی مشترک ساخت کیبورد نمایش تعرفه: هر حجم یک دکمه دکوراتیو (غیرقابل کلیک واقعی)
    + یک دکمه خرید مشترک + یک دکمه بازگشت"""
    kb = types.InlineKeyboardMarkup()
    for vol, price in prices_dict.items():
        kb.add(btn(f"📦 {vol}  ━━━━━━  {format_p(price)} تومان", "price_info_dummy", style="primary"))
    if buy_cb:
        kb.add(btn("🛒 خرید این سرور", buy_cb, style="success"))
    kb.add(btn("🔙 بازگشت", back_cb, style="danger"))
    return kb


@bot.callback_query_handler(func=lambda c: c.data == "price_info_dummy")
def price_info_dummy_cb(c):
    bot.answer_callback_query(c.id, "ℹ️ برای خرید از دکمه «🛒 خرید این سرور» استفاده کنید.", show_alert=True)


def render_price_list(c, p_type, title, buy_cb, back_cb):
    p = get_db_prices(p_type)
    kb = price_plan_kb(p_type, p, back_cb, buy_cb)
    bot.edit_message_text(title, c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "show_month_prices")
def show_month_prices(c):
    render_price_list(c, "PRICES_MONTH", "📅 ۱ ماهه (تک کاربره)", "goto_buy_month", "price_month")


@bot.callback_query_handler(func=lambda c: c.data == "price_vip")
def price_vip(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("♾ بدون محدودیت کاربری", "show_vip_prices", style="primary"))
    kb.add(btn("🔙 بازگشت", "price", style="danger"))
    bot.edit_message_text("VIP:", c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "show_vip_prices")
def show_vip_prices(c):
    render_price_list(c, "PRICES_VIP", "♾ بدون محدودیت + VIP (تخفیف)", "goto_buy_vip", "price_vip")


@bot.callback_query_handler(func=lambda c: c.data == "price_napsterv")
def price_napsterv(c):
    render_price_list(c, "PRICES_NAPSTERV", "🔮 سرور نپستر", "goto_buy_napsterv", "price")


@bot.callback_query_handler(func=lambda c: c.data == "price_napsterv_unlim")
def price_napsterv_unlim(c):
    render_price_list(c, "PRICES_NAPSTERV_UNLIM", "🌀 سرور نامحدود نپستر", "goto_buy_napsterv_unlim", "price")


@bot.callback_query_handler(func=lambda c: c.data == "price_wireguard")
def price_wireguard(c):
    render_price_list(c, "PRICES_WIREGUARD", "🔴 سرور وایرگارد", "goto_buy_wireguard", "price")


def render_volume_select(c, plan, p_type, back_cb, text):
    if not get_setting(SALE_PLAN_MAP_REVERSE.get(plan, "")):
        pass
    user_states[c.from_user.id] = {"state": "BUY_PLAN", "plan": plan}
    p = get_db_prices(p_type)
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in p.keys():
        kb.add(btn(v, f"vol_{v}", style="success"))
    kb.add(btn("🔙 بازگشت", back_cb, style="danger"))
    bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb)


SALE_PLAN_MAP_REVERSE = {v[0]: k for k, v in SALE_PLAN_MAP.items()}


@bot.callback_query_handler(func=lambda c: c.data == "goto_buy_month")
def goto_buy_month(c):
    if not get_setting('sale_month'):
        show_waiting_list_option(c, "MONTH", "۱ ماهه")
        return
    render_volume_select(c, "MONTH", "PRICES_MONTH", "show_month_prices", "حجم ۱ ماهه را انتخاب کنید:")


@bot.callback_query_handler(func=lambda c: c.data == "goto_buy_vip")
def goto_buy_vip(c):
    if not get_setting('sale_vip'):
        show_waiting_list_option(c, "VIP", "VIP")
        return
    render_volume_select(c, "VIP", "PRICES_VIP", "show_vip_prices", "حجم VIP را انتخاب کنید:")


@bot.callback_query_handler(func=lambda c: c.data == "goto_buy_napsterv")
def goto_buy_napsterv(c):
    if not get_setting('sale_napsterv'):
        show_waiting_list_option(c, "NAPSTERV", "نپستر")
        return
    render_volume_select(c, "NAPSTERV", "PRICES_NAPSTERV", "price_napsterv", "حجم سرور نپستر را انتخاب کنید:")


@bot.callback_query_handler(func=lambda c: c.data == "goto_buy_napsterv_unlim")
def goto_buy_napsterv_unlim(c):
    if not get_setting('sale_napsterv_unlim'):
        show_waiting_list_option(c, "NAPSTERV_UNLIM", "نامحدود نپستر")
        return
    render_volume_select(c, "NAPSTERV_UNLIM", "PRICES_NAPSTERV_UNLIM", "price_napsterv_unlim",
                          "حجم سرور نامحدود نپستر را انتخاب کنید:")


@bot.callback_query_handler(func=lambda c: c.data == "goto_buy_wireguard")
def goto_buy_wireguard(c):
    if not get_setting('sale_wireguard'):
        show_waiting_list_option(c, "WIREGUARD", "وایرگارد")
        return
    render_volume_select(c, "WIREGUARD", "PRICES_WIREGUARD", "price_wireguard", "حجم سرور وایرگارد را انتخاب کنید:")


# --------------- BUY ---------------
@bot.callback_query_handler(func=lambda c: c.data == "buy")
def buy(c):
    kb = types.InlineKeyboardMarkup()
    if get_setting('sale_month'):
        kb.add(btn("📅 ۱ ماهه", "buy_month", style="primary"))
    if get_setting('sale_vip'):
        kb.add(btn("♾ بدون محدودیت + VIP", "buy_vip", style="primary"))
    if get_setting('sale_napsterv'):
        kb.add(btn("🔮 سرور نپستر", "buy_napsterv", style="primary"))
    if get_setting('sale_napsterv_unlim'):
        kb.add(btn("🌀 سرور نامحدود نپستر", "buy_napsterv_unlim", style="primary"))
    if get_setting('sale_wireguard'):
        kb.add(btn("🔴 سرور وایرگارد", "buy_wireguard", style="primary"))
    kb.add(btn("🔙 بازگشت", "back", style="danger"))
    bot.edit_message_text("🛒 خرید سرویس:", c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "buy_month")
def buy_month(c):
    if not get_setting('sale_month'):
        show_waiting_list_option(c, "MONTH", "۱ ماهه")
        return
    user_states[c.from_user.id] = {"state": "BUY_PLAN", "plan": "MONTH"}
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("👤 تک کاربره", "buy_month_single", style="primary"))
    kb.add(btn("🔙 بازگشت", "buy", style="danger"))
    bot.edit_message_text("۱ ماهه:", c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "buy_month_single")
def buy_month_single(c):
    p = get_db_prices("PRICES_MONTH")
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in p.keys():
        kb.add(btn(v, f"vol_{v}", style="success"))
    kb.add(btn("🔙 بازگشت", "buy_month", style="danger"))
    bot.edit_message_text("حجم را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "buy_vip")
def buy_vip(c):
    if not get_setting('sale_vip'):
        show_waiting_list_option(c, "VIP", "VIP")
        return
    user_states[c.from_user.id] = {"state": "BUY_PLAN", "plan": "VIP"}
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("♾ بدون محدودیت کاربری", "buy_vip_unlim", style="primary"))
    kb.add(btn("🔙 بازگشت", "buy", style="danger"))
    bot.edit_message_text("VIP:", c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "buy_vip_unlim")
def buy_vip_unlim(c):
    p = get_db_prices("PRICES_VIP")
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in p.keys():
        kb.add(btn(v, f"vol_{v}", style="success"))
    kb.add(btn("🔙 بازگشت", "buy_vip", style="danger"))
    bot.edit_message_text("حجم را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "buy_napsterv")
def buy_napsterv(c):
    if not get_setting('sale_napsterv'):
        show_waiting_list_option(c, "NAPSTERV", "نپستر")
        return
    user_states[c.from_user.id] = {"state": "BUY_PLAN", "plan": "NAPSTERV"}
    p = get_db_prices("PRICES_NAPSTERV")
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in p.keys():
        kb.add(btn(v, f"vol_{v}", style="success"))
    kb.add(btn("🔙 بازگشت", "buy", style="danger"))
    bot.edit_message_text("حجم سرور نپستر را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "buy_napsterv_unlim")
def buy_napsterv_unlim(c):
    if not get_setting('sale_napsterv_unlim'):
        show_waiting_list_option(c, "NAPSTERV_UNLIM", "نامحدود نپستر")
        return
    user_states[c.from_user.id] = {"state": "BUY_PLAN", "plan": "NAPSTERV_UNLIM"}
    p = get_db_prices("PRICES_NAPSTERV_UNLIM")
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in p.keys():
        kb.add(btn(v, f"vol_{v}", style="success"))
    kb.add(btn("🔙 بازگشت", "buy", style="danger"))
    bot.edit_message_text("حجم سرور نامحدود نپستر را انتخاب کنید:", c.message.chat.id, c.message.message_id,
                           reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "buy_wireguard")
def buy_wireguard(c):
    if not get_setting('sale_wireguard'):
        show_waiting_list_option(c, "WIREGUARD", "وایرگارد")
        return
    user_states[c.from_user.id] = {"state": "BUY_PLAN", "plan": "WIREGUARD"}
    p = get_db_prices("PRICES_WIREGUARD")
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in p.keys():
        kb.add(btn(v, f"vol_{v}", style="success"))
    kb.add(btn("🔙 بازگشت", "buy", style="danger"))
    bot.edit_message_text("حجم سرور وایرگارد را انتخاب کنید:", c.message.chat.id, c.message.message_id,
                           reply_markup=kb)


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
        bot.answer_callback_query(c.id, "❌ابتدا حساب خود را شارژ کنید", show_alert=True)
        return
    user_states[uid] = {"state": "CONFIRM_BUY", "plan": plan, "volume": volume, "price": price,
                         "discount_applied": False, "final_price": price}

    kb = types.InlineKeyboardMarkup()
    kb.add(btn("✅ تایید", "final_buy", style="success"), btn("❌ لغو", "back", style="danger"))

    if get_setting('coupon_system_status'):
        kb.add(btn("🏷 دارم کد تخفیف", "apply_coupon_prompt", style="primary"))

    bot.send_message(uid, f"آیا از خرید سرویس {plan} حجم {volume} به مبلغ {format_p(price)} اطمینان دارید؟",
                      reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "final_buy")
def final_buy(c):
    uid = c.from_user.id
    data = user_states.get(uid, {})
    if data.get("state") != "CONFIRM_BUY":
        return
    price = data["price"]
    final_p = data.get("final_price", price)

    user = users_col.find_one({"user_id": uid})
    if user['balance'] < final_p:
        bot.answer_callback_query(c.id, "❌ موجودی ناکافی است.", show_alert=True)
        return

    users_col.update_one({"user_id": uid}, {"$inc": {"balance": -final_p, "configs_count": 1}})

    track_code = generate_track_code()

    res = orders_col.insert_one({
        "user_id": uid,
        "plan": data["plan"],
        "volume": data["volume"],
        "price": final_p,
        "status": "pending",
        "created_at": now_str(),
        "track_code": track_code
    })
    order_id = str(res.inserted_id)

    if data.get("coupon_code"):
        register_coupon_usage(data["coupon_code"], uid)

    bot.send_message(uid, f"⏳ سفارش شما ثبت شد. در حال ساخت کانفیگ...\nکد پیگیری: #{track_code}")
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("📤 ارسال کانفیگ", f"sendcfg_{order_id}", style="success"))

    bot.send_message(ADMIN_ID,
                      f"🛒 سفارش جدید\n\n🆔 OrderID: {order_id}\n📌 کد پیگیری: #{track_code}\n👤 کاربر: {uid}\n📦 پلن: {data['plan']}\n📊 حجم: {data['volume']}\n💵 مبلغ: {format_p(final_p)}",
                      reply_markup=kb)

    is_sub_system = get_setting('subadmin_system_status')
    if is_sub_system:
        subs = subadmins_col.find({"config_access": True})
        for sub in subs:
            try:
                bot.send_message(sub["user_id"],
                                  f"🛒 سفارش جدید (ادمین فرعی)\n\n🆔 OrderID: {order_id}\n📌 کد پیگیری: #{track_code}\n👤 کاربر: {uid}\n📦 پلن: {data['plan']}\n📊 حجم: {data['volume']}\n💵 مبلغ: {format_p(final_p)}",
                                  reply_markup=kb)
            except:
                pass

    masked = mask_user_id(uid)
    order_alert = f"✅ سفارش جدید ثبت شد\n━━━━━━━━━━━━━━━━\n📦 سرویس: [{data['plan']}]\n📊 حجم: [{data['volume']}]\n💳 مبلغ: {format_p(final_p)} تومان\n👤 کاربر: {masked}\n⌛ {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}\n━━━━━━━━━━━━━━━━\n🔒 AmirPlus | سرویس مطمئن"
    send_to_channels(order_alert)

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
    clicker_id = c.from_user.id

    if clicker_id != ADMIN_ID:
        sub_check = subadmins_col.find_one({"user_id": clicker_id})
        if not sub_check or not get_setting('subadmin_system_status') or not sub_check['config_access']:
            bot.answer_callback_query(c.id, "❌ شما دسترسی ارسال کانفیگ را ندارید.", show_alert=True)
            return

    order_id_str = c.data.split("_")[1]
    order = orders_col.find_one({"_id": ObjectId(order_id_str)})
    if not order:
        bot.answer_callback_query(c.id, "سفارش پیدا نشد", show_alert=True)
        return
    if order['status'] != "pending":
        bot.answer_callback_query(c.id, "این سفارش قبلا انجام شده", show_alert=True)
        return
    user_states[clicker_id] = {"state": "SEND_CONFIG", "order_id": order_id_str, "user_id": order['user_id']}
    bot.send_message(clicker_id, "📤 کانفیگ رو ارسال کن:\n(می‌عنوانید متن، فایل .conf یا هر نوع فایلی ارسال کنید)")


@bot.message_handler(content_types=['document'],
                      func=lambda m: user_states.get(m.from_user.id, {}).get("state") == "SEND_CONFIG")
def send_config_file_to_user(m):
    from bson.objectid import ObjectId
    sender_id = m.from_user.id
    data = user_states.get(sender_id)
    if not data:
        return
    order_id = data["order_id"]
    user_id = data["user_id"]
    caption = m.caption or "✅ فایل کانفیگ شما آماده است"

    kb_expire = None
    if get_setting('reminder_system_status'):
        kb_expire = types.InlineKeyboardMarkup()
        kb_expire.add(btn("📅 ثبت تاریخ انقضا", f"set_expire_{order_id}", style="primary"))

    bot.send_document(user_id, m.document.file_id, caption=f"✅ کانفیگ سفارش شما:\n\n{caption}")
    orders_col.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "done"}})
    bot.send_message(sender_id, f"✅ فایل کانفیگ برای سفارش {order_id} ارسال شد", reply_markup=kb_expire)

    # نوتیف به ادمین اصلی درصورت ارسال فایل کانفیگ توسط ادمین فرعی
    if sender_id != ADMIN_ID:
        try:
            bot.send_document(ADMIN_ID, m.document.file_id,
                               caption=f"📤 ادمین فرعی [{sender_id}] فایل کانفیگ برای سفارش [{order_id}] کاربر [{user_id}] ارسال کرد.")
        except:
            pass

    if get_setting('review_system_status'):
        Thread(target=schedule_review_poll, args=(user_id, order_id), daemon=True).start()

    user_states[sender_id] = None


@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("state") == "SEND_CONFIG")
def send_config_to_user(m):
    from bson.objectid import ObjectId
    sender_id = m.from_user.id
    if m.text == "/admin":
        user_states[sender_id] = None
        admin_panel(m)
        return
    data = user_states[sender_id]
    order_id = data["order_id"]
    user_id = data["user_id"]

    kb_expire = None
    if get_setting('reminder_system_status'):
        kb_expire = types.InlineKeyboardMarkup()
        kb_expire.add(btn("📅 ثبت تاریخ انقضا", f"set_expire_{order_id}", style="primary"))

    bot.send_message(user_id, f"✅ کانفیگ شما:\n\n{m.text}")
    orders_col.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "done"}})
    bot.send_message(sender_id, f"✅ کانفیگ برای سفارش {order_id} ارسال شد", reply_markup=kb_expire)

    # نوتیف به ادمین اصلی درصورت ارسال متن کانفیگ توسط ادمین فرعی
    if sender_id != ADMIN_ID:
        try:
            bot.send_message(ADMIN_ID,
                              f"📤 ادمین فرعی [{sender_id}] کانفیگ متنی برای سفارش [{order_id}] کاربر [{user_id}] ارسال کرد:\n\n{m.text}")
        except:
            pass

    if get_setting('review_system_status'):
        Thread(target=schedule_review_poll, args=(user_id, order_id), daemon=True).start()

    user_states[sender_id] = None


# --------------- ACCOUNT ---------------
@bot.callback_query_handler(func=lambda c: c.data == "account")
def account(c):
    d = users_col.find_one({"user_id": c.from_user.id})
    username = f"@{c.from_user.username}" if c.from_user.username else "❌ ندارد"
    status = "🚫 مسدود" if d.get("is_banned") or d.get("warnings", 0) >= 3 else "✅ فعال"
    level = get_user_level(d.get("success_payments", 0))
    text = f"📊 اطلاعات حساب کاربری شما در ربات: \n\n🔢 آیدی عددی : {c.from_user.id}\n🔆 یوزرنیم : {username}\n📱 وضعیت : {status}\n🏅 سطح کاربری : {level}\n💰 موجودی : {format_p(d['balance'])} تومان\n🏦 پرداخت های موفق : {d['success_payments']} عدد\n🛍 تعداد سرویس ها : {d['configs_count']} عدد\n⚠️ تعداد اخطار ها : {d['warnings']} عدد\n⏰ تاریخ عضویت : {d['join_date']}\n\n🤖 | @rafe_filter_GB_bot"
    bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=back_kb())


# --------------- SUPPORT ---------------
@bot.callback_query_handler(func=lambda c: c.data == "support")
def support(c):
    uid = c.from_user.id
    user = users_col.find_one({"user_id": uid})
    username_display = f"@{c.from_user.username}" if c.from_user.username else "ندارد"
    try:
        bot.send_message(ADMIN_ID,
                          f"📞 درخواست پشتیبانی\n\n" f"👤 نام: {c.from_user.first_name or ''}\n" f"🔆 یوزرنیم: {username_display}\n" f"🔢 آیدی: {uid}\n" f"💰 موجودی: {format_p(user['balance'] if user else 0)} تومان")
    except:
        pass
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("💬 ارتباط با پشتیبانی", url=f"https://t.me/{SUPPORT_ID.replace('@', '')}", style="primary"))
    kb.add(btn("🔙 بازگشت", "back", style="danger"))
    bot.edit_message_text("📞 برای ارتباط با پشتیبانی روی دکمه زیر کلیک کنید:", c.message.chat.id,
                           c.message.message_id, reply_markup=kb)


# --------------- BACK ---------------
@bot.callback_query_handler(func=lambda c: c.data == "back")
def back(c):
    bot.edit_message_text("👇 منوی اصلی:", c.message.chat.id, c.message.message_id, reply_markup=main_menu())


# --------------- ADMIN OTHER FUNCTIONS ---------------
@bot.callback_query_handler(func=lambda c: c.data == "adm_orders")
def adm_orders(c):
    if c.from_user.id != ADMIN_ID:
        return
    rows = list(orders_col.find({"status": "pending"}).sort("_id", -1).limit(20))
    if not rows:
        bot.send_message(ADMIN_ID, "سفارشی وجود ندارد")
        return
    txt = "📦 سفارشات باز:\n\n"
    for r in rows:
        txt += f"ID:{r['_id']} | U:{r['user_id']} | {r['plan']} | {r['volume']} | {format_p(r['price'])}\n{r['created_at']}\n---\n"
    bot.send_message(ADMIN_ID, txt)


@bot.callback_query_handler(func=lambda c: c.data == "adm_get_user")
def adm_get_user(c):
    if c.from_user.id != ADMIN_ID:
        return
    user_states[ADMIN_ID] = {"state": "ADM_GET_USER"}
    bot.send_message(ADMIN_ID, "آیدی عددی کاربر را ارسال کنید:")


@bot.message_handler(
    func=lambda m: user_states.get(ADMIN_ID, {}).get("state") == "ADM_GET_USER" and m.from_user.id == ADMIN_ID)
def adm_show_user(m):
    if not m.text.isdigit():
        bot.send_message(ADMIN_ID, "آیدی نامعتبر")
        return
    uid = int(m.text)
    d = users_col.find_one({"user_id": uid})
    if not d:
        bot.send_message(ADMIN_ID, "کاربر یافت نشد")
        return
    is_banned = d.get("is_banned") or d.get("warnings", 0) >= 3
    ban_txt = "🔓 آن‌بن کردن" if is_banned else "🚫 بن کردن"
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("➕ افزودن موجودی", f"adm_add_{uid}", style="success"), btn("➖ کسر موجودی", f"adm_sub_{uid}", style="danger"))
    kb.add(btn("⚠️ اخطار", f"adm_warn_{uid}", style="danger"), btn(ban_txt, f"adm_ban_{uid}", style="danger"))
    kb.add(btn("📩 پیام خصوصی", f"adm_pmsg_{uid}", style="primary"))
    bot.send_message(ADMIN_ID,
                      f"👤 کاربر {uid} \n\n💰 موجودی: {format_p(d['balance'])}\n🏦 پرداخت موفق: {d['success_payments']}\n🛍 سرویس‌ها: {d['configs_count']}\n⚠️ اخطار: {d['warnings']}\n🚫 وضعیت: {'مسدود' if is_banned else 'آزاد'}\n⏰ عضویت: {d['join_date']}",
                      reply_markup=kb)
    user_states[ADMIN_ID] = None


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_ban_"))
def adm_ban_toggle(c):
    if c.from_user.id != ADMIN_ID:
        return
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
    if c.from_user.id != ADMIN_ID:
        return
    uid = int(c.data.split("_")[2])
    user_states[ADMIN_ID] = {"state": "ADM_ADD", "uid": uid}
    bot.send_message(ADMIN_ID, "مبلغ برای افزودن را بفرست:")


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_sub_"))
def adm_sub(c):
    if c.from_user.id != ADMIN_ID:
        return
    uid = int(c.data.split("_")[2])
    user_states[ADMIN_ID] = {"state": "ADM_SUB", "uid": uid}
    bot.send_message(ADMIN_ID, "مبلغ برای کسر را بفرست:")


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_warn_"))
def adm_warn(c):
    if c.from_user.id != ADMIN_ID:
        return
    uid = int(c.data.split("_")[2])
    users_col.update_one({"user_id": uid}, {"$inc": {"warnings": 1}})
    bot.send_message(uid, "⚠️ از سمت ادمین اخطار دریافت کردید")
    bot.answer_callback_query(c.id, "ثبت شد")


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_pmsg_"))
def adm_pmsg_start(c):
    if c.from_user.id != ADMIN_ID:
        return
    uid = c.data.split("_")[2]
    user_states[ADMIN_ID] = {"state": "ADM_SEND_PMSG", "target": uid}
    bot.send_message(ADMIN_ID, f"پیام خود را برای کاربر {uid} بنویسید:")


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "ADM_SEND_PMSG")
def adm_pmsg_send(m):
    target = user_states[ADMIN_ID]["target"]
    try:
        bot.send_message(target, f"📩 پیام جدید از مدیریت:\n\n{m.text}")
        bot.send_message(ADMIN_ID, "✅ با موفقیت ارسال شد")
    except:
        bot.send_message(ADMIN_ID, "❌ ارسال ناموفق (شاید بلاک کرده)")
    user_states[ADMIN_ID] = None


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") in ["ADM_ADD", "ADM_SUB"])
def adm_balance_edit(m):
    st = user_states.get(ADMIN_ID, {})
    if not m.text.isdigit():
        bot.send_message(ADMIN_ID, "عدد بفرست")
        return
    amt = int(m.text)
    uid = st["uid"]
    if st["state"] == "ADM_ADD":
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
        bot.send_message(uid, f"💰 {format_p(amt)} تومان به حسابت اضافه شد (ادمین)")
    else:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": -amt}})
        bot.send_message(uid, f"💰 {format_p(amt)} تومان از حسابت کسر شد (ادمین)")
    user_states[ADMIN_ID] = None
    bot.send_message(ADMIN_ID, "انجام شد")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "ADM_BC")
def do_broadcast(m):
    users = users_col.find({}, {"user_id": 1})
    ok = 0
    for u in users:
        try:
            bot.send_message(u['user_id'], m.text)
            ok += 1
        except:
            pass
    user_states[ADMIN_ID] = None
    bot.send_message(ADMIN_ID, f"ارسال شد برای {ok} نفر")


# --------------- مدیریت قیمت‌ها ---------------
@bot.callback_query_handler(func=lambda c: c.data == "adm_change_prices")
def adm_change_prices(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("📅 قیمت ۱ ماهه", "FIXEDsetp_MONTH", style="primary"), btn("♾ قیمت VIP", "FIXEDsetp_VIP", style="primary"))
    kb.add(btn("🔮 قیمت نپستر", "FIXEDsetp_NAPSTERV", style="primary"), btn("🌀 قیمت نپستر نامحدود", "FIXEDsetp_NAPSTERV_UNLIM", style="primary"))
    kb.add(btn("🔴 قیمت وایرگارد", "FIXEDsetp_WIREGUARD", style="primary"))
    kb.add(btn("🔙 بازگشت", "admin_back", style="danger"))
    bot.edit_message_text("⚙️ مدیریت تعرفه‌ها و حجم سرورها:\nکدام دسته‌بندی را مدیریت می‌کنید؟", c.message.chat.id,
                           c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("FIXEDsetp_"))
def FIXED_adm_setp_plan(c):
    plan = c.data.replace("FIXEDsetp_", "")
    kb = types.InlineKeyboardMarkup(row_width=1)
    p = get_db_prices(f"PRICES_{plan}")
    for v in list(p.keys()):
        kb.add(
            btn(f"⚙️ {v} ({format_p(p[v])} ت)", f"FIXEDedit_{plan}:::{v}", style="primary"),
            btn(f"❌ حذف حجم {v}", f"FIXEDdel_{plan}:::{v}", style="danger")
        )
    kb.add(btn("➕ افزودن حجم جدید به این سرویس", f"FIXEDadd_{plan}", style="success"))
    kb.add(btn("🔙 بازگشت", "adm_change_prices", style="danger"))
    bot.edit_message_text(f"لیست حجم‌های فعلی پلن {plan}:\nجهت تغییر قیمت یا حذف انتخاب کنید یا حجم جدید بسازید:",
                           c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("FIXEDadd_"))
def FIXED_adm_addp_start(c):
    plan = c.data.replace("FIXEDadd_", "")
    user_states[ADMIN_ID] = {"state": "FIXED_ADD_VOLUME_NAME", "plan": plan}
    bot.send_message(ADMIN_ID, f"نام حجم جدید برای پلن {plan} را وارد کنید (مثلا: 10G یا 50G):")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "FIXED_ADD_VOLUME_NAME", content_types=['text'])
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


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "FIXED_SETTING_PRICE", content_types=['text'])
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
    bot.send_message(ADMIN_ID,
                      f"✅ تنظیمات در دیتابیس ذخیره شد.\n{data['plan']} حجم {data['vol']} به قیمت {format_p(new_p)} تومان تغییر یافت.")
    user_states[ADMIN_ID] = None


# --------------- مدیریت عضویت اجباری ---------------
@bot.callback_query_handler(func=lambda c: c.data == "adm_fjoin_mgr")
def adm_fjoin_mgr(c):
    if c.from_user.id != ADMIN_ID:
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("📢 مدیریت کانال‌ها", "fjm_channel", style="primary"), btn("👥 مدیریت گروه‌ها", "fjm_group", style="primary"))
    kb.add(btn("🔙 بازگشت", "admin_back", style="danger"))
    bot.edit_message_text("🛡 بخش مدیریت عضویت اجباری:\nیکی از موارد زیر را انتخاب کنید:", c.message.chat.id,
                           c.message.message_id, reply_markup=kb)


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
            kb.add(btn(f"❌ حذف {item['chat_id']}", f"fjdel_{item['_id']}", style="danger"))
    kb.add(btn(f"➕ افزودن {label} جدید", f"fjadd_{target_type}", style="success"))
    kb.add(btn("🔙 بازگشت", "adm_fjoin_mgr", style="danger"))
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
        bot.send_message(ADMIN_ID, "❌ آیدی باید با @ شروع شود.")
        return
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
# ویژگی‌های موجود
# =====================================================================
announcements_col = db['announcements']
tutorial_col = db['tutorials']

for s_new in ['tutorial_status']:
    if not settings_col.find_one({"key": s_new}):
        settings_col.insert_one({"key": s_new, "value": 1})

if not settings_col.find_one({"key": "server_status_text"}):
    settings_col.insert_one({"key": "server_status_text", "value": "🟢 همه سرورها آنلاین هستند."})

default_tutorials = [
    {"os": "android", "label": "📱 اندروید", "type": "text"},
    {"os": "ios", "label": "🍎 iOS (آیفون)", "type": "text"},
    {"os": "windows", "label": "💻 ویندوز", "type": "text"},
    {"os": "mac", "label": "🖥 مک", "type": "text"},
]
for tut in default_tutorials:
    if not tutorial_col.find_one({"os": tut["os"]}):
        tutorial_col.insert_one(tut)

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
spam_tracker = {}
spam_muted = {}


def check_spam(uid):
    now_ts = time.time()
    if uid in spam_muted:
        if now_ts < spam_muted[uid]:
            return True
        else:
            del spam_muted[uid]
    if uid not in spam_tracker:
        spam_tracker[uid] = []
    spam_tracker[uid] = [t for t in spam_tracker[uid] if now_ts - t < 5]
    spam_tracker[uid].append(now_ts)
    if len(spam_tracker[uid]) > 4:
        spam_muted[uid] = now_ts + 30
        spam_tracker[uid] = []
        return True
    return False


# ==================== میدلور یکپارچه (ادغام ضد اسپم + last_activity) ====================
_orig_process_new_updates = bot.process_new_updates


def full_middleware(updates):
    """میدلور واحد: هم ضداسپم و هم بروزرسانی last_activity را انجام می‌دهد.
    جایگزین دو میدلور جداگانه قبلی که با هم تداخل داشتند."""
    filtered_updates = []
    for update in updates:
        uid = None
        if update.callback_query:
            uid = update.callback_query.from_user.id
        elif update.message:
            uid = update.message.from_user.id

        if uid is not None:
            # بروزرسانی last_activity برای هر کاربری که تعامل می‌کند
            try:
                users_col.update_one({"user_id": uid}, {"$set": {"last_activity": datetime.now()}})
            except:
                pass

            # بررسی اسپم فقط برای callback query ها و به جز ادمین اصلی
            if update.callback_query and uid != ADMIN_ID and check_spam(uid):
                remaining = int(spam_muted.get(uid, time.time()) - time.time())
                if remaining < 0:
                    remaining = 0
                try:
                    bot.answer_callback_query(update.callback_query.id,
                                               f"⛔ اسپم شناسایی شد!\nلطفاً {remaining} ثانیه صبر کنید.",
                                               show_alert=True)
                except:
                    pass
                continue

        filtered_updates.append(update)

    _orig_process_new_updates(filtered_updates)


bot.process_new_updates = full_middleware

# ==================== ویژگی ۲: وضعیت سرورها ====================
@bot.callback_query_handler(func=lambda c: c.data == "server_status")
def server_status(c):
    res = settings_col.find_one({"key": "server_status_text"})
    status_text = res['value'] if res else "وضعیت سرورها در دسترس نیست."
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("🔄 بروزرسانی", "server_status", style="primary"))
    kb.add(btn("🔙 بازگشت", "back", style="danger"))
    bot.edit_message_text(f"🖥 وضعیت سرورها:\n\n{status_text}", c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "adm_server_status")
def adm_server_status(c):
    if c.from_user.id != ADMIN_ID: return
    res = settings_col.find_one({"key": "server_status_text"})
    current = res['value'] if res else ""
    user_states[ADMIN_ID] = {"state": "ADM_SET_SERVER_STATUS"}
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("🔙 بازگشت", "admin_back", style="danger"))
    bot.edit_message_text(f"🖥 وضعیت فعلی سرورها:\n\n{current}\n\n✏️ متن جدید را ارسال کنید:", c.message.chat.id,
                           c.message.message_id, reply_markup=kb)


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "ADM_SET_SERVER_STATUS")
def save_server_status(m):
    settings_col.update_one({"key": "server_status_text"}, {"$set": {"value": m.text.strip()}})
    bot.send_message(ADMIN_ID, "✅ وضعیت سرورها بروزرسانی شد.")
    user_states[ADMIN_ID] = None


# ==================== ویژگی ۳: اطلاعیه هوشمند ====================
@bot.callback_query_handler(func=lambda c: c.data == "announcements")
def announcements_list(c):
    items = list(announcements_col.find({}).sort("_id", -1).limit(10))
    if not items:
        bot.edit_message_text("📢 اطلاعیه‌ای موجود نیست.", c.message.chat.id, c.message.message_id, reply_markup=back_kb())
        return
    txt = "📢 آخرین اطلاعیه‌ها:\n\n"
    for item in items:
        txt += f"🔹 {item.get('date', '')}\n{item.get('text', '')}\n━━━━━━━━━━━━━━━━\n"
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=back_kb())


@bot.callback_query_handler(func=lambda c: c.data == "adm_smart_announce")
def adm_smart_announce(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state": "ADM_SMART_ANNOUNCE"}
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("🔙 بازگشت", "admin_back", style="danger"))
    bot.edit_message_text(
        "📢 اطلاعیه هوشمند:\n\nمتن اطلاعیه را ارسال کنید.\nپیام پس از ۶۰ ثانیه از چت کاربران حذف خواهد شد و در تاریخچه ذخیره می‌شود.",
        c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "ADM_SMART_ANNOUNCE")
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
        except:
            pass
    user_states[ADMIN_ID] = None
    bot.send_message(ADMIN_ID, f"✅ اطلاعیه برای {ok} نفر ارسال شد. پس از ۶۰ ثانیه حذف می‌شود.")

    def delete_after_60(messages):
        time.sleep(60)
        for item in messages:
            try:
                bot.delete_message(item['uid'], item['mid'])
            except:
                pass

    Thread(target=delete_after_60, args=(sent_messages,), daemon=True).start()


# ==================== ویژگی ۴: سطح‌بندی کاربران ====================
def get_user_level(success_payments):
    if success_payments >= 10:
        return "💎 VIP"
    elif success_payments >= 6:
        return "🥇 طلایی"
    elif success_payments >= 3:
        return "🥈 نقره‌ای"
    else:
        return "🥉 برنزی"


@bot.callback_query_handler(func=lambda c: c.data == "price_vip_exclusive")
def price_vip_exclusive(c):
    uid = c.from_user.id
    user = users_col.find_one({"user_id": uid})
    if not user or get_user_level(user.get("success_payments", 0)) != "💎 VIP":
        bot.answer_callback_query(c.id, "❌ این بخش فقط برای کاربران VIP قابل دسترس است.", show_alert=True)
        return
    txt = "💎 سرور اختصاصی VIP\n\nبرای دریافت اطلاعات سرور اختصاصی VIP با پشتیبانی تماس بگیرید."
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("📞 تماس با پشتیبانی", url=f"https://t.me/{SUPPORT_ID.replace('@', '')}", style="primary"))
    kb.add(btn("🔙 بازگشت", "price", style="danger"))
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=kb)


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
    kb.add(btn(f"📅 امروز: {today_count} نفر", "adm_active_stats", style="primary"))
    kb.add(btn(f"📆 هفته گذشته: {week_count} نفر", "adm_active_stats", style="primary"))
    kb.add(btn(f"🗓 ماه گذشته: {month_count} نفر", "adm_active_stats", style="primary"))
    kb.add(btn(f"👥 کل کاربران: {total_count} نفر", "adm_active_stats", style="primary"))
    kb.add(btn("🔙 بازگشت", "admin_back", style="danger"))
    bot.edit_message_text(
        f"📊 آمار کاربران فعال:\n\n"
        f"📅 امروز: {today_count} نفر\n"
        f"📆 هفته گذشته: {week_count} نفر\n"
        f"🗓 ماه گذشته: {month_count} نفر\n"
        f"👥 کل کاربران: {total_count} نفر",
        c.message.chat.id, c.message.message_id, reply_markup=kb
    )


# ==================== ویژگی ۶: آموزش اتصال ====================
@bot.callback_query_handler(func=lambda c: c.data == "tutorial")
def tutorial_menu(c):
    res = settings_col.find_one({"key": "tutorial_status"})
    if res and res['value'] == 0:
        bot.answer_callback_query(c.id, "⚠️ بخش آموزش در حال حاضر توسط ادمین بسته شده است.", show_alert=True)
        return
    items = list(tutorial_col.find({}))
    kb = types.InlineKeyboardMarkup()
    for item in items:
        kb.add(btn(item['label'], f"tut_os_{item['os']}", style="primary"))
    kb.add(btn("🔙 بازگشت", "back", style="danger"))
    bot.edit_message_text("📚 آموزش اتصال\n\nسیستم‌عامل خود را انتخاب کنید:", c.message.chat.id, c.message.message_id,
                           reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("tut_os_"))
def tutorial_os_servers(c):
    os_key = c.data.replace("tut_os_", "")
    item = tutorial_col.find_one({"os": os_key})
    if not item:
        bot.answer_callback_query(c.id, "سیستم‌عامل یافت نشد", show_alert=True)
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("🔵 سرور V2ray", f"tut_show_{os_key}_v2ray", style="primary"))
    kb.add(btn("🟣 سرور Npv", f"tut_show_{os_key}_npv", style="primary"))
    kb.add(btn("🔴 سرور Wireguard", f"tut_show_{os_key}_wireguard", style="primary"))
    kb.add(btn("🔙 بازگشت", "tutorial", style="danger"))
    bot.edit_message_text(f"📚 آموزش {item['label']}\n\nنوع سرور را انتخاب کنید:", c.message.chat.id,
                           c.message.message_id, reply_markup=kb)


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
    kb.add(btn("🔙 بازگشت", f"tut_os_{os_key}", style="danger"))
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


def send_multi_content(user_id, items, header, back_cb):
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("🔙 بازگشت", back_cb, style="danger"))
    for i, item in enumerate(items):
        t = item.get("type", "text")
        content = item.get("content", "")
        file_id = item.get("file_id")
        caption = header + content if i == 0 else content
        if t == "text":
            bot.send_message(user_id, caption, reply_markup=kb if i == len(items) - 1 else None)
        elif t == "photo" and file_id:
            bot.send_photo(user_id, file_id, caption=caption, reply_markup=kb if i == len(items) - 1 else None)
        elif t == "video" and file_id:
            bot.send_video(user_id, file_id, caption=caption, reply_markup=kb if i == len(items) - 1 else None)
        elif t == "document" and file_id:
            bot.send_document(user_id, file_id, caption=caption, reply_markup=kb if i == len(items) - 1 else None)


# ==================== مدیریت آموزش‌ها توسط ادمین ====================
@bot.callback_query_handler(func=lambda c: c.data == "adm_tutorial_mgr")
def adm_tutorial_mgr(c):
    if c.from_user.id != ADMIN_ID: return
    res = settings_col.find_one({"key": "tutorial_status"})
    status = "✅ باز" if (res and res['value'] == 1) else "❌ بسته"
    items = list(tutorial_col.find({}))
    kb = types.InlineKeyboardMarkup()
    kb.add(btn(f"بخش آموزش: {status}", "TUT_SYS_TOG", style="primary"))
    kb.add(btn("➕ افزودن سیستم‌عامل جدید", "tut_adm_add_os", style="success"))
    for item in items:
        kb.add(
            btn(f"✏️ {item['label']}", f"tut_adm_manage_{item['os']}", style="primary"),
            btn(f"🗑 حذف {item['label']}", f"tut_adm_del_os_{item['os']}", style="danger")
        )
    kb.add(btn("🔙 بازگشت", "admin_back", style="danger"))
    bot.edit_message_text("📚 مدیریت آموزش اتصال:", c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("tut_adm_del_os_"))
def tut_adm_del_os(c):
    if c.from_user.id != ADMIN_ID: return
    os_key = c.data.replace("tut_adm_del_os_", "")
    item = tutorial_col.find_one({"os": os_key})
    if not item:
        bot.answer_callback_query(c.id, "یافت نشد", show_alert=True)
        return
    tutorial_col.delete_one({"os": os_key})
    for srv in ["v2ray", "npv", "wireguard"]:
        settings_col.delete_one({"key": f"tut_content_{os_key}_{srv}"})
    bot.answer_callback_query(c.id, f"✅ {item['label']} با موفقیت حذف شد", show_alert=True)
    adm_tutorial_mgr(c)


@bot.callback_query_handler(func=lambda c: c.data.startswith("tut_adm_manage_"))
def tut_adm_manage_os(c):
    if c.from_user.id != ADMIN_ID: return
    os_key = c.data.replace("tut_adm_manage_", "")
    item = tutorial_col.find_one({"os": os_key})
    if not item: return
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("🔵 ثبت آموزش V2ray", f"tut_adm_set_{os_key}_v2ray", style="primary"))
    kb.add(btn("🟣 ثبت آموزش Npv", f"tut_adm_set_{os_key}_npv", style="primary"))
    kb.add(btn("🔴 ثبت آموزش Wireguard", f"tut_adm_set_{os_key}_wireguard", style="primary"))
    kb.add(btn("🔙 بازگشت", "adm_tutorial_mgr", style="danger"))
    bot.edit_message_text(f"📚 مدیریت آموزش‌های {item['label']}:\nکدام سرور را ویرایش می‌کنید؟", c.message.chat.id,
                           c.message.message_id, reply_markup=kb)


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
        "collected": [],
        "os_label": os_label,
        "srv_label": srv_label
    }
    bot.send_message(ADMIN_ID,
                      f"📝 ثبت آموزش {os_label} - {srv_label}\n\n" f"محتوای آموزش را ارسال کنید:\n" f"• می‌توانید متن، عکس، ویدیو، یا فایل ارسال کنید\n" f"• می‌توانید چندین محتوا ارسال کنید\n\n" f"وقتی آماده بودید، دکمه زیر را بزنید:")
    kb2 = types.InlineKeyboardMarkup()
    kb2.add(btn("✅ ثبت آموزش", f"tut_adm_save_{os_key}_{srv_type}", style="success"))
    kb2.add(btn("❌ لغو", f"tut_adm_manage_{os_key}", style="danger"))
    bot.send_message(ADMIN_ID, "👆 محتوا را ارسال کنید، سپس دکمه ثبت را بزنید:", reply_markup=kb2)


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "TUT_COLLECTING_CONTENT", content_types=['text'])
def tut_collect_text(m):
    data = user_states.get(ADMIN_ID, {})
    if data.get("state") != "TUT_COLLECTING_CONTENT": return
    data["collected"].append({"type": "text", "content": m.text.strip(), "file_id": None})
    bot.send_message(ADMIN_ID, f"✅ متن دریافت شد. می‌توانید محتوای بیشتری ارسال کنید یا دکمه ثبت را بزنید.")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "TUT_COLLECTING_CONTENT", content_types=['photo'])
def tut_collect_photo(m):
    data = user_states.get(ADMIN_ID, {})
    if data.get("state") != "TUT_COLLECTING_CONTENT": return
    data["collected"].append({"type": "photo", "content": m.caption or "", "file_id": m.photo[-1].file_id})
    bot.send_message(ADMIN_ID, f"✅ عکس دریافت شد. می‌توانید محتوای بیشتری ارسال کنید یا دکمه ثبت را بزنید.")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "TUT_COLLECTING_CONTENT", content_types=['video'])
def tut_collect_video(m):
    data = user_states.get(ADMIN_ID, {})
    if data.get("state") != "TUT_COLLECTING_CONTENT": return
    data["collected"].append({"type": "video", "content": m.caption or "", "file_id": m.video.file_id})
    bot.send_message(ADMIN_ID, f"✅ ویدیو دریافت شد. می‌توانید محتوای بیشتری ارسال کنید یا دکمه ثبت را بزنید.")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "TUT_COLLECTING_CONTENT", content_types=['document'])
def tut_collect_document(m):
    data = user_states.get(ADMIN_ID, {})
    if data.get("state") != "TUT_COLLECTING_CONTENT": return
    data["collected"].append({"type": "document", "content": m.caption or "", "file_id": m.document.file_id})
    bot.send_message(ADMIN_ID, f"✅ فایل دریافت شد. می‌توانید محتوای بیشتری ارسال کنید یا دکمه ثبت را بزنید.")


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
    save_value = collected[0] if len(collected) == 1 else {"type": "multi", "items": collected}
    settings_col.update_one({"key": content_key}, {"$set": {"value": save_value}}, upsert=True)
    bot.answer_callback_query(c.id, "✅ آموزش با موفقیت ذخیره شد", show_alert=True)
    os_label = data.get("os_label", os_key)
    srv_label = data.get("srv_label", srv_type)
    bot.send_message(ADMIN_ID, f"✅ آموزش {os_label} - {srv_label} با {len(collected)} محتوا ذخیره شد.")
    user_states[ADMIN_ID] = None


@bot.callback_query_handler(func=lambda c: c.data == "TUT_SYS_TOG")
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


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "TUT_WAIT_NEW_OS_NAME")
def tut_save_new_os_name(m):
    os_key = m.text.strip().lower().replace(" ", "_")
    user_states[ADMIN_ID] = {"state": "TUT_WAIT_NEW_OS_LABEL", "os": os_key}
    bot.send_message(ADMIN_ID, f"کلید: {os_key}\nحالا نام نمایشی را با ایموجی وارد کنید (مثل: 🐧 لینوکس):")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "TUT_WAIT_NEW_OS_LABEL")
def tut_save_new_os_label(m):
    label = m.text.strip()
    os_key = user_states[ADMIN_ID]["os"]
    tutorial_col.insert_one({"os": os_key, "label": label, "type": "text"})
    for srv in ["v2ray", "npv", "wireguard"]:
        key = f"tut_content_{os_key}_{srv}"
        if not settings_col.find_one({"key": key}):
            settings_col.insert_one({
                "key": key,
                "value": {"type": "text", "content": f"آموزش {srv} برای {label} هنوز تنظیم نشده است.",
                          "file_id": None}
            })
    bot.send_message(ADMIN_ID, f"✅ سیستم‌عامل '{label}' با کلید '{os_key}' اضافه شد.")
    user_states[ADMIN_ID] = None


# =====================================================================
# ویژگی جدید ۷: سیستم اکانت تست
# =====================================================================
@bot.callback_query_handler(func=lambda c: c.data == "test_account")
def test_account_menu(c):
    uid = c.from_user.id
    if not get_setting('test_status'):
        bot.answer_callback_query(c.id, "⚠️ بخش اکانت تست در حال حاضر بسته است.", show_alert=True)
        return
    if not is_member(uid):
        kb = types.InlineKeyboardMarkup()
        items = list(fjoin_col.find({}))
        for item in items:
            label = "📢 کانال" if item['type'] == "channel" else "👥 گروه"
            url = f"https://t.me/{item['chat_id'].replace('@', '')}"
            kb.add(btn(label, url=url, style="primary"))
        kb.add(btn("✅ عضو شدم", "test_check_join", style="primary"))
        kb.add(btn("🔙 بازگشت", "back", style="danger"))
        bot.edit_message_text("⚠️ برای دریافت اکانت تست، ابتدا باید عضو کانال و گروه ما باشید:", c.message.chat.id,
                               c.message.message_id, reply_markup=kb)
        return

    test_buttons_doc = settings_col.find_one({"key": "test_buttons"})
    test_buttons = test_buttons_doc['value'] if test_buttons_doc else []
    if not test_buttons:
        bot.edit_message_text("⚠️ در حال حاضر هیچ نوع تست فعالی موجود نیست.", c.message.chat.id, c.message.message_id,
                               reply_markup=back_kb())
        return
    kb = types.InlineKeyboardMarkup()
    for tb in test_buttons:
        btn_key = tb['key']
        btn_label = tb['label']
        already_used = test_used_col.find_one({"user_id": uid, "test_key": btn_key})
        if already_used:
            kb.add(btn(f"✅ {btn_label} (قبلاً دریافت شد)", f"test_already_{btn_key}", style="primary"))
        else:
            kb.add(btn(f"🎁 {btn_label}", f"test_get_{btn_key}", style="success"))
    kb.add(btn("🔙 بازگشت", "back", style="danger"))
    bot.edit_message_text("🎁 اکانت تست\n\nنوع سرور تست را انتخاب کنید:", c.message.chat.id, c.message.message_id,
                           reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "test_check_join")
def test_check_join(c):
    uid = c.from_user.id
    if is_member(uid):
        test_account_menu(c)
    else:
        bot.answer_callback_query(c.id, "هنوز عضو کانال یا گروه نشدی!", show_alert=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith("test_already_"))
def test_already(c):
    bot.answer_callback_query(c.id, "⚠️ شما قبلاً این تست را دریافت کرده‌اید و امکان دریافت مجدد وجود ندارد.",
                               show_alert=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith("test_get_"))
def test_get(c):
    uid = c.from_user.id
    btn_key = c.data.replace("test_get_", "")
    if not get_setting('test_status'):
        bot.answer_callback_query(c.id, "⚠️ بخش اکانت تست بسته است.", show_alert=True)
        return
    if not is_member(uid):
        bot.answer_callback_query(c.id, "⚠️ ابتدا باید عضو کانال و گروه ما باشید.", show_alert=True)
        return
    already_used = test_used_col.find_one({"user_id": uid, "test_key": btn_key})
    if already_used:
        bot.answer_callback_query(c.id, "⚠️ شما قبلاً این تست را دریافت کرده‌اید.", show_alert=True)
        return
    test_acc = test_accounts_col.find_one({"btn_key": btn_key, "used": False})
    if not test_acc:
        bot.answer_callback_query(c.id, "⚠️ فعلاً تست در مخزن موجود نیست!", show_alert=True)
        bot.edit_message_text("❌ متأسفانه در حال حاضر اکانت تست در مخزن موجود نیست.\nلطفاً بعداً مراجعه کنید.",
                               c.message.chat.id, c.message.message_id, reply_markup=back_kb())
        return

    test_accounts_col.update_one({"_id": test_acc["_id"]}, {"$set": {"used": True, "given_to": uid, "given_at": now_str()}})
    test_used_col.insert_one({"user_id": uid, "test_key": btn_key, "account_id": str(test_acc["_id"]), "date": now_str()})

    test_buttons_doc = settings_col.find_one({"key": "test_buttons"})
    test_buttons = test_buttons_doc['value'] if test_buttons_doc else []
    btn_label = next((b['label'] for b in test_buttons if b['key'] == btn_key), btn_key)

    remaining_count = test_accounts_col.count_documents({"btn_key": btn_key, "used": False})
    if remaining_count < 5:
        try:
            bot.send_message(ADMIN_ID, f"⚠️ هشدار! موجودی تست [{btn_label}] فقط {remaining_count} تا مونده!")
        except:
            pass

    msg = f"🎁 اکانت تست {btn_label}\n\n"
    msg += f"📋 اطلاعات اکانت:\n{test_acc['account_data']}\n\n"
    msg += f"📊 حجم: ۵۰۰ مگ\n"
    msg += f"⏰ مهلت استفاده: ۱ روز\n"
    msg += f"👤 حداکثر اتصال: ۱\n\n"
    msg += f"⚠️ این اکانت تست بوده و فقط یک بار قابل استفاده است."
    bot.send_message(uid, msg)
    bot.edit_message_text("✅ اکانت تست شما ارسال شد!\nبه پیام‌های خود مراجعه کنید.", c.message.chat.id,
                           c.message.message_id, reply_markup=back_kb())


# ---- بخش ادمین: مدیریت اکانت تست ----
@bot.callback_query_handler(func=lambda c: c.data == "adm_test_mgr")
def adm_test_mgr(c):
    if c.from_user.id != ADMIN_ID: return
    test_buttons_doc = settings_col.find_one({"key": "test_buttons"})
    test_buttons = test_buttons_doc['value'] if test_buttons_doc else []
    t_status = "✅ فعال" if get_setting('test_status') else "❌ غیرفعال"
    kb = types.InlineKeyboardMarkup()
    kb.add(btn(f"وضعیت تست: {t_status}", "TEST_SYS_TOG", style="primary"))
    kb.add(btn("➕ افزودن نوع تست جدید", "adm_test_add_btn", style="success"))
    for tb in test_buttons:
        btn_key = tb['key']
        btn_label = tb['label']
        total = test_accounts_col.count_documents({"btn_key": btn_key})
        used = test_accounts_col.count_documents({"btn_key": btn_key, "used": True})
        remaining = total - used
        kb.add(btn(f"📦 {btn_label} | موجود: {remaining} | داده‌شده: {used}", f"adm_test_detail_{btn_key}", style="primary"))
    kb.add(btn("🔙 بازگشت", "admin_back", style="danger"))
    bot.edit_message_text("🎁 مدیریت اکانت تست\n\nوضعیت هر نوع تست را مشاهده و مدیریت کنید:", c.message.chat.id,
                           c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "TEST_SYS_TOG")
def adm_tog_test(c):
    if c.from_user.id != ADMIN_ID: return
    current = get_setting('test_status')
    settings_col.update_one({"key": "test_status"}, {"$set": {"value": 0 if current else 1}})
    adm_test_mgr(c)


@bot.callback_query_handler(func=lambda c: c.data == "adm_test_add_btn")
def adm_test_add_btn(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state": "ADM_TEST_WAIT_BTN_KEY"}
    bot.send_message(ADMIN_ID, "نام کلید برای نوع تست جدید را وارد کنید (فقط انگلیسی، مثلاً: wireguard یا v2ray):")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "ADM_TEST_WAIT_BTN_KEY")
def adm_test_save_btn_key(m):
    btn_key = m.text.strip().lower().replace(" ", "_")
    user_states[ADMIN_ID] = {"state": "ADM_TEST_WAIT_BTN_LABEL", "btn_key": btn_key}
    bot.send_message(ADMIN_ID, f"کلید: {btn_key}\nحالا نام نمایشی دکمه را وارد کنید (مثلاً: وایرگارد یا WireGuard):")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "ADM_TEST_WAIT_BTN_LABEL")
def adm_test_save_btn_label(m):
    btn_label = m.text.strip()
    btn_key = user_states[ADMIN_ID]["btn_key"]
    test_buttons_doc = settings_col.find_one({"key": "test_buttons"})
    test_buttons = test_buttons_doc['value'] if test_buttons_doc else []
    if any(b['key'] == btn_key for b in test_buttons):
        bot.send_message(ADMIN_ID, f"❌ کلید '{btn_key}' قبلاً وجود دارد. یک کلید دیگر انتخاب کنید.")
        user_states[ADMIN_ID] = None
        return
    test_buttons.append({"key": btn_key, "label": btn_label})
    settings_col.update_one({"key": "test_buttons"}, {"$set": {"value": test_buttons}})
    bot.send_message(ADMIN_ID, f"✅ نوع تست '{btn_label}' با کلید '{btn_key}' اضافه شد.\nحالا می‌توانید اکانت‌های تست برای آن اضافه کنید.")
    user_states[ADMIN_ID] = None


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_test_detail_") and not c.data.startswith(
    "adm_test_detail_{"))
def adm_test_detail(c):
    if c.from_user.id != ADMIN_ID: return
    btn_key = c.data.replace("adm_test_detail_", "")
    test_buttons_doc = settings_col.find_one({"key": "test_buttons"})
    test_buttons = test_buttons_doc['value'] if test_buttons_doc else []
    btn_label = next((b['label'] for b in test_buttons if b['key'] == btn_key), btn_key)
    total = test_accounts_col.count_documents({"btn_key": btn_key})
    used = test_accounts_col.count_documents({"btn_key": btn_key, "used": True})
    remaining = total - used
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("➕ افزودن اکانت‌های تست", f"adm_test_add_acc_{btn_key}", style="success"))
    kb.add(btn("🗑 حذف این نوع تست", f"adm_test_del_btn_{btn_key}", style="danger"))
    kb.add(btn("🔙 بازگشت", "adm_test_mgr", style="danger"))
    bot.edit_message_text(
        f"📦 مدیریت تست: {btn_label}\n\n📊 کل اکانت‌ها: {total}\n✅ داده‌شده: {used}\n🔵 موجود در مخزن: {remaining}\n\nبرای افزودن اکانت‌های جدید روی دکمه زیر کلیک کنید:",
        c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_test_add_acc_"))
def adm_test_add_acc(c):
    if c.from_user.id != ADMIN_ID: return
    btn_key = c.data.replace("adm_test_add_acc_", "")
    user_states[ADMIN_ID] = {"state": "ADM_TEST_WAIT_ACCOUNTS", "btn_key": btn_key, "accounts": []}
    bot.send_message(ADMIN_ID,
                      f"📝 افزودن اکانت تست برای: {btn_key}\n\n" f"هر اکانت را در یک پیام جداگانه ارسال کنید.\n" f"وقتی همه اکانت‌ها را فرستادید، بنویسید: /done")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "ADM_TEST_WAIT_ACCOUNTS")
def adm_test_collect_accounts(m):
    if m.text == "/done":
        data = user_states.get(ADMIN_ID, {})
        accounts = data.get("accounts", [])
        btn_key = data.get("btn_key")
        if not accounts:
            bot.send_message(ADMIN_ID, "❌ هیچ اکانتی ارسال نشد.")
        else:
            for acc in accounts:
                test_accounts_col.insert_one({
                    "btn_key": btn_key,
                    "account_data": acc,
                    "used": False,
                    "given_to": None,
                    "given_at": None,
                    "added_at": now_str()
                })
            bot.send_message(ADMIN_ID, f"✅ {len(accounts)} اکانت تست برای '{btn_key}' اضافه شد.")
        user_states[ADMIN_ID] = None
        return
    data = user_states.get(ADMIN_ID, {})
    data["accounts"].append(m.text.strip())
    count = len(data["accounts"])
    bot.send_message(ADMIN_ID, f"✅ اکانت {count} دریافت شد. ادامه دهید یا /done بنویسید.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_test_del_btn_"))
def adm_test_del_btn(c):
    if c.from_user.id != ADMIN_ID: return
    btn_key = c.data.replace("adm_test_del_btn_", "")
    test_buttons_doc = settings_col.find_one({"key": "test_buttons"})
    test_buttons = test_buttons_doc['value'] if test_buttons_doc else []
    test_buttons = [b for b in test_buttons if b['key'] != btn_key]
    settings_col.update_one({"key": "test_buttons"}, {"$set": {"value": test_buttons}})
    test_accounts_col.delete_many({"btn_key": btn_key, "used": False})
    bot.answer_callback_query(c.id, f"✅ نوع تست '{btn_key}' حذف شد. (اکانت‌های داده‌شده در تاریخچه باقی ماندند)",
                               show_alert=True)
    adm_test_mgr(c)


# =====================================================================
# ویژگی جدید ۸: گزارش خریداران
# =====================================================================
@bot.callback_query_handler(func=lambda c: c.data == "adm_buyers_report")
def adm_buyers_report(c):
    if c.from_user.id != ADMIN_ID: return
    kb = types.InlineKeyboardMarkup()
    server_list = [
        ("📅 ۱ ماهه", "MONTH"),
        ("♾ VIP", "VIP"),
        ("🔮 نپستر", "NAPSTERV"),
        ("🌀 نپستر نامحدود", "NAPSTERV_UNLIM"),
        ("🔴 وایرگارد", "WIREGUARD"),
    ]
    for label, plan_key in server_list:
        count = orders_col.count_documents({"plan": plan_key, "status": "done"})
        kb.add(btn(f"{label} ({count} خرید)", f"adm_buyers_{plan_key}", style="primary"))
    kb.add(btn("🔙 بازگشت", "admin_back", style="danger"))
    bot.edit_message_text("📋 گزارش خریداران\n\nروی هر سرور کلیک کنید تا خریداران آن را ببینید:", c.message.chat.id,
                           c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_buyers_") and not c.data.startswith(
    "adm_buyers_report"))
def adm_buyers_plan(c):
    if c.from_user.id != ADMIN_ID: return
    plan_key = c.data.replace("adm_buyers_", "")
    orders = list(orders_col.find({"plan": plan_key, "status": "done"}).sort("_id", -1).limit(50))
    if not orders:
        bot.answer_callback_query(c.id, "هیچ خریدی برای این سرور ثبت نشده.", show_alert=True)
        return
    txt = f"📋 خریداران سرور {plan_key}:\n\n"
    for o in orders:
        txt += f"👤 کاربر: {o['user_id']} | حجم: {o['volume']} | {format_p(o['price'])} ت | {o.get('created_at', '')}\n"
    if len(txt) > 4000:
        parts = [txt[i:i + 4000] for i in range(0, len(txt), 4000)]
        for part in parts:
            bot.send_message(ADMIN_ID, part)
    else:
        kb = types.InlineKeyboardMarkup()
        kb.add(btn("🔙 بازگشت", "adm_buyers_report", style="danger"))
        bot.send_message(ADMIN_ID, txt, reply_markup=kb)


# =====================================================================
# ویژگی‌های درخواستی جدید کاربر (کدهای تخفیف، چند ادمینی، نظرسنجی و ...)
# =====================================================================

# ---- پیگیری سفارش ----
@bot.callback_query_handler(func=lambda c: c.data == "track_order")
def track_order_menu(c):
    uid = c.from_user.id
    user_states[uid] = {"state": "WAIT_TRACK_CODE"}
    bot.send_message(uid, "🔍 لطفاً کد پیگیری ۶ رقمی خود را وارد کنید:")


@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("state") == "WAIT_TRACK_CODE")
def process_track_code(m):
    uid = m.from_user.id
    code = m.text.strip().upper().replace("#", "")
    order = orders_col.find_one({"track_code": code})
    if not order:
        bot.send_message(uid, "❌ سفارش با این کد پیگیری یافت نشد. مجدداً تلاش کنید یا منوی اصلی را انتخاب کنید:")
        return

    status_map = {"pending": "در انتظار بررسی", "done": "تحویل داده شده", "approved": "تایید شده/شارژ شده",
                  "rejected": "لغو شده"}
    current_st = status_map.get(order.get("status", "pending"), "نامشخص")

    bot.send_message(uid,
                      f"🔍 وضعیت سفارش شما:\n━━━━━━━━━━━━━━━━\n📦 نوع سرویس: {order.get('plan')}\n📊 حجم: {order.get('volume')}\n💰 مبلغ: {format_p(order.get('price'))} تومان\n🛠 وضعیت: {current_st}\n📅 تاریخ ثبت: {order.get('created_at')}")
    user_states[uid] = None


# ---- سیستم لیست انتظار سرور و سوئیچ هوشمند ----
def show_waiting_list_option(c, plan_key, plan_title):
    uid = c.from_user.id
    kb = types.InlineKeyboardMarkup()
    already = waiting_list_col.find_one({"user_id": uid, "plan": plan_key})
    if already:
        kb.add(btn("✅ در لیست انتظار هستید", "already_in_wait", style="primary"))
    else:
        kb.add(btn("🔔 وقتی باز شد بهم خبر بده", f"join_wait_{plan_key}_{plan_title}", style="success"))
    kb.add(btn("🔙 بازگشت", "price", style="danger"))
    bot.edit_message_text(f"⚠️ سرور [{plan_title}] در حال حاضر بسته است. مایلید به لیست انتظار اضافه شوید؟",
                           c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "already_in_wait")
def already_in_wait_cb(c):
    bot.answer_callback_query(c.id, "✅ شما در لیست انتظار این سرور عضو هستید.", show_alert=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith("join_wait_"))
def join_wait_cb(c):
    uid = c.from_user.id
    parts = c.data.split("_")
    plan_key = parts[2]
    plan_title = parts[3]
    waiting_list_col.insert_one({"user_id": uid, "plan": plan_key, "plan_title": plan_title, "created_at": datetime.now()})
    bot.answer_callback_query(c.id, "🔔 شما با موفقیت به لیست انتظار اضافه شدید.", show_alert=True)
    back_to_prices_btn = types.InlineKeyboardMarkup()
    back_to_prices_btn.add(btn("🔙 بازگشت به تعرفه‌ها", "price", style="danger"))
    bot.edit_message_text("✅ به محض باز شدن ظرفیت یا فعال‌سازی مجدد این سرور، به شما پیام و دکمه خرید مستقیم ارسال خواهد شد.",
                           c.message.chat.id, c.message.message_id, reply_markup=back_to_prices_btn)


def check_and_notify_waiting_list(plan_key, plan_title):
    """این تابع اکنون مستقیماً و به‌صورت Thread از هندلر SALE_TOG_ فراخوانی می‌شود"""
    waiters = list(waiting_list_col.find({"plan": plan_key}))
    if not waiters:
        return
    count = 0
    kb_buy = types.InlineKeyboardMarkup()
    kb_buy.add(btn("🛒 خرید آنلاین سرور", f"goto_buy_{plan_key.lower()}", style="success"))

    for w in waiters:
        try:
            bot.send_message(w["user_id"], f"🔔 سرور {plan_title} دوباره باز شد! همین الان خریداری کن 🚀", reply_markup=kb_buy)
            count += 1
        except:
            pass
    waiting_list_col.delete_many({"plan": plan_key})
    try:
        bot.send_message(ADMIN_ID, f"📢 سیستم هوشمند لیست انتظار: سرور {plan_title} باز شد و به تعداد {count} کاربر اطلاع‌رسانی مستقیم گردید.")
    except:
        pass


# ---- مدیریت جامع کدهای تخفیف (بازنویسی کامل فاز ۲) ----
def coupon_expire_label(cp):
    expire_at = cp.get("expire_at")
    if not expire_at:
        return "نامحدود"
    try:
        exp_dt = datetime.fromisoformat(expire_at)
        return exp_dt.strftime("%Y/%m/%d %H:%M")
    except:
        return "نامشخص"


@bot.callback_query_handler(func=lambda c: c.data == "adm_coupon_mgr")
def adm_coupon_mgr(c):
    if c.from_user.id != ADMIN_ID: return
    status_str = "✅ روشن" if get_setting('coupon_system_status') else "❌ خاموش"
    kb = types.InlineKeyboardMarkup()
    kb.add(btn(f"سیستم کد تخفیف: {status_str}", "COUPON_SYS_TOG", style="primary"))
    kb.add(btn("➕ ساخت کد تخفیف جدید", "adm_add_coupon", style="success"))

    coupons = list(coupons_col.find({}))
    for cp in coupons:
        active_label = "✅" if cp.get("active", True) else "❌"
        max_use = cp['max_uses'] if cp['max_uses'] > 0 else "∞"
        kb.add(btn(f"🏷 {cp['code']} | {cp['percent']}% | ({cp['used_count']}/{max_use}) | {active_label}",
                   f"COUPON_DETAIL_{cp['_id']}", style="primary"))

    kb.add(btn("🔙 بازگشت", "admin_back", style="danger"))
    bot.edit_message_text("🏷 پنل مدیریت کدهای تخفیف:\nبرای مشاهده جزئیات هر کد روی آن کلیک کنید:",
                           c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "COUPON_SYS_TOG")
def tog_coupon_system_cb(c):
    if c.from_user.id != ADMIN_ID: return
    current = get_setting('coupon_system_status')
    settings_col.update_one({"key": "coupon_system_status"}, {"$set": {"value": 0 if current else 1}})
    adm_coupon_mgr(c)


@bot.callback_query_handler(func=lambda c: c.data == "adm_add_coupon")
def adm_add_coupon_cb(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state": "COUPON_WAIT_PERCENT"}
    bot.send_message(ADMIN_ID, "💯 درصد تخفیف را وارد کنید (فقط عدد بین ۱ تا ۱۰۰):")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "COUPON_WAIT_PERCENT")
def coupon_save_percent(m):
    if not m.text.isdigit() or not (1 <= int(m.text) <= 100):
        bot.send_message(ADMIN_ID, "❌ فقط عدد بین ۱ تا ۱۰۰ وارد کنید:")
        return
    pct = int(m.text)
    user_states[ADMIN_ID] = {"state": "COUPON_WAIT_MAX", "percent": pct}
    bot.send_message(ADMIN_ID, "🔢 حداکثر دفعات استفاده از این کد را وارد کنید (عدد 0 یعنی نامحدود):")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "COUPON_WAIT_MAX")
def coupon_save_max(m):
    if not m.text.isdigit():
        bot.send_message(ADMIN_ID, "❌ فقط عدد وارد کنید:")
        return
    max_u = int(m.text)
    data = user_states[ADMIN_ID]
    user_states[ADMIN_ID] = {"state": "COUPON_WAIT_DURATION", "percent": data["percent"], "max_uses": max_u}
    bot.send_message(ADMIN_ID,
                      "⏳ مدت اعتبار کد را وارد کنید:\nفرمت: 7d (روز) / 24h (ساعت) / 30m (دقیقه) / 0 (بدون محدودیت)\nمثال: 7d")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "COUPON_WAIT_DURATION")
def coupon_save_duration(m):
    delta, label = parse_duration_text(m.text)
    if delta == "ERROR":
        bot.send_message(ADMIN_ID, "❌ فرمت اشتباه است. مثال صحیح: 7d یا 24h یا 30m یا 0")
        return
    data = user_states[ADMIN_ID]
    code = generate_coupon_code()
    expire_at = (datetime.now() + delta).isoformat() if delta else None
    coupons_col.insert_one({
        "code": code,
        "percent": data["percent"],
        "max_uses": data["max_uses"],
        "used_count": 0,
        "active": True,
        "expire_at": expire_at,
        "used_by": [],
        "created_at": datetime.now().isoformat()
    })
    bot.send_message(ADMIN_ID,
                      f"✅ کد تخفیف ساخته شد!\n\n🏷 کد: {code}\n💯 درصد: {data['percent']}%\n🔢 سقف استفاده: {data['max_uses'] if data['max_uses'] > 0 else 'نامحدود'}\n⏳ اعتبار: {label}")
    user_states[ADMIN_ID] = None


def render_coupon_detail(chat_id, message_id, cp_id):
    from bson.objectid import ObjectId
    cp = coupons_col.find_one({"_id": ObjectId(cp_id)})
    if not cp:
        return
    active_label = "✅ فعال" if cp.get("active", True) else "❌ غیرفعال"
    max_use = cp['max_uses'] if cp['max_uses'] > 0 else "نامحدود"
    txt = (f"🏷 جزئیات کد تخفیف\n\n"
           f"🔖 کد: {cp['code']}\n"
           f"💯 درصد تخفیف: {cp['percent']}%\n"
           f"🔢 استفاده‌شده: {cp['used_count']} از {max_use}\n"
           f"📌 وضعیت: {active_label}\n"
           f"⏳ اعتبار تا: {coupon_expire_label(cp)}\n"
           f"👥 تعداد کاربران استفاده‌کننده: {len(cp.get('used_by', []))}")
    kb = types.InlineKeyboardMarkup()
    toggle_label = "❌ غیرفعال کردن" if cp.get("active", True) else "✅ فعال کردن"
    kb.add(btn(toggle_label, f"COUPON_TOGGLE_{cp_id}", style="primary"))
    kb.add(btn("⏳ تمدید اعتبار", f"COUPON_EXTEND_{cp_id}", style="primary"))
    kb.add(btn("💯 تغییر درصد", f"COUPON_EDIT_PCT_{cp_id}", style="primary"), btn("🔢 تغییر سقف استفاده", f"COUPON_EDIT_MAX_{cp_id}", style="primary"))
    kb.add(btn("🗑 حذف کد", f"COUPON_DEL_{cp_id}", style="danger"))
    kb.add(btn("🔙 بازگشت", "adm_coupon_mgr", style="danger"))
    if message_id:
        try:
            bot.edit_message_text(txt, chat_id, message_id, reply_markup=kb)
            return
        except:
            pass
    bot.send_message(chat_id, txt, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("COUPON_DETAIL_"))
def coupon_detail_cb(c):
    if c.from_user.id != ADMIN_ID: return
    cp_id = c.data.replace("COUPON_DETAIL_", "")
    render_coupon_detail(c.message.chat.id, c.message.message_id, cp_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("COUPON_TOGGLE_"))
def coupon_toggle_cb(c):
    from bson.objectid import ObjectId
    if c.from_user.id != ADMIN_ID: return
    cp_id = c.data.replace("COUPON_TOGGLE_", "")
    coupon = coupons_col.find_one({"_id": ObjectId(cp_id)})
    if coupon:
        new_status = not coupon.get("active", True)
        coupons_col.update_one({"_id": ObjectId(cp_id)}, {"$set": {"active": new_status}})
    render_coupon_detail(c.message.chat.id, c.message.message_id, cp_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("COUPON_DEL_"))
def coupon_del_cb(c):
    from bson.objectid import ObjectId
    if c.from_user.id != ADMIN_ID: return
    cp_id = c.data.replace("COUPON_DEL_", "")
    coupons_col.delete_one({"_id": ObjectId(cp_id)})
    bot.answer_callback_query(c.id, "✅ کد تخفیف حذف شد.", show_alert=True)
    adm_coupon_mgr(c)


@bot.callback_query_handler(func=lambda c: c.data.startswith("COUPON_EXTEND_"))
def coupon_extend_cb(c):
    if c.from_user.id != ADMIN_ID: return
    cp_id = c.data.replace("COUPON_EXTEND_", "")
    user_states[ADMIN_ID] = {"state": "COUPON_WAIT_EXTEND", "cp_id": cp_id}
    bot.send_message(ADMIN_ID,
                      "⏳ مدت اعتبار جدید را وارد کنید (از همین لحظه محاسبه می‌شود):\nفرمت: 7d / 24h / 30m / 0")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "COUPON_WAIT_EXTEND")
def coupon_save_extend(m):
    from bson.objectid import ObjectId
    delta, label = parse_duration_text(m.text)
    if delta == "ERROR":
        bot.send_message(ADMIN_ID, "❌ فرمت اشتباه است. مثال صحیح: 7d یا 24h یا 30m یا 0")
        return
    cp_id = user_states[ADMIN_ID]["cp_id"]
    expire_at = (datetime.now() + delta).isoformat() if delta else None
    coupons_col.update_one({"_id": ObjectId(cp_id)}, {"$set": {"expire_at": expire_at}})
    bot.send_message(ADMIN_ID, f"✅ اعتبار کد تمدید شد. اعتبار جدید: {label} (از همین لحظه)")
    user_states[ADMIN_ID] = None
    render_coupon_detail(ADMIN_ID, None, cp_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("COUPON_EDIT_PCT_"))
def coupon_edit_pct_cb(c):
    if c.from_user.id != ADMIN_ID: return
    cp_id = c.data.replace("COUPON_EDIT_PCT_", "")
    user_states[ADMIN_ID] = {"state": "COUPON_WAIT_EDIT_PCT", "cp_id": cp_id}
    bot.send_message(ADMIN_ID, "💯 درصد تخفیف جدید را وارد کنید (۱ تا ۱۰۰):")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "COUPON_WAIT_EDIT_PCT")
def coupon_save_edit_pct(m):
    from bson.objectid import ObjectId
    if not m.text.isdigit() or not (1 <= int(m.text) <= 100):
        bot.send_message(ADMIN_ID, "❌ فقط عدد بین ۱ تا ۱۰۰ وارد کنید:")
        return
    cp_id = user_states[ADMIN_ID]["cp_id"]
    coupons_col.update_one({"_id": ObjectId(cp_id)}, {"$set": {"percent": int(m.text)}})
    bot.send_message(ADMIN_ID, "✅ درصد تخفیف با موفقیت تغییر یافت.")
    user_states[ADMIN_ID] = None
    render_coupon_detail(ADMIN_ID, None, cp_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("COUPON_EDIT_MAX_"))
def coupon_edit_max_cb(c):
    if c.from_user.id != ADMIN_ID: return
    cp_id = c.data.replace("COUPON_EDIT_MAX_", "")
    user_states[ADMIN_ID] = {"state": "COUPON_WAIT_EDIT_MAX", "cp_id": cp_id}
    bot.send_message(ADMIN_ID, "🔢 سقف استفاده جدید را وارد کنید (0 یعنی نامحدود):")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "COUPON_WAIT_EDIT_MAX")
def coupon_save_edit_max(m):
    from bson.objectid import ObjectId
    if not m.text.isdigit():
        bot.send_message(ADMIN_ID, "❌ فقط عدد وارد کنید:")
        return
    cp_id = user_states[ADMIN_ID]["cp_id"]
    coupons_col.update_one({"_id": ObjectId(cp_id)}, {"$set": {"max_uses": int(m.text)}})
    bot.send_message(ADMIN_ID, "✅ سقف استفاده با موفقیت تغییر یافت.")
    user_states[ADMIN_ID] = None
    render_coupon_detail(ADMIN_ID, None, cp_id)


@bot.callback_query_handler(func=lambda c: c.data == "apply_coupon_prompt")
def apply_coupon_prompt_cb(c):
    uid = c.from_user.id
    if uid not in user_states or user_states[uid].get("state") != "CONFIRM_BUY":
        bot.answer_callback_query(c.id, "خطای نشست خرید.", show_alert=True)
        return
    user_states[uid]["state"] = "WAIT_COUPON_CODE"
    bot.send_message(uid, "🏷 لطفاً کد تخفیف خود را ارسال کنید:")


@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("state") == "WAIT_COUPON_CODE")
def process_user_coupon(m):
    uid = m.from_user.id
    code = m.text.strip().upper()
    data = user_states.get(uid)
    if not data: return

    valid, result = check_coupon_valid(code, uid)
    if not valid:
        bot.send_message(uid, f"{result}\nفرآیند تایید خرید بدون کد ادامه می‌یابد.")
        data["state"] = "CONFIRM_BUY"
        return

    cp = result
    orig_p = data["price"]
    pct = cp["percent"]
    final_p = int(orig_p - (orig_p * pct / 100))

    data["state"] = "CONFIRM_BUY"
    data["discount_applied"] = True
    data["coupon_code"] = cp["code"]
    data["final_price"] = final_p

    kb = types.InlineKeyboardMarkup()
    kb.add(btn("✅ تایید", "final_buy", style="success"), btn("❌ لغو", "back", style="danger"))
    bot.send_message(uid,
                      f"✅ کد تخفیف اعمال شد!\n━━━━━━━━━━━━━━━━\n💰 قیمت اصلی: {format_p(orig_p)} تومان\n🏷 درصد تخفیف: {pct}%\n💵 قیمت نهایی: {format_p(final_p)} تومان\n━━━━━━━━━━━━━━━━\nجهت نهایی کردن فاکتور روی تایید کلیک کنید.",
                      reply_markup=kb)


# ---- سیستم چند ادمینی پیشرفته (بازنویسی کامل فاز ۲) ----
@bot.callback_query_handler(func=lambda c: c.data == "adm_subadmin_mgr")
def adm_subadmin_mgr(c):
    if c.from_user.id != ADMIN_ID: return
    status_str = "✅ روشن" if get_setting('subadmin_system_status') else "❌ خاموش"
    kb = types.InlineKeyboardMarkup()
    kb.add(btn(f"سیستم ادمین‌های فرعی: {status_str}", "SUBADMIN_SYS_TOG", style="primary"))
    kb.add(btn("➕ افزودن ادمین فرعی جدید", "adm_add_subadmin", style="success"))

    subs = list(subadmins_col.find({}))
    for sb in subs:
        kb.add(btn(
            f"👤 {sb['user_id']} | رسید: {'✅' if sb['receipt_access'] else '❌'} | کانفیگ: {'✅' if sb['config_access'] else '❌'}",
            f"SUBADMIN_EDIT_{sb['user_id']}", style="primary"))
        kb.add(btn(f"🗑 حذف ادمین {sb['user_id']}", f"SUBADMIN_DEL_{sb['user_id']}", style="danger"))

    kb.add(btn("🔙 بازگشت", "admin_back", style="danger"))
    bot.edit_message_text("👥 مدیریت ادمین‌های فرعی ربات:\nروی هر ادمین کلیک کنید تا دسترسی‌هایش را مدیریت کنید:",
                           c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "SUBADMIN_SYS_TOG")
def tog_subadmin_system_cb(c):
    if c.from_user.id != ADMIN_ID: return
    current = get_setting('subadmin_system_status')
    settings_col.update_one({"key": "subadmin_system_status"}, {"$set": {"value": 0 if current else 1}})
    adm_subadmin_mgr(c)


def render_subadmin_edit(chat_id, message_id, sub_id):
    sb = subadmins_col.find_one({"user_id": sub_id})
    if not sb:
        return
    txt = (f"👤 مدیریت دسترسی ادمین فرعی\n\n"
           f"🔢 آیدی: {sub_id}\n"
           f"💳 تایید/رد رسید: {'✅ فعال' if sb['receipt_access'] else '❌ غیرفعال'}\n"
           f"📤 ارسال کانفیگ: {'✅ فعال' if sb['config_access'] else '❌ غیرفعال'}")
    kb = types.InlineKeyboardMarkup()
    kb.add(btn(f"💳 دسترسی رسید: {'❌ خاموش کن' if sb['receipt_access'] else '✅ روشن کن'}",
               f"SUBADMIN_TOG_RECEIPT_{sub_id}", style="primary"))
    kb.add(btn(f"📤 دسترسی کانفیگ: {'❌ خاموش کن' if sb['config_access'] else '✅ روشن کن'}",
               f"SUBADMIN_TOG_CONFIG_{sub_id}", style="primary"))
    kb.add(btn("🗑 حذف این ادمین", f"SUBADMIN_DEL_{sub_id}", style="danger"))
    kb.add(btn("🔙 بازگشت", "adm_subadmin_mgr", style="danger"))
    if message_id:
        try:
            bot.edit_message_text(txt, chat_id, message_id, reply_markup=kb)
            return
        except:
            pass
    bot.send_message(chat_id, txt, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("SUBADMIN_EDIT_"))
def subadmin_edit_cb(c):
    if c.from_user.id != ADMIN_ID: return
    sub_id = int(c.data.replace("SUBADMIN_EDIT_", ""))
    render_subadmin_edit(c.message.chat.id, c.message.message_id, sub_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("SUBADMIN_TOG_RECEIPT_"))
def subadmin_toggle_receipt_cb(c):
    if c.from_user.id != ADMIN_ID: return
    sub_id = int(c.data.replace("SUBADMIN_TOG_RECEIPT_", ""))
    sb = subadmins_col.find_one({"user_id": sub_id})
    if sb:
        subadmins_col.update_one({"user_id": sub_id}, {"$set": {"receipt_access": not sb['receipt_access']}})
    render_subadmin_edit(c.message.chat.id, c.message.message_id, sub_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("SUBADMIN_TOG_CONFIG_"))
def subadmin_toggle_config_cb(c):
    if c.from_user.id != ADMIN_ID: return
    sub_id = int(c.data.replace("SUBADMIN_TOG_CONFIG_", ""))
    sb = subadmins_col.find_one({"user_id": sub_id})
    if sb:
        subadmins_col.update_one({"user_id": sub_id}, {"$set": {"config_access": not sb['config_access']}})
    render_subadmin_edit(c.message.chat.id, c.message.message_id, sub_id)


@bot.callback_query_handler(func=lambda c: c.data == "adm_add_subadmin")
def adm_add_subadmin_cb(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state": "SUBADMIN_WAIT_ID"}
    bot.send_message(ADMIN_ID, "لطفاً آیدی عددی ادمین فرعی جدید را ارسال کنید:")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "SUBADMIN_WAIT_ID")
def subadmin_save_id(m):
    if not m.text.isdigit():
        bot.send_message(ADMIN_ID, "❌ فقط آیدی عددی معتبر وارد کنید:")
        return
    sub_id = int(m.text)
    user_states[ADMIN_ID] = {"state": "SUBADMIN_WAIT_ACCESS", "sub_id": sub_id}
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("💳 فقط تایید/رد رسید", "SUB_ACC_1", style="primary"))
    kb.add(btn("📤 فقط ارسال کانفیگ", "SUB_ACC_2", style="primary"))
    kb.add(btn("🔥 هردو دسترسی کامل", "SUB_ACC_3", style="success"))
    bot.send_message(ADMIN_ID, f"سطح دسترسی برای ادمین فرعی {sub_id} را انتخاب کنید:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("SUB_ACC_"))
def sub_acc_save_cb(c):
    if c.from_user.id != ADMIN_ID: return
    mode = c.data.replace("SUB_ACC_", "")
    data = user_states.get(ADMIN_ID)
    if not data or data.get("state") != "SUBADMIN_WAIT_ACCESS": return

    receipt_access = mode in ["1", "3"]
    config_access = mode in ["2", "3"]

    subadmins_col.update_one(
        {"user_id": data["sub_id"]},
        {"$set": {"receipt_access": receipt_access, "config_access": config_access}},
        upsert=True
    )
    bot.send_message(ADMIN_ID, f"✅ ادمین فرعی {data['sub_id']} با موفقیت ثبت و دسترسی‌های مربوطه اعمال شد.")
    user_states[ADMIN_ID] = None
    adm_subadmin_mgr(c)


@bot.callback_query_handler(func=lambda c: c.data.startswith("SUBADMIN_DEL_"))
def adm_del_sub_cb(c):
    if c.from_user.id != ADMIN_ID: return
    sub_id = int(c.data.replace("SUBADMIN_DEL_", ""))
    subadmins_col.delete_one({"user_id": sub_id})
    bot.answer_callback_query(c.id, f"ادمین فرعی {sub_id} حذف شد.", show_alert=True)
    adm_subadmin_mgr(c)


@bot.callback_query_handler(func=lambda c: c.data == "sub_view_orders")
def sub_view_orders_cb(c):
    uid = c.from_user.id
    sub = subadmins_col.find_one({"user_id": uid})
    if not sub or not get_setting('subadmin_system_status'): return

    rows = list(orders_col.find({"status": "pending"}).sort("_id", -1).limit(10))
    if not rows:
        bot.send_message(uid, "📦 هیچ سفارش بازی در سیستم نیست.")
        return
    txt = "📦 سفارشات باز (مشاهده ادمین فرعی):\n\n"
    for r in rows:
        txt += f"OrderID: `{r['_id']}`\n📌 پلن: {r['plan']} | حجم: {r['volume']}\n💵 قیمت: {format_p(r['price'])} تومان\n📅 تاریخ: {r['created_at']}\n───────────────────\n"
    bot.send_message(uid, txt, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda c: c.data == "sub_send_config_by_id")
def sub_send_config_by_id_cb(c):
    uid = c.from_user.id
    sub = subadmins_col.find_one({"user_id": uid})
    if not sub or not get_setting('subadmin_system_status') or not sub['config_access']:
        bot.answer_callback_query(c.id, "❌ شما دسترسی ارسال کانفیگ ندارید.", show_alert=True)
        return
    user_states[uid] = {"state": "SUB_WAIT_ORDER_ID"}
    bot.send_message(uid, "📤 لطفاً کد شناسه سفارش (OrderID) بیست و چهار رقمی را ارسال کنید:")


@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("state") == "SUB_WAIT_ORDER_ID")
def sub_process_order_id(m):
    from bson.objectid import ObjectId
    uid = m.from_user.id
    order_id_str = m.text.strip()
    try:
        order = orders_col.find_one({"_id": ObjectId(order_id_str)})
        if not order or order['status'] != "pending":
            bot.send_message(uid, "❌ سفارش معتبری با این شناسه یافت نشد یا قبلاً تکمیل شده است.")
            user_states[uid] = None
            return
        user_states[uid] = {"state": "SEND_CONFIG", "order_id": order_id_str, "user_id": order['user_id']}
        bot.send_message(uid, "📥 سفارش با موفقیت فراخوانی شد. اکنون کانفیگ را به صورت متن یا فایل بفرستید:")
    except:
        bot.send_message(uid, "❌ قالب شناسه سفارش اشتباه است.")
        user_states[uid] = None


# ---- سیستم نظرسنجی ستاره‌ای زمان‌بندی شده سرورها ----
def schedule_review_poll(user_id, order_id):
    time.sleep(3600)
    if not get_setting('review_system_status'): return
    try:
        kb = types.InlineKeyboardMarkup(row_width=5)
        stars = [btn(f"{i} ⭐", f"rate_{order_id}_{i}", style="primary") for i in range(1, 6)]
        kb.add(*stars)
        bot.send_message(user_id, "از سرویس راضی بودی؟ لطفا با کلیک روی ستاره‌ها به کیفیت کانفیگ خود امتیاز دهید:", reply_markup=kb)
    except:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("rate_"))
def save_user_rating(c):
    from bson.objectid import ObjectId
    parts = c.data.split("_")
    order_id = parts[1]
    stars = int(parts[2])

    order = orders_col.find_one({"_id": ObjectId(order_id)})
    if order:
        server_plan = order.get("plan", "UNKNOWN")
        reviews_col.insert_one({
            "plan": server_plan,
            "stars": stars,
            "timestamp": datetime.now()
        })
        bot.answer_callback_query(c.id, "⭐ تشکر از نظرسنجی شما!", show_alert=True)
        bot.edit_message_text("❤️ از اینکه به ما در بهبود کیفیت خدمات کمک کردید سپاسگزاریم.", c.message.chat.id,
                               c.message.message_id)


# منوهای اضافه ادمین برای نظرسنجی، یادآوری و هدیه VIP
@bot.callback_query_handler(func=lambda c: c.data == "adm_extra_systems")
def adm_extra_systems(c):
    if c.from_user.id != ADMIN_ID: return
    r_status = "✅ روشن" if get_setting('review_system_status') else "❌ خاموش"
    rem_status = "✅ روشن" if get_setting('reminder_system_status') else "❌ خاموش"
    f_status = "✅ روشن" if get_setting('fake_messages_status') else "❌ خاموش"

    kb = types.InlineKeyboardMarkup()
    kb.add(btn(f"سیستم نظرسنجی: {r_status}", "EXTRA_TOG_review_system_status", style="primary"))
    kb.add(btn(f"یادآوری تمدید خودکار: {rem_status}", "EXTRA_TOG_reminder_system_status", style="primary"))
    kb.add(btn(f"ارسال پیام‌های نمایشی فیک: {f_status}", "EXTRA_TOG_fake_messages_status", style="primary"))
    kb.add(btn("📊 مشاهده آمار تفکیکی نظرسنجی‌ها", "view_reviews_stats", style="primary"))
    kb.add(btn("🔙 بازگشت", "admin_back", style="danger"))
    bot.edit_message_text("⭐ تنظیمات تکمیلی سیستم‌های ربات:", c.message.chat.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("EXTRA_TOG_"))
def extra_toggle_cb(c):
    if c.from_user.id != ADMIN_ID: return
    key = c.data.replace("EXTRA_TOG_", "")
    if key not in ['review_system_status', 'reminder_system_status', 'fake_messages_status']:
        return
    current = get_setting(key)
    settings_col.update_one({"key": key}, {"$set": {"value": 0 if current else 1}})
    adm_extra_systems(c)


@bot.callback_query_handler(func=lambda c: c.data == "view_reviews_stats")
def view_reviews_stats_cb(c):
    if c.from_user.id != ADMIN_ID: return
    now = datetime.now()
    today_s = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_s = now - timedelta(days=30)

    txt = "📊 گزارش تفکیکی و میانگین سیستم نظرسنجی سرورها:\n\n"
    plans = ["MONTH", "VIP", "NAPSTERV", "NAPSTERV_UNLIM", "WIREGUARD"]

    for p in plans:
        all_p = list(reviews_col.find({"plan": p}))
        today_p = list(reviews_col.find({"plan": p, "timestamp": {"$gte": today_s}}))
        month_p = list(reviews_col.find({"plan": p, "timestamp": {"$gte": month_s}}))

        avg_all = sum(x['stars'] for x in all_p) / len(all_p) if all_p else 0
        avg_today = sum(x['stars'] for x in today_p) / len(today_p) if today_p else 0
        avg_month = sum(x['stars'] for x in month_p) / len(month_p) if month_p else 0

        txt += f"📦 سرور {p}:\n"
        txt += f"  - میانگین امروز: {avg_today:.1f} ({len(today_p)} نظر)\n"
        txt += f"  - میانگین این ماه: {avg_month:.1f} ({len(month_p)} نظر)\n"
        txt += f"  - میانگین کل: {avg_all:.1f} ({len(all_p)} نظر)\n"
        txt += "───────────────────\n"

    kb = types.InlineKeyboardMarkup()
    kb.add(btn("🔙 بازگشت", "adm_extra_systems", style="danger"))
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=kb)


# ---- یادآوری انقضای سرورها (بازنویسی کامل با تقویم جلالی/میلادی) ----
@bot.callback_query_handler(func=lambda c: c.data.startswith("set_expire_"))
def set_expire_cb(c):
    clicker = c.from_user.id
    if clicker != ADMIN_ID:
        sub = subadmins_col.find_one({"user_id": clicker})
        if not sub or not sub['config_access']: return

    order_id = c.data.replace("set_expire_", "")
    txt = get_current_time_both_calendars() + "\n\nلطفاً تقویم موردنظر برای ثبت تاریخ انقضا را انتخاب کنید:"
    kb = types.InlineKeyboardMarkup()
    kb.add(btn("📅 شمسی (جلالی)", f"EXPCAL_jalali_{order_id}", style="primary"))
    kb.add(btn("📅 میلادی (گریگوری)", f"EXPCAL_gregorian_{order_id}", style="primary"))
    bot.send_message(clicker, txt, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("EXPCAL_"))
def set_expire_calendar_cb(c):
    clicker = c.from_user.id
    if clicker != ADMIN_ID:
        sub = subadmins_col.find_one({"user_id": clicker})
        if not sub or not sub['config_access']: return

    parts = c.data.replace("EXPCAL_", "").split("_", 1)
    cal_type = parts[0]
    order_id = parts[1]
    user_states[clicker] = {"state": "WAIT_EXPIRE_DATE", "order_id": order_id, "calendar_type": cal_type}
    cal_label = "شمسی (مثال: 1403/05/20)" if cal_type == "jalali" else "میلادی (مثال: 2026/07/20)"
    txt = (get_current_time_both_calendars() +
           f"\n\n✏️ تاریخ و ساعت انقضا را به تقویم {cal_label} وارد کنید.\n"
           f"فرمت ورودی: YYYY/MM/DD HH:MM\n"
           f"(اگر ساعت وارد نکنید، به‌صورت پیش‌فرض 23:59 در نظر گرفته می‌شود)")
    bot.send_message(clicker, txt)


@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("state") == "WAIT_EXPIRE_DATE")
def process_expire_date_save(m):
    from bson.objectid import ObjectId
    sender = m.from_user.id
    data = user_states.get(sender)
    if not data: return

    raw = m.text.strip()
    parts = raw.split()
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else "23:59"

    try:
        date_bits = date_part.split("/")
        y, mo, d = int(date_bits[0]), int(date_bits[1]), int(date_bits[2])
        time_bits = time_part.split(":")
        hh, mm = int(time_bits[0]), int(time_bits[1])
    except:
        bot.send_message(sender, "❌ فرمت ورودی اشتباه است. مثال صحیح: 1403/05/20 14:30\nدوباره تلاش کنید:")
        return

    cal_type = data.get("calendar_type", "gregorian")
    try:
        if cal_type == "jalali":
            gy, gm, gd = jalali_to_gregorian(y, mo, d)
        else:
            gy, gm, gd = y, mo, d
        expire_dt = datetime(gy, gm, gd, hh, mm)
    except Exception:
        bot.send_message(sender, "❌ تاریخ وارد شده نامعتبر است. دوباره تلاش کنید:")
        return

    orders_col.update_one({"_id": ObjectId(data["order_id"])}, {"$set": {
        "expire_date_str": f"{date_part} {time_part}",
        "expire_calendar_type": cal_type,
        "expire_date_gregorian": expire_dt.isoformat(),
        "expire_notified": False
    }})
    bot.send_message(sender,
                      f"✅ تاریخ انقضا با موفقیت ثبت شد.\n\n📅 تاریخ وارد شده ({'شمسی' if cal_type == 'jalali' else 'میلادی'}): {date_part} {time_part}\n📅 معادل میلادی: {expire_dt.strftime('%Y/%m/%d %H:%M')}")
    user_states[sender] = None


# ---- ارسال هدیه VIP از ادمین به کاربر ----
@bot.callback_query_handler(func=lambda c: c.data.startswith("gift_vip_"))
def gift_vip_prompt(c):
    if c.from_user.id != ADMIN_ID: return
    target_uid = int(c.data.replace("gift_vip_", ""))
    user_states[ADMIN_ID] = {"state": "WAIT_GIFT_AMOUNT", "target_uid": target_uid}
    bot.send_message(ADMIN_ID, f"مبلغ هدیه دلخواه برای کاربر {target_uid} را به تومان وارد کنید:")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID, {}).get(
    "state") == "WAIT_GIFT_AMOUNT")
def process_gift_amount(m):
    if not m.text.isdigit():
        bot.send_message(ADMIN_ID, "❌ فقط عدد وارد کنید:")
        return
    amt = int(m.text)
    data = user_states[ADMIN_ID]
    target = data["target_uid"]

    users_col.update_one({"user_id": target}, {"$inc": {"balance": amt}})
    try:
        bot.send_message(target, f"به مناسبت رسیدن به سطح VIP، {format_p(amt)} تومان از طرف ادمین به حسابت اضافه شد ❤️‍🔥")
        bot.send_message(ADMIN_ID, "✅ هدیه با موفقیت به حساب کاربر منظور و اعلان آن ارسال شد.")
    except:
        bot.send_message(ADMIN_ID, "❌ موجودی اضافه شد اما پیام به کاربر منتقل نگردید.")
    user_states[ADMIN_ID] = None


# =====================================================================
# ریسه‌ها و لوپ‌های پیشرفته ناظر به قابلیت‌های زمان‌بندی‌شده (Worker Threads)
# =====================================================================
def background_scheduler_worker():
    last_hourly_check = datetime.now() - timedelta(hours=1)
    last_daily_backup = None
    last_monthly_promo = None

    while True:
        try:
            now = datetime.now()

            for uid, state_data in list(user_states.items()):
                if state_data and state_data.get("state") == "WAIT_RECEIPT":
                    inv_time = state_data.get("invoice_time")
                    if inv_time and (now - inv_time).total_seconds() >= 1800:
                        state_data["is_expired"] = True
                        state_data["state"] = None
                        try:
                            bot.send_message(uid, "❌ فاکتور منقضی شد")
                        except:
                            pass

            if (now - last_hourly_check).total_seconds() >= 3600:
                last_hourly_check = now

                # چک انقضای کوپن‌ها: active True و expire_at گذشته -> active False
                try:
                    active_coupons = list(coupons_col.find({"active": True, "expire_at": {"$ne": None}}))
                    for cp in active_coupons:
                        try:
                            exp_dt = datetime.fromisoformat(cp["expire_at"])
                            if now > exp_dt:
                                coupons_col.update_one({"_id": cp["_id"]}, {"$set": {"active": False}})
                        except:
                            pass
                except:
                    pass

                # یادآوری تمدید سرویس‌ها: کمتر از ۳ روز به انقضا مانده
                if get_setting('reminder_system_status'):
                    try:
                        pending_orders = list(orders_col.find({
                            "expire_date_gregorian": {"$exists": True, "$ne": None},
                            "expire_notified": False
                        }))
                        for o in pending_orders:
                            try:
                                exp_dt = datetime.fromisoformat(o["expire_date_gregorian"])
                                remaining_days = (exp_dt - now).total_seconds() / 86400
                                if remaining_days <= 3:
                                    bot.send_message(o["user_id"],
                                                      f"⏰ یادآوری تمدید سرویس\n\nسرویس شما ({o.get('plan', '')} - {o.get('volume', '')}) تا {remaining_days:.1f} روز دیگر منقضی می‌شود.\nبرای جلوگیری از قطعی، سرویس خود را تمدید کنید.")
                                    orders_col.update_one({"_id": o["_id"]}, {"$set": {"expire_notified": True}})
                            except:
                                pass
                    except:
                        pass

            if now.hour == 23 and now.minute == 59:
                if last_daily_backup != now.date():
                    last_daily_backup = now.date()
                    total_u = users_col.count_documents({})
                    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

                    today_orders = list(orders_col.find({"status": "done", "created_at": {"$regex": now.strftime("%Y/%m/%d")}}))
                    sales_count = len(today_orders)
                    total_income = sum(o.get("price", 0) for o in today_orders)

                    breakdown = {}
                    for o in today_orders:
                        p_key = o.get("plan", "UNKNOWN")
                        breakdown[p_key] = breakdown.get(p_key, 0) + 1

                    details_str = ""
                    for pk, v in breakdown.items():
                        details_str += f"  - سرور {pk}: تعداد {v} فروش\n"

                    backup_msg = f"💾 گزارش مالی و آماری ربات\n📅 تاریخ امروز: {now.strftime('%Y/%m/%d')}\n👥 کل کاربران: {total_u}\n🛍 فروش امروز: {sales_count} عدد\n{details_str}💰 مجموع درآمد امروز: {format_p(total_income)} تومان"
                    try:
                        bot.send_message(ADMIN_ID, backup_msg)
                    except:
                        pass

            if now.day == 1 and now.hour == 10 and now.minute == 0:
                if last_monthly_promo != now.month:
                    last_monthly_promo = now.month
                    all_users = list(users_col.find({}))
                    for u in all_users:
                        try:
                            cc = u.get("configs_count", 0)
                            if cc == 0:
                                bot.send_message(u["user_id"],
                                                  "✨ مایلید کیفیت اینترنت خود را دگرگون کنید؟ همین حالا سریع‌ترین سرورها را در بخش خرید سرور تست کنید! 🚀")
                            elif cc <= 2:
                                bot.send_message(u["user_id"],
                                                  "🔥 از انتخاب شما متشکریم! شما یک همراه فوق‌العاده هستید، با ارتقای حساب خود از تخفیف‌های بیشتر بهره‌مند شوید.")
                            else:
                                bot.send_message(u["user_id"],
                                                  "💎 شما از بهترین کاربران ما هستید! با معرفی ربات به دوستان خود با لینک اختصاصی، هدیه نقدی بگیرید. ❤️")
                        except:
                            pass

        except:
            pass
        time.sleep(10)


def fake_transactions_worker():
    while True:
        delay = random.randint(7, 60) * 60
        time.sleep(delay)

        if not get_setting('fake_messages_status'):
            continue

        try:
            plans = ["PRICES_MONTH", "PRICES_VIP", "PRICES_NAPSTERV", "PRICES_NAPSTERV_UNLIM", "PRICES_WIREGUARD"]
            chosen_plan_key = random.choice(plans)
            prices_dict = get_db_prices(chosen_plan_key)
            if not prices_dict: continue

            vol = random.choice(list(prices_dict.keys()))
            real_price = prices_dict[vol]

            fake_uid = random.randint(100000000, 999999999)
            masked = mask_user_id(fake_uid)
            plan_name = chosen_plan_key.replace("PRICES_", "")

            scenario = random.choice([1, 2])
            deposit_amt = real_price if scenario == 1 else (real_price * 2) + random.randint(5000, 20000)

            charge_alert = f"💳 شارژ حساب انجام شد\n━━━━━━━━━━━━━━━━\n💰 مبلغ واریزی: {format_p(deposit_amt)} تومان\n👤 کاربر: {masked}\n⌛ {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}\n━━━━━━━━━━━━━━━━\n🔒 AmirPlus | سرویس مطمئن"
            send_to_channels(charge_alert)

            time.sleep(random.randint(5, 30))

            order_alert1 = f"✅ سفارش جدید ثبت شد\n━━━━━━━━━━━━━━━━\n📦 سرویس: [{plan_name}]\n📊 حجم: [{vol}]\n💳 مبلغ: {format_p(real_price)} تومان\n👤 کاربر: {masked}\n⌛ {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}\n━━━━━━━━━━━━━━━━\n🔒 AmirPlus | سرویس مطمئن"
            send_to_channels(order_alert1)

            if scenario == 2:
                time.sleep(random.randint(10, 45))
                order_alert2 = f"✅ سفارش جدید ثبت شد\n━━━━━━━━━━━━━━━━\n📦 سرویس: [{plan_name}]\n📊 حجم: [{vol}]\n💳 مبلغ: {format_p(real_price)} تومان\n👤 کاربر: {masked}\n⌛ {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}\n━━━━━━━━━━━━━━━━\n🔒 AmirPlus | سرویس مطمئن"
                send_to_channels(order_alert2)

        except:
            pass


Thread(target=background_scheduler_worker, daemon=True).start()
Thread(target=fake_transactions_worker, daemon=True).start()


# --------------- WEB ---------------
@app.route('/')
def home():
    return "OK - MongoDB Active"


def run():
    app.run(host="0.0.0.0", port=8080)


if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling(skip_pending=True)
