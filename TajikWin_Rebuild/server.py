"""Tajik Win Telegram Mini App API. Play credits only; no payment processing."""
import asyncio, hashlib, hmac, json, os, time, uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qsl
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
import engine,storage

BOT_TOKEN=os.getenv('BOT_TOKEN','')
ADMIN_ID=int(os.getenv('ADMIN_ID','0'))
WEB=Path(__file__).parent/'webapp'

async def crash_cycle():
    """One global sequence per process. Set WEB_CONCURRENCY=1; durable round history in SQLite."""
    while True:
        try:
            existing=storage.crash_status()
            if existing and existing['ended'] is None:
                # On restart, do not resurrect an interrupted flight as a new outcome.
                storage.crash_abort_round(existing['id'])
            rid=storage.crash_create_round(7)
            await asyncio.sleep(7)
            point=engine.crash_point()
            storage.crash_start(rid,point)
            if point>1.0:
                # A flight is bounded by 21x; not forced to finish in 7 seconds.
                duration=max(0.1,__import__('math').log(point)/.16)
                flight_start=time.time()
                while time.time()-flight_start<duration:
                    current=engine.crash_multiplier(time.time()-flight_start)
                    storage.crash_auto_cashout(rid,min(current,point))
                    await asyncio.sleep(.15)
                storage.crash_auto_cashout(rid,point)
            storage.crash_finish(rid)
            await asyncio.sleep(1.5)
        except asyncio.CancelledError:raise
        except Exception as exc:
            print('crash loop error:',repr(exc),flush=True)
            await asyncio.sleep(2)

@asynccontextmanager
async def lifespan(app):
    storage.init()
    task=asyncio.create_task(crash_cycle())
    yield
    task.cancel()
    try:await task
    except asyncio.CancelledError:pass
app=FastAPI(title='Tajik Win Play-Credit API',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=WEB),name='static')

@app.get('/')
def index():return FileResponse(WEB/'index.html')
@app.get('/health')
def health():return {'ok':True,'time':int(time.time())}

def user_from_init(init_data):
    if os.getenv('LOCAL_TEST')=='1' and init_data.startswith('test:'):
        # EXPLICITLY never enable LOCAL_TEST on a publicly accessible deployment.
        try:uid=int(init_data.split(':',1)[1]);assert uid>0
        except:raise HTTPException(401,'invalid test id')
        storage.user(uid,'test_user');return uid
    if not BOT_TOKEN or not init_data:raise HTTPException(401,'Open inside Telegram')
    try:parsed=dict(parse_qsl(init_data,strict_parsing=True))
    except Exception:raise HTTPException(401,'invalid initData')
    given=parsed.pop('hash','')
    if not given:raise HTTPException(401,'no initData signature')
    # Third-party signature field is excluded only if present in Telegram's scheme.
    parsed.pop('signature',None)
    check='\n'.join(f'{k}={v}' for k,v in sorted(parsed.items()))
    secret=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest()
    expected=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(given,expected):raise HTTPException(401,'signature mismatch')
    try:
        age=time.time()-int(parsed['auth_date'])
        if age>86400 or age< -60:raise ValueError('expired')
        u=json.loads(parsed['user']);uid=int(u['id'])
        if uid<=0:raise ValueError('bad id')
    except Exception:raise HTTPException(401,'invalid user or expired auth')
    storage.user(uid,u.get('username') or u.get('first_name') or 'player')
    return uid

class Auth(BaseModel):
    initData:str
class Bet(Auth):
    stake:int
    requestId:str=Field(min_length=12,max_length=100)
    params:dict=Field(default_factory=dict)
class Start(Bet):pass
class Move(Auth):
    action:str
    params:dict=Field(default_factory=dict)
class Promo(Auth):
    code:str
class CreditRequest(Auth):
    amount:int
class CrashBet(Auth):
    stake:int
    auto:float|None=None
class Cashout(Auth):pass
class Settings(Auth):
    sound:bool|None=None
    currency:str|None=None

def err_wrap(fn):
    try:return fn()
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/me')
def me(initData:str):
    uid=user_from_init(initData)
    active=storage.session(uid)
    safe=None
    if active:
        safe={'game':active['game'],'bet_id':active['bet_id'],'result':engine.public_session(json.loads(active['state']))}
    return {'profile':storage.get_user(uid),'session':safe}
@app.get('/api/history')
def history(initData:str):return storage.history(user_from_init(initData))
@app.get('/api/leaderboard')
def leaderboard(initData:str):
    user_from_init(initData);return storage.leaderboard()
@app.post('/api/instant/{game}')
def instant(game:str,b:Bet):
    uid=user_from_init(b.initData)
    if game not in ('slots','roulette','dice','plinko','keno','wheel'):raise HTTPException(404,'not an instant game')
    return err_wrap(lambda:storage.instant_bet(uid,game,b.stake,b.params,b.requestId))
@app.post('/api/session/{game}/start')
def start(game:str,b:Start):
    uid=user_from_init(b.initData)
    if game not in ('blackjack','mines','hilo','poker','tower'):raise HTTPException(404,'not a session game')
    s=err_wrap(lambda:storage.start_session(uid,game,b.stake,b.params,b.requestId))
    return {'result':engine.public_session(s),'balance':storage.get_user(uid)['balance']}
@app.post('/api/session/move')
def move(b:Move):return err_wrap(lambda:storage.session_move(user_from_init(b.initData),b.action,b.params))
@app.post('/api/promos/redeem')
def redeem(b:Promo):
    uid=user_from_init(b.initData)
    v=err_wrap(lambda:storage.redeem(uid,b.code))
    return {'credited':v,'balance':storage.get_user(uid)['balance']}
@app.post('/api/credits/request')
async def credits_request(b:CreditRequest):
    uid=user_from_init(b.initData)
    rid=err_wrap(lambda:storage.create_request(uid,b.amount))
    if ADMIN_ID and BOT_TOKEN:
        # Best effort notification; request itself is saved even if Telegram is unreachable.
        try:
            async with httpx.AsyncClient(timeout=6) as client:
                await client.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',json={'chat_id':ADMIN_ID,'text':f'Заявка Tajik Win #{rid}\nИгрок ID: {uid}\nСумма: {b.amount:,} UZS\nОдобрить: /approve {rid}\nОтклонить: /reject {rid}'})
        except Exception:pass
    return {'request_id':rid,'status':'pending'}
@app.get('/api/events')
def events(initData:str,after:int=0):return storage.events(user_from_init(initData),after)
@app.post('/api/settings')
def settings(b:Settings):
    uid=user_from_init(b.initData)
    if b.currency is not None and b.currency not in ('UZS','USD','EUR','RUB'):raise HTTPException(400,'bad currency')
    with storage.tx() as c:
        if b.currency is not None:c.execute('UPDATE users SET currency=? WHERE id=?',(b.currency,uid))
        if b.sound is not None:c.execute('UPDATE users SET sound=? WHERE id=?',(int(b.sound),uid))
    return storage.get_user(uid)
@app.get('/api/rates')
async def rates():
    """Reference rates CBU Uzbekistan. Never imply real payout currency."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r=await client.get('https://cbu.uz/uz/arkhiv-kursov-valyut/json/')
            r.raise_for_status(); items=r.json()
        fx={x['Ccy']:float(x['Rate']) for x in items if x.get('Ccy') in ('USD','EUR','RUB')}
        if len(fx)!=3:raise ValueError('rates incomplete')
        return {'rates':{'UZS':1,**fx},'date':items[0].get('Date'),'source':'CBU'}
    except Exception:
        return {'rates':{'UZS':1},'source':'unavailable','warning':'Курсы недоступны'}
@app.get('/api/crash/status')
def crash_status(initData:str):
    uid=user_from_init(initData)
    r=storage.crash_status()
    if not r:return {'phase':'initializing'}
    now=time.time();phase='betting' if now<r['closed'] and r['point'] is None else 'finished' if r['ended'] else 'flying'
    mult=1.0 if phase=='betting' else r['point'] if phase=='finished' else engine.crash_multiplier(now-r['closed'])
    with storage.connect() as c:
        my=c.execute('SELECT stake,auto,payout FROM crash_bets WHERE round_id=? AND user_id=?',(r['id'],uid)).fetchone()
        recent=[dict(v) for v in c.execute('SELECT point FROM crash_rounds WHERE ended IS NOT NULL ORDER BY ended DESC LIMIT 10')]
        players=c.execute('SELECT count(*) n FROM crash_bets WHERE round_id=?',(r['id'],)).fetchone()['n']
    return {'round_id':r['id'],'phase':phase,'remaining':round(max(0,r['closed']-now),1),'multiplier':mult,'players':players,'my_bet':dict(my) if my else None,'recent':[x['point'] for x in recent]}
@app.post('/api/crash/bet')
def crash_bet(b:CrashBet):return err_wrap(lambda:storage.crash_place(user_from_init(b.initData),b.stake,b.auto))
@app.post('/api/crash/cashout')
def crash_cashout(b:Cashout):return err_wrap(lambda:storage.crash_cashout(user_from_init(b.initData),0))
