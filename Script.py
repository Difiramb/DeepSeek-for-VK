# script.py
import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("ds-vk-bot")

load_dotenv()
VK_TOKEN = os.getenv("VK_TOKEN")
PRIME_RAW = os.getenv("PRIME_USER_ID", "").strip()
PRIME_USER_ID = int(PRIME_RAW) if PRIME_RAW.isdigit() else None

if not VK_TOKEN:
    print("!!! VK_TOKEN не найден в .env")
    sys.exit(1)
if PRIME_USER_ID is None:
    log.warning("PRIME_USER_ID не задан или не является числом — команда Prime не будет работать")

try:
    from vkbottle.bot import Bot, Message
    from vkbottle import Keyboard, Text, KeyboardButtonColor, EMPTY_KEYBOARD
except Exception as e:
    print(f"!!! Ошибка импорта vkbottle: {e}")
    sys.exit(1)

try:
    from openai import OpenAI
except Exception as e:
    print(f"!!! Ошибка импорта openai: {e}")
    sys.exit(1)

client = OpenAI(base_url="http://127.0.0.1:9655/v1", api_key="not-needed")
bot = Bot(token=VK_TOKEN)

# --- Конфигурация ---
MAX_SLOTS = 4
COOLDOWN_SECONDS = 10
INACTIVE_TIMEOUT_MINUTES = 15
MAX_HISTORY_MESSAGES = 20


# --- Состояние ---
@dataclass
class UserSession:
    user_id: int
    history: list = field(default_factory=list)
    last_activity: datetime = field(default_factory=datetime.now)
    started_at: datetime = field(default_factory=datetime.now)


active_users: dict[int, UserSession] = {}
last_message_time: dict[int, datetime] = {}
seen_users: set[int] = set()
panel_enabled: set[int] = set()  # <-- новое: у кого включена панель


START_MESSAGE = (
    "👋 Привет! Я — бот-обёртка над DeepSeek.\n\n"
    "📋 Команды:\n"
    "• «Новый диалог» или /new — начать диалог с чистого листа\n"
    "• /myid — узнать свой VK ID\n"
    "• /help — показать это сообщение\n"
    "• /panelon — включить панель с кнопками\n"
    "• /paneloff — выключить панель с кнопками\n\n"
    "ℹ️ Правила:\n"
    f"• Одновременно могут общаться максимум {MAX_SLOTS} человека\n"
    f"• Между вашими сообщениями должно пройти не менее {COOLDOWN_SECONDS} сек\n"
    f"• Слот освобождается автоматически после {INACTIVE_TIMEOUT_MINUTES} мин неактивности\n\n"
    "Просто напишите вопрос — и я передам его DeepSeek 🤖"
)


def build_panel() -> str:
    """Собирает клавиатуру с кнопками и возвращает JSON-строку."""
    keyboard = (
        Keyboard(one_time=False, inline=False)
        .add(Text("Новый диалог"), color=KeyboardButtonColor.PRIMARY)
        .add(Text("Помощь"))
        .add(Text("Мой ID"))
    )
    return keyboard.get_json()


PANEL_JSON = build_panel()  # собираем один раз


async def reply(message: Message, text: str, force_keyboard=None):
    """
    Отправляет ответ. Если у пользователя включена панель — прикрепляет клавиатуру.
    force_keyboard можно передать явно (например, EMPTY_KEYBOARD при /paneloff).
    """
    if force_keyboard is not None:
        await message.answer(text, keyboard=force_keyboard)
        return
    if message.from_id in panel_enabled:
        await message.answer(text, keyboard=PANEL_JSON)
    else:
        await message.answer(text)


def cleanup_inactive():
    now = datetime.now()
    for uid in list(active_users.keys()):
        if now - active_users[uid].last_activity > timedelta(minutes=INACTIVE_TIMEOUT_MINUTES):
            del active_users[uid]
            log.info(f"Слот освобождён по таймауту: {uid}")


async def background_cleanup():
    while True:
        await asyncio.sleep(60)
        try:
            cleanup_inactive()
        except Exception as e:
            log.error(f"Ошибка в background_cleanup: {e}")


def get_oldest_non_prime() -> int | None:
    candidates = [(uid, s) for uid, s in active_users.items() if uid != PRIME_USER_ID]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[1].started_at)
    return candidates[0][0]


@bot.on.message()
async def handle_message(message: Message):
    user_id = message.from_id
    text = (message.text or "").strip()
    if not text:
        return

    low = text.lower()

    # --- /panelon: включить панель ---
    if low in ("/panelon", "panelon"):
        panel_enabled.add(user_id)
        await message.answer(
            "✅ Панель с кнопками включена. Кнопки появятся под полем ввода.",
            keyboard=PANEL_JSON,
        )
        return

    # --- /paneloff: выключить панель ---
    if low in ("/paneloff", "paneloff"):
        panel_enabled.discard(user_id)
        await message.answer(
            "🗑️ Панель с кнопками выключена. Команды снова нужно писать вручную.",
            keyboard=EMPTY_KEYBOARD,
        )
        return

    # --- /myid: без ограничений, без слота ---
    if low in ("/myid", "myid", "/id"):
        await reply(message, f"Ваш VK ID: {user_id}")
        return

    # --- /help: без ограничений, без слота ---
    if low in ("/help", "help", "/start", "start"):
        await reply(message, START_MESSAGE)
        return

    # --- Prime: только админ ---
    if low in ("prime", "/prime"):
        if PRIME_USER_ID is None:
            await reply(message, "⚠️ PRIME_USER_ID не настроен на сервере.")
            return
        if user_id != PRIME_USER_ID:
            await reply(message, "⛔ Команда доступна только администратору.")
            return

        if user_id in active_users:
            active_users[user_id].last_activity = datetime.now()
            await reply(message, "✅ Вы уже занимаете слот.")
            return

        cleanup_inactive()
        if len(active_users) < MAX_SLOTS:
            active_users[user_id] = UserSession(user_id=user_id)
            await reply(message, "✅ Слот получен (был свободен).")
            return

        victim = get_oldest_non_prime()
        if victim is None:
            await reply(message, "⚠️ Некого вытеснять.")
            return

        del active_users[victim]
        active_users[user_id] = UserSession(user_id=user_id)
        log.info(f"Prime: {user_id} вытеснил {victim}")

        await reply(message, f"✅ Слот получен. Пользователь {victim} отправлен в ожидание.")
        try:
            await bot.api.messages.send(
                user_id=victim,
                message=(
                    "ℹ️ Ваш слот был освобождён администратором. "
                    "Напишите что-нибудь, когда будете готовы — если место освободится, вы его займёте."
                ),
                random_id=int(datetime.now().timestamp()),
            )
        except Exception as e:
            log.warning(f"Не удалось уведомить выкинутого пользователя {victim}: {e}")
        return

    # --- «Новый диалог» / /new ---
    if low in ("новый диалог", "/new", "new"):
        if user_id in active_users:
            active_users[user_id].history = []
            active_users[user_id].last_activity = datetime.now()
            await reply(message, "🔄 Диалог начат с чистого листа. Задавайте вопрос!")
        else:
            await reply(message, "ℹ️ У вас пока нет активного диалога. Напишите любое сообщение — я начну новый.")
        return

    # --- Cooldown ---
    now = datetime.now()
    last = last_message_time.get(user_id)
    if last and (now - last).total_seconds() < COOLDOWN_SECONDS:
        remaining = int(COOLDOWN_SECONDS - (now - last).total_seconds())
        await reply(message, f"⏳ Подождите {remaining} сек. перед следующим сообщением.")
        return
    last_message_time[user_id] = now

    # --- Стартовое сообщение при первом обращении ---
    if user_id not in seen_users:
        seen_users.add(user_id)
        await reply(message, START_MESSAGE)

    # --- Проверка слотов ---
    cleanup_inactive()
    if user_id not in active_users:
        if len(active_users) >= MAX_SLOTS:
            await reply(message, "😔 Извините — все слоты заняты, попробуйте позже.")
            return
        active_users[user_id] = UserSession(user_id=user_id)
        log.info(f"Слот занят: {user_id} ({len(active_users)}/{MAX_SLOTS})")

    session = active_users[user_id]
    session.last_activity = now

    # --- История ---
    session.history.append({"role": "user", "content": text})
    if len(session.history) > MAX_HISTORY_MESSAGES:
        session.history = session.history[-MAX_HISTORY_MESSAGES:]
        while session.history and session.history[0]["role"] != "user":
            session.history.pop(0)

    # --- Запрос в DeepSeek ---
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=session.history,
        )
        answer = response.choices[0].message.content
        session.history.append({"role": "assistant", "content": answer})
    except Exception as e:
        log.error(f"Ошибка DeepSeek: {e}")
        if session.history and session.history[-1]["role"] == "user":
            session.history.pop()
        answer = f"⚠️ Ошибка при запросе к DeepSeek: {e}"

    await reply(message, answer)


async def main():
    log.info("Бот запускается...")
    asyncio.create_task(background_cleanup())
    await bot.run_polling()


if __name__ == "__main__":
    asyncio.run(main())