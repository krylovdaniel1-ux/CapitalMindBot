import os
import telebot
from telebot import types
from openai import OpenAI

# ====== ТОКЕНЫ ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# ====== ТВОИ ДАННЫЕ ======
CARD_NUMBER = "4441114434646897"
ADMIN_ID = "1215610657"

# ====== ГЛАВНОЕ МЕНЮ ======
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👤 Профиль", "💎 PRO")
    markup.add("🚀 Карьера", "❓ Помощь")
    markup.add("🤖 Задать вопрос")
    return markup

# ====== START ======
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🚀 Добро пожаловать в CapitalMind!\n\n"
        "💰 Умный AI помощник по финансам\n"
        "⭐ PRO версия — 200 ⭐\n\n"
        "Выберите действие ниже 👇",
        reply_markup=main_menu()
    )

# ====== ПРОФИЛЬ ======
@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
    bot.send_message(
        message.chat.id,
        f"👤 Ваш профиль:\n\n"
        f"🆔 ID: {message.from_user.id}\n"
        f"⭐ Статус: Free\n\n"
        f"Хотите больше возможностей? Нажмите 💎 PRO"
    )

# ====== PRO ======
@bot.message_handler(func=lambda m: m.text == "💎 PRO")
def pro(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💳 Оплатить PRO")
    markup.add("🔙 Назад")

    bot.send_message(
        message.chat.id,
        "💎 PRO подписка — 200 ⭐\n\n"
        "Что дает PRO:\n"
        "🔥 Приоритетные ответы\n"
        "⚡ Быстрее AI\n"
        "📊 Расширенный анализ\n\n"
        "Нажмите оплатить 👇",
        reply_markup=markup
    )

# ====== ОПЛАТА ======
@bot.message_handler(func=lambda m: m.text == "💳 Оплатить PRO")
def pay(message):
    bot.send_message(
        message.chat.id,
        f"💳 Для оплаты PRO (200 ⭐)\n\n"
        f"Переведите 200 ⭐ (или эквивалент)\n"
        f"на карту:\n\n"
        f"💳 {CARD_NUMBER}\n\n"
        f"После перевода нажмите 'Я оплатил' 👇"
    )

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("✅ Я оплатил")
    markup.add("🔙 Назад")
    bot.send_message(message.chat.id, "Ожидаю подтверждение оплаты 💬", reply_markup=markup)

# ====== ПОДТВЕРЖДЕНИЕ ======
@bot.message_handler(func=lambda m: m.text == "✅ Я оплатил")
def confirm_payment(message):
    bot.send_message(
        message.chat.id,
        "⏳ Проверяем оплату...\n"
        "Администратор скоро подтвердит ✅"
    )

    bot.send_message(
        ADMIN_ID,
        f"💰 Новая заявка на PRO!\n\n"
        f"Пользователь: @{message.from_user.username}\n"
        f"ID: {message.from_user.id}"
    )

# ====== КАРЬЕРА ======
@bot.message_handler(func=lambda m: m.text == "🚀 Карьера")
def career(message):
    bot.send_message(
        message.chat.id,
        "🚀 Раздел Карьера\n\n"
        "📈 Здесь скоро появятся инвестиционные стратегии,\n"
        "аналитика и рекомендации 💰"
    )

# ====== ПОМОЩЬ ======
@bot.message_handler(func=lambda m: m.text == "❓ Помощь")
def help_section(message):
    bot.send_message(
        message.chat.id,
        "❓ Помощь\n\n"
        "💬 Чтобы задать вопрос AI — нажмите 🤖 Задать вопрос\n"
        "💎 Чтобы купить PRO — нажмите PRO"
    )

# ====== НАЗАД ======
@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def back(message):
    bot.send_message(
        message.chat.id,
        "Главное меню 👇",
        reply_markup=main_menu()
    )

# ====== КНОПКА AI ======
@bot.message_handler(func=lambda m: m.text == "🤖 Задать вопрос")
def ask_ai(message):
    bot.send_message(
        message.chat.id,
        "🤖 Напишите свой вопрос, и я отвечу 👇"
    )

# ====== AI ОБРАБОТКА ======
@bot.message_handler(func=lambda m: m.text not in [
    "👤 Профиль",
    "💎 PRO",
    "🚀 Карьера",
    "❓ Помощь",
    "🤖 Задать вопрос",
    "💳 Оплатить PRO",
    "✅ Я оплатил",
    "🔙 Назад"
])
def handle_ai(message):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты умный финансовый AI ассистент. Отвечай на русском языке красиво и с эмодзи."},
                {"role": "user", "content": message.text}
            ]
        )

        bot.send_message(
            message.chat.id,
            response.choices[0].message.content
        )

    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

# ====== ЗАПУСК ======
bot.infinity_polling()
