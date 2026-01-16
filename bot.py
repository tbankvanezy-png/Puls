import asyncio
import re
from datetime import datetime, timedelta
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# ─────────── НАСТРОЙКИ ───────────
BOT_TOKEN = "8557190026:AAHAhHOxPQ4HlFHbGokpyTFoQ2R_a634rE4"
OWNER_ID = 6708209142  # @vanezyyy
OWNER_USERNAME = "vanezyyy"
ADMIN_PASSWORD = "vanezypuls13579cod"

# ─────────── ИНИЦИАЛИЗАЦИЯ ───────────
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ─────────── SQLite ───────────
conn = sqlite3.connect("puls_bot.db")
cur = conn.cursor()

# Права модераторов
cur.execute("""
CREATE TABLE IF NOT EXISTS permissions(
    chat_id INTEGER,
    user_id INTEGER,
    can_mute INTEGER DEFAULT 0,
    can_ban INTEGER DEFAULT 0,
    can_kick INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, user_id)
)
""")
# Система наказаний
cur.execute("""
CREATE TABLE IF NOT EXISTS punishments(
    chat_id INTEGER,
    user_id INTEGER,
    type TEXT,
    until TIMESTAMP,
    reason TEXT
)
""")
# Игровая система
cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    puls_coins INTEGER DEFAULT 0,
    dollars INTEGER DEFAULT 0,
    last_work TIMESTAMP,
    work_count INTEGER DEFAULT 0,
    last_game TIMESTAMP,
    game_count INTEGER DEFAULT 0
)
""")
conn.commit()

# ─────────── FSM ───────────
class AdminPasswordFSM(StatesGroup):
    waiting_for_password = State()

admin_attempts = {}  # user_id -> количество попыток
admin_blocked = {}   # user_id -> время разблокировки

# ─────────── УТИЛИТЫ ───────────
TIME_RE = re.compile(r"(\d+)([smhd])", re.IGNORECASE)

def parse_time(text: str):
    if text.lower() in ("0", "inf", "навсегда"):
        return None
    m = TIME_RE.match(text)
    if not m:
        return None
    value, unit = m.groups()
    value = int(value)
    return {
        "s": timedelta(seconds=value),
        "m": timedelta(minutes=value),
        "h": timedelta(hours=value),
        "d": timedelta(days=value),
    }[unit.lower()]

async def is_creator(message: Message):
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status == ChatMemberStatus.OWNER

async def has_permission(chat_id, user_id, command):
    if user_id == OWNER_ID:
        return True
    cur.execute(f"SELECT {command} FROM permissions WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    row = cur.fetchone()
    return row and row[0]

async def resolve_user(message: Message, arg: str | None):
    if message.reply_to_message:
        return message.reply_to_message.from_user
    if not arg:
        return None
    if arg.startswith("@"):
        try:
            member = await bot.get_chat_member(message.chat.id, arg[1:])
            return member.user
        except:
            return None
    if arg.isdigit():
        try:
            member = await bot.get_chat_member(message.chat.id, int(arg))
            return member.user
        except:
            return None
    return None

def perms_all():
    return ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True
    )

def perms_mute():
    return ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False
    )

# ─────────── ПРИВЕТСТВИЕ И ДОБАВЛЕНИЕ БОТА ───────────
@dp.message(F.new_chat_members)
async def on_join(message: Message):
    for user in message.new_chat_members:
        if user.id == (await bot.me).id:
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton("📜 Правила", url="https://t.me/RulesPulsOfficial/8"),
                InlineKeyboardButton("🛠 Админ-панель", callback_data="admin_panel"),
                InlineKeyboardButton("➕ Добавить в группу", url="https://t.me/vanezyyy_bot?startgroup=true"),
                InlineKeyboardButton("🎮 Играть", callback_data="game")
            )
            text = (
                f"🎉 Привет! Я — Puls Bot 🎊\n\n"
                f"Я универсальный бот, который может наказывать участников, "
                f"которые нарушают ваши правила.\n"
                f"Для начала прочитайте правила, нажав кнопку ниже.\n\n"
                f"➕ Добавьте меня в группу и веселитесь!"
            )
            await message.answer(text, reply_markup=kb)
        else:
            text = (
                f"👋 <b>Новый участник!</b>\n\n"
                f"👤 Имя: {user.full_name}\n"
                f"🆔 ID: <code>{user.id}</code>\n"
                f"🔗 Username: @{user.username if user.username else 'отсутствует'}\n"
                f"🤖 Бот: {'Да' if user.is_bot else 'Нет'}\n\n"
                f"━━━━━━━━━━━━━━━\n"
                f"Рады видеть тебя в нашем сообществе 🙂\n"
                f"Пожалуйста, ознакомься с правилами чата и приятного общения!"
            )
            await message.answer(text)

@dp.message(F.left_chat_member)
async def on_leave(message: Message):
    user = message.left_chat_member
    text = (
        f"🚪 <b>Участник покинул чат</b>\n\n"
        f"👤 Имя: {user.full_name}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"🔗 Username: @{user.username if user.username else 'отсутствует'}\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Надеемся увидеть тебя снова 👋"
    )
    await message.answer(text)

# ─────────── МОДЕРАЦИЯ ───────────
async def apply_punishment(message: Message, command: str):
    parts = message.text.split()
    duration_str = parts[1] if len(parts) > 1 else "inf"
    target_arg = parts[2] if len(parts) > 2 and not message.reply_to_message else None
    reason = " ".join(parts[3:] if target_arg else parts[2:]) or "не указана"
    user_target = await resolve_user(message, target_arg)
    if not user_target:
        return
    # Проверка прав
    cmd_map = {"мут": "can_mute", "бан": "can_ban", "кик": "can_kick"}
    if not await has_permission(message.chat.id, message.from_user.id, cmd_map.get(command, "")):
        await message.answer(
            f"❌ Вы не можете {command} этого участника.\n"
            f"💡 Только создатель группы или участник с правами +lm может это сделать."
        )
        return
    until_time = parse_time(duration_str)
    until_ts = datetime.utcnow() + until_time if until_time else None

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("Снять ограничение", callback_data=f"un{command}_{message.chat.id}_{user_target.id}")
    ) if command in ("мут", "бан") else None

    if command == "мут":
        await bot.restrict_chat_member(message.chat.id, user_target.id, permissions=perms_mute(), until_date=until_ts)
    elif command == "бан":
        await bot.ban_chat_member(message.chat.id, user_target.id, until_date=until_ts)
    elif command == "кик":
        await bot.ban_chat_member(message.chat.id, user_target.id)
        await bot.unban_chat_member(message.chat.id, user_target.id)

    await message.answer(
        f"⚠️ <b>{user_target.full_name}</b> {command}!\n"
        f"⏱ Время: {duration_str}\n📄 Причина: {reason}\n🛡 Модератор: {message.from_user.full_name}",
        reply_markup=kb
    )
    if command in ("мут", "бан"):
        cur.execute("INSERT INTO punishments(chat_id,user_id,type,until,reason) VALUES(?,?,?,?,?)",
                    (message.chat.id, user_target.id, command, until_ts, reason))
        conn.commit()

# ─────────── Регексы команд ───────────
MUTE_RE = re.compile(r"^(?:/)?m", re.IGNORECASE)
BAN_RE = re.compile(r"^(?:/)?b", re.IGNORECASE)
KICK_RE = re.compile(r"^(?:/)?k", re.IGNORECASE)
UNMUTE_RE = re.compile(r"^(?:/)?rm", re.IGNORECASE)
UNBAN_RE = re.compile(r"^(?:/)?rb", re.IGNORECASE)
START_RE = re.compile(r"^(?:/)?start$", re.IGNORECASE)
STARTPULS_RE = re.compile(r"^(?:/)?startpuls", re.IGNORECASE)
HELP_RE = re.compile(r"^(?:/)?helppuls|помощь", re.IGNORECASE)

@dp.message(F.text.regexp(MUTE_RE))
async def mute_cmd(message: Message):
    await apply_punishment(message, "мут")

@dp.message(F.text.regexp(BAN_RE))
async def ban_cmd(message: Message):
    await apply_punishment(message, "бан")

@dp.message(F.text.regexp(KICK_RE))
async def kick_cmd(message: Message):
    await apply_punishment(message, "кик")

@dp.message(F.text.regexp(UNMUTE_RE))
async def unmute_cmd(message: Message):
    # Здесь логика размут
    pass

@dp.message(F.text.regexp(UNBAN_RE))
async def unban_cmd(message: Message):
    # Здесь логика разбан
    pass

@dp.message(F.text.regexp(START_RE))
@dp.message(F.text.regexp(STARTPULS_RE))
async def start_cmd(message: Message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📜 Правила", url="https://t.me/RulesPulsOfficial/8"),
        InlineKeyboardButton("🛠 Админ-панель", callback_data="admin_panel"),
        InlineKeyboardButton("🎮 Играть", callback_data="game")
    )
    text = (
        f"👋 Добро пожаловать в <b>Puls Bot</b>\n\n"
        f"Pulse — универсальный Telegram-бот, который может наказывать участников, "
        f"поддерживать порядок и добавлять интерактив.\n"
        f"📜 Перед началом ознакомьтесь с правилами бота.\n"
        f"➕ Добавьте меня в группу и веселитесь!"
    )
    await message.answer(text, reply_markup=kb)

@dp.message(F.text.regexp(HELP_RE))
async def help_cmd(message: Message):
    await message.answer(
        "📖 Доступные команды:\n\n"
        "/m — мут, /rm — размут\n"
        "/b — бан, /rb — разбан\n"
        "/k — кик\n"
        "/start, /startpuls — приветствие\n"
        "/helppuls — показать это сообщение\n\n"
        "⚠️ Полное руководство по всем командам в разработке."
    )

# ─────────── ЗАПУСК ───────────
async def main():
    print("Puls Bot запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
