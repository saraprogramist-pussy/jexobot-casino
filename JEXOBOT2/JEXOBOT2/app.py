import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
import uvicorn

import db
from server import app as fastapi_app, set_bot_token

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0") or "0")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
PORT = int(os.environ.get("PORT", "8000"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


def webapp_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Открыть Casino", web_app=WebAppInfo(url=WEBAPP_URL))],
    ])


@dp.message(CommandStart())
async def cmd_start(message: Message):
    db.get_or_create_user(message.from_user.id, message.from_user.username or message.from_user.first_name)
    if not WEBAPP_URL:
        await message.answer(
            "⚠️ Приложение ещё не настроено (нет WEBAPP_URL). Попроси администратора завершить настройку."
        )
        return
    await message.answer(
        "🎲 *Demo Casino*\nВиртуальная валюта, реальные деньги не используются.\n\n"
        "Жми на кнопку ниже, чтобы открыть казино:",
        parse_mode="Markdown",
        reply_markup=webapp_keyboard(),
    )


@dp.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"Твой Telegram ID: `{message.from_user.id}`", parse_mode="Markdown")


@dp.message(Command("top"))
async def cmd_top(message: Message):
    rows = db.get_leaderboard(10)
    text = "🏆 *Топ игроков*\n\n" + "\n".join(
        f"{i+1}. {r['username'] or 'аноним'} — {r['balance']} сум" for i, r in enumerate(rows)
    )
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("give"))
async def cmd_give(message: Message):
    if ADMIN_ID == 0:
        await message.answer("⚠️ ADMIN_ID не настроен. См. README.")
        return
    if message.from_user.id != ADMIN_ID:
        await message.answer("Эта команда доступна только администратору.")
        return

    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer(
            "Использование:\n`/give @username 500`\nили\n`/give 123456789 500`\n\n"
            "(игрок должен хотя бы раз написать /start этому боту, иначе его не найти)",
            parse_mode="Markdown",
        )
        return

    target, amount_str = parts[1], parts[2]
    try:
        amount = int(amount_str)
    except ValueError:
        await message.answer("Сумма должна быть целым числом.")
        return

    user_row = db.find_user(target)
    if not user_row:
        await message.answer(f"Игрок «{target}» не найден. Пусть сначала напишет /start боту.")
        return

    db.adjust_balance(user_row["user_id"], amount)
    new_balance = db.get_balance(user_row["user_id"])
    await message.answer(
        f"✅ Игроку {user_row['username']} начислено {amount} сум.\nНовый баланс: {new_balance} сум"
    )
    try:
        sign = "+" if amount >= 0 else ""
        await bot.send_message(
            user_row["user_id"],
            f"🎁 Администратор изменил твой баланс: {sign}{amount} сум.\nТекущий баланс: {new_balance} сум",
        )
    except Exception:
        pass  # пользователь мог заблокировать бота — не критично


async def main():
    db.init_db()
    set_bot_token(BOT_TOKEN)
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await asyncio.gather(
        dp.start_polling(bot),
        server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
