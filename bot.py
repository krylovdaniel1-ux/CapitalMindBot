import os
import time
import telebot
from openai import OpenAI

# =========================
# 1) ENV (Railway Variables)
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ Railway Variables: не найдена переменная TELEGRAM_TOKEN")
if not OPENAI_API_KEY:
    raise ValueError("❌ Railway Variables: не найдена переменная OPENAI_API_KEY")

# =========================
# 2) Init clients
# =========================
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# 3) Style / System prompt
# =========================
SYSTEM_PROMPT = (
    "Ты — телеграм-бот CapitalMind 🚀\n"
    "Всегда отвечай ТОЛЬКО на русском языке.\n"
    "Пиши живо, уверенно и дружелюбно, используй эмодзи по смыслу (🚀🔥📈💡🤝💰).\n"
    "Пиши коротко и понятно. Если нужно — структурируй списками.\n"
    "Если вопрос непонятен — задай 1 уточняющий вопрос.\n"
    "Никогда не говори, что ты 'языковая модель' или 'AI от OpenAI'.\n"
)

# =========================
# 4) Simple anti-spam (optional)
# =========================
# Ограничим частоту /ai, чтобы не улететь в расходы: 1 запрос в 3 секунды на пользователя.
LAST_AI_CALL = {}  # user_id -> timestamp
AI_COOLDOWN_SEC = 3

def can_call_ai(user_id: int) -> bool:
    now = time.time()
    last = LAST_AI_CALL.get(user_id, 0)
    if now - last < AI_COOLDOWN_SEC:
        return False
    LAST_AI_CALL[user_id] = now
    return True

# =========================
# 5) Commands
# =========================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "🚀 <b>CapitalMind</b> на связи!\n\n"
        "Я помогу тебе:\n"
        "• 💰 понять, как зарабатывать и не сливать деньги\n"
        "• 📈 составить план действий\n"
        "• 🔥 быстро объяснить сложное простыми словами\n\n"
        "✅ Чтобы задать вопрос ИИ, пиши так:\n"
        "<b>/ai</b> Как заработать первые 500$?\n\n"
        "Команды:\n"
        "• /ai — спросить ИИ\n"
        "• /help — как пользоваться"
    )

@bot.message_handler(commands=["help"])
def cmd_help(message):
    bot.send_message(
        message.chat.id,
        "🧠 <b>Как пользоваться</b>\n\n"
        "1) Пиши команду <b>/ai</b> и сразу вопрос:\n"
        "   <b>/ai</b> Как накопить 10 000 грн за 2 месяца?\n\n"
        "2) Я отвечу кратко и по делу, со стратегией 🚀\n\n"
        "Если бот не отвечает — проверь, что он задеплоен и переменные добавлены ✅"
    )

@bot.message_handler(commands=["ai"])
def cmd_ai(message):
    user_id = message.from_user.id if message.from_user else 0

    # Вырезаем "/ai " из текста
    full_text = message.text or ""
    parts = full_text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        bot.send_message(
            message.chat.id,
            "✍️ Напиши вопрос после <b>/ai</b>.\n"
            "Пример: <b>/ai</b> Как начать зарабатывать в 15–16 лет?"
        )
        return

    if not can_call_ai(user_id):
        bot.send_message(
            message.chat.id,
            f"⏳ Подожди {AI_COOLDOWN_SEC} сек и попробуй снова 🙌"
        )
        return

    question = parts[1].strip()

    # Можем показать "печатает..."
    bot.send_chat_action(message.chat.id, "typing")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        )
        answer = (response.choices[0].message.content or "").strip()

        if not answer:
            answer = "🤔 Пустой ответ. Попробуй переформулировать вопрос."

        # маленькая “подпись” в конце, чтобы выглядело фирменно
        answer = answer + "\n\n🤝 <b>CapitalMind</b>"

        bot.send_message(message.chat.id, answer)

    except Exception as e:
        # Типовые ошибки: нет биллинга/квоты/неверный ключ и т.д.
        bot.send_message(
            message.chat.id,
            "⚠️ Упс, что-то пошло не так.\n"
            "Проверь:\n"
            "• ✅ Railway Variables: <b>OPENAI_API_KEY</b>\n"
            "• ✅ есть биллинг/кредит на OpenAI\n"
            "• ✅ бот задеплоен (Deploy Completed)\n\n"
            f"Текст ошибки (для логов): <code>{str(e)[:180]}</code>"
        )

# =========================
# 6) Fallback: если пишут без /ai
# =========================
@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.send_message(
        message.chat.id,
        "💡 Я отвечаю через команду <b>/ai</b>.\n"
        "Например:\n"
        "<b>/ai</b> Как перестать сливать деньги и начать копить? 🚀"
    )

# =========================
# 7) Start polling (important for Railway)
# =========================
# Убираем webhook на всякий случай (чтобы избежать конфликтов режима webhook/polling)
bot.remove_webhook()

# skip_pending=True — чтобы после рестарта не прилетели старые сообщения пачкой
# timeout — держим соединение стабильнее
bot.infinity_polling(skip_pending=True, timeout=30)
