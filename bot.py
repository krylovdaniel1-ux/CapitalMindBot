import os
import time
import datetime
import telebot
from telebot import types
from openai import OpenAI

# ======================
# ENV
# ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не найден в Railway Variables")

if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY не найден в Railway Variables")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)

# ======================
# CONFIG
# ======================
FREE_LIMIT = 5
PRO_PRICE_STARS = 200

users = {}
ai_mode = {}

# ======================
# MENU
# ======================
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🤖 AI", "👤 Профиль")
    kb.add("⭐ PRO", "❓ Помощь")
    return kb

# ======================
# USER HELPERS
# ======================
def get_user(user_id):
    return users.setdefault(user_id, {
        "questions_today": 0,
        "last_date": datetime.date.today(),
        "pro_until": None
    })

def is_pro(user_id):
    u = get_user(user_id)
    return u["pro_until"] and u["pro_until"] > datetime.datetime.now()

def can_use(user_id):
    u = get_user(user_id)

    if is_pro(user_id):
        return True

    if u["last_date"] != datetime.date.today():
        u["questions_today"] = 0
        u["last_date"] = datetime.date.today()

    if u["questions_today"] < FREE_LIMIT:
        u["questions_today"] += 1
        return True

    return False

# ======================
# START
# ======================
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🚀 <b>CapitalMind</b>\n\n"
        "Я твой AI-помощник по финансам, развитию и стратегиям 💰📈\n\n"
        "💎 Бесплатно: 5 вопросов в день\n"
        "⭐ PRO: безлимит + приоритет\n\n"
        "Выбирай кнопку ниже 👇",
        reply_markup=main_menu()
    )

# ======================
# HELP
# ======================
@bot.message_handler(func=lambda m: m.text == "❓ Помощь")
def help_btn(message):
    bot.send_message(
        message.chat.id,
        "🤖 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Нажми <b>AI</b>\n"
        "2️⃣ Напиши вопрос\n"
        "3️⃣ Получи умный ответ 🚀\n\n"
        "Хочешь безлимит? Жми ⭐ PRO",
        reply_markup=main_menu()
    )

# ======================
# PROFILE
# ======================
@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
    user_id = message.from_user.id
    u = get_user(user_id)

    bot.send_message(
        message.chat.id,
        f"👤 <b>Твой профиль</b>\n\n"
        f"📊 Вопросов сегодня: {u['questions_today']}/{FREE_LIMIT}\n"
        f"💎 PRO: {'✅ активен' if is_pro(user_id) else '❌ нет'}\n",
        reply_markup=main_menu()
    )

# ======================
# PRO PURCHASE
# ======================
@bot.message_handler(func=lambda m: m.text == "⭐ PRO")
def buy_pro(message):
    prices = [types.LabeledPrice(label="PRO подписка", amount=PRO_PRICE_STARS)]

    bot.send_invoice(
        message.chat.id,
        title="⭐ PRO CapitalMind",
        description="Безлимитный доступ к AI на 30 дней 🚀",
        invoice_payload="pro-subscription",
        provider_token="",  # для Stars оставить пустым
        currency="XTR",
        prices=prices,
        start_parameter="buy-pro"
    )

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    user_id = message.from_user.id
    u = get_user(user_id)
    u["pro_until"] = datetime.datetime.now() + datetime.timedelta(days=30)

    bot.send_message(
        message.chat.id,
        "🎉 <b>Оплата прошла успешно!</b>\n\n"
        "⭐ PRO активирован на 30 дней 🚀\n"
        "Теперь у тебя безлимит!",
        reply_markup=main_menu()
    )

# ======================
# AI BUTTON
# ======================
@bot.message_handler(func=lambda m: m.text == "🤖 AI")
def ai_button(message):
    ai_mode[message.chat.id] = True
    bot.send_message(
        message.chat.id,
        "🤖 Режим AI включён!\n\n"
        "Напиши свой вопрос ниже 👇",
        reply_markup=main_menu()
    )

# ======================
# AI RESPONSE
# ======================
@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not ai_mode.get(chat_id):
        return

    if not can_use(user_id):
        bot.send_message(
            chat_id,
            "🚫 Лимит бесплатных вопросов исчерпан.\n\n"
            "Купи ⭐ PRO за 200 Stars и получи безлимит 🚀",
            reply_markup=main_menu()
        )
        return

    bot.send_chat_action(chat_id, "typing")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Ты финансовый AI-ассистент. Отвечай по-русски, структурировано, с эмодзи 🚀📈💰."
                },
                {"role": "user", "content": message.text}
            ]
        )

        answer = response.choices[0].message.content
        bot.send_message(chat_id, answer, reply_markup=main_menu())

    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка AI: {e}")

# ======================
# RUN
# ======================
bot.remove_webhook()
bot.infinity_polling(skip_pending=True, timeout=30)
