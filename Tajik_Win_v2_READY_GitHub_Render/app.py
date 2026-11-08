import asyncio
import os
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
import uvicorn

import db
from server import app as fastapi_app, set_bot_token

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0") or "0")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
PORT = int(os.environ.get("PORT", "8000"))

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())


def webapp_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♠ Открыть Tajik Win", web_app=WebAppInfo(url=WEBAPP_URL))],
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
        "♠ *Tajik Win*\nИгры с условными кредитами, без денежных платежей и вывода средств.\n\n"
        "Нажми кнопку ниже, чтобы открыть игры:",
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


@dp.message(Command("promo"))
async def cmd_promo(message: Message):
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        await message.answer("Команда только для администратора.")
        return
    parts = (message.text or "").split()
    if len(parts) != 4:
        await message.answer("Создать промокод: /promo CODE 50000 20\n(код, сумма виртуальных монет, число активаций)")
        return
    try:
        code = db.create_promo(parts[1], int(parts[2]), int(parts[3]))
        await message.answer(f"Промокод {code} создан. Номинал: {parts[2]}, активаций: {parts[3]}.")
    except (ValueError, sqlite3.IntegrityError) as exc:
        await message.answer(f"Не удалось создать промокод: {exc}")


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

    try:
        new_balance = db.adjust_balance(user_row["user_id"], amount)
    except ValueError:
        await message.answer("Нельзя списать больше, чем есть на балансе.")
        return
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


@dp.callback_query(lambda c: c.data and c.data.startswith('credit:'))
async def handle_credit(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID or not ADMIN_ID:
        await callback.answer('Доступ запрещён', show_alert=True)
        return
    try:
        _, action, ident = callback.data.split(':', 2)
        if action == 'reply':
            await callback.answer()
            await callback.message.answer(f'Ответ игроку: /reply {ident} текст')
            return
        if action not in ('yes', 'no'): raise ValueError('invalid_action')
        decision = db.decide_credit_request(int(ident), action == 'yes')
        await callback.answer('Решение сохранено')
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"Заявка #{ident}: {decision['status']}")
        await bot.send_message(decision['user_id'],f"Заявка #{ident}: {'одобрена, баланс начислен' if action == 'yes' else 'отклонена'}. Сумма: {decision['amount']:,} сум.")
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
    except Exception:
        await callback.answer('Решение сохранено, но уведомление не доставлено.')


@dp.message(Command('admin'))
async def cmd_admin(message: Message):
    if not ADMIN_ID or message.from_user.id != ADMIN_ID: return
    stats = db.admin_stats()
    await message.answer(f"""Tajik Win — панель
Игроков: {stats['users']}
Ставок: {stats['bets']}
Заявок: {stats['pending']}

/promo CODE 50000 10
/give ID 10000
/requests
/reply ID сообщение
/broadcast текст""")


@dp.message(Command('requests'))
async def cmd_requests(message: Message):
    if not ADMIN_ID or message.from_user.id != ADMIN_ID: return
    rows = db.credit_requests(15)
    text = '\n'.join(f"#{r['id']} @{r['username']} — {r['amount']:,} сум — {r['status']}" for r in rows)
    await message.answer(text or 'Заявок нет')


@dp.message(Command('reply'))
async def cmd_reply(message: Message):
    if not ADMIN_ID or message.from_user.id != ADMIN_ID: return
    parts = (message.text or '').split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer('Формат: /reply 123456789 сообщение')
        return
    uid = int(parts[1])
    if not db.find_user(str(uid)):
        await message.answer('Игрок не найден')
        return
    db.log_support(uid, 'admin', parts[2])
    try:
        await bot.send_message(uid, f'Сообщение администратора: \n{parts[2]}')
        await message.answer('Отправлено')
    except Exception:
        await message.answer('Сохранено, но Telegram-сообщение не доставлено')


@dp.message(Command('broadcast'))
async def cmd_broadcast(message: Message):
    if not ADMIN_ID or message.from_user.id != ADMIN_ID: return
    parts = (message.text or '').split(maxsplit=1)
    if len(parts)<2: return await message.answer('Формат: /broadcast текст')
    # Intentionally omit bulk send until admin confirmation and opt-in flow exist.
    await message.answer('Массовая рассылка пока выключена. Нужны согласие игроков и подтверждение сообщения.')


@dp.message(lambda m: bool(m.photo))
async def relay_photo(message: Message):
    if message.from_user.id == ADMIN_ID: return
    db.get_or_create_user(message.from_user.id,message.from_user.username or message.from_user.first_name or 'Игрок')
    db.log_support(message.from_user.id,'player',message.caption or '',message.photo[-1].file_id)
    if ADMIN_ID:
        try:
            await bot.send_photo(ADMIN_ID,message.photo[-1].file_id,caption=f"Tajik Win · фото от @{message.from_user.username or 'игрок'} (ID {message.from_user.id})\n{message.caption or ''}\nОтвет: /reply {message.from_user.id} текст")
        except Exception: pass
    await message.answer('Скриншот отправлен администратору.')


async def main():
    db.init_db()
    set_bot_token(BOT_TOKEN)
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    if bot:
        await asyncio.gather(dp.start_polling(bot), server.serve())
    else:
        await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
