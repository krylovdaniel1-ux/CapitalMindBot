import os
import time
import sqlite3
from datetime import datetime, timedelta, timezone

import telebot
from telebot import types

# OpenAI SDK
from openai import OpenAI

# =========================
# ENV
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Можно указать админов через переменную ADMIN_IDS="123,456"
ADMIN_IDS = set()
_admin_raw = os.getenv("ADMIN_IDS", "").strip()
if _admin_raw:
    for x in _admin_raw.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.add(int(x))

# Цена (Stars) — пока как “витрина”, без автосписания
PRO_PRICE_STARS = 200
PRO_DAYS = 30

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не задан в Variables (Railway).")
if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY не задан в Variables (Railway).")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
ai = OpenAI(api_key=OPENAI_API_KEY)

UTC = timezone.utc

# =========================
# DB
# =========================
DB_PATH = "data.db"

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        created_ts INTEGER,
        pro_until_ts INTEGER DEFAULT 0,
        mode TEXT DEFAULT 'career'  -- career | none
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS test_state(
        user_id INTEGER PRIMARY KEY,
        step INTEGER DEFAULT 0,
        score_it INTEGER DEFAULT 0,
        score_bus INTEGER DEFAULT 0,
        score_cre INTEGER DEFAULT 0,
        score_an INTEGER DEFAULT 0,
        in_test INTEGER DEFAULT 0
    )
    """)

    con.commit()
    con.close()

def upsert_user(u):
    con = db()
    cur = con.cursor()
    now = int(time.time())
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (u.id,))
    exists = cur.fetchone()
    if exists:
        cur.execute("""
            UPDATE users
            SET username=?, first_name=?
            WHERE user_id=?
        """, (u.username or "", u.first_name or "", u.id))
    else:
        cur.execute("""
            INSERT INTO users(user_id, username, first_name, created_ts, pro_until_ts, mode)
            VALUES(?,?,?,?,?,?)
        """, (u.id, u.username or "", u.first_name or "", now, 0, "career"))
        # test_state
        cur.execute("""
            INSERT OR IGNORE INTO test_state(user_id, step, score_it, score_bus, score_cre, score_an, in_test)
            VALUES(?,?,?,?,?,?,?)
        """, (u.id, 0, 0, 0, 0, 0, 0))
    con.commit()
    con.close()

def get_user(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT user_id, username, first_name, created_ts, pro_until_ts, mode FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    con.close()
    return row

def set_mode(user_id: int, mode: str):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE users SET mode=? WHERE user_id=?", (mode, user_id))
    con.commit()
    con.close()

def is_pro(user_id: int) -> bool:
    row = get_user(user_id)
    if not row:
        return False
    pro_until_ts = int(row[4] or 0)
    return pro_until_ts > int(time.time())

def pro_until_str(user_id: int) -> str:
    row = get_user(user_id)
    if not row:
        return "-"
    ts = int(row[4] or 0)
    if ts <= 0:
        return "-"
    dt = datetime.fromtimestamp(ts, tz=UTC)
    return dt.strftime("%d.%m.%Y %H:%M (UTC)")

def grant_pro(user_id: int, days: int = PRO_DAYS):
    now = int(time.time())
    current = 0
    row = get_user(user_id)
    if row:
        current = int(row[4] or 0)
    base = max(now, current)
    new_until = int((datetime.fromtimestamp(base, tz=UTC) + timedelta(days=days)).timestamp())

    con = db()
    cur = con.cursor()
    cur.execute("UPDATE users SET pro_until_ts=? WHERE user_id=?", (new_until, user_id))
    con.commit()
    con.close()

# =========================
# COPY (Texts)
# =========================
WELCOME = (
    "🚀 <b>CapitalMind — Карьерный AI-бот</b>\n\n"
    "Я помогаю в <b>карьере</b>: резюме, собеседования, план развития, навыки, профессии.\n\n"
    "🧭 Выбери действие кнопками ниже."
)

CAREER_INFO = (
    "💼 <b>Режим: Карьера</b>\n"
    "Напиши вопрос по работе/карьере.\n\n"
    "Примеры:\n"
    "• «Подбери мне 3 профессии под мои сильные стороны»\n"
    "• «Сделай резюме для Junior Python»\n"
    "• «Подготовь к собеседованию на Sales»\n"
)

TERMS = (
    "📜 <b>Правила</b>\n\n"
    "• Бот даёт карьерные рекомендации, но не гарантирует трудоустройство.\n"
    "• Не передавай пароли/коды/ключи.\n"
    "• По медицине/праву — только общая информация.\n"
)

PAY_SUPPORT = (
    "🧾 <b>Оплата PRO</b>\n\n"
    "Сейчас кнопка PRO работает как витрина.\n"
    "Чтобы сделать <b>автоматическое списание Stars</b>, нужно подключить оплату правильно\n"
    "(это зависит от метода: провайдер платежей или Stars-подписки).\n\n"
    "Пока можешь написать админу, и мы активируем PRO вручную ✅"
)

# =========================
# TEST
# =========================
# 4 направления: it / business / creative / analytic
TEST_QUESTIONS = [
    ("1/8 🧩 Что тебе ближе?",
     [("💻 Кодить/разбираться в технике", "it"),
      ("📈 Продажи/переговоры/бизнес", "bus"),
      ("🎨 Дизайн/креатив/контент", "cre"),
      ("📊 Анализ/логика/данные", "an")]),

    ("2/8 🧩 Что больше нравится в задачах?",
     [("🧠 Решать сложные технические штуки", "it"),
      ("🤝 Общаться и убеждать", "bus"),
      ("✨ Придумывать идеи и визуал", "cre"),
      ("🔎 Искать закономерности", "an")]),

    ("3/8 🧩 Твой любимый тип результата:",
     [("Работающий продукт/код", "it"),
      ("Сделка/прибыль/рост", "bus"),
      ("Красиво и оригинально", "cre"),
      ("Точно и доказуемо", "an")]),

    ("4/8 🧩 Какой стиль тебе ближе?",
     [("Системность + технологии", "it"),
      ("Лидерство + люди", "bus"),
      ("Творчество + свобода", "cre"),
      ("Структура + цифры", "an")]),

    ("5/8 🧩 В команде ты чаще…",
     [("Делаю сложную часть руками", "it"),
      ("Договариваюсь и двигаю процесс", "bus"),
      ("Придумываю концепты/идеи", "cre"),
      ("Считаю/проверяю/улучшаю", "an")]),

    ("6/8 🧩 Что интереснее изучать?",
     [("Программирование/гаджеты", "it"),
      ("Маркетинг/продажи/деньги", "bus"),
      ("Дизайн/видео/музыка", "cre"),
      ("Математика/аналитика", "an")]),

    ("7/8 🧩 Где ты быстрее прокачаешься?",
     [("Техскиллы + практика", "it"),
      ("Софтскиллы + коммуникация", "bus"),
      ("Портфолио + креатив", "cre"),
      ("Задачи + логика", "an")]),

    ("8/8 🧩 Что тебе важнее всего?",
     [("Создавать и строить", "it"),
      ("Влиять и зарабатывать", "bus"),
      ("Выделяться и творить", "cre"),
      ("Понимать и оптимизировать", "an")]),
]

def reset_test(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        UPDATE test_state
        SET step=0, score_it=0, score_bus=0, score_cre=0, score_an=0, in_test=1
        WHERE user_id=?
    """, (user_id,))
    con.commit()
    con.close()

def get_test_state(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT step, score_it, score_bus, score_cre, score_an, in_test
        FROM test_state WHERE user_id=?
    """, (user_id,))
    row = cur.fetchone()
    con.close()
    return row

def set_test_step(user_id: int, step: int):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE test_state SET step=? WHERE user_id=?", (step, user_id))
    con.commit()
    con.close()

def add_score(user_id: int, bucket: str, delta: int = 1):
    con = db()
    cur = con.cursor()
    if bucket == "it":
        cur.execute("UPDATE test_state SET score_it=score_it+? WHERE user_id=?", (delta, user_id))
    elif bucket == "bus":
        cur.execute("UPDATE test_state SET score_bus=score_bus+? WHERE user_id=?", (delta, user_id))
    elif bucket == "cre":
        cur.execute("UPDATE test_state SET score_cre=score_cre+? WHERE user_id=?", (delta, user_id))
    elif bucket == "an":
cur.execute("UPDATE test_state SET score_an=score_an+? WHERE user_id=?", (delta, user_id))
    con.commit()
    con.close()

def finish_test(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE test_state SET in_test=0 WHERE user_id=?", (user_id,))
    con.commit()
    con.close()

def calc_test_result(scores):
    it, bus, cre, an = scores
    mx = max(scores)
    if mx == it:
        return "it"
    if mx == bus:
        return "bus"
    if mx == cre:
        return "cre"
    return "an"

def base_plan_for(result: str) -> str:
    if result == "it":
        return (
            "✅ <b>Твой вектор: IT/ТЕХ</b> 💻\n\n"
            "🔹 Подойдёт: Python/JS, QA, DevOps (начально), аналитика данных.\n"
            "🔹 План на 7 дней:\n"
            "1) Выбери 1 роль (например, Junior Python)\n"
            "2) 30–60 мин/день практика (задачи)\n"
            "3) Сделай мини-проект и оформи GitHub\n"
        )
    if result == "bus":
        return (
            "✅ <b>Твой вектор: БИЗНЕС/ПРОДАЖИ</b> 📈\n\n"
            "🔹 Подойдёт: Sales, SMM/маркетинг, аккаунт-менеджер.\n"
            "🔹 План на 7 дней:\n"
            "1) Подготовь короткий питч о себе\n"
            "2) Отработай 20 вопросов собеседования\n"
            "3) Собери портфолио кейсов (даже учебных)\n"
        )
    if result == "cre":
        return (
            "✅ <b>Твой вектор: КРЕАТИВ</b> 🎨\n\n"
            "🔹 Подойдёт: дизайн, монтаж, контент, копирайт.\n"
            "🔹 План на 7 дней:\n"
            "1) Выбери нишу и стиль\n"
            "2) Сделай 3 работы в портфолио\n"
            "3) Оформи профиль и описание услуг\n"
        )
    return (
        "✅ <b>Твой вектор: АНАЛИТИКА</b> 📊\n\n"
        "🔹 Подойдёт: аналитик, финансы, data-аналитика (начально).\n"
        "🔹 План на 7 дней:\n"
        "1) Освой Excel/Sheets базу + диаграммы\n"
        "2) Сделай 2 мини-отчёта по данным\n"
        "3) Научись объяснять выводы простыми словами\n"
    )

# =========================
# Keyboards
# =========================
def main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("💼 Карьера", "🧪 Тест")
    kb.row("👤 Профиль", "⭐ PRO")
    kb.row("ℹ️ Помощь")
    return kb

def test_kb(step: int):
    q_text, options = TEST_QUESTIONS[step]
    kb = types.InlineKeyboardMarkup()
    for title, bucket in options:
        kb.add(types.InlineKeyboardButton(title, callback_data=f"test:{step}:{bucket}"))
    kb.add(types.InlineKeyboardButton("⛔️ Отменить тест", callback_data="test_cancel"))
    return q_text, kb

def pro_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"⭐ Купить PRO — {PRO_PRICE_STARS} Stars / {PRO_DAYS} дней", callback_data="buy_pro"))
    kb.add(types.InlineKeyboardButton("📩 Связаться с админом", callback_data="contact_admin"))
    return kb

# =========================
# AI (career-only)
# =========================
SYSTEM_CAREER = (
    "Ты карьерный консультант. Отвечай ТОЛЬКО по вопросам работы/карьеры: "
    "резюме, собеседования, профессии, навыки, карьерный план, зарплаты в общих чертах. "
    "Если вопрос не про карьеру — вежливо откажись и попроси переформулировать под карьеру. "
    "Язык ответа: русский. Стиль: дружелюбно, коротко, по пунктам, с эмодзи."
)

def ai_answer_career(user_text: str, pro: bool) -> str:
    # Чуть разные лимиты
    max_tokens = 650 if pro else 420

    resp = ai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_CAREER},
            {"role": "user", "content": user_text.strip()},
        ],
        temperature=0.7,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()

# =========================
# Commands
# =========================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    upsert_user(message.from_user)
    bot.send_message(message.chat.id, WELCOME, reply_markup=main_kb())

@bot.message_handler(commands=["terms"])
def cmd_terms(message):
    upsert_user(message.from_user)
bot.send_message(message.chat.id, TERMS, reply_markup=main_kb())

@bot.message_handler(commands=["profile"])
def cmd_profile(message):
    upsert_user(message.from_user)
    uid = message.from_user.id
    row = get_user(uid)
    if not row:
        bot.send_message(message.chat.id, "⚠️ Не нашёл профиль. Напиши /start", reply_markup=main_kb())
        return

    name = row[2] or "User"
    pro = is_pro(uid)
    until = pro_until_str(uid)

    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"• Имя: <b>{name}</b>\n"
        f"• PRO: {'✅ <b>Активен</b>' if pro else '❌ <b>Нет</b>'}\n"
        f"• До: <b>{until}</b>\n\n"
        f"• Режим: <b>Карьера</b> 💼\n"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_kb())

# Админ: выдать PRO вручную
@bot.message_handler(commands=["grantpro"])
def cmd_grantpro(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "⛔️ Нет доступа.")
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Используй: /grantpro <user_id> [days]")
        return
    uid = int(parts[1])
    days = int(parts[2]) if len(parts) >= 3 else PRO_DAYS
    grant_pro(uid, days=days)
    bot.send_message(message.chat.id, f"✅ Выдал PRO пользователю {uid} на {days} дней.")

# =========================
# Buttons (Reply keyboard)
# =========================
@bot.message_handler(func=lambda m: (m.text or "") == "💼 Карьера")
def btn_career(message):
    upsert_user(message.from_user)
    set_mode(message.from_user.id, "career")
    bot.send_message(message.chat.id, CAREER_INFO, reply_markup=main_kb())

@bot.message_handler(func=lambda m: (m.text or "") == "👤 Профиль")
def btn_profile(message):
    cmd_profile(message)

@bot.message_handler(func=lambda m: (m.text or "") == "🧪 Тест")
def btn_test(message):
    upsert_user(message.from_user)
    reset_test(message.from_user.id)
    q_text, kb = test_kb(0)
    bot.send_message(message.chat.id, "🧪 <b>Карьерный тест</b>\nОтветь на 8 вопросов:", reply_markup=main_kb())
    bot.send_message(message.chat.id, q_text, reply_markup=kb)

@bot.message_handler(func=lambda m: (m.text or "") == "⭐ PRO")
def btn_pro(message):
    upsert_user(message.from_user)
    uid = message.from_user.id
    if is_pro(uid):
        bot.send_message(
            message.chat.id,
            f"⭐ <b>PRO уже активен</b>\nДействует до: <b>{pro_until_str(uid)}</b>",
            reply_markup=main_kb()
        )
    else:
        bot.send_message(
            message.chat.id,
            f"⭐ <b>PRO-подписка</b>\n\n"
            f"• Цена: <b>{PRO_PRICE_STARS} Stars</b>\n"
            f"• Длительность: <b>{PRO_DAYS} дней</b>\n\n"
            f"Что даёт PRO:\n"
            f"✅ более сильные ответы AI\n"
            f"✅ PRO-разбор результатов теста\n",
            reply_markup=pro_kb()
        )

@bot.message_handler(func=lambda m: (m.text or "") == "ℹ️ Помощь")
def btn_help(message):
    upsert_user(message.from_user)
    bot.send_message(
        message.chat.id,
        "ℹ️ <b>Помощь</b>\n\n"
        "💼 Карьера — задавай вопросы про работу.\n"
        "🧪 Тест — определим направление.\n"
        "👤 Профиль — статус PRO.\n"
        "⭐ PRO — расширенный разбор.\n\n"
        "Команды:\n"
        "/start /profile /terms\n",
        reply_markup=main_kb()
    )

# =========================
# Inline callbacks
# =========================
@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    uid = call.from_user.id
    upsert_user(call.from_user)

    if call.data == "test_cancel":
        finish_test(uid)
        bot.answer_callback_query(call.id, "Тест отменён")
        bot.send_message(call.message.chat.id, "⛔️ Тест отменён.", reply_markup=main_kb())
        return

    if call.data.startswith("test:"):
        # test:<step>:<bucket>
        try:
            _, step_s, bucket = call.data.split(":")
            step = int(step_s)
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка данных теста")
            return
st = get_test_state(uid)
        if not st:
            bot.answer_callback_query(call.id, "Состояние теста не найдено. Нажми «Тест» ещё раз.")
            return

        add_score(uid, bucket, 1)
        next_step = step + 1
        set_test_step(uid, next_step)
        bot.answer_callback_query(call.id, "✅ Принято")

        # следующий вопрос
        if next_step < len(TEST_QUESTIONS):
            q_text, kb = test_kb(next_step)
            bot.edit_message_text(q_text, call.message.chat.id, call.message.message_id, reply_markup=kb)
            return

        # финал
        finish_test(uid)
        st2 = get_test_state(uid)
        # step, it, bus, cre, an, in_test
        scores = (st2[1], st2[2], st2[3], st2[4])
        result = calc_test_result(scores)

        bot.edit_message_text("✅ Тест завершён!", call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, base_plan_for(result), reply_markup=main_kb())

        # PRO-разбор теста (AI) — только если PRO
        if is_pro(uid):
            bot.send_message(call.message.chat.id, "⭐ <b>PRO-разбор:</b> делаю персональный план на 30 дней… ⏳")
            try:
                prompt = (
                    f"Результат теста: {result}. "
                    f"Составь план развития на 30 дней по карьере: "
                    f"навыки, ежедневные задания, 3 идеи как заработать/стажировка, "
                    f"и 5 вопросов для самопроверки."
                )
                ans = ai_answer_career(prompt, pro=True)
                bot.send_message(call.message.chat.id, ans, reply_markup=main_kb())
            except Exception as e:
                bot.send_message(call.message.chat.id, f"⚠️ Ошибка AI: <code>{e}</code>")
        else:
            bot.send_message(
                call.message.chat.id,
                f"⭐ Хочешь PRO-разбор теста (план на 30 дней)?\n"
                f"Нажми: ⭐ PRO → купить за {PRO_PRICE_STARS} Stars",
                reply_markup=main_kb()
            )
        return

    if call.data == "buy_pro":
        bot.answer_callback_query(call.id, "Открываю оплату…")
        bot.send_message(call.message.chat.id, PAY_SUPPORT, reply_markup=main_kb())
        return

    if call.data == "contact_admin":
        bot.answer_callback_query(call.id, "Ок")
        admin_text = "📩 Напиши админу: (добавь контакт тут)\n\nИли попроси /grantpro (если ты админ)."
        bot.send_message(call.message.chat.id, admin_text, reply_markup=main_kb())
        return

    bot.answer_callback_query(call.id, "Ок")

# =========================
# Main text handler (career-only AI)
# =========================
@bot.message_handler(content_types=["text"])
def handle_text(message):
    upsert_user(message.from_user)

    text = (message.text or "").strip()
    if not text:
        return

    # Если это команды/кнопки — их уже поймали handlers выше.
    # Здесь — обычный текст.

    # Проверим, не идёт ли тест (чтобы пользователь не ломал поток)
    st = get_test_state(message.from_user.id)
    if st and int(st[5] or 0) == 1:
        bot.send_message(message.chat.id, "🧪 Ты сейчас проходишь тест. Ответь кнопками под вопросом 🙂", reply_markup=main_kb())
        return

    # Режим — только карьера
    uid = message.from_user.id
    row = get_user(uid)
    mode = row[5] if row else "career"
    if mode != "career":
        set_mode(uid, "career")

    pro = is_pro(uid)

    # “Типичный ответ” перед AI (как ты просил)
    bot.send_message(message.chat.id, "✅ Принял! Сейчас подумаю и дам карьерный ответ… 🤝")

    try:
        ans = ai_answer_career(text, pro=pro)
        if not ans:
            ans = "⚠️ Не получилось сформировать ответ. Попробуй спросить иначе."
        bot.send_message(message.chat.id, ans, reply_markup=main_kb())
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка AI: <code>{e}</code>", reply_markup=main_kb())

# =========================
# Run
# =========================
def main():
    init_db()
    print("✅ Bot started (polling)...")
# long_polling: True чтобы меньше 409 конфликтов
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == "__main__":
    main()
