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
    status TEXT,            -- pending / done / canceled
    created_at TEXT
)
""")
conn.commit()

# --------------- STATE ---------------
# state structure per user:
# { "state": str, "amount": int, "card": str, "expire_at": iso, "plan": str, "volume": str, "price": int }
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

# ---------- CHANNEL CHECK (optional) ----------
def is_member(user_id):
    try:
        st = bot.get_chat_member(CHANNEL_ID, user_id).status
        return st in ['member', 'creator', 'administrator']
    except:
        return True  # اگر خواستی اجباری نباشه

# --------------- START ---------------
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

    # اگر میخوای اجبار عضویت:
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

# --------------- CHARGE ---------------
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

    user_states[m.from_user.id] = {
        "state": "WAIT_RECEIPT",
        "amount": amt,
        "card": m.text.strip(),
        "expire_at": expire_at
    }

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📸 ارسال رسید", callback_data="send_receipt"))

    bot.send_message(
        m.chat.id,
        f"""✅ اطلاعات ثبت شد

💰 مبلغ: {format_p(amt)} تومان
💳 کارت مقصد:
`6221061233705260`
👤 به نام: افراس

⚠️ مبلغ را واریز کرده و رسید را ارسال کنید

⏰ فاکتور تا ۳۰ دقیقه معتبر است
""",
        parse_mode="Markdown",
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "send_receipt")
def send_receipt(c):
    bot.send_message(c.from_user.id, "📸 لطفاً تصویر رسید را ارسال کنید")

@bot.message_handler(content_types=['photo'])
def receipt(m):
    data = user_states.get(m.from_user.id)
    if not data or data.get("state") != "WAIT_RECEIPT":
        return

    # انقضا
    try:
        if datetime.now() > datetime.fromisoformat(data["expire_at"]):
            user_states[m.from_user.id] = None
            bot.send_message(m.chat.id, "⛔️ فاکتور منقضی شده، دوباره اقدام کنید.")
            return
    except:
        pass

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ تایید", callback_data=f"ok_{m.from_user.id}_{data['amount']}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"no_{m.from_user.id}")
    )

    bot.send_photo(
        ADMIN_ID,
        m.photo[-1].file_id,
        caption=f"""💰 درخواست شارژ

👤 کاربر: {m.from_user.id}
💵 مبلغ: {format_p(data['amount'])}
💳 کارت مبدا: {data['card']}
""",
        reply_markup=kb
    )

    bot.send_message(m.chat.id, "✅ رسید برای ادمین ارسال شد، لطفاً منتظر بمانید 🙏")
    user_states[m.from_user.id] = None

@bot.callback_query_handler(func=lambda c: c.data.startswith("ok_"))
def ok(c):
    _, uid, amt = c.data.split("_")
    uid = int(uid); amt = int(amt)

    cursor.execute("UPDATE users SET balance=balance+?, success_payments=success_payments+1 WHERE user_id=?", (amt, uid))
    conn.commit()

    bot.send_message(uid, f"✅ مبلغ {format_p(amt)} تومان به حساب شما اضافه شد")

@bot.callback_query_handler(func=lambda c: c.data.startswith("no_"))
def no(c):
    uid = int(c.data.split("_")[1])
    cursor.execute("UPDATE users SET warnings=warnings+1 WHERE user_id=?", (uid,))
    conn.commit()
    bot.send_message(uid, "❌ رسید شما رد شد و اخطار دریافت کردید")

# --------------- PRICE (طبق خواسته) ---------------
@bot.callback_query_handler(func=lambda c: c.data == "price")
def price_menu(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("📅 ۱ ماهه", callback_data="price_month"),
        types.InlineKeyboardButton("♾ بدون محدودیت زمانی + ساب + VIP", callback_data="price_vip")
    )
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
    txt = """📅 ۱ ماهه (تک کاربره)

1گیگ : ۳۵۰,۰۰۰
2گیگ : ۶۹۹,۰۰۰
3گیگ : ۹۹۹,۰۰۰
5گیگ : ۱,۴۹۹,۰۰۰
"""
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

@bot.callback_query_handler(func=lambda c: c.data == "price_vip")
def price_vip(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("♾ بدون محدودیت کاربری", callback_data="show_vip_prices"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="price"))
    bot.edit_message_text("VIP:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "show_vip_prices")
def show_vip_prices(c):
    txt = """♾ بدون محدودیت + VIP (تخفیف)

1گیگ : ۵۹۹,۰۰۰
2گیگ : ۱,۱۹۸,۰۰۰
3گیگ : ۱,۷۹۷,۰۰۰
5گیگ : ۲,۸۹۹,۰۰۰
10گیگ : ۵,۲۹۹,۰۰۰
"""
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

# --------------- BUY ---------------
PRICES_MONTH = {"1G":350000,"2G":699000,"3G":999000,"5G":1499000}
PRICES_VIP   = {"1G":599000,"2G":1198000,"3G":1797000,"5G":2899000,"10G":5299000}

@bot.callback_query_handler(func=lambda c: c.data == "buy")
def buy(c):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("📅 ۱ ماهه", callback_data="buy_month"),
        types.InlineKeyboardButton("♾ بدون محدودیت + VIP", callback_data="buy_vip")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    bot.edit_message_text("🛒 خرید سرویس:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "buy_month")
def buy_month(c):
    user_states[c.from_user.id] = {"state":"BUY_PLAN","plan":"MONTH"}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👤 تک کاربره", callback_data="buy_month_single"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy"))
    bot.edit_message_text("۱ ماهه:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "buy_month_single")
def buy_month_single(c):
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in ["1G","2G","3G","5G"]:
        kb.add(types.InlineKeyboardButton(v, callback_data=f"vol_{v}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_month"))
    bot.edit_message_text("حجم را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "buy_vip")
def buy_vip(c):
    user_states[c.from_user.id] = {"state":"BUY_PLAN","plan":"VIP"}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("♾ بدون محدودیت کاربری", callback_data="buy_vip_unlim"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy"))
    bot.edit_message_text("VIP:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "buy_vip_unlim")
def buy_vip_unlim(c):
    kb = types.InlineKeyboardMarkup(row_width=3)
    for v in ["1G","2G","3G","5G","10G"]:
        kb.add(types.InlineKeyboardButton(v, callback_data=f"vol_{v}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_vip"))
    bot.edit_message_text("حجم را انتخاب کنید:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("vol_"))
def select_volume(c):
    uid = c.from_user.id
    st = user_states.get(uid, {})
    plan = st.get("plan")
    volume = c.data.split("_")[1]

    price = PRICES_MONTH.get(volume) if plan=="MONTH" else PRICES_VIP.get(volume)
    if price is None:
        bot.answer_callback_query(c.id, "نامعتبر", show_alert=True); return

    cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    balance = cursor.fetchone()[0]

    if balance < price:
        bot.answer_callback_query(c.id, "❌ موجودی کافی نمی‌باشد", show_alert=True)
        return

    user_states[uid] = {"state":"CONFIRM_BUY","plan":plan,"volume":volume,"price":price}

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ تایید", callback_data="final_buy"),
        types.InlineKeyboardButton("❌ لغو", callback_data="back")
    )
    bot.send_message(uid, f"آیا از خرید {volume} به مبلغ {format_p(price)} اطمینان دارید؟", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "final_buy")
def final_buy(c):
    uid = c.from_user.id
    data = user_states.get(uid, {})
    if data.get("state") != "CONFIRM_BUY":
        return

    price = data["price"]

    # کم کردن موجودی و افزایش تعداد سرویس
    cursor.execute("UPDATE users SET balance=balance-?, configs_count=configs_count+1 WHERE user_id=?", (price, uid))
    # ثبت سفارش
    cursor.execute("INSERT INTO orders (user_id,plan,volume,price,status,created_at) VALUES (?,?,?,?,?,?)",
                   (uid, data["plan"], data["volume"], price, "pending", now_str()))
    order_id = cursor.lastrowid
    conn.commit()

    bot.send_message(uid, "⏳ سفارش شما ثبت شد. در حال ساخت کانفیگ...")

    # ارسال برای ادمین
    bot.send_message(
        ADMIN_ID,
        f"""🛒 سفارش جدید

🆔 OrderID: {order_id}
👤 کاربر: {uid}
📦 پلن: {data['plan']}
📊 حجم: {data['volume']}
💵 مبلغ: {format_p(price)}
""")

    user_states[uid] = None

# --------------- ADMIN: SEND CONFIG BY REPLY ---------------
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.reply_to_message)
def admin_reply_send_config(m):
    # انتظار داریم روی پیام سفارش ریپلای شود که داخلش OrderID هست
    try:
        txt = m.reply_to_message.text or ""
        if "OrderID:" not in txt:
            return
        order_id = int(txt.split("OrderID:")[1].split("\n")[0].strip())

        cursor.execute("SELECT user_id, status FROM orders WHERE id=?", (order_id,))
        row = cursor.fetchone()
        if not row:
            bot.send_message(ADMIN_ID, "سفارش پیدا نشد"); return
        uid, status = row
        if status != "pending":
            bot.send_message(ADMIN_ID, "این سفارش قبلاً بسته شده"); return

        # ارسال کانفیگ (هرچی ادمین نوشته)
        bot.send_message(uid, f"✅ کانفیگ شما:\n\n{m.text}")

        # بستن سفارش
        cursor.execute("UPDATE orders SET status='done' WHERE id=?", (order_id,))
        conn.commit()

        bot.send_message(ADMIN_ID, f"سفارش {order_id} انجام شد")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"خطا در ارسال: {e}")

# --------------- ACCOUNT ---------------
@bot.callback_query_handler(func=lambda c: c.data == "account")
def account(c):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (c.from_user.id,))
    d = cursor.fetchone()

    username = f"@{c.from_user.username}" if c.from_user.username else "❌ ندارد"

    text = f"""📊 اطلاعات حساب کاربری شما در ربات:

🔢 آیدی عددی : {c.from_user.id}
🔆 یوزرنیم : {username}
📱 شماره : ❌ ثبت نشده است
💰 موجودی : {format_p(d[1])} تومان
🏦 پرداخت های موفق : {d[4]} عدد
🛍 تعداد سرویس ها : {d[2]} عدد
⚠️ تعداد اخطار ها : {d[3]} عدد
⏰ تاریخ عضویت : {d[7]}

🤖 | @rafe_filter_GB_bot
"""
    bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=back_kb())

# --------------- SUPPORT ---------------
@bot.callback_query_handler(func=lambda c: c.data == "support")
def support(c):
    bot.edit_message_text(f"📞 پشتیبانی:\n{SUPPORT_ID}", c.message.chat.id, c.message.message_id, reply_markup=back_kb())

# --------------- BACK ---------------
@bot.callback_query_handler(func=lambda c: c.data == "back")
def back(c):
    bot.edit_message_text("👇 منوی اصلی:", c.message.chat.id, c.message.message_id, reply_markup=main_menu())

# --------------- ADMIN PANEL ---------------
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
    kb.add(types.InlineKeyboardButton("📦 سفارشات باز", callback_data="adm_orders"))
    kb.add(types.InlineKeyboardButton("🔎 مشاهده کاربر", callback_data="adm_get_user"))
    kb.add(types.InlineKeyboardButton("📣 ارسال همگانی", callback_data="adm_broadcast"))

    bot.send_message(m.chat.id,
                     f"""👑 پنل ادمین

👤 تعداد کاربران: {users}
💰 مجموع موجودی: {format_p(total)}
📦 سفارشات باز: {pending}
""",
                     reply_markup=kb)

# لیست سفارشات باز
@bot.callback_query_handler(func=lambda c: c.data == "adm_orders")
def adm_orders(c):
    if c.from_user.id != ADMIN_ID: return
    cursor.execute("SELECT id,user_id,plan,volume,price,created_at FROM orders WHERE status='pending' ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(ADMIN_ID, "سفارشی وجود ندارد"); return
    txt = "📦 سفارشات باز:\n\n"
    for r in rows:
        txt += f"ID:{r[0]} | U:{r[1]} | {r[2]} | {r[3]} | {format_p(r[4])}\n{r[5]}\n---\n"
    bot.send_message(ADMIN_ID, txt)

# مشاهده/مدیریت کاربر
@bot.callback_query_handler(func=lambda c: c.data == "adm_get_user")
def adm_get_user(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state":"ADM_GET_USER"}
    bot.send_message(ADMIN_ID, "آیدی عددی کاربر را ارسال کنید:")

@bot.message_handler(func=lambda m: user_states.get(ADMIN_ID, {}).get("state") == "ADM_GET_USER" and m.from_user.id==ADMIN_ID)
def adm_show_user(m):
    if not m.text.isdigit():
        bot.send_message(ADMIN_ID, "آیدی نامعتبر"); return
    uid = int(m.text)
    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    d = cursor.fetchone()
    if not d:
        bot.send_message(ADMIN_ID, "کاربر یافت نشد"); return

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ افزودن موجودی", callback_data=f"adm_add_{uid}"),
        types.InlineKeyboardButton("➖ کسر موجودی", callback_data=f"adm_sub_{uid}")
    )
    kb.add(types.InlineKeyboardButton("⚠️ اخطار", callback_data=f"adm_warn_{uid}"))

    bot.send_message(ADMIN_ID,
                     f"""👤 کاربر {uid}

💰 موجودی: {format_p(d[1])}
🏦 پرداخت موفق: {d[4]}
🛍 سرویس‌ها: {d[2]}
⚠️ اخطار: {d[3]}
⏰ عضویت: {d[7]}
""",
                     reply_markup=kb)
    user_states[ADMIN_ID] = None

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
    cursor.execute("UPDATE users SET warnings=warnings+1 WHERE user_id=?", (uid,))
    conn.commit()
    bot.send_message(uid, "⚠️ از سمت ادمین اخطار دریافت کردید")
    bot.answer_callback_query(c.id, "ثبت شد")

@bot.message_handler(func=lambda m: m.from_user.id==ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") in ["ADM_ADD","ADM_SUB"])
def adm_balance_edit(m):
    st = user_states.get(ADMIN_ID, {})
    if not m.text.isdigit():
        bot.send_message(ADMIN_ID, "عدد بفرست"); return
    amt = int(m.text); uid = st["uid"]

    if st["state"] == "ADM_ADD":
        cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amt, uid))
        bot.send_message(uid, f"💰 {format_p(amt)} تومان به حسابت اضافه شد (ادمین)")
    else:
        cursor.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amt, uid))
        bot.send_message(uid, f"💰 {format_p(amt)} تومان از حسابت کسر شد (ادمین)")

    conn.commit()
    user_states[ADMIN_ID] = None
    bot.send_message(ADMIN_ID, "انجام شد")

# برودکست
@bot.callback_query_handler(func=lambda c: c.data == "adm_broadcast")
def adm_broadcast(c):
    if c.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {"state":"ADM_BC"}
    bot.send_message(ADMIN_ID, "پیام همگانی را ارسال کنید:")

@bot.message_handler(func=lambda m: m.from_user.id==ADMIN_ID and user_states.get(ADMIN_ID, {}).get("state") == "ADM_BC")
def do_broadcast(m):
    cursor.execute("SELECT user_id FROM users")
    users = [r[0] for r in cursor.fetchall()]
    ok = 0
    for u in users:
        try:
            bot.send_message(u, m.text)
            ok += 1
        except:
            pass
    user_states[ADMIN_ID] = None
    bot.send_message(ADMIN_ID, f"ارسال شد برای {ok} نفر")

# --------------- WEB ---------------
@app.route('/')
def home():
    return "OK"

def run():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling(skip_pending=True)
