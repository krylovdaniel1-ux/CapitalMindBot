import os
import sqlite3
from datetime import datetime, timedelta, timezone

import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, LabeledPrice
from openai import OpenAI

# =========================
# ENV
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

# =========================
# CONFIG
# =========================
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
PRO_PRICE_STARS = 200
PRO_DAYS = 30

# ВАЖНО: XTR = Telegram Stars
CURRENCY = "XTR"
PROVIDER_TOKEN = ""  # Для Stars он должен быть пустым

# =========================
# INIT
# =========================
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# DB (persist pro & mode)
# =========================
DB_PATH = "bot.db"

def db():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            mode TEXT DEFAULT 'menu',
            pro_until TEXT DEFAULT NULL
        )
    """)
    conn.commit()
    conn.close()

def set_mode(user_id: int, mode: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT INTO users(user_id, mode) VALUES(?, ?) ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode", (user_id, mode))
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT mode, pro_until FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return ("menu", None)
    return row[0], row[1]

def set_pro(user_id: int, until_iso: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users(user_id, pro_until) VALUES(?, ?)
        ON CONFLICT(user_id) DO UPDATE SET pro_until=excluded.pro_until
    """, (user_id, until_iso))
    conn.commit()
    conn.close()

def is_pro_active(pro_until_iso: str) -> bool:
    if not pro_until_iso:
        return False
    try:
        until = datetime.fromisoformat(pro_until_iso)
        return datetime.now(timezone.utc) < until
    except Exception:
        return False

# =========================
# UI
# =========================
BTN_CAREER = "💼 Карьера"
BTN_PROFILE = "👤 Профиль"
BTN_PRO = "⭐ Pro (200⭐/30 дней)"
BTN_HELP = "🆘 Помощь"
BTN_MENU = "🏠 Меню"

def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton(BTN_CAREER), KeyboardButton(BTN_PROFILE))
    kb.row(KeyboardButton(BTN_PRO), KeyboardButton(BTN_HELP))
    return kb

def career_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton(BTN_MENU))
    return kb

# =========================
# TEXTS
# =========================
WELCOME_TEXT = (
    "🚀 <b>CapitalMind</b>\n\n"
    "Я помогу по <b>карьере и работе</b>: резюме, собеседования, профессии, зарплаты, планы развития, навыки.\n\n"
    "Нажми кнопку ниже 👇"
)

HELP_TEXT = (
    "🧠 <b>Как пользоваться</b>\n\n"
    f"1) Нажми <b>{BTN_CAREER}</b> — включится режим карьеры.\n"
    "2) После этого просто пиши вопрос — я отвечу.\n\n"
    f"⭐ <b>Pro</b>: 200⭐ на 30 дней (покажу расширенные ответы и чек-листы).\n"
    "⚠️ Я отвечаю только по теме карьеры/работы."
)

CAREER_START_TEXT = (
    "💼 <b>Режим “Карьера” включён</b> ✅\n\n"
    "Пиши вопрос по работе.\n\n"
    "Примеры:\n"
    "• «Составь резюме на позицию…»\n"
    "• «Подготовь ответы на собеседование…»\n"
    "• «Какие навыки нужны для…?»\n"
    "• «Как поднять зарплату?»\n\n"
    "Я отвечу быстро и по делу 😎"
)

PRO_INFO_TEXT = (
    "⭐ <b>Pro подписка</b>\n\n"
    f"Цена: <b>{PRO_PRICE_STARS}⭐</b> на <b>{PRO_DAYS} дней</b>.\n\n"
    "Что даёт Pro:\n"
    "✅ Более подробные планы и чек-листы\n"
    "✅ Больше примеров + структура действий\n"
    "✅ Более длинные ответы и разборы\n\n"
    "Нажми кнопку оплаты — Telegram сам покажет окно оплаты ⭐"
)

# =========================
# AI
# =========================
CAREER_SYSTEM_PROMPT = (
    "Ты — карьерный ассистент. Отвечай ТОЛЬКО по теме карьеры, работы, профессий, резюме, собеседований, "
    "зарплаты, навыков, обучения, выбора специальности, коммуникации на работе, карьерного роста.\n"
    "Если вопрос не относится к работе/карьере — вежливо откажись и попроси переформулировать в контексте карьеры.\n"
    "Пиши по-русски. Используй дружелюбный тон и умеренно эмодзи.\n"
    "Структурируй ответ: коротко, затем пункты/шаги."
)

def ai_answer_career(user_text: str, pro: bool) -> str:
    # Для Pro делаем ответы более подробными
    detail_hint = (
        "Пользователь Pro: дай расширенный ответ, добавь чек-лист, примеры формулировок и план на 7 дней."
        if pro else
        "Пользователь не Pro: ответ будь кратким и практичным, без лишней воды."
    )

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": CAREER_SYSTEM_PROMPT},
            {"role": "system", "content": detail_hint},
            {"role": "user", "content": user_text},
        ],
        temperature=0.6,
    )
    return resp.choices[0].message.content

# =========================
# COMMANDS / START
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    set_mode(message.from_user.id, "menu")
    bot.send_message(message.chat.id, WELCOME_TEXT, reply_markup=main_keyboard())

# =========================
# BUTTON HANDLERS
# =========================
@bot.message_handler(func=lambda m: m.text == BTN_HELP)
def help_btn(message):
    bot.send_message(message.chat.id, HELP_TEXT, reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == BTN_MENU)
def menu_btn(message):
    set_mode(message.from_user.id, "menu")
    bot.send_message(message.chat.id, "🏠 Ты в меню. Выбирай кнопку 👇", reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == BTN_CAREER)
def career_btn(message):
    # типичный ответ (как ты просил) + потом ИИ уже на вопросы
    set_mode(message.from_user.id, "career")
    bot.send_message(message.chat.id, CAREER_START_TEXT, reply_markup=career_keyboard())

@bot.message_handler(func=lambda m: m.text == BTN_PROFILE)
def profile_btn(message):
    mode, pro_until = get_user(message.from_user.id)
    active = is_pro_active(pro_until)
    if active:
        until = datetime.fromisoformat(pro_until).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        pro_line = f"⭐ Pro: <b>активен</b> до <b>{until}</b>"
    else:
        pro_line = "⭐ Pro: <b>не активен</b>"

    text = (
        "👤 <b>Профиль</b>\n\n"
        f"🧭 Режим: <b>{mode}</b>\n"
        f"{pro_line}\n\n"
        "Хочешь — включай 💼 Карьера и задавай вопросы 😎"
    )
    bot.se
