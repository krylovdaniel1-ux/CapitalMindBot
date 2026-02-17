import os
import json
import telebot
from telebot import types
from openai import OpenAI

# ================= CONFIG =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

ADMIN_ID =1215610657   # <-- ВСТАВЬ СВОЙ TELEGRAM ID
CARD_NUMBER = "4441114434646897"  # <-- ВСТАВЬ СВОЮ КАРТУ
PRO_PRICE = "200 грн"
FREE_LIMIT = 5

DATA_FILE = "users.json"

# ==========================================

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)

# ================= STORAGE =================
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        users = json.load(f)
else:
    users = {}

def save_users():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f)

def get_user(user_id):
    user_id = str(user_id)
    if user_id not in users:
        users[user_id] = {
            "is_pro": False,
            "questions_today": 0
        }
        save_users()
    return users[user_id]

# ================= MENU =================
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🤖 Задать вопрос")
    markup.add("👤 Профиль", "💎 PRO")
    markup.add("🚀 Карьера", "❓ Помощь")
    return markup

# ================= START =================
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🚀 <b>CapitalMind</b>\n\n"
        "Твой AI-ассистент по развитию и финансам 💰\n\n"
        "🆓 Бесплатно: 5 вопросов\n"
        "💎 PRO: безлимит\n\n"
        "Выбирай ниже 👇",
        reply_markup=main_menu()
    )

# ================= PROFILE =================
@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
    user = get_user(message.from_user.id)
    status = "💎 PRO" if user["is_pro"] else "🆓 Бесплатный"

    bot.send_message(
        message.chat.id,
        f"👤 <b>Профиль</b>\n\n"
        f"ID: <code>{message.from_user.id}</code>\n"
        f"Статус: {status}\n"
        f"Вопросов сегодня: {user['questions_today']}/{FREE_LIMIT}"
    )

# ================= PRO INFO =================
@bot.message_handler(func=lambda m: m.text == "💎 PRO")
def pro_info(message):
    bot.send_message(
        message.chat.id,
        f"💎 <b>PRO подписка</b>\n\n"
        f"✨ Безлимитные ответы\n"
        f"🚀 Более глубокий анализ\n\n"
        f"💰 Цена: {PRO_PRICE}\n\n"
        f"Для оплаты нажми: <b>Оплатить PRO</b>"
    )

@bot.message_handler(func=lambda m: m.text == "Оплатить PRO")
def payment_instruction(message):
    bot.send_message(
        message.chat.id,
        f"💳 <b>Оплата PRO</b>\n\n"
        f"Переведи {PRO_PRICE} на карту:\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        f"После перевода напиши:\n"
        f"<b>Я оплатил</b>"
    )

@bot.message_handler(func=lambda m: m.text == "Я оплатил")
def payment_notify(message):
    bot.send_message(
        ADMIN_ID,
        f"💰 Пользователь {message.from_user.id} сообщил об оплате."
    )
    bot.send_message(
        message.chat.id,
        "⏳ Ожидай подтверждения администратора."
    )

# ================= ACTIVATE PRO =================
@bot.message_handler(commands=["activate"])
def activate_pro(message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        user_id = message.text.split()[1]
        users[user_id]["is_pro"] = True
        save_users()

        bot.send_message(user_id, "🎉 <b>PRO активирован!</b>\nТеперь безлимит 🚀")
        bot.reply_to(message, "✅ PRO включен")
    except:
        bot.reply_to(message, "Используй: /activate USER_ID")

# ================= HELP =================
@bot.message_handler(func=lambda m: m.text == "❓ Помощь")
def help_section(message):
    bot.send_message(
        message.chat.id,
        "🤖 Просто напиши вопрос и я отвечу.\n\n"
        "Хочешь без лимитов? Подключай 💎 PRO."
    )

# ================= CAREER =================
@bot.message_handler(func=lambda m: m.text == "🚀 Карьера")
def career(message):
    bot.send_message(
        message.chat.id,
        "🚀 Раздел карьеры.\n\n"
        "Напиши:\n"
        "• Как выбрать профессию?\n"
        "• Как увеличить доход?\n"
        "• Как построить стратегию роста?"
    )

# ================= AI =================
@bot.message_handler(func=lambda m: m.text == "🤖 Задать вопрос")
def ask_ai(message):
    bot.send_message(
        message.chat.id,
        "🤖 Напиши свой вопрос 👇"
    )

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user = get_user(message.from_user.id)

    if not user["is_pro"]:
        if user["questions_today"] >= FREE_LIMIT:
            bot.send_message(
                message.chat.id,
                "🚫 Лимит бесплатных вопросов исчерпан.\nПодключи 💎 PRO."
            )
            return
        user["questions_today"] += 1
        save_users()

    bot.send_chat_action(message.chat.id, "typing")

    try:
        system_prompt = (
            "Ты профессиональный AI-наставник. "
            "Отвечай красиво, структурировано, с эмодзи."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message.text}
            ]
        )

        bot.send_message(
            message.chat.id,
            response.choices[0].message.content,
            reply_markup=main_menu()
        )

    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

# ================= RUN =================
bot.infinity_polling(skip_pending=True)
