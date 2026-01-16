import asyncio
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, ChatPermissions
)
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.client.default import DefaultBotProperties

# ─────────── НАСТРОЙКИ ───────────
BOT_TOKEN = "8557190026:AAHAhHOxPQ4HlFHbGokpyTFoQ2R_a634rE4"
OWNER_ID = 6708209142
ADMIN_PASSWORD = "vanezypuls13579cod"

# ─────────── БОТ ───────────
bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ─────────── БД ───────────
conn = sqlite3.connect("puls.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS admin_access (
    user_id INTEGER PRIMARY KEY,
    unlocked INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    blocked_until INTEGER
)
""")

conn.commit()

# ─────────── ПРАВА ───────────
def mute_perms():
    return ChatPermissions(can_send_messages=False)

def full_perms():
    return ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True
    )

# ─────────── ПРИВЕТСТВИЕ БОТА В ГРУППЕ ───────────
@dp.message(F.new_chat_members)
async def bot_added(message: Message):
    for user in message.new_chat_members:
        if user.id == (await bot.me()).id:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📜 Правила бота", url="https://t.me/RulesPulsOfficial/8")],
                [InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel")],
                [InlineKeyboardButton(text="➕ Добавить меня", url=f"https://t.me/{(await bot.me()).username}?startgroup=true")],
            ])

            await message.answer(
                "🎉 <b>Добро пожаловать в Puls Bot!</b>\n\n"
                "Я — универсальный бот для модерации и развлечений.\n\n"
                "📌 Я могу:\n"
                "• наказывать нарушителей\n"
                "• помогать администраторам\n"
                "• в будущем — игры и экономика\n\n"
                "📖 Перед началом работы ознакомьтесь с правилами.\n"
                "Продолжая пользоваться ботом, вы подтверждаете их.\n\n"
                "✨ Приятного использования!",
                reply_markup=kb
            )

# ─────────── /start ───────────
@dp.message(F.text.regexp(r"(?i)^/start$"))
async def start_cmd(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Правила бота", url="https://t.me/RulesPulsOfficial/8")],
        [InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel")],
    ])

    await message.answer(
        f"👋 <b>Добро пожаловать в Puls Bot!</b>\n\n"
        f"👤 Имя: {message.from_user.full_name}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"🔗 Username: @{message.from_user.username or 'нет'}\n\n"
        f"Этот бот создан для удобного управления чатами.\n"
        f"Используйте кнопки ниже 👇",
        reply_markup=kb
    )

# ─────────── ПОМОЩЬ ───────────
@dp.message(F.text.regexp(r"(?i)^(/helppuls|помощь)$"))
async def help_cmd(message: Message):
    await message.answer(
        "📖 <b>Команды Puls Bot</b>\n\n"
        "🛡 Модерация:\n"
        "/m — мут\n"
        "/rm — размут\n"
        "/b — бан\n"
        "/rb — разбан\n"
        "/k — кик\n\n"
        "ℹ️ Прочее:\n"
        "/start — старт\n"
        "/helppuls — помощь\n\n"
        "🚧 Дополнительные функции находятся в разработке."
    )

# ─────────── АДМИН ПАНЕЛЬ ───────────
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(query: CallbackQuery):
    user_id = query.from_user.id

    cur.execute("SELECT unlocked, blocked_until FROM admin_access WHERE user_id=?", (user_id,))
    row = cur.fetchone()

    now = int(datetime.utcnow().timestamp())

    if row:
        unlocked, blocked_until = row
        if blocked_until and now < blocked_until:
            wait = blocked_until - now
            await query.answer(
                f"⛔ Доступ заблокирован\n⏳ Осталось: {wait} сек.",
                show_alert=True
            )
            return

        if unlocked:
            await query.message.answer("🛠 <b>Админ-панель активна</b>")
            return

    await query.message.answer(
        "🔐 <b>Введите пароль для доступа к админ-панели</b>\n\n"
        "Отправьте пароль следующим сообщением."
    )

# ─────────── ПАРОЛЬ ───────────
@dp.message(F.text)
async def admin_password_check(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    cur.execute("SELECT attempts, blocked_until FROM admin_access WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    now = int(datetime.utcnow().timestamp())

    attempts = row[0] if row else 0
    blocked_until = row[1] if row else None

    if blocked_until and now < blocked_until:
        return

    if text == ADMIN_PASSWORD:
        cur.execute("""
        INSERT OR REPLACE INTO admin_access (user_id, unlocked, attempts, blocked_until)
        VALUES (?, 1, 0, NULL)
        """, (user_id,))
        conn.commit()

        await message.answer("✅ <b>Доступ к админ-панели открыт</b>")
    else:
        attempts += 1
        if attempts >= 2:
            block_until = now + 300
            cur.execute("""
            INSERT OR REPLACE INTO admin_access (user_id, unlocked, attempts, blocked_until)
            VALUES (?, 0, ?, ?)
            """, (user_id, attempts, block_until))
            conn.commit()
            await message.answer("⛔ Неверный пароль.\nДоступ заблокирован на 5 минут.")
        else:
            cur.execute("""
            INSERT OR REPLACE INTO admin_access (user_id, unlocked, attempts, blocked_until)
            VALUES (?, 0, ?, NULL)
            """, (user_id, attempts))
            conn.commit()
            await message.answer("❌ Неверный пароль. Осталась 1 попытка.")

# ─────────── ЗАПУСК ───────────
async def main():
    print("✅ Puls Bot запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
