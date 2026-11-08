"""Run both FastAPI web app and Telegram bot in one Render instance."""
import asyncio,os
from aiogram import Bot,Dispatcher,F
from aiogram.filters import Command,CommandStart
from aiogram.types import Message,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo
import uvicorn
import storage
from server import app

TOKEN=os.getenv('BOT_TOKEN','')
ADMIN=int(os.getenv('ADMIN_ID','0') or 0)
URL=os.getenv('WEBAPP_URL','')
PORT=int(os.getenv('PORT','8000'))

async def bot_main():
    if not TOKEN:
        print('BOT_TOKEN missing: serving web only (Telegram bot disabled)',flush=True)
        await asyncio.Event().wait()
    bot=Bot(TOKEN);dp=Dispatcher()
    @dp.message(CommandStart())
    async def start(m:Message):
        storage.user(m.from_user.id,m.from_user.username or m.from_user.first_name or 'player')
        if not URL:return await m.answer('Настройте WEBAPP_URL в Render.')
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Открыть Tajik Win',web_app=WebAppInfo(url=URL))]])
        await m.answer('Tajik Win — игровой клуб внутри Telegram.\nУ новых игроков баланс: 0. Игровые кредиты не обмениваются на деньги.',reply_markup=kb)
    @dp.message(Command('myid'))
    async def myid(m:Message):await m.answer(f'ID: {m.from_user.id}')
    @dp.message(Command('top'))
    async def top(m:Message):
        rows=storage.leaderboard()[:10]
        await m.answer('Топ игроков:\n'+'\n'.join(f"{i+1}. {r['username']}: {r['balance']:,} сум" for i,r in enumerate(rows)))
    @dp.message(Command('admin'))
    async def admin(m:Message):
        if m.from_user.id!=ADMIN:return
        await m.answer('Админ-команды:\n/requests — заявки\n/approve ID\n/reject ID\n/give user_id amount\n/promo CODE amount limit\n/reply user_id текст')
    @dp.message(Command('requests'))
    async def requests(m:Message):
        if m.from_user.id!=ADMIN:return
        rows=storage.requests()
        await m.answer('Заявки:\n'+'\n'.join(f"#{r['id']} | {r['user_id']} | {r['amount']:,} | {r['status']}" for r in rows) if rows else 'Заявок нет')
    @dp.message(Command('approve','reject'))
    async def review(m:Message):
        if m.from_user.id!=ADMIN:return
        words=m.text.split()
        if len(words)!=2:return await m.answer('Укажи ID заявки')
        approved=words[0].split('@')[0]=='/approve'
        result=storage.review_request(words[1],approved)
        if not result:return await m.answer('Заявка не найдена')
        await m.answer(f"Статус: {result['status']}. {'Изменено' if result['changed'] else 'Уже обработано'}")
        if result['changed']:
            try:await bot.send_message(result['user_id'],'Начисление подтверждено.' if approved else 'Заявка отклонена.')
            except Exception:pass
    @dp.message(Command('give'))
    async def give(m:Message):
        if m.from_user.id!=ADMIN:return
        parts=m.text.split()
        if len(parts)!=3:return await m.answer('Пример: /give 123456789 100000')
        try:
            uid,amount=int(parts[1]),int(parts[2]);storage.admin_credit(uid,amount,f'give:{m.message_id}:{uid}')
            await m.answer(f'Начислено {amount:,} пользователю {uid}.')
            try:await bot.send_message(uid,f'Баланс начислен: +{amount:,} сум')
            except Exception:pass
        except Exception as e:await m.answer(str(e))
    @dp.message(Command('promo'))
    async def promo(m:Message):
        if m.from_user.id!=ADMIN:return
        p=m.text.split()
        if len(p)!=4:return await m.answer('Пример: /promo START 100000 50')
        try:storage.create_promo(p[1],int(p[2]),int(p[3]));await m.answer('Промокод создан.')
        except Exception as e:await m.answer(str(e))
    @dp.message(Command('reply'))
    async def reply(m:Message):
        if m.from_user.id!=ADMIN:return
        p=m.text.split(maxsplit=2)
        if len(p)!=3:return await m.answer('/reply 123456789 Сообщение')
        try:await bot.send_message(int(p[1]),'Поддержка Tajik Win: '+p[2]);await m.answer('Отправлено')
        except Exception as e:await m.answer(str(e))
    @dp.message(F.photo | F.document)
    async def media(m:Message):
        if m.from_user.id==ADMIN or not ADMIN:return
        try:await bot.forward_message(ADMIN,m.chat.id,m.message_id);await m.answer('Передано администратору.')
        except Exception:await m.answer('Не удалось передать файл.')
    @dp.message(F.text)
    async def message(m:Message):
        if m.from_user.id==ADMIN or not ADMIN:return
        try:await bot.send_message(ADMIN,f'Сообщение от {m.from_user.id} (@{m.from_user.username or ""}):\n{m.text}');await m.answer('Передано администратору.')
        except Exception:await m.answer('Сообщение временно недоступно.')
    try:await dp.start_polling(bot)
    finally:await bot.session.close()

async def main():
    storage.init()
    server=uvicorn.Server(uvicorn.Config(app,host='0.0.0.0',port=PORT,log_level='info'))
    await asyncio.gather(server.serve(),bot_main())
if __name__=='__main__':asyncio.run(main())
