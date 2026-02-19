import os
import time
import telebot
from telebot import types
from openai import OpenAI

# ====== ENV ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ Не найден TELEGRAM_TOKEN в переменных окружения Railway")
if not OPENAI_API_KEY:
    raise RuntimeError("❌ Не найден OPENAI_API_KEY в переменных окружения Railway")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)

# ====== SIMPLE STATE (сбрасывается при перезапуске) ======
user_mode = {}  # chat_id -> "career" | None

# ====== UI ======
BTN_CAREER = "💼 Карьера"
BTN_PROFILE = "👤 Профиль"
BTN_PRO = "⭐ Pro (200 звёзд)"
BTN_HELP = "🆘 Помощь"
BTN_EXIT = "⬅️ Выйти из Карьеры"

def main_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_CAREER), types.KeyboardButton(BTN_PROFILE))
    kb.add(types.KeyboardButton(BTN_PRO), types.KeyboardButton(BTN_HELP))
    return kb

def career_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_EXIT))
    return kb

# ====== TEXTS ======
WELCOME_TEXT = (
    "🚀 <b>CapitalMind</b> на связи!\n\n"
    "Я помогу по теме <b>карьеры</b>: профессии, резюме, собеседования, навыки, план развития.\n\n"
    "Выбирай кнопку 👇"
)

PROFILE_TEXT = (
    "👤 <b>Профиль</b>\n\n"
    "Пока в разработке, но скоро тут будет:\n"
    "• твои цели 🎯\n"
    "• прогресс 📈\n"
    "• история вопросов 🧠\n\n"
    "А пока заходи в <b>Карьера</b> — там уже работает ИИ 🙂"
)

PRO_TEXT = (
    "⭐ <b>Pro (200 звёзд)</b>\n\n"
    "Сейчас честно: <b>авто-оплата звёздами</b> в твоём боте ещё не подключена.\n"
    "Чтобы принимать платежи официально, нужен платёжный провайдер Telegram (через BotFather → Payments).\n\n"
    "✅ Что можно сделать уже сейчас:\n"
    "1) Я сделаю кнопку Pro и доступ к фишкам (лимиты/режимы) ✅\n"
    "2) Оплату подключим, когда выберешь провайдера (Portmone/Redsys и т.д.)\n\n"
    "Напиши: <b>Хочу Pro</b> — и я подскажу, что именно выбрать под Украину/твою ситуацию."
)

HELP_TEXT = (
    "🆘 <b>Помощь</b>\n\n"
    "• Нажми <b>💼 Карьера</b> и задай вопрос (например: «какая профессия мне подходит?»)\n"
    "• <b>👤 Профиль</b> — скоро добавим\n"
    "• <b>⭐ Pro</b> — подключим оплату официально через провайдера\n\n"
    "Команды:\n"
    "• /start — меню\n"
    "• /career — режим карьеры\n"
    "• /exit — выйти из карьеры"
)

# ====== AI (Career only) ======
def career_ai_answer(user_text: str) -> str:
    # Жёстко ограничиваем тематику: карьера/работа/образование/навыки
    system_prompt = (
        "Ты — карьерный консультант. Отвечай ТОЛЬКО по теме карьеры: "
        "профессии, резюме, собеседования, навыки, обучение, поиск работы, "
        "фриланс/стажировки, план развития. "
        "Если вопрос не про карьеру — вежливо откажись и попроси задать вопрос про карьеру. "
        "Пиши по-русски, дружелюбно, со смайликами, короткими списками."
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()

# ====== HANDLERS ======
@bot.message_handler(commands=["start"])
def cmd_start(message):
    user_mode[message.chat.id] = None
    bot.send_message(message.chat.id, WELCOME_TEXT, reply_markup=main_menu_keyboard())

@bot.message_handler(commands=["career"])
def cmd_career(message):
    user_mode[message.chat.id] = "career"
    bot.send_message(
        message.chat.id,
        "💼 <b>Режим Карьера включён</b> ✅\n\nЗадай вопрос про карьеру 👇",
        reply_markup=career_keyboard()
    )

@bot.message_handler(commands=["exit"])
def cmd_exit(message):
    user_mode[message.chat.id] = None
    bot.send_message(message.chat.id, "⬅️ Ок, вышел из режима Карьера.", reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    text = (message.text or "").strip()
    chat_id = message.chat.id

    # кнопки меню
    if text == BTN_CAREER:
        return cmd_career(message)

    if text == BTN_EXIT:
        return cmd_exit(message)

    if text == BTN_PROFILE:
        user_mode[chat_id] = None
        bot.send_message(chat_id, PROFILE_TEXT, reply_markup=main_menu_keyboard())
        return

    if text == BTN_PRO:
        user_mode[chat_id] = None
        bot.send_message(chat_id, PRO_TEXT, reply_markup=main_menu_keyboard())
        return

    if text == BTN_HELP:
        bot.send_message(chat_id, HELP_TEXT, reply_markup=main_menu_keyboard())
        return

    # если включён режим карьеры -> отвечает ИИ
    if user_mode.get(chat_id) == "career":
        bot.send_chat_action(chat_id, "typing")
        try:
            answer = career_ai_answer(text)
            bot.send_message(chat_id, answer, reply_markup=career_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Ошибка ИИ: <code>{e}</code>\nПопробуй ещё раз.", reply_markup=career_keyboard())
        return

    # если не в режиме карьеры — направляем
    bot.send_message(
        chat_id,
        "🙂 Я отвечаю через ИИ только в режиме <b>💼 Карьера</b>.\nНажми кнопку <b>💼 Карьера</b> и задай вопрос.",
        reply_markup=main_menu_keyboard()
    )

# ====== RUN ======
if __name__ == "__main__":
    # чтобы не падал из-за временных сетевых глюков
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            print("Polling error:", e)
            time.sleep(3)

