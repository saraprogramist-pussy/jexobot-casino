import sqlite3
import time
from contextlib import contextmanager

DB_PATH = "casino.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance INTEGER NOT NULL DEFAULT 1000,
    last_bonus_ts INTEGER NOT NULL DEFAULT 0,
    total_wagered INTEGER NOT NULL DEFAULT 0,
    total_won INTEGER NOT NULL DEFAULT 0,
    created_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    game TEXT NOT NULL,
    stake INTEGER NOT NULL,
    payout INTEGER NOT NULL,
    ts INTEGER NOT NULL
);
"""

STARTING_BALANCE = 100000
DAILY_BONUS = 50000
BONUS_COOLDOWN_SEC = 24 * 3600


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def get_or_create_user(user_id: int, username: str) -> sqlite3.Row:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, username, balance, created_ts) VALUES (?, ?, ?, ?)",
                (user_id, username, STARTING_BALANCE, int(time.time())),
            )
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        else:
            # keep username fresh
            conn.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        return row


def get_balance(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["balance"] if row else 0


def adjust_balance(user_id: int, delta: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))


def record_bet(user_id: int, game: str, stake: int, payout: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO bets (user_id, game, stake, payout, ts) VALUES (?, ?, ?, ?, ?)",
            (user_id, game, stake, payout, int(time.time())),
        )
        conn.execute(
            "UPDATE users SET total_wagered = total_wagered + ?, total_won = total_won + ? WHERE user_id = ?",
            (stake, payout, user_id),
        )


def try_claim_daily_bonus(user_id: int):
    """Returns (success: bool, seconds_left: int)"""
    now = int(time.time())
    with get_conn() as conn:
        row = conn.execute("SELECT last_bonus_ts FROM users WHERE user_id = ?", (user_id,)).fetchone()
        last_ts = row["last_bonus_ts"] if row else 0
        elapsed = now - last_ts
        if elapsed < BONUS_COOLDOWN_SEC:
            return False, BONUS_COOLDOWN_SEC - elapsed
        conn.execute(
            "UPDATE users SET balance = balance + ?, last_bonus_ts = ? WHERE user_id = ?",
            (DAILY_BONUS, now, user_id),
        )
        return True, 0


def get_leaderboard(limit: int = 10):
    with get_conn() as conn:
        return conn.execute(
            "SELECT username, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,)
        ).fetchall()


def get_stats(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT balance, total_wagered, total_won FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()


def find_user(identifier: str):
    """Находит игрока по числовому Telegram ID или по username (без @)."""
    identifier = identifier.lstrip("@")
    with get_conn() as conn:
        if identifier.isdigit():
            return conn.execute("SELECT * FROM users WHERE user_id = ?", (int(identifier),)).fetchone()
        return conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (identifier,)
        ).fetchone()
