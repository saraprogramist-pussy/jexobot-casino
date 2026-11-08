import json
import time
import hashlib
import hmac
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import games

app = FastAPI()

_BOT_TOKEN = ""


def set_bot_token(token: str):
    global _BOT_TOKEN
    _BOT_TOKEN = token


# user_id -> {"player": [...], "dealer": [...], "stake": int}
blackjack_sessions: dict[int, dict] = {}

# user_id -> {"stake": int, "crash_point": float, "start_ts": float}
crash_sessions: dict[int, dict] = {}

# user_id -> {"stake": int, "mines_count": int, "mine_positions": set, "revealed": set}
mines_sessions: dict[int, dict] = {}


def validate_init_data(init_data: str):
    """Проверяет подпись Telegram WebApp initData (защита от подделки запросов).
    См. https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
    """
    if not init_data or not _BOT_TOKEN:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", _BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        return None
    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError:
        return None
    if time.time() - auth_date > 86400:  # защита от повторного использования старых запросов
        return None
    user_json = parsed.get("user")
    if not user_json:
        return None
    return json.loads(user_json)


def auth_or_error(init_data: str):
    user = validate_init_data(init_data)
    if not user:
        return None, JSONResponse(status_code=401, content={"error": "invalid_init_data"})
    db.get_or_create_user(user["id"], user.get("username") or user.get("first_name", "player"))
    return user, None


class InitDataBody(BaseModel):
    initData: str


class StakeBody(InitDataBody):
    stake: int


class RouletteBody(InitDataBody):
    stake: int
    bet_type: str
    bet_value: str


class DiceBody(InitDataBody):
    stake: int
    guess: int


@app.get("/api/me")
async def api_me(initData: str):
    user, err = auth_or_error(initData)
    if err:
        return err
    stats = db.get_stats(user["id"])
    return {"user_id": user["id"], "username": user.get("username"), "balance": stats["balance"]}


@app.post("/api/bonus")
async def api_bonus(body: InitDataBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    ok, seconds_left = db.try_claim_daily_bonus(user["id"])
    return {"success": ok, "seconds_left": seconds_left, "balance": db.get_balance(user["id"])}


def _check_stake(user_id: int, stake: int):
    bal = db.get_balance(user_id)
    if stake <= 0 or stake > bal:
        return JSONResponse(status_code=400, content={"error": "insufficient_balance"})
    return None


@app.post("/api/slots")
async def api_slots(body: StakeBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    bad = _check_stake(user["id"], body.stake)
    if bad:
        return bad
    reels, payout = games.spin_slots(body.stake)
    db.adjust_balance(user["id"], payout - body.stake)
    db.record_bet(user["id"], "slots", body.stake, payout)
    return {"reels": reels, "payout": payout, "balance": db.get_balance(user["id"])}


@app.post("/api/roulette")
async def api_roulette(body: RouletteBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    bad = _check_stake(user["id"], body.stake)
    if bad:
        return bad
    number, color, payout = games.resolve_roulette_bet(body.bet_type, body.bet_value, body.stake)
    db.adjust_balance(user["id"], payout - body.stake)
    db.record_bet(user["id"], "roulette", body.stake, payout)
    return {"number": number, "color": color, "payout": payout, "balance": db.get_balance(user["id"])}


@app.post("/api/dice")
async def api_dice(body: DiceBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    bad = _check_stake(user["id"], body.stake)
    if bad:
        return bad
    result, payout = games.roll_dice(body.stake, body.guess)
    db.adjust_balance(user["id"], payout - body.stake)
    db.record_bet(user["id"], "dice", body.stake, payout)
    return {"result": result, "payout": payout, "balance": db.get_balance(user["id"])}


@app.post("/api/blackjack/start")
async def api_bj_start(body: StakeBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    bad = _check_stake(user["id"], body.stake)
    if bad:
        return bad
    player, dealer = games.new_blackjack_hand()
    blackjack_sessions[user["id"]] = {"player": player, "dealer": dealer, "stake": body.stake}
    return {"player": player, "dealer_visible": dealer[0], "player_value": games.hand_value(player)}


@app.post("/api/blackjack/hit")
async def api_bj_hit(body: InitDataBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    s = blackjack_sessions.get(user["id"])
    if not s:
        return JSONResponse(status_code=400, content={"error": "no_session"})
    s["player"].append(games.draw_card())
    value = games.hand_value(s["player"])
    if value > 21:
        return _finish_blackjack(user["id"])
    return {"player": s["player"], "player_value": value, "dealer_visible": s["dealer"][0], "finished": False}


@app.post("/api/blackjack/stand")
async def api_bj_stand(body: InitDataBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    s = blackjack_sessions.get(user["id"])
    if not s:
        return JSONResponse(status_code=400, content={"error": "no_session"})
    s["dealer"] = games.dealer_play(s["dealer"])
    return _finish_blackjack(user["id"])


def _finish_blackjack(user_id: int):
    s = blackjack_sessions.pop(user_id)
    payout, outcome = games.settle_blackjack(s["player"], s["dealer"], s["stake"])
    db.adjust_balance(user_id, payout - s["stake"])
    db.record_bet(user_id, "blackjack", s["stake"], payout)
    return {
        "player": s["player"], "dealer": s["dealer"],
        "payout": payout, "outcome": outcome, "finished": True,
        "balance": db.get_balance(user_id),
    }


class MinesStartBody(StakeBody):
    mines_count: int


class MinesTileBody(InitDataBody):
    tile_index: int


# ---------------- Crash ----------------
@app.post("/api/crash/start")
async def api_crash_start(body: StakeBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    bad = _check_stake(user["id"], body.stake)
    if bad:
        return bad
    crash_point = games.generate_crash_point()
    crash_sessions[user["id"]] = {
        "stake": body.stake, "crash_point": crash_point, "start_ts": time.time(),
    }
    return {"ok": True}


@app.get("/api/crash/status")
async def api_crash_status(initData: str):
    user, err = auth_or_error(initData)
    if err:
        return err
    s = crash_sessions.get(user["id"])
    if not s:
        return JSONResponse(status_code=400, content={"error": "no_session"})
    elapsed = time.time() - s["start_ts"]
    current = games.crash_multiplier_at(elapsed)
    crashed = current >= s["crash_point"]
    if crashed:
        current = s["crash_point"]
    return {"multiplier": current, "crashed": crashed}


@app.post("/api/crash/cashout")
async def api_crash_cashout(body: InitDataBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    s = crash_sessions.pop(user["id"], None)
    if not s:
        return JSONResponse(status_code=400, content={"error": "no_session"})
    elapsed = time.time() - s["start_ts"]
    current = games.crash_multiplier_at(elapsed)
    if current >= s["crash_point"]:
        # опоздал — раунд уже лопнул
        db.record_bet(user["id"], "crash", s["stake"], 0)
        db.adjust_balance(user["id"], -s["stake"])
        return {"busted": True, "crash_point": s["crash_point"], "balance": db.get_balance(user["id"])}
    payout = int(s["stake"] * current)
    db.adjust_balance(user["id"], payout - s["stake"])
    db.record_bet(user["id"], "crash", s["stake"], payout)
    return {"busted": False, "multiplier": current, "payout": payout, "balance": db.get_balance(user["id"])}


# ---------------- Mines ----------------
@app.post("/api/mines/start")
async def api_mines_start(body: MinesStartBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    if body.mines_count < 1 or body.mines_count > 24:
        return JSONResponse(status_code=400, content={"error": "bad_mines_count"})
    bad = _check_stake(user["id"], body.stake)
    if bad:
        return bad
    mines_sessions[user["id"]] = {
        "stake": body.stake, "mines_count": body.mines_count,
        "mine_positions": games.generate_mine_positions(body.mines_count),
        "revealed": set(),
    }
    return {"ok": True}


@app.post("/api/mines/reveal")
async def api_mines_reveal(body: MinesTileBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    s = mines_sessions.get(user["id"])
    if not s:
        return JSONResponse(status_code=400, content={"error": "no_session"})
    idx = body.tile_index
    if idx in s["revealed"]:
        return JSONResponse(status_code=400, content={"error": "already_revealed"})
    if idx in s["mine_positions"]:
        mine_positions = list(s["mine_positions"])
        mines_sessions.pop(user["id"])
        db.adjust_balance(user["id"], -s["stake"])
        db.record_bet(user["id"], "mines", s["stake"], 0)
        return {"busted": True, "mine_positions": mine_positions, "balance": db.get_balance(user["id"])}
    s["revealed"].add(idx)
    multiplier = games.mines_multiplier(len(s["revealed"]), s["mines_count"])
    max_safe = games.MINES_GRID_SIZE - s["mines_count"]
    cleared_all = len(s["revealed"]) == max_safe
    if cleared_all:
        payout = int(s["stake"] * multiplier)
        mines_sessions.pop(user["id"])
        db.adjust_balance(user["id"], payout - s["stake"])
        db.record_bet(user["id"], "mines", s["stake"], payout)
        return {
            "busted": False, "cleared_all": True, "multiplier": multiplier,
            "payout": payout, "balance": db.get_balance(user["id"]),
        }
    return {"busted": False, "cleared_all": False, "multiplier": multiplier, "revealed_count": len(s["revealed"])}


@app.post("/api/mines/cashout")
async def api_mines_cashout(body: InitDataBody):
    user, err = auth_or_error(body.initData)
    if err:
        return err
    s = mines_sessions.pop(user["id"], None)
    if not s:
        return JSONResponse(status_code=400, content={"error": "no_session"})
    multiplier = games.mines_multiplier(len(s["revealed"]), s["mines_count"])
    payout = int(s["stake"] * multiplier)
    db.adjust_balance(user["id"], payout - s["stake"])
    db.record_bet(user["id"], "mines", s["stake"], payout)
    return {"payout": payout, "multiplier": multiplier, "balance": db.get_balance(user["id"])}


@app.get("/api/leaderboard")
async def api_leaderboard():
    rows = db.get_leaderboard(10)
    return [{"username": r["username"], "balance": r["balance"]} for r in rows]


WEBAPP_DIR = Path(__file__).parent / "webapp"
app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(WEBAPP_DIR / "index.html")
