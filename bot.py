import os
import time
import sqlite3
from datetime import datetime, timedelta, timezone

import telebot
from telebot import types
from telebot.types import LabeledPrice

from openai import OpenAI

# ======================
# CONFIG
# ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is missing in environment variables")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is missing in environment variables")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)

DB_PATH = "bot.db"
UTC = timezone.utc

PRO_PRICE_STARS = 200          # 200 ⭐
PRO_DAYS = 30                  # 30 дней
PRO_PAYLOAD = "capitalmind_pro_30d"
PRO_CURRENCY = "XTR"           # Telegram Stars currency tag
SUPPORT_USERNAME = "@CapitalMind360_bot"  # можешь поменять на свой @username

# ======================
# DB
# ======================
def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL;")
    return con

con = db()
con.execute("""
CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY,
  username TEXT,
  first_name TEXT,
  mode TEXT DEFAULT 'none',
  pro_until INTEGER DEFAULT 0,
  created_at INTEGER DEFAULT 0
);
""")
con.commit()

def upsert_user(u: types.User):
    now = int(time.time())
    con.execute("""
    INSERT INTO users(user_id, username, first_name, mode, pro_until, created_at)
    VALUES(?,?,?,?,?,?)
    ON CONFLICT(user_id) DO UPDATE SET
      username=excluded.username,
      first_name=excluded.first_name
    """, (u.id, u.username or "", u.first_name or "", "none", 0, now))
    con.commit()

def set_mode(user_id: int, mode: str):
    con.execute("UPDATE users SET mode=? WHERE user_id=?", (mode, user_id))
    con.commit()

def get_user(user_id: int):
    cur = con.execute("SELECT user_id, username, first_name, mode, pro_until FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row

def is_pro(user_id: int) -> bool:
    row = get_user(user_id)
    if not row:
        return False
    pro_until = int(row[4] or 0)
    return pro_until > int(time.time())

def add_pro(user_id: int, days: int):
    now = int(time.time())
    row = get_user(user_id)
    current_until = int(row[4] or 0) if row else 0
    base = max(now, current_until)
    new_until = int(base + days * 86400)
    con.execute("UPDATE users SET pro_until=? WHERE user_id=?", (new_until, user_id))
    con.commit()
    return new_until

# ======================
# UI
# ======================
BTN_CAREER = "💼 Карьера"
BTN_PROFILE = "👤 Профиль"
BTN_TEST = "🧠 Тест"
BTN_PRO = "⭐ PRO (200⭐ / 30 дней)"

def main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton(BTN_CAREER), types.KeyboardButton(BTN_PROFILE))
    kb.row(types.KeyboardButton(BTN_TEST), types.KeyboardButton(BTN_PRO))
    return kb

# ======================
# TEXTS
# ======================
WELCOME = (
    "🚀 <b>CapitalMind</b>\n\n"
    "Я карьерный помощник: резюме, собеседования, навыки, поиск работы.\n"
    "Выбери кнопку ниже 👇"
)

CAREER_INTRO = (
    "💼 <b>Режим карьеры включён</b>\n\n"
    "Напиши вопрос про работу.\n"
    "Примеры:\n"
    "• «Сделай резюме под вакансию…»\n"
    "• «Как отвечать на вопрос про зарплату?»\n"
    "• «Составь план изучения Python для джуна»\n\n"
    "🙂 Я отвечаю <b>только</b> по карьерной теме."
)

NOT_CAREER_TOPIC = (
    "🙂 Я заточен только под <b>карьеру и работу</b>.\n"
    "Спроси про резюме, собеседование, навыки, вакансии или карьерный план 👇"
)

PROFILE_TEXT = (
    "👤 <b>Профиль</b>\n"
    "• Пользователь: {name}\n"
    "• PRO: {pro}\n"
    "• До: {until}\n"
)

TEST_Q = (
    "🧠 <b>Мини-тест (карьера)</b>\n\n"
    "Вопрос:\n"
    "Как лучше ответить на собеседовании на «Расскажите о себе»?\n\n"
    "A) Пересказать всю биографию с детсада\n"
    "B) Коротко: кто я, ключевые навыки, 1–2 достижения, почему подхожу\n"
    "C) Сказать «не знаю»\n\n"
    "Напиши букву: A / B / C"
)

TEST_OK = "✅ Верно! Самый сильный вариант — <b>B</b>."
TEST_BAD = "❌ Почти. Правильный ответ — <b>B</b> (структурно и по делу)."

PRO_INFO = (
    "⭐ <b>PRO-подписка</b>\n\n"
    "• Цена: <b>200⭐</b>\n"
    "• Срок: <b>30 дней</b>\n"
    "• Дает: приоритетные ответы + больше лимитов (можно расширять дальше)\n\n"
    "Нажми кнопку оплаты ниже 👇"
)

TERMS = (
    "📜 <b>Условия</b>\n"
    "Оплачивая PRO, ты получаешь доступ на 30 дней.\n"
    "Если есть вопросы по оплате: /paysupport\n"
)

PAY_SUPPORT = (
    "🆘 <b>Поддержка по оплатам</b>\n"
    f"Напиши нам в Telegram: {SUPPORT_USERNAME}\n"
    "Укажи: дату, сумму (⭐), и что случилось."
)

# ======================
# OPENAI (career-only)
# ======================
SYSTEM_PROMPT = (
    "Ты — карьерный ассистент для Telegram-бота. "
    "Отвечай только по теме: работа, карьера, резюме, собеседования, навыки, поиск вакансий, "
    "переговоры о зарплате, планы обучения для профессии, рабочие ситуации. "
    "Если вопрос не про карьеру/работу — вежливо откажись и предложи задать карьерный вопрос. "
    "Пиши по-русски, дружелюбно, с лёгкими эмодзи. "
    "Ответы делай практичными: шаги + пример(ы)."
)

def ai_answer(user_text: str) -> str:
    # лёгкая фильтрация по ключевым словам (чтобы AI не уходил в “всё подряд”)
    career_keywords = [
        "работ", "карьер", "резюме", "cv", "собесед", "ваканс", "зарплат", "офер",
        "портфолио", "skill", "навык", "hr", "рекрутер", "linkedin", "опыт", "должност"
    ]
    text_low = user_text.lower()
    if not any(k in text_low for k in career_keywords):
        return NOT_CAREER_TOPIC

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text}
        ],
        temperature=0.6,
    )
    return resp.choices[0].message.content.strip()

# ======================
# COMMANDS
# ======================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    upsert_user(message.from_user)
    bot.send_message(message.chat.id, WELCOME, reply_markup=main_kb())

@bot.message_handler(commands=["terms"])
def cmd_terms(message):
    bot.send_message(message.chat.id, TERMS, reply_markup=main_kb())

@bot.message_handler(commands=["paysupport"])
def cmd_paysupport(message):
    bot.send_message(message.chat.id, PAY_SUPPORT, reply_markup=main_kb())

@bot.message_handler(commands=["profile"])
def cmd_profile(message):
    upsert_user(message.from_user)
    row = get_user(message.from_user.id)
    pro = is_pro(message.from_user.id)
    until_ts = int(row[4] or 0) if row else 0
    until = "—"
    if until_ts > 0:
        until = datetime.fromtimestamp(until_ts, tz=UTC).strftime("%d.%m.%Y %H:%M (UTC)")
    name = (message.from_user.first_name or "User")
    bot.send_message(
        mes
