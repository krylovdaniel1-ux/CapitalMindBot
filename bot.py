import os
import time
import sqlite3
from datetime import datetime, timedelta, timezone

import telebot
from telebot import types
from telebot.types import LabeledPrice

from openai import OpenAI

# =========================
# ENV
# =========================
TELEGRAM_TOKEN = (os.getenv("TELEGRAM_TOKEN") or "").strip()
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не задан в Railway Variables")
if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY не задан в Railway Variables")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)

UTC = timezone.utc
DB_PATH = "bot.db"

# =========================
# STARS / PRO
# =========================
PRO_PRICE_STARS = 200
PRO_DAYS = 30
STARS_CURRENCY = "XTR"     # Telegram Stars
PROVIDER_TOKEN = ""        # Для Stars оставляем пустым
PRO_PAYLOAD = "capitalmind_pro_30d"

# =========================
# UI TEXT BUTTONS
# =========================
BTN_CAREER = "💼 Карьера"
BTN_TEST = "🧠 Тест"
BTN_PROFILE = "👤 Профиль"
BTN_PRO = "⭐ PRO (200⭐)"
BTN_HELP = "🆘 Помощь"
BTN_MENU = "🏠 Меню"
BTN_EXIT_CAREER = "⬅️ Выйти из карьеры"

# =========================
# DB
# =========================
def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            pro_until TEXT DEFAULT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS state (
            user_id INTEGER PRIMARY KEY,
            mode TEXT DEFAULT 'menu',
            test_step INTEGER DEFAULT 0,
            score_it INTEGER DEFAULT 0,
            score_business INTEGER DEFAULT 0,
            score_creative INTEGER DEFAULT 0,
            score_analytics INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def ensure_user(user):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users(user_id, first_name, username, pro_until) VALUES(?,?,?,NULL)",
            (user.id, user.first_name or "", user.username or "")
        )
    else:
        cur.execute(
            "UPDATE users SET first_name=?, username=? WHERE user_id=?",
            (user.first_name or "", user.username or "", user.id)
        )

    cur.execute("SELECT user_id FROM state WHERE user_id=?", (user.id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO state(user_id, mode, test_step, score_it, score_business, score_creative, score_analytics) "
            "VALUES(?, 'menu', 0, 0, 0, 0, 0)",
            (user.id,)
        )
    conn.commit()
    conn.close()

def set_mode(user_id: int, mode: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE state SET mode=? WHERE user_id=?", (mode, user_id))
    conn.commit()
    conn.close()

def get_state(user_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT mode, test_step, score_it, score_business, score_creative, score_analytics FROM state WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return ("menu", 0, 0, 0, 0, 0)
    return row

def reset_test(user_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE state
        SET test_step=0, score_it=0, score_business=0, score_creative=0, score_analytics=0, mode='test'
        WHERE user_id=?
    """, (user_id,))
    conn.commit()
    conn.close()

def add_score(user_id: int, it=0, business=0, creative=0, analytics=0):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE state
        SET score_it = score_it + ?,
            score_business = score_business + ?,
            score_creative = score_creative + ?,
            score_analytics = score_analytics + ?
        WHERE user_id=?
    """, (it, business, creative, analytics, user_id))
    conn.commit()
    conn.close()

def set_test_step(user_id: int, step: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE state SET test_step=? WHERE user_id=?", (step, user_id))
    conn.commit()
    conn.close()

def get_pro_until(user_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT pro_until FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def set_pro_until(user_id: int, until_iso: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET pro_until=? WHERE user_id=?", (until_iso, user_id))
    conn.commit()
    conn.close()

def is_pro(user_id: int) -> bool:
    pro_until = get_pro_until(user_id)
    if not pro_until:
        return False
    try:
        until = datetime.fromisoformat(pro_until)
        return datetime.now(UTC) < until
    except Exception:
        return False

# =========================
# KEYBOARDS
# =========================
def main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton(BTN_CAREER), types.KeyboardButton(BTN_TEST))
    kb.row(types.KeyboardButton(BTN_PROFILE), types.KeyboardButton(BTN_PRO))
    kb.row(types.KeyboardButton(BTN_HELP), types.KeyboardButton(BTN_MENU))
    return kb

def career_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton(BTN_EXIT_CAREER), types.KeyboardButton(BTN_MENU))
    return kb

def test_kb(options):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for row in options:
        kb.row(*[types.KeyboardButton(x) for x in row])
    kb.row(types.KeyboardButton(BTN_MENU))
    return kb

# =========================
# TEXTS
# =========================
WELCOME = (
    "🚀 <b>CapitalMind</b>\n\n"
    "Я — карьерный бот.\n"
    "✅ В режиме <b>Карьера</b> отвечает AI только по работе/навыкам/резюме/заработку.\n"
    "🧠 В <b>Тесте</b> подбираю направление и даю план.\n\n"
    "Выбирай кнопки ниже 👇"
)

HELP = (
    "🆘 <b>Помощь</b>\n\n"
    f"• <b>{BTN_CAREER}</b> — AI отвечает только по карьере 💼\n"
    f"• <b>{BTN_TEST}</b> — мини-тест → направление + советы 🧠\n"
    f"• <b>{BTN_PROFILE}</b> — статус PRO 👤\n"
    f"• <b>{BTN_PRO}</b> — PRO на 30 дней за 200⭐ ⭐\n\n"
    "Команды:\n"
    "/start — меню\n"
    "/terms — условия\n"
    "/paysupport — поддержка оплат"
)

TERMS = (
    "📜 <b>Условия</b>\n\n"
    "• Бот даёт рекомендации по карьере и обучению.\n"
    "• Не вводи пароли/коды/карты.\n"
    "• PRO — цифровая услуга на 30 дней.\n"
)

PAY_SUPPORT = (
    "💳 <b>Поддержка оплат</b>\n\n"
    "Если платёж не проходит:\n"
    "• перезапусти Telegram\n"
    "• попробуй снова через 2–5 минут\n"
    "• проверь, что у
