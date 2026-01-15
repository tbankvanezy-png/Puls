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

# ─────────── ИНИЦИАЛИЗАЦИЯ ───────────
bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
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
conn.commit()

# ─────────── FSM ПАРОЛЬ ───────────
class AdminPassword(StatesGroup):
    waiting_for_password = State()

admin_password = "vanezypuls13579cod"
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
                f"🎉 Приветствую всех! Я — Pulse Bot 🎊\n\n"
                f"Я универсальный бот для модерации, игр и мини-экономики.\n"
                f"Пожалуйста, ознакомьтесь с правилами и используйте кнопки ниже."
            )
            await message.answer(text, reply_markup=kb)
        else:
            text = (
                f"👋 <b>Новый участник!</b>\n\n"
                f"👤 Имя: {user.full_name}\n"
                f"🆔 ID: <code>{user.id}</code>\n"
                f"🔗 Username: @{user.username if user.username else 'отсутствует'}\n"
                f"🤖 Бот: {'Да' if user.is_bot else 'Нет'}\n\n"
                "━━━━━━━━━━━━━━━\n"
                "Рады видеть тебя в нашем сообществе 🙂\n"
                "Пожалуйста, ознакомься с правилами чата и приятного общения!"
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
        "━━━━━━━━━━━━━━━\n"
        "Надеемся увидеть тебя снова 👋"
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

# ─────────── КОМАНДЫ ───────────
@dp.message(F.text.lower().startswith("м") | F.text.lower().startswith("/m"))
async def mute_cmd(message: Message):
    await apply_punishment(message, "мут")

@dp.message(F.text.lower().startswith("б") | F.text.lower().startswith("/b"))
async def ban_cmd(message: Message):
    await apply_punishment(message, "бан")

@dp.message(F.text.lower().startswith("к") | F.text.lower().startswith("/k"))
async def kick_cmd(message: Message):
    await apply_punishment(message, "кик")

@dp.message(F.text.lower().startswith("рм") | F.text.lower().startswith("/rm"))
async def unmute_cmd(message: Message):
    parts = message.text.split()
    target_arg = parts[1] if len(parts) > 1 else None
    user_target = await resolve_user(message, target_arg)
    if not user_target:
        return
    if not await has_permission(message.chat.id, message.from_user.id, "can_mute"):
        await message.answer("❌ Вы не можете размучить этого участника.")
        return
    await bot.restrict_chat_member(message.chat.id, user_target.id, permissions=perms_all())
    await message.answer(f"🔓 <b>{user_target.full_name}</b> размучен\n🛡 Модератор: {message.from_user.full_name}")
    cur.execute("DELETE FROM punishments WHERE chat_id=? AND user_id=? AND type='мут'", (message.chat.id, user_target.id))
    conn.commit()

@dp.message(F.text.lower().startswith("рб") | F.text.lower().startswith("/rb"))
async def unban_cmd(message: Message):
    parts = message.text.split()
    target_arg = parts[1] if len(parts) > 1 else None
    user_target = await resolve_user(message, target_arg)
    if not user_target:
        return
    if not await has_permission(message.chat.id, message.from_user.id, "can_ban"):
        await message.answer("❌ Вы не можете разбанить этого участника.")
        return
    await bot.unban_chat_member(message.chat.id, user_target.id)
    await message.answer(f"🔓 <b>{user_target.full_name}</b> разбанен\n🛡 Модератор: {message.from_user.full_name}")
    cur.execute("DELETE FROM punishments WHERE chat_id=? AND user_id=? AND type='бан'", (message.chat.id, user_target.id))
    conn.commit()

# ─────────── КНОПКИ СНЯТИЯ ───────────
@dp.callback_query(F.data.regexp(r"^un(мут|бан)_"))
async def un_punish_cb(query: CallbackQuery):
    cmd, chat_id, user_id = query.data.split("_")
    chat_id, user_id = int(chat_id), int(user_id)
    if cmd == "мут":
        await bot.restrict_chat_member(chat_id, user_id, permissions=perms_all())
        cur.execute("DELETE FROM punishments WHERE chat_id=? AND user_id=? AND type='мут'", (chat_id, user_id))
    elif cmd == "бан":
        await bot.unban_chat_member(chat_id, user_id)
        cur.execute("DELETE FROM punishments WHERE chat_id=? AND user_id=? AND type='бан'", (chat_id, user_id))
    conn.commit()
    await query.message.edit_text(f"✅ Ограничение снято (автор: {query.from_user.full_name})")

# ─────────── АВТО-ОГРАНИЧЕНИЯ ───────────
async def punishment_watcher():
    while True:
        now = datetime.utcnow()
        cur.execute("SELECT chat_id, user_id, type FROM punishments WHERE until IS NOT NULL AND until<=?", (now,))
        rows = cur.fetchall()
        for chat_id, user_id, type_ in rows:
            try:
                if type_ == "мут":
                    await bot.restrict_chat_member(chat_id, user_id, permissions=perms_all())
                elif type_ == "бан":
                    await bot.unban_chat_member(chat_id, user_id)
                cur.execute("DELETE FROM punishments WHERE chat_id=? AND user_id=? AND type=?", (chat_id, user_id, type_))
            except:
                pass
        conn.commit()
        await asyncio.sleep(10)

# ─────────── /start и /startpuls ───────────
@dp.message(F.text.lower().startswith("start") | F.text.lower().startswith("/start"))
@dp.message(F.text.lower().startswith("startpuls") | F.text.lower().startswith("/startpuls"))
async def start_cmd(message: Message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📜 Правила", url="https://t.me/RulesPulsOfficial/8"),
        InlineKeyboardButton("🛠 Админ-панель", callback_data="admin_panel"),
        InlineKeyboardButton("🎮 Играть", callback_data="game")
    )
    text = (
        f"👋 Добро пожаловать в <b>Pulse Bot</b>\n\n"
        f"Pulse — универсальный Telegram-бот для модерации, игр и мини-экономики.\n"
        f"Перед началом ознакомьтесь с правилами.\n"
        f"Продолжая пользоваться ботом, вы подтверждаете их принятие.\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"➕ Добавьте меня в группу и веселитесь!"
    )
    await message.answer(text, reply_markup=kb)

# ─────────── /helppuls ───────────
@dp.message(F.text.lower().startswith("helppuls") | F.text.lower().startswith("помощь"))
async def help_cmd(message: Message):
    await message.answer(
        "📖 Помощь Pulse Bot\n\n"
        "Доступные команды:\n"
        "• /start, /startpuls — запуск бота\n"
        "• /helppuls, помощь — список команд\n"
        "• м / /m — мут\n"
        "• рм / /rm — размут\n"
        "• б / /b — бан\n"
        "• рб / /rb — разбан\n"
        "• к / /k — кик\n\n"
        "⚙️ В разработке: расширенная админ-панель, дополнительные игры, магазин и топы"
    )

# ─────────── ПАРОЛЬ АДМИН-ПАНЕЛИ ───────────
@dp.callback_query(F.data == "admin_panel")
async def open_admin_panel(query: CallbackQuery):
    user_id = query.from_user.id
    now = datetime.utcnow()

    if user_id != OWNER_ID:
        await query.answer("⛔ Только владелец может открыть админ-панель.", show_alert=True)
        return

    # Проверка блокировки
    if user_id in admin_blocked:
        if now < admin_blocked[user_id]:
            remaining = admin_blocked[user_id] - now
            minutes, seconds = divmod(int(remaining.total_seconds()), 60)
            await query.answer(
                f"⛔ Доступ временно заблокирован. Попробуйте через {minutes} мин {seconds} сек.",
                show_alert=True
            )
            return
        else:
            admin_blocked.pop(user_id)
            admin_attempts[user_id] = 0

    await query.message.answer("🔑 Введите пароль для доступа к админ-панели:")
    await AdminPassword.waiting_for_password.set()

@dp.message(AdminPassword.waiting_for_password)
async def check_password(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    attempts = admin_attempts.get(user_id, 0)

    if text == admin_password:
        await message.answer("✅ Пароль верный! Добро пожаловать в админ-панель.")
        admin_attempts[user_id] = 0
        await state.clear()
        await show_admin_panel(message)
        return

    attempts += 1
    admin_attempts[user_id] = attempts

    if attempts >= 2:
        admin_blocked[user_id] = datetime.utcnow() + timedelta(minutes=5)
        admin_attempts[user_id] = 0
        await message.answer("⛔ Доступ временно заблокирован на 5 минут.")
        await state.clear()
    else:
        await message.answer(f"❌ Неверный пароль. Осталась {2 - attempts} попытка.")

async def show_admin_panel(message: Message):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📢 Разослать сообщение", callback_data="broadcast"),
        InlineKeyboardButton("🎮 Игры и экономика", callback_data="games")
    )
    await message.answer("🛠 Админ-панель активирована", reply_markup=kb)

# ─────────── ЗАПУСК ───────────
async def main():
    asyncio.create_task(punishment_watcher())
    print("Pulse Bot запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
