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
    "• проверь, что у тебя есть Stars\n"
)

CAREER_ON = (
    "💼 <b>Режим «Карьера» включён</b> ✅\n\n"
    "Пиши вопрос по карьере:\n"
    "• резюме / портфолио\n"
    "• собеседование\n"
    "• навыки\n"
    "• план на 30 дней\n"
    "• как заработать первые деньги\n\n"
    "Я отвечу структурно и по делу 😎"
)

# =========================
# TEST (5 вопросов)
# =========================
TEST_QUESTIONS = [
    {
        "q": "1/5 🎯 Что тебе интереснее?",
        "opts": [["💻 IT", "💰 Бизнес"], ["🎨 Креатив", "📊 Аналитика"]],
        "score": {
            "💻 IT": ("it", 2),
            "💰 Бизнес": ("business", 2),
            "🎨 Креатив": ("creative", 2),
            "📊 Аналитика": ("analytics", 2),
        }
    },
    {
        "q": "2/5 🧠 Ты больше…",
        "opts": [["🧩 Логик", "🗣 Коммуникатор"], ["🎭 Творец", "🧠 Стратег"]],
        "score": {
            "🧩 Логик": ("analytics", 2),
            "🗣 Коммуникатор": ("business", 2),
            "🎭 Творец": ("creative", 2),
            "🧠 Стратег": ("it", 1),  # чуть к IT/продуктам
        }
    },
    {
        "q": "3/5 ⏱ Какой формат тебе ближе?",
"opts": [["🧑‍💻 Делаю сам", "🤝 Работаю с людьми"], ["📈 Считаю/сравниваю", "🎬 Создаю контент"]],
        "score": {
            "🧑‍💻 Делаю сам": ("it", 2),
            "🤝 Работаю с людьми": ("business", 2),
            "📈 Считаю/сравниваю": ("analytics", 2),
            "🎬 Создаю контент": ("creative", 2),
        }
    },
    {
        "q": "4/5 💸 Что важнее сейчас?",
        "opts": [["💵 Деньги", "🛡 Стабильность"], ["🕊 Свобода", "🚀 Рост"]],
        "score": {
            "💵 Деньги": ("business", 1),
            "🛡 Стабильность": ("analytics", 1),
            "🕊 Свобода": ("creative", 1),
            "🚀 Рост": ("it", 1),
        }
    },
    {
        "q": "5/5 🏁 На что готов(а) в ближайший месяц?",
        "opts": [["📚 Учиться каждый день", "🧪 Сделать проект"], ["📣 Продавать/искать клиентов", "🧾 Собрать резюме"]],
        "score": {
            "📚 Учиться каждый день": ("it", 1),
            "🧪 Сделать проект": ("creative", 1),
            "📣 Продавать/искать клиентов": ("business", 1),
            "🧾 Собрать резюме": ("analytics", 1),
        }
    },
]

def build_test_question(step: int):
    item = TEST_QUESTIONS[step]
    return item["q"], item["opts"], item["score"]

def calc_test_result(scores):
    # scores = (it, business, creative, analytics)
    labels = ["IT", "Бизнес", "Креатив", "Аналитика"]
    best_idx = max(range(4), key=lambda i: scores[i])
    return labels[best_idx]

def base_plan_for(result: str) -> str:
    if result == "IT":
        return (
            "💻 <b>Твоё направление: IT</b>\n\n"
            "План на 7 дней:\n"
            "1) Выбери роль: Python/Frontend/QA\n"
            "2) 30–60 мин в день: обучение\n"
            "3) Мини-проект за неделю (калькулятор/бот/сайт)\n"
            "4) Оформи GitHub/портфолио\n"
            "5) Найди 3 стажировки/задачи\n\n"
            "Хочешь — скажи: возраст + что уже умеешь, и я составлю план на 30 дней 🚀"
        )
    if result == "Бизнес":
        return (
            "💰 <b>Твоё направление: Бизнес</b>\n\n"
            "План на 7 дней:\n"
            "1) Выбери простую услугу: дизайн/монтаж/тексты/настройка\n"
            "2) Сделай 1 пример работы\n"
            "3) Найди 10 потенциальных клиентов\n"
            "4) Напиши 10 сообщений (скрипт дам)\n"
            "5) Сделай 1 продажу/заказ\n\n"
            "Хочешь — опиши, что умеешь, и я дам 10 идей заработка 😎"
        )
    if result == "Креатив":
        return (
            "🎨 <b>Твоё направление: Креатив</b>\n\n"
            "План на 7 дней:\n"
            "1) Выбери нишу: видео/дизайн/музыка/контент\n"
            "2) 1 работа в день (портфолио)\n"
            "3) Выложи 3 поста/ролика\n"
            "4) Найди 5 заказчиков/коллаб\n"
            "5) Собери 1 кейс «до/после»\n\n"
            "Хочешь — расскажи, что именно нравится, и я сделаю план развития 🚀"
        )
    return (
        "📊 <b>Твоё направление: Аналитика</b>\n\n"
        "План на 7 дней:\n"
        "1) Научись Excel/Google Sheets (база)\n"
        "2) Сделай 1 таблицу-проект (расходы/спорт/учёба)\n"
        "3) Освой графики и сводные\n"
        "4) Попробуй простую аналитику (KPI/метрики)\n"
        "5) Оформи резюме и 3 навыка\n\n"
        "Хочешь — скажи цель (какая роль), и я сделаю roadmap 🧠"
    )

# =========================
# AI (career only)
# =========================
CAREER_SYSTEM = (
    "Ты карьерный консультант. Отвечай ТОЛЬКО по темам карьеры/работы: "
    "профессии, навыки, обучение, резюме, собеседование, поиск вакансий/стажировок, "
    "фриланс, первые деньги, переговоры о зарплате. "
    "Если вопрос не по карьере — вежливо откажись и попроси задать карьерный вопрос. "
    "Пиши на русском, дружелюбно, 1–3 эмодзи, структурно (шаги/список)."
)

def ai_answer_career(text: str, pro: bool) -> str:
    hint = (
        "Пользователь PRO: дай расширенный ответ, добавь чек-лист, примеры и план на 7 дней."
        if pro else
        "Пользователь Free: ответ практичный и короткий, 6–10 пунктов максимум."
    )
    resp = client.chat.completions.create(
model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": CAREER_SYSTEM},
            {"role": "system", "content": hint},
            {"role": "user", "content": text},
        ],
        temperature=0.6
    )
    return (resp.choices[0].message.content or "").strip()

# =========================
# PAYMENTS (Stars)
# =========================
def send_pro_invoice(chat_id: int):
    prices = [LabeledPrice(label=f"PRO на {PRO_DAYS} дней", amount=PRO_PRICE_STARS)]
    bot.send_invoice(
        chat_id=chat_id,
        title="⭐ CapitalMind PRO",
        description=f"PRO доступ на {PRO_DAYS} дней (расширенные карьерные разборы)",
        invoice_payload=PRO_PAYLOAD,
        provider_token=PROVIDER_TOKEN,  # Stars -> пустой
        currency=STARS_CURRENCY,        # XTR
        prices=prices,
        start_parameter="capitalmind_pro"
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q):
    # Telegram требует ответить OK
    if q.invoice_payload != PRO_PAYLOAD:
        bot.answer_pre_checkout_query(q.id, ok=False, error_message="Неверный payload оплаты.")
        return
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=["successful_payment"])
def on_successful_payment(message):
    sp = message.successful_payment
    if sp.currency != STARS_CURRENCY:
        bot.send_message(message.chat.id, "⚠️ Платёж пришёл не в Stars. Напиши /paysupport")
        return
    if sp.total_amount != PRO_PRICE_STARS:
        bot.send_message(message.chat.id, "⚠️ Сумма оплаты отличается. Напиши /paysupport")
        return
    if sp.invoice_payload != PRO_PAYLOAD:
        bot.send_message(message.chat.id, "⚠️ Платёж не распознан. Напиши /paysupport")
        return

    until = datetime.now(UTC) + timedelta(days=PRO_DAYS)
    set_pro_until(message.from_user.id, until.isoformat())

    bot.send_message(
        message.chat.id,
        f"🎉 <b>PRO активирован!</b>\n\n"
        f"⭐ На <b>{PRO_DAYS} дней</b>\n"
        f"⏳ До: <b>{until.strftime('%d.%m.%Y %H:%M (UTC)')}</b>\n\n"
        "Теперь тест и карьера будут давать более мощные разборы 😎",
        reply_markup=main_kb()
    )

# =========================
# COMMANDS
# =========================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    ensure_user(message.from_user)
    set_mode(message.from_user.id, "menu")
    bot.send_message(message.chat.id, WELCOME, reply_markup=main_kb())

@bot.message_handler(commands=["terms"])
def cmd_terms(message):
    ensure_user(message.from_user)
    bot.send_message(message.chat.id, TERMS, reply_markup=main_kb())

@bot.message_handler(commands=["paysupport"])
def cmd_paysupport(message):
    ensure_user(message.from_user)
    bot.send_message(message.chat.id, PAY_SUPPORT, reply_markup=main_kb())

# =========================
# BUTTON HANDLERS
# =========================
@bot.message_handler(func=lambda m: m.text == BTN_MENU)
def btn_menu(message):
    ensure_user(message.from_user)
    set_mode(message.from_user.id, "menu")
    bot.send_message(message.chat.id, "🏠 Меню 👇", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text == BTN_HELP)
def btn_help(message):
    ensure_user(message.from_user)
    bot.send_message(message.chat.id, HELP, reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text == BTN_PROFILE)
def btn_profile(message):
    ensure_user(message.from_user)
    pro = is_pro(message.from_user.id)
    pro_until = get_pro_until(message.from_user.id)

    until_str = "—"
    if pro_until:
        try:
            until_str = datetime.fromisoformat(pro_until).astimezone(UTC).strftime("%d.%m.%Y %H:%M (UTC)")
        except Exception:
            until_str = "—"

    bot.send_message(
        message.chat.id,
        "👤 <b>Профиль</b>\n\n"
        f"Имя: <b>{message.from_user.first_name or 'User'}</b>\n"
        f"PRO: {'✅ <b>Активен</b>' if pro else '❌ <b>Нет</b>'}\n"
        f"До: <b>{until_str}</b>\n\n"
        "Совет: пройди 🧠 Тест — он реально помогает выбрать направление 😎",
reply_markup=main_kb()
    )

@bot.message_handler(func=lambda m: m.text == BTN_PRO)
def btn_pro(message):
    ensure_user(message.from_user)
    bot.send_message(
        message.chat.id,
        "⭐ <b>PRO</b>\n\n"
        f"Цена: <b>{PRO_PRICE_STARS}⭐</b>\n"
        f"Срок: <b>{PRO_DAYS} дней</b>\n\n"
        "✅ PRO даёт:\n"
        "• расширенные ответы в карьере\n"
        "• расширенный разбор теста\n"
        "• чек-листы + план на 7 дней\n\n"
        "Сейчас открою оплату 👇",
        reply_markup=main_kb()
    )
    send_pro_invoice(message.chat.id)

@bot.message_handler(func=lambda m: m.text == BTN_CAREER)
def btn_career(message):
    ensure_user(message.from_user)
    set_mode(message.from_user.id, "career")
    bot.send_message(message.chat.id, CAREER_ON, reply_markup=career_kb())

@bot.message_handler(func=lambda m: m.text == BTN_EXIT_CAREER)
def btn_exit_career(message):
    ensure_user(message.from_user)
    set_mode(message.from_user.id, "menu")
    bot.send_message(message.chat.id, "⬅️ Ок, вышли из режима карьеры.", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text == BTN_TEST)
def btn_test(message):
    ensure_user(message.from_user)
    reset_test(message.from_user.id)
    q, opts, _score_map = build_test_question(0)
    bot.send_message(message.chat.id, f"🧠 <b>Карьерный тест</b>\n\n{q}", reply_markup=test_kb(opts))

# =========================
# MAIN TEXT HANDLER
# =========================
@bot.message_handler(content_types=["text"])
def handle_text(message):
    ensure_user(message.from_user)

    text = (message.text or "").strip()
    # Не даём текстовым обработчиком ловить кнопки (если вдруг попало сюда)
    if text in {BTN_CAREER, BTN_TEST, BTN_PROFILE, BTN_PRO, BTN_HELP, BTN_MENU, BTN_EXIT_CAREER}:
        return

    mode, step, s_it, s_bus, s_cre, s_an = get_state(message.from_user.id)
    pro = is_pro(message.from_user.id)

    # ===== TEST MODE =====
    if mode == "test":
        # ожидаем один из вариантов ответа
        if step < len(TEST_QUESTIONS):
            q, opts, score_map = build_test_question(step)
            allowed = set(sum(opts, []))  # flatten
            if text not in allowed:
                bot.send_message(
                    message.chat.id,
                    "🙂 Выбери вариант кнопкой ниже 👇",
                    reply_markup=test_kb(opts)
                )
                return

            # начисляем очки
            bucket, val = score_map[text]
            if bucket == "it":
                add_score(message.from_user.id, it=val)
            elif bucket == "business":
                add_score(message.from_user.id, business=val)
            elif bucket == "creative":
                add_score(message.from_user.id, creative=val)
            elif bucket == "analytics":
                add_score(message.from_user.id, analytics=val)

            # следующий шаг
            next_step = step + 1
            set_test_step(message.from_user.id, next_step)

            if next_step < len(TEST_QUESTIONS):
                q2, opts2, _ = build_test_question(next_step)
                bot.send_message(message.chat.id, q2, reply_markup=test_kb(opts2))
                return

            # финал теста
            # берём финальные скоры
            _, _, s_it2, s_bus2, s_cre2, s_an2 = get_state(message.from_user.id)
            result = calc_test_result((s_it2, s_bus2, s_cre2, s_an2))

            bot.send_message(message.chat.id, base_plan_for(result), reply_markup=main_kb())

            # PRO доп-разбор от AI
            if pro:
                try:
                    bot.send_message(message.chat.id, "🧠 PRO-разбор: делаю персональные советы… ✨", reply_markup=main_kb())
                    ai = ai_answer_career(
                        f"По результату теста направление = {result}. "
                        "Сделай план на 30 дней + список навыков + 3 идеи заработка для подростка/студента.",
                        pro=True
                    )
                    bot.send_message(message.chat.id, ai, reply_markup=main_kb())
except Exception as e:
                    bot.send_message(message.chat.id, f"⚠️ Ошибка AI: <code>{str(e)[:160]}</code>", reply_markup=main_kb())

            else:
                bot.send_message(
                    message.chat.id,
                    "🔒 Хочешь PRO-разбор теста (план на 30 дней + идеи заработка)?\n"
                    f"Открой PRO за <b>{PRO_PRICE_STARS}⭐</b> ⭐",
                    reply_markup=main_kb()
                )

            set_mode(message.from_user.id, "menu")
            return

    # ===== CAREER MODE =====
    if mode == "career":
        # базовый “типичный ответ” перед AI
        bot.send_message(message.chat.id, "🧩 Понял. Сейчас дам карьерный разбор… ⏳✨", reply_markup=career_kb())
        try:
            ans = ai_answer_career(text, pro=pro)
            bot.send_message(message.chat.id, ans, reply_markup=career_kb())
        except Exception as e:
            bot.send_message(message.chat.id, f"⚠️ Ошибка AI: <code>{str(e)[:160]}</code>", reply_markup=career_kb())
        return

    # ===== MENU / OTHER =====
    bot.send_message(
        message.chat.id,
        "🙂 Выбери режим кнопкой ниже:\n"
        f"• {BTN_CAREER} — спрашивай AI по карьере\n"
        f"• {BTN_TEST} — тест и план\n"
        f"• {BTN_PRO} — подписка\n",
        reply_markup=main_kb()
    )

# =========================
# RUN
# =========================
if name == "__main__":
    init_db()
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e:
            print("Polling error:", e)
            time.sleep(3)
