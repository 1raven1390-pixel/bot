import telebot
from telebot import types
import sqlite3
import time
from datetime import datetime

TOKEN = "8695463789:AAF7vKrNUtp05Nm5ydsEY6W8qeUYJ45KXoE"
ADMIN_ID = 8521801987
CHANNEL = "@rafe_filter_A"

bot = telebot.TeleBot(TOKEN)

# ---------------- DATABASE ----------------
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    configs INTEGER DEFAULT 0,
    name TEXT,
    username TEXT,
    join_date TEXT
)
""")
conn.commit()

user_state = {}

# ---------------- ADD USER ----------------
def add_user(u):
    try:
        cursor.execute("SELECT * FROM users WHERE user_id=?", (u.id,))
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO users VALUES (?,?,?,?,?,?)",
                (u.id,0,0,u.first_name,u.username,str(datetime.now()))
            )
            conn.commit()
    except Exception as e:
        print("DB ERROR:", e)

# ---------------- CHECK MEMBER ----------------
def is_member(user_id):
    try:
        m = bot.get_chat_member(CHANNEL, user_id)
        return m.status in ["member", "creator", "administrator"]
    except:
        return False

# ---------------- MENU ----------------
def menu(chat_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛒 خرید", callback_data="buy"))
    kb.add(types.InlineKeyboardButton("💰 افزایش موجودی", callback_data="charge"))
    kb.add(types.InlineKeyboardButton("👤 حساب کاربری", callback_data="account"))
    kb.add(types.InlineKeyboardButton("📊 تعرفه", callback_data="price"))
    kb.add(types.InlineKeyboardButton("📞 پشتیبانی", callback_data="support"))
    bot.send_message(chat_id,"👇 پنل:",reply_markup=kb)

# ---------------- START ----------------
@bot.message_handler(commands=['start'])
def start(m):
    add_user(m.from_user)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL.replace('@','')}"))
    kb.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data="check"))

    bot.send_message(m.chat.id,"برای استفاده از ربات اول عضو کانال شو 👇",reply_markup=kb)

# ---------------- CHECK JOIN ----------------
@bot.callback_query_handler(func=lambda c:c.data=="check")
def check(c):
    if is_member(c.from_user.id):
        menu(c.message.chat.id)
    else:
        bot.answer_callback_query(c.id,"❌ هنوز عضو نشدی",show_alert=True)

# ---------------- BUY ----------------
@bot.callback_query_handler(func=lambda c:c.data=="buy")
def buy(c):
    kb=types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("۱ ماهه",callback_data="1m"))
    kb.add(types.InlineKeyboardButton("♾ بدون محدودیت+VIP",callback_data="vip"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت",callback_data="menu"))
    bot.edit_message_text("انتخاب پلن:",c.message.chat.id,c.message.message_id,reply_markup=kb)

# ---------------- 1 MONTH ----------------
@bot.callback_query_handler(func=lambda c:c.data=="1m")
def m1(c):
    kb=types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("تک کاربره",callback_data="single"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت",callback_data="buy"))
    bot.edit_message_text("نوع:",c.message.chat.id,c.message.message_id,reply_markup=kb)

@bot.callback_query_handler(func=lambda c:c.data=="single")
def single(c):
    kb=types.InlineKeyboardMarkup()
    for i in ["1","2","3","5"]:
        kb.add(types.InlineKeyboardButton(f"{i} گیگ",callback_data=f"buy_{i}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت",callback_data="menu"))
    bot.edit_message_text("حجم:",c.message.chat.id,c.message.message_id,reply_markup=kb)

# ---------------- VIP ----------------
@bot.callback_query_handler(func=lambda c:c.data=="vip")
def vip(c):
    kb=types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("بدون محدودیت کاربری",callback_data="vip_user"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت",callback_data="buy"))
    bot.edit_message_text("VIP:",c.message.chat.id,c.message.message_id,reply_markup=kb)

@bot.callback_query_handler(func=lambda c:c.data=="vip_user")
def vip_user(c):
    kb=types.InlineKeyboardMarkup()
    for i in ["1","2","3","5","10"]:
        kb.add(types.InlineKeyboardButton(f"{i} گیگ",callback_data=f"vip_{i}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت",callback_data="menu"))
    bot.edit_message_text("حجم:",c.message.chat.id,c.message.message_id,reply_markup=kb)

# ---------------- CONFIRM ----------------
@bot.callback_query_handler(func=lambda c:c.data.startswith("buy_") or c.data.startswith("vip_"))
def confirm(c):
    kb=types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ تایید",callback_data=f"ok_{c.data}"))
    kb.add(types.InlineKeyboardButton("❌ لغو",callback_data="menu"))
    bot.edit_message_text("آیا مطمئن هستید؟",c.message.chat.id,c.message.message_id,reply_markup=kb)

# ---------------- SEND ORDER ----------------
@bot.callback_query_handler(func=lambda c:c.data.startswith("ok_"))
def send_order(c):
    data=c.data.replace("ok_","")
    user=c.from_user.id

    bot.send_message(ADMIN_ID,f"🛒 سفارش جدید\n👤 {user}\n📦 {data}")
    bot.send_message(user,"⏳ سرور در حال آماده سازی است")

# ---------------- CHARGE ----------------
@bot.callback_query_handler(func=lambda c:c.data=="charge")
def charge(c):
    msg=bot.send_message(c.message.chat.id,"💰 مبلغ به تومان:")
    bot.register_next_step_handler(msg,get_amount)

def get_amount(m):
    try:
        amount=int(m.text)
    except:
        return bot.send_message(m.chat.id,"❌ فقط عدد وارد کن")

    user_state[m.chat.id]={"amount":amount}
    bot.send_message(m.chat.id,f"{amount} تومان\n💳 شماره کارت مبدا:")
    bot.register_next_step_handler(m,get_card)

def get_card(m):
    user_state[m.chat.id]["card"]=m.text
    amount=user_state[m.chat.id]["amount"]

    kb=types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📤 ارسال رسید",callback_data="receipt"))

    bot.send_message(m.chat.id,f"""💳 کارت مقصد:
6221061233705260
افراس

💰 مبلغ: {amount} تومان""",reply_markup=kb)

@bot.callback_query_handler(func=lambda c:c.data=="receipt")
def receipt(c):
    msg=bot.send_message(c.message.chat.id,"📸 رسید را ارسال کن")
    bot.register_next_step_handler(msg,send_receipt)

def send_receipt(m):
    data=user_state.get(m.chat.id)

    kb=types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ تایید",callback_data=f"okcharge_{m.chat.id}_{data['amount']}"),
        types.InlineKeyboardButton("❌ رد",callback_data="reject")
    )

    bot.send_message(ADMIN_ID,f"💰 درخواست شارژ\n👤 {m.chat.id}\n💵 {data['amount']}",reply_markup=kb)

    if m.photo:
        bot.forward_message(ADMIN_ID,m.chat.id,m.message_id)

    bot.send_message(m.chat.id,"✅ رسید ارسال شد")

@bot.callback_query_handler(func=lambda c:c.data.startswith("okcharge_"))
def confirm_charge(c):
    if c.from_user.id!=ADMIN_ID: return

    data=c.data.split("_")
    uid=int(data[1])
    amount=int(data[2])

    cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount,uid))
    conn.commit()

    bot.send_message(uid,f"✅ {amount} تومان اضافه شد")

# ---------------- ACCOUNT ----------------
@bot.callback_query_handler(func=lambda c:c.data=="account")
def account(c):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (c.from_user.id,))
    d=cursor.fetchone()

    username = f"@{d[4]}" if d[4] else "ندارد"

    bot.send_message(c.message.chat.id,f"""
📊 اطلاعات حساب:
🆔 {d[0]}
👤 {username}
💰 {d[1]} تومان
📦 {d[2]}
📅 {d[5]}
""")

# ---------------- SUPPORT ----------------
@bot.callback_query_handler(func=lambda c:c.data=="support")
def support(c):
    bot.send_message(c.message.chat.id,"📞 @Amir_confing_meli")

# ---------------- RUN ----------------
print("Bot is running...")

while True:
    try:
        bot.polling(none_stop=True, interval=1, timeout=60)
    except Exception as e:
        print("CRASH:", e)
        time.sleep(3)