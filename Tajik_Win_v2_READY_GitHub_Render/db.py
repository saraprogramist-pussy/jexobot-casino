import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.getenv('DB_PATH', str(Path(__file__).with_name('casino.db')))
STARTING_BALANCE = 100_000
MIN_STAKE = 3_000
MAX_STAKE = 1_000_000

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
 user_id INTEGER PRIMARY KEY, username TEXT,
 balance INTEGER NOT NULL DEFAULT 100000 CHECK(balance >= 0),
 last_bonus_ts INTEGER NOT NULL DEFAULT 0,
 total_wagered INTEGER NOT NULL DEFAULT 0,
 total_won INTEGER NOT NULL DEFAULT 0,
 created_ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bets (
 id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
 game TEXT NOT NULL, stake INTEGER NOT NULL, payout INTEGER NOT NULL, ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 user_id INTEGER PRIMARY KEY, game TEXT NOT NULL, stake INTEGER NOT NULL,
 state TEXT NOT NULL, created_ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS promocodes (
 code TEXT PRIMARY KEY, amount INTEGER NOT NULL CHECK(amount > 0),
 max_uses INTEGER NOT NULL CHECK(max_uses > 0),
 uses INTEGER NOT NULL DEFAULT 0, created_ts INTEGER NOT NULL,
 expires_ts INTEGER, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS promo_redemptions (
 code TEXT NOT NULL, user_id INTEGER NOT NULL, ts INTEGER NOT NULL,
 PRIMARY KEY(code, user_id)
);
'''

@contextmanager
def get_conn(write=False):
 conn = sqlite3.connect(DB_PATH, timeout=15)
 conn.row_factory = sqlite3.Row
 conn.execute('PRAGMA busy_timeout=15000')
 try:
  if write: conn.execute('BEGIN IMMEDIATE')
  yield conn
  conn.commit()
 except Exception:
  conn.rollback()
  raise
 finally: conn.close()

def init_db():
 with get_conn() as conn: conn.executescript(SCHEMA)

def get_or_create_user(user_id, username):
 with get_conn(True) as conn:
  conn.execute('INSERT OR IGNORE INTO users (user_id, username, balance, created_ts) VALUES (?, ?, ?, ?)', (user_id, username, STARTING_BALANCE, int(time.time())))
  conn.execute('UPDATE users SET username=? WHERE user_id=?', (username, user_id))
  return conn.execute('SELECT * FROM users WHERE user_id=?', (user_id,)).fetchone()

def get_balance(user_id):
 with get_conn() as conn:
  row=conn.execute('SELECT balance FROM users WHERE user_id=?',(user_id,)).fetchone()
  return row['balance'] if row else 0

def adjust_balance(user_id, delta):
 with get_conn(True) as conn:
  cur=conn.execute('UPDATE users SET balance=balance+? WHERE user_id=? AND balance+? >= 0', (delta,user_id,delta))
  if cur.rowcount!=1: raise ValueError('user_not_found_or_insufficient_balance')
  if delta:
   conn.execute('INSERT INTO ledger(user_id,delta,kind,reference,created_ts) VALUES(?,?,?,?,?)',(user_id,delta,'manual_credit' if delta>0 else 'admin_debit','admin_command',int(time.time())))
  return conn.execute('SELECT balance FROM users WHERE user_id=?',(user_id,)).fetchone()['balance']

def _debit(conn,user_id,stake):
 if isinstance(stake,bool) or not isinstance(stake,int) or not MIN_STAKE<=stake<=MAX_STAKE: raise ValueError('invalid_stake')
 cur=conn.execute('UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?',(stake,user_id,stake))
 if cur.rowcount != 1: raise ValueError('insufficient_balance')

def _credit_and_record(conn,user_id,game,stake,payout):
 if isinstance(payout,bool) or not isinstance(payout,int) or payout<0: raise ValueError('invalid_payout')
 conn.execute('UPDATE users SET balance=balance+?,total_wagered=total_wagered+?,total_won=total_won+? WHERE user_id=?',(payout,stake,payout,user_id))
 conn.execute('INSERT INTO bets (user_id,game,stake,payout,ts) VALUES (?,?,?,?,?)',(user_id,game,stake,payout,int(time.time())))
 return conn.execute('SELECT balance FROM users WHERE user_id=?',(user_id,)).fetchone()['balance']

def play_bet(user_id,game,stake,draw):
 with get_conn(True) as conn:
  if conn.execute('SELECT 1 FROM sessions WHERE user_id=?',(user_id,)).fetchone(): raise ValueError('finish_active_game_first')
  _debit(conn,user_id,stake)
  result,payout=draw()
  balance=_credit_and_record(conn,user_id,game,stake,payout)
  return result,payout,balance

def session_start(user_id,game,stake,state):
 with get_conn(True) as conn:
  if conn.execute('SELECT 1 FROM sessions WHERE user_id=?',(user_id,)).fetchone(): raise ValueError('active_session_exists')
  _debit(conn,user_id,stake)
  conn.execute('INSERT INTO sessions VALUES (?,?,?,?,?)',(user_id,game,stake,json.dumps(state),int(time.time())))
  return conn.execute('SELECT balance FROM users WHERE user_id=?',(user_id,)).fetchone()['balance']

def session_get(user_id):
 with get_conn() as conn:
  row=conn.execute('SELECT * FROM sessions WHERE user_id=?',(user_id,)).fetchone()
  return {'game':row['game'],'stake':row['stake'],'state':json.loads(row['state'])} if row else None

def session_mutate(user_id,game,change):
 with get_conn(True) as conn:
  row=conn.execute('SELECT * FROM sessions WHERE user_id=? AND game=?',(user_id,game)).fetchone()
  if not row: raise ValueError('no_session')
  state=json.loads(row['state'])
  next_state,payout,output=change(state,row['stake'])
  if payout is None: conn.execute('UPDATE sessions SET state=? WHERE user_id=?',(json.dumps(next_state),user_id))
  else:
   conn.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
   output['balance']=_credit_and_record(conn,user_id,game,row['stake'],payout)
  return output

def create_promo(code,amount,max_uses,expires_ts=None):
 code=code.strip().upper()
 if not (3<=len(code)<=32 and all(c.isascii() and (c.isalnum() or c in '-_') for c in code)): raise ValueError('invalid_promo_code')
 if not 1<=amount<=100_000_000 or not 1<=max_uses<=100_000: raise ValueError('invalid_promo_values')
 with get_conn(True) as conn:
  conn.execute('INSERT INTO promocodes (code,amount,max_uses,created_ts,expires_ts) VALUES (?,?,?,?,?)',(code,amount,max_uses,int(time.time()),expires_ts))
 return code

def redeem_promo(user_id,code):
 code=code.strip().upper()
 with get_conn(True) as conn:
  promo=conn.execute('SELECT * FROM promocodes WHERE code=?',(code,)).fetchone()
  if not promo or not promo['active']: raise ValueError('promo_not_found')
  if promo['expires_ts'] and promo['expires_ts']<=time.time(): raise ValueError('promo_expired')
  if promo['uses']>=promo['max_uses']: raise ValueError('promo_exhausted')
  if conn.execute('SELECT 1 FROM promo_redemptions WHERE code=? AND user_id=?',(code,user_id)).fetchone(): raise ValueError('promo_already_used')
  conn.execute('INSERT INTO promo_redemptions VALUES (?,?,?)',(code,user_id,int(time.time())))
  conn.execute('UPDATE promocodes SET uses=uses+1 WHERE code=?',(code,))
  conn.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(promo['amount'],user_id))
  return {'amount':promo['amount'],'balance':conn.execute('SELECT balance FROM users WHERE user_id=?',(user_id,)).fetchone()['balance']}

def get_leaderboard(limit=10):
 with get_conn() as conn: return conn.execute('SELECT username,balance FROM users ORDER BY balance DESC LIMIT ?',(limit,)).fetchall()

def get_stats(user_id):
 with get_conn() as conn: return conn.execute('SELECT balance,total_wagered,total_won FROM users WHERE user_id=?',(user_id,)).fetchone()

def find_user(identifier):
 identifier=identifier.lstrip('@')
 with get_conn() as conn:
  if identifier.isdigit(): return conn.execute('SELECT * FROM users WHERE user_id=?',(int(identifier),)).fetchone()
  return conn.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE',(identifier,)).fetchone()

EXTRA_SCHEMA = '''
CREATE TABLE IF NOT EXISTS preferences (user_id INTEGER PRIMARY KEY, nickname TEXT, avatar TEXT DEFAULT '♠', lang TEXT DEFAULT 'ru', currency TEXT DEFAULT 'UZS', sound INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS bet_preferences (user_id INTEGER, bet_id INTEGER, hidden INTEGER DEFAULT 0, pinned INTEGER DEFAULT 0, PRIMARY KEY(user_id,bet_id));
CREATE TABLE IF NOT EXISTS credit_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_ts INTEGER NOT NULL, decided_ts INTEGER);
CREATE TABLE IF NOT EXISTS support_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, sender TEXT NOT NULL, text TEXT, file_id TEXT, created_ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,delta INTEGER NOT NULL,kind TEXT NOT NULL,reference TEXT,created_ts INTEGER NOT NULL);
'''
_original_init_db = init_db
def init_db():
 _original_init_db()
 with get_conn() as c: c.executescript(EXTRA_SCHEMA)

def get_preferences(user_id):
 with get_conn(True) as c:
  c.execute('INSERT OR IGNORE INTO preferences(user_id) VALUES(?)',(user_id,))
  return dict(c.execute('SELECT * FROM preferences WHERE user_id=?',(user_id,)).fetchone())

def save_preferences(user_id, **values):
 allowed={'nickname','avatar','lang','currency','sound'}
 if not values or not set(values)<=allowed: raise ValueError('invalid_preferences')
 if 'nickname' in values and (not isinstance(values['nickname'],str) or len(values['nickname'])>32): raise ValueError('invalid_nickname')
 if 'avatar' in values and values['avatar'] not in ('♠','♦','♣','♥','★','⚡','👑','🎲'): raise ValueError('invalid_avatar')
 if 'lang' in values and values['lang'] not in ('ru','uz','en'): raise ValueError('invalid_language')
 if 'currency' in values and values['currency'] not in ('UZS','USD','EUR','RUB'): raise ValueError('invalid_currency')
 if 'sound' in values and values['sound'] not in (0,1): raise ValueError('invalid_sound')
 with get_conn(True) as c:
  c.execute('INSERT OR IGNORE INTO preferences(user_id) VALUES(?)',(user_id,))
  c.execute('UPDATE preferences SET '+','.join(k+'=?' for k in values)+' WHERE user_id=?',(*values.values(),user_id))
 return get_preferences(user_id)

def get_history(user_id,limit=50):
 with get_conn() as c:
  rows=c.execute('''SELECT b.id,b.game,b.stake,b.payout,b.ts,COALESCE(p.hidden,0) hidden,COALESCE(p.pinned,0) pinned FROM bets b LEFT JOIN bet_preferences p ON p.bet_id=b.id AND p.user_id=b.user_id WHERE b.user_id=? ORDER BY pinned DESC,b.id DESC LIMIT ?''',(user_id,limit)).fetchall()
  return [dict(r) for r in rows]

def modify_history(user_id,bet_id,action):
 if action not in ('hide','show','pin','unpin'): raise ValueError('invalid_action')
 col='hidden' if action in ('hide','show') else 'pinned'
 val=int(action in ('hide','pin'))
 with get_conn(True) as c:
  if not c.execute('SELECT 1 FROM bets WHERE id=? AND user_id=?',(bet_id,user_id)).fetchone(): raise ValueError('not_found')
  c.execute('INSERT OR IGNORE INTO bet_preferences(user_id,bet_id) VALUES(?,?)',(user_id,bet_id))
  c.execute(f'UPDATE bet_preferences SET {col}=? WHERE user_id=? AND bet_id=?',(val,user_id,bet_id))
 return True

def create_credit_request(user_id,amount):
 if isinstance(amount,bool) or not isinstance(amount,int) or not 3000<=amount<=10_000_000: raise ValueError('invalid_amount')
 with get_conn(True) as c:
  if c.execute("SELECT 1 FROM credit_requests WHERE user_id=? AND status='pending'",(user_id,)).fetchone(): raise ValueError('pending_request_exists')
  cur=c.execute('INSERT INTO credit_requests(user_id,amount,created_ts) VALUES(?,?,?)',(user_id,amount,int(time.time())))
  return cur.lastrowid

def decide_credit_request(request_id,approve):
 with get_conn(True) as c:
  r=c.execute('SELECT * FROM credit_requests WHERE id=?',(request_id,)).fetchone()
  if not r or r['status']!='pending': raise ValueError('request_not_pending')
  status='approved' if approve else 'rejected'
  c.execute('UPDATE credit_requests SET status=?,decided_ts=? WHERE id=? AND status=?',(status,int(time.time()),request_id,'pending'))
  balance=None
  if approve:
   c.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(r['amount'],r['user_id']))
   c.execute('INSERT INTO ledger(user_id,delta,kind,reference,created_ts) VALUES(?,?,?,?,?)',(r['user_id'],r['amount'],'manual_credit',str(request_id),int(time.time())))
   balance=c.execute('SELECT balance FROM users WHERE user_id=?',(r['user_id'],)).fetchone()['balance']
  return {'id':request_id,'user_id':r['user_id'],'amount':r['amount'],'status':status,'balance':balance}

def credit_requests(limit=20):
 with get_conn() as c: return [dict(r) for r in c.execute('SELECT r.*,u.username FROM credit_requests r JOIN users u USING(user_id) ORDER BY r.id DESC LIMIT ?',(limit,)).fetchall()]

def log_support(user_id,sender,text='',file_id=None):
 if not text and not file_id: raise ValueError('empty_message')
 if len(text or '')>3000: raise ValueError('message_too_long')
 with get_conn(True) as c: c.execute('INSERT INTO support_messages(user_id,sender,text,file_id,created_ts) VALUES(?,?,?,?,?)',(user_id,sender,text,file_id,int(time.time())))

def support_history(user_id,limit=50):
 with get_conn() as c: return [dict(r) for r in c.execute('SELECT * FROM support_messages WHERE user_id=? ORDER BY id DESC LIMIT ?',(user_id,limit)).fetchall()][::-1]

def admin_stats():
 with get_conn() as c: return {'users':c.execute('SELECT COUNT(*) FROM users').fetchone()[0],'bets':c.execute('SELECT COUNT(*) FROM bets').fetchone()[0],'pending':c.execute("SELECT COUNT(*) FROM credit_requests WHERE status='pending'").fetchone()[0]}

def credit_events(user_id,limit=10):
 with get_conn() as c:
  return [dict(r) for r in c.execute('SELECT id,delta,kind,created_ts FROM ledger WHERE user_id=? AND kind=? ORDER BY id DESC LIMIT ?',(user_id,'manual_credit',limit)).fetchall()]

def club_status(user_id):
 with get_conn() as c:
  row=c.execute('SELECT total_wagered FROM users WHERE user_id=?',(user_id,)).fetchone()
  wagered=row['total_wagered'] if row else 0
  level=('Gold' if wagered>=10_000_000 else 'Silver' if wagered>=2_000_000 else 'Bronze')
  # UTC week, leaderboard based on volume; no external rewards are granted.
  from datetime import datetime, timezone, timedelta
  current=datetime.now(timezone.utc)
  week_start=int((current-timedelta(days=current.weekday(),hours=current.hour,minutes=current.minute,seconds=current.second,microseconds=current.microsecond)).timestamp())
  rows=c.execute('''SELECT b.user_id,u.username,SUM(b.stake) AS points FROM bets b JOIN users u USING(user_id) WHERE b.ts>=? GROUP BY b.user_id ORDER BY points DESC LIMIT 20''',(week_start,)).fetchall()
  return {'level':level,'wagered':wagered,'weekly':[dict(r) for r in rows],'week_start_ts':week_start}
