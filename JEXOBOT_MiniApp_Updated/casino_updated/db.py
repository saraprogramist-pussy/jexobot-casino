import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.getenv('DB_PATH', str(Path(__file__).with_name('casino.db')))
STARTING_BALANCE = 100_000
MAX_STAKE = 1_000_000_000

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
  return conn.execute('SELECT balance FROM users WHERE user_id=?',(user_id,)).fetchone()['balance']

def _debit(conn,user_id,stake):
 if isinstance(stake,bool) or not isinstance(stake,int) or not 1<=stake<=MAX_STAKE: raise ValueError('invalid_stake')
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
