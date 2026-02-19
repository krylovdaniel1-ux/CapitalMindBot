import os
import sqlite3
from datetime import datetime, timedelta, timezone, date
import random

import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, LabeledPrice
from openai import OpenAI

# =========================
# ENV
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не задан в Railway Variables")
if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY не задан в Railway Variables")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# STARS (Telegram)
# =========================
PRO_PRICE_STARS = 200
PRO_DAYS = 30
CURRENCY = "XTR"          # Telegram Stars
PROVIDER_TOKEN = ""       # Для Stars — пустой

# =========================
# DB
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
            xp INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_quest_date TEXT DEFAULT NULL,
            pro_until TEXT DEFAULT NULL
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT mode, xp, streak, last_quest_date, pro_until FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users(user_id) VALUES(?)", (user_id,))
        conn.commit()
        row = ("menu", 0, 0, None, None)
    conn.close()
    return {
        "mode": row[0],
        "xp": row[1],
        "streak": row[2],
        "last_quest_date": row[3],
        "pro_until": row[4],
    }

def set_mode(user_id: int, mode: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT INTO users(user_id, mode) VALUES(?, ?) ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode",
                (user_id, mode))
    conn.commit()
    conn.close()

def add_xp(user_id: int, amount: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET xp = COALESCE(xp,0) + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def set_streak_and_quest_date(user_id: int, streak: int, quest_date_iso: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET streak=?, last_quest_date=? WHERE user_id=?",
                (streak, quest_date_iso, user_id))
    conn.commit()
    conn.close()

def set_pro_until(user_id: int, until_iso: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET pro_until=? WHERE user_id=?", (until_iso, user_id))
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
BTN_QUEST = "📅 Задание дня"
BTN_PROFILE = "👤 Профиль"
BTN_PRO = "⭐ PRO 200⭐"
BTN_HELP = "🆘 Помощь"
BTN_MENU = "🏠 Меню"

def menu_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton(BTN_CAREER), KeyboardButton(BTN_QUEST))
    kb.row(KeyboardButton(BTN_PROFILE), KeyboardButton(BTN_PRO))
    kb.row(KeyboardButton(BTN_HELP))
    return kb

def career_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton(BTN_MENU))
    return kb

# =========================
# GAME CONTENT
# =========================
QUESTS_FREE = [
    "Составь 3 предложения о себе для резюме (кто ты, что умеешь, что хочешь).",
    "Найди 1 вакансию/стажировку и выпиши 3 требования к кандидату.",
    "Напиши 1 сообщение работодателю/наставнику: кто ты и чем можешь быть полезен.",
    "Выбери 1 навык и удели 20 минут обучению. Напиши, что именно изучал.",
    "Составь список из 5 профессий, которые тебе интересны, и почему.",
]

QUESTS_PRO = [
    "Сделай мини-резюме (5 пунктов): цель, навыки, проекты/опыт, достижения, контакты. Пришли — улучшу.",
    "Подготовь ответы на 5 вопросов собеседования: о себе, сильные/слабые стороны, опыт, конфликт, цель.",
    "Сделай план заработка на 7 дней: 1 услуга/навык → где найти клиентов → 1 действие в день.",
    "Составь портфолио-идею: 1 проект за 3 дня. Опиши тему, результат, как показать.",
    "Напиши 3 варианта cold-message для поиска подработки (разные стили).",
]

def pick_daily_quest(is_pro: bool) -> str:
    pool = QUESTS_PRO if is_pro else QUESTS_FREE
    return random.choice(pool)

# =========================
# AI PROMPT (Career only)
# =========================
CAREER_SYSTEM_PROMPT = (
    "Ты карьерный наставник. Отвечай ТОЛЬКО по темам работы и карьеры: "
    "профессии, навыки, обучение, резюме/CV, портфолио, собеседования, "
    "поиск стажировки/работы, зарплата, переговоры, фриланс, первые деньги. "
    "Если вопрос НЕ про карьеру/работу — вежливо откажись и попроси переформулировать в карьерном контексте. "
    "Отвечай на русском, дружелюбно, 1–3 эмодзи, структурировано (шаги/список)."
)

def ai_career_answer(user_text: str, pro: bool) -> str:
    pro_hint = (
        "Пользователь PRO: дай расширенный ответ, добавь чек-лист, примеры фраз и план на 7 дней."
        if pro else
        "Пользователь Free: ответ краткий и практичный, 5–8 пунктов максимум."
    )
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": CAREER_SYSTEM_PROMPT},
            {"role": "system", "content": pro_hint},
            {"role": "user", "content": user_text},
        ],
        temperature=0.6
    )
    return (resp.choices[0].message.content or "").strip()

# =========================
# MESSAGES
# =========================
WELCOME = (
    "🚀 <b>CapitalMind</b>\n\n"
    "Я — карьерный AI-наставник. Помогаю выбрать направление, заработать первые деньги, "
    "сделать резюме и пройти собеседование 💼\n\n"
    "Нажми <b>💼 Карьера</b> и задай вопрос.\n"
    "Или возьми <b>📅 Задание дня</b> — прокачаемся по шагам 🎯"
)

HELP = (
    "🆘 <b>Помощь</b>\n\n"
    f"• <b>{BTN_CAREER}</b> — включить режим карьеры (я отвечаю только по работе)\n"
    f"• <b>{BTN_QUEST}</b> — ежедневное задание + XP\n"
    f"• <b>{BTN_PRO}</b> — подписка на 30 дней за 200⭐\n\n"
    "⚠️ Если спросишь не про карьеру — я попрошу переформулировать."
)

CAREER_ON = (
    "💼 <b>Режим «Карьера» включён</b> ✅\n\n"
    "Пиши вопрос по работе/навыкам/резюме/заработку.\n"
    "Я отвечу структурировано и по делу 😎"
)

# =========================
# START / MENU
# =========================
@bot.message_handler(commands=["start"])
def cmd_s
