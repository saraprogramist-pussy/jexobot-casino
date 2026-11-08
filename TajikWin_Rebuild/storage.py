"""SQLite state store. Uses BEGIN IMMEDIATE for atomic balance and round mutations.
For production use persistent disk or replace SQLite with PostgreSQL.
"""
import json,os,sqlite3,time,uuid
from contextlib import contextmanager
DB=os.getenv('DATABASE_PATH','tajikwin.sqlite3')
SCHEMA='''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT NOT NULL DEFAULT '', balance INTEGER NOT NULL DEFAULT 0 CHECK(balance>=0), created INTEGER NOT NULL, currency TEXT DEFAULT 'UZS', sound INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, delta INTEGER NOT NULL, kind TEXT NOT NULL, ref TEXT UNIQUE, ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS bets(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,game TEXT NOT NULL,stake INTEGER NOT NULL CHECK(stake>0),payout INTEGER,details TEXT,ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(user_id INTEGER PRIMARY KEY, game TEXT NOT NULL, bet_id TEXT NOT NULL, state TEXT NOT NULL, updated INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,amount INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending',ts INTEGER NOT NULL,reviewed INTEGER);
CREATE TABLE IF NOT EXISTS promos(code TEXT PRIMARY KEY, amount INTEGER NOT NULL, max_uses INTEGER NOT NULL, uses INTEGER NOT NULL DEFAULT 0, expires INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS redemptions(code TEXT NOT NULL,user_id INTEGER NOT NULL, ts INTEGER NOT NULL,PRIMARY KEY(code,user_id));
CREATE TABLE IF NOT EXISTS crash_rounds(id TEXT PRIMARY KEY,started REAL NOT NULL,closed REAL NOT NULL,point REAL,ended REAL);
CREATE TABLE IF NOT EXISTS crash_bets(id TEXT PRIMARY KEY,round_id TEXT NOT NULL,user_id INTEGER NOT NULL, stake INTEGER NOT NULL, auto REAL, payout INTEGER, UNIQUE(round_id,user_id));
'''

def init():
    with connect() as c:c.executescript(SCHEMA)
@contextmanager
def connect():
    c=sqlite3.connect(DB,timeout=30, isolation_level=None);c.row_factory=sqlite3.Row
    c.execute('PRAGMA busy_timeout=30000');c.execute('PRAGMA foreign_keys=ON')
    try:yield c
    finally:c.close()
@contextmanager
def tx():
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        try:yield c;c.execute('COMMIT')
        except Exception:c.execute('ROLLBACK');raise

def user(uid,name=''):
    # Status polling is frequent; do not take a write lock for an existing user.
    with connect() as c:
        row=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        if row and (not name or row['username']==name):return dict(row)
    with tx() as c:
        c.execute('INSERT OR IGNORE INTO users(id,username,created) VALUES(?,?,?)',(uid,name,int(time.time())))
        if name:c.execute('UPDATE users SET username=? WHERE id=?',(name,uid))
        return dict(c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())

def get_user(uid):
    with connect() as c:
        r=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        return dict(r) if r else None

def credit(c,uid,amount,kind,ref=None):
    if type(amount)!=int:raise ValueError('Сумма должна быть целым числом')
    if ref and c.execute('SELECT 1 FROM ledger WHERE ref=?',(ref,)).fetchone():return False
    changed=c.execute('UPDATE users SET balance=balance+? WHERE id=? AND balance+?>=0',(amount,uid,amount)).rowcount
    if not changed:raise ValueError('Недостаточно средств или игрок не найден')
    c.execute('INSERT INTO ledger VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,uid,amount,kind,ref,int(time.time())))
    return True

def admin_credit(uid,amount,ref):
    if amount<=0 or amount>100_000_000:raise ValueError('Недопустимая сумма')
    with tx() as c:return credit(c,uid,amount,'admin',ref)
def buy_bet(uid,game,stake,request_id):
    """Idempotent debit, returns (bet_id, new)."""
    from engine import validate_stake
    validate_stake(stake)
    with tx() as c:
        b=c.execute('SELECT id FROM bets WHERE id=? AND user_id=?',(request_id,uid)).fetchone()
        if b:return request_id,False
        credit(c,uid,-stake,'bet',f'bet:{request_id}')
        c.execute('INSERT INTO bets(id,user_id,game,stake,ts) VALUES(?,?,?,?,?)',(request_id,uid,game,stake,int(time.time())))
    return request_id,True

def settle(c,uid,bet_id,payout,details):
    if type(payout)!=int or payout<0:raise ValueError('Недопустимая выплата')
    b=c.execute('SELECT stake,payout FROM bets WHERE id=? AND user_id=?',(bet_id,uid)).fetchone()
    if not b:raise ValueError('Ставка не найдена')
    if b['payout'] is not None:return False
    c.execute('UPDATE bets SET payout=?,details=? WHERE id=?',(payout,json.dumps(details,ensure_ascii=False),bet_id))
    if payout:credit(c,uid,payout,'win',f'win:{bet_id}')
    return True

def instant_bet(uid,game,stake,params,request_id):
    from engine import instant,validate_stake
    validate_stake(stake)
    with tx() as c:
        old=c.execute('SELECT * FROM bets WHERE id=? AND user_id=?',(request_id,uid)).fetchone()
        if old:
            if old['payout'] is None:raise ValueError('Раунд ещё обрабатывается')
            return {'bet_id':request_id,'result':json.loads(old['details']),'payout':old['payout'],'balance':c.execute('SELECT balance FROM users WHERE id=?',(uid,)).fetchone()['balance']}
        # Validate game options and resolve once before debit.
        outcome,payout=instant(game,stake,params)
        credit(c,uid,-stake,'bet',f'bet:{request_id}')
        c.execute('INSERT INTO bets VALUES(?,?,?,?,?,?,?)',(request_id,uid,game,stake,None,None,int(time.time())))
        settle(c,uid,request_id,payout,outcome)
        balance=c.execute('SELECT balance FROM users WHERE id=?',(uid,)).fetchone()['balance']
        return {'bet_id':request_id,'result':outcome,'payout':payout,'balance':balance}

def start_session(uid,game,stake,params,request_id):
    from engine import new_session
    state=new_session(game,stake,params)
    with tx() as c:
        current=c.execute('SELECT state,bet_id FROM sessions WHERE user_id=?',(uid,)).fetchone()
        if current:
            if current['bet_id']==request_id:return json.loads(current['state'])
            raise ValueError('Сначала закончи предыдущую игру')
        credit(c,uid,-stake,'bet',f'bet:{request_id}')
        c.execute('INSERT INTO bets VALUES(?,?,?,?,?,?,?)',(request_id,uid,game,stake,None,None,int(time.time())))
        c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(uid,game,request_id,json.dumps(state),int(time.time())))
    return state

def session(uid):
    with connect() as c:
        row=c.execute('SELECT * FROM sessions WHERE user_id=?',(uid,)).fetchone()
        return dict(row) if row else None

def session_move(uid,action,params):
    from engine import move
    with tx() as c:
        current=c.execute('SELECT * FROM sessions WHERE user_id=?',(uid,)).fetchone()
        if not current:raise ValueError('Активной игры нет')
        state=json.loads(current['state']); result,payout=move(state,action,params)
        if payout is None:c.execute('UPDATE sessions SET state=?,updated=? WHERE user_id=?',(json.dumps(state),int(time.time()),uid))
        else:
            settle(c,uid,current['bet_id'],payout,result)
            c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
        balance=c.execute('SELECT balance FROM users WHERE id=?',(uid,)).fetchone()['balance']
        return {'result':result,'payout':payout,'balance':balance,'bet_id':current['bet_id']}

def history(uid,limit=30):
    with connect() as c:return [dict(r) for r in c.execute('SELECT id,game,stake,payout,ts,details FROM bets WHERE user_id=? ORDER BY ts DESC LIMIT ?',(uid,limit))]
def leaderboard():
    with connect() as c:return [dict(r) for r in c.execute('SELECT username,balance FROM users ORDER BY balance DESC LIMIT 20')]

def create_request(uid,amount):
    if type(amount)!=int or not 1<=amount<=10_000_000:raise ValueError('Укажи сумму 1–10 000 000')
    rid=uuid.uuid4().hex[:12]
    with tx() as c:c.execute('INSERT INTO requests(id,user_id,amount,ts) VALUES(?,?,?,?)',(rid,uid,amount,int(time.time())))
    return rid

def review_request(rid,approve):
    with tx() as c:
        r=c.execute('SELECT * FROM requests WHERE id=?',(rid,)).fetchone()
        if not r:return None
        if r['status']!='pending':return {'changed':False,**dict(r)}
        c.execute('UPDATE requests SET status=?,reviewed=? WHERE id=?',('approved' if approve else 'rejected',int(time.time()),rid))
        if approve:credit(c,r['user_id'],r['amount'],'request',f'request:{rid}')
        return {'changed':True,**dict(r),'status':'approved' if approve else 'rejected'}

def requests():
    with connect() as c:return [dict(x) for x in c.execute('SELECT r.*,u.username FROM requests r JOIN users u ON u.id=r.user_id ORDER BY r.ts DESC LIMIT 20')]

def create_promo(code,amount,limit):
    code=code.strip().upper()
    if not code.isalnum() or not 3<=len(code)<=24 or not 1<=amount<=1_000_000 or not 1<=limit<=100000:raise ValueError('Промокод: 3–24 символа, сумма 1–1 000 000, лимит >=1')
    with tx() as c:c.execute('INSERT INTO promos(code,amount,max_uses) VALUES(?,?,?)',(code,amount,limit))
def redeem(uid,code):
    code=code.strip().upper()
    with tx() as c:
        p=c.execute('SELECT * FROM promos WHERE code=?',(code,)).fetchone()
        if not p or p['uses']>=p['max_uses'] or (p['expires'] and p['expires']<time.time()):raise ValueError('Промокод недоступен')
        if c.execute('SELECT 1 FROM redemptions WHERE code=? AND user_id=?',(code,uid)).fetchone():raise ValueError('Уже активирован')
        c.execute('INSERT INTO redemptions VALUES(?,?,?)',(code,uid,int(time.time())))
        c.execute('UPDATE promos SET uses=uses+1 WHERE code=?',(code,))
        credit(c,uid,p['amount'],'promo',f'promo:{code}:{uid}')
        return p['amount']

def events(uid,after=0):
    with connect() as c:return [dict(r) for r in c.execute("SELECT rowid AS cursor,ts,delta,kind,ref FROM ledger WHERE user_id=? AND delta>0 AND kind IN ('admin','request','promo') AND rowid>? ORDER BY rowid ASC LIMIT 30",(uid,after))]

def crash_create_round(betting_seconds=7):
    rid=uuid.uuid4().hex[:10];now=time.time()
    with tx() as c:c.execute('INSERT INTO crash_rounds(id,started,closed) VALUES(?,?,?)',(rid,now,now+betting_seconds))
    return rid

def crash_status():
    with connect() as c:
        r=c.execute('SELECT * FROM crash_rounds ORDER BY started DESC LIMIT 1').fetchone()
        if not r:return None
        return dict(r)

def crash_place(uid,stake,auto):
    from engine import validate_stake
    validate_stake(stake)
    if auto is not None and (type(auto) not in (int,float) or not 1.01<=auto<=21):raise ValueError('Автовывод 1.01×–21×')
    with tx() as c:
        r=c.execute('SELECT * FROM crash_rounds ORDER BY started DESC LIMIT 1').fetchone()
        if not r or r['closed']<=time.time() or r['point'] is not None:raise ValueError('Приём ставок уже закрыт')
        if c.execute('SELECT 1 FROM crash_bets WHERE round_id=? AND user_id=?',(r['id'],uid)).fetchone():raise ValueError('В этом раунде ставка уже есть')
        bid=uuid.uuid4().hex;credit(c,uid,-stake,'bet',f'bet:{bid}')
        c.execute('INSERT INTO bets VALUES(?,?,?,?,?,?,?)',(bid,uid,'crash',stake,None,None,int(time.time())))
        c.execute('INSERT INTO crash_bets VALUES(?,?,?,?,?,NULL)',(bid,r['id'],uid,stake,auto))
        return {'bet_id':bid,'round_id':r['id']}

def crash_start(rid,point):
    with tx() as c:c.execute('UPDATE crash_rounds SET point=? WHERE id=? AND point IS NULL',(point,rid))

def crash_auto_cashout(rid,current):
    """Settle auto cashouts promptly during the shared flight, not after the crash."""
    with tx() as c:
        r=c.execute('SELECT * FROM crash_rounds WHERE id=?',(rid,)).fetchone()
        if not r or r['point'] is None or r['ended'] is not None:return 0
        bets=c.execute('SELECT * FROM crash_bets WHERE round_id=? AND payout IS NULL AND auto IS NOT NULL AND auto<=? AND auto<=?',(rid,current,r['point'])).fetchall()
        for b in bets:
            payout=int(b['stake']*b['auto'])
            c.execute('UPDATE crash_bets SET payout=? WHERE id=?',(payout,b['id']))
            settle(c,b['user_id'],b['id'],payout,{'multiplier':b['auto'],'auto_cashout':True})
        return len(bets)

def crash_cashout(uid,mult):
    with tx() as c:
        r=c.execute('SELECT * FROM crash_rounds ORDER BY started DESC LIMIT 1').fetchone()
        if not r or r['point'] is None or r['ended'] is not None:raise ValueError('Нет активного полёта')
        from engine import crash_multiplier
        current=crash_multiplier(time.time()-r['closed'])
        if current>=r['point']:raise ValueError('Ракета уже упала')
        b=c.execute('SELECT * FROM crash_bets WHERE round_id=? AND user_id=?',(r['id'],uid)).fetchone()
        if not b or b['payout'] is not None:raise ValueError('Нет незавершённой ставки')
        payout=int(b['stake']*current)
        c.execute('UPDATE crash_bets SET payout=? WHERE id=?',(payout,b['id']))
        settle(c,uid,b['id'],payout,{'multiplier':current,'point':r['point']})
        return {'payout':payout,'multiplier':current,'balance':c.execute('SELECT balance FROM users WHERE id=?',(uid,)).fetchone()['balance']}

def crash_abort_round(rid):
    """Return any unresolved stake if process restarted mid-round. No artificial loss."""
    with tx() as c:
        r=c.execute('SELECT * FROM crash_rounds WHERE id=?',(rid,)).fetchone()
        if not r or r['ended'] is not None:return
        for b in c.execute('SELECT * FROM crash_bets WHERE round_id=? AND payout IS NULL',(rid,)).fetchall():
            payout=b['stake']
            c.execute('UPDATE crash_bets SET payout=? WHERE id=?',(payout,b['id']))
            settle(c,b['user_id'],b['id'],payout,{'aborted':True,'reason':'server_restart'})
        c.execute('UPDATE crash_rounds SET point=COALESCE(point,1.0),ended=? WHERE id=?',(time.time(),rid))

def crash_finish(rid):
    with tx() as c:
        r=c.execute('SELECT * FROM crash_rounds WHERE id=?',(rid,)).fetchone()
        if not r or r['ended'] is not None:return
        for b in c.execute('SELECT * FROM crash_bets WHERE round_id=? AND payout IS NULL',(rid,)).fetchall():
            # auto cashouts are settled if their threshold was reached; at cap exact 21 is payable
            payout=int(b['stake']*b['auto']) if b['auto'] and b['auto']<=r['point'] else 0
            c.execute('UPDATE crash_bets SET payout=? WHERE id=?',(payout,b['id']))
            settle(c,b['user_id'],b['id'],payout,{'point':r['point'],'auto':b['auto'],'multiplier':b['auto'] if payout else 0})
        c.execute('UPDATE crash_rounds SET ended=? WHERE id=?',(time.time(),rid))
