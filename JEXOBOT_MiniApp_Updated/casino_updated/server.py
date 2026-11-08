import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import games

app = FastAPI(title='Demo Casino', docs_url=None, redoc_url=None)
_BOT_TOKEN = ''


def set_bot_token(token):
    global _BOT_TOKEN
    _BOT_TOKEN = token


def validate_init_data(init_data):
    if not init_data or not _BOT_TOKEN:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
        incoming_hash = parsed.pop('hash', '')
        if not incoming_hash:
            return None
        data_check = '\n'.join(f'{k}={v}' for k, v in sorted(parsed.items()))
        secret = hmac.new(b'WebAppData', _BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, incoming_hash):
            return None
        auth_ts = int(parsed.get('auth_date', '0'))
        if not 0 <= time.time() - auth_ts <= 86400:
            return None
        user = json.loads(parsed.get('user', 'null'))
        if not isinstance(user, dict) or not isinstance(user.get('id'), int):
            return None
        return user
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def auth_or_error(init_data):
    user = validate_init_data(init_data)
    if user is None:
        return None, JSONResponse(status_code=401, content={'error': 'invalid_init_data'})
    db.get_or_create_user(user['id'], user.get('username') or user.get('first_name') or 'Игрок')
    return user, None


def game_error(exc):
    return JSONResponse(status_code=400, content={'error': str(exc)})


class InitDataBody(BaseModel):
    initData: str


class StakeBody(InitDataBody):
    stake: int


class RouletteBody(StakeBody):
    bet_type: str
    bet_value: str


class DiceBody(StakeBody):
    guess: int


class MinesStartBody(StakeBody):
    mines_count: int


class MinesTileBody(InitDataBody):
    tile_index: int


@app.get('/api/me')
async def me(initData: str):
    user, err = auth_or_error(initData)
    if err: return err
    s = db.get_stats(user['id'])
    session = db.session_get(user['id'])
    if session:
        state = session['state']
        if session['game'] == 'blackjack':
            state = {'player': state['player'], 'dealer': [state['dealer'][0], '🂠']}
        elif session['game'] == 'mines':
            state = {'revealed': state['revealed'], 'mines_count': state['mines_count']}
        else:
            state = {}
        session = {'game': session['game'], 'stake': session['stake'], 'state': state}
    return {'user_id': user['id'], 'username': user.get('username') or user.get('first_name'),
            'balance': s['balance'], 'total_wagered': s['total_wagered'], 'total_won': s['total_won'],
            'active_session': session}


class PromoBody(InitDataBody):
    code: str


@app.post('/api/promo/redeem')
async def promo_redeem(body: PromoBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        return db.redeem_promo(user['id'], body.code)
    except ValueError as exc: return game_error(exc)


@app.post('/api/slots')
async def slots(body: StakeBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        def draw():
            reels, payout = games.spin_slots(body.stake)
            return {'reels': reels}, payout
        result, payout, balance = db.play_bet(user['id'], 'slots', body.stake, draw)
        return {**result, 'payout': payout, 'balance': balance}
    except ValueError as exc: return game_error(exc)


@app.post('/api/roulette')
async def roulette(body: RouletteBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        if body.bet_type not in ('color', 'number', 'parity'):
            raise ValueError('invalid_bet_type')
        if body.bet_type == 'color' and body.bet_value not in ('red', 'black', 'green'):
            raise ValueError('invalid_bet_value')
        if body.bet_type == 'parity' and body.bet_value not in ('even', 'odd'):
            raise ValueError('invalid_bet_value')
        if body.bet_type == 'number' and not (body.bet_value.isascii() and body.bet_value.isdecimal() and 0 <= int(body.bet_value) <= 36):
            raise ValueError('invalid_bet_value')
        def draw():
            n, color, payout = games.resolve_roulette_bet(body.bet_type, body.bet_value, body.stake)
            return {'number': n, 'color': color}, payout
        result, payout, balance = db.play_bet(user['id'], 'roulette', body.stake, draw)
        return {**result, 'payout': payout, 'balance': balance}
    except ValueError as exc: return game_error(exc)


@app.post('/api/dice')
async def dice(body: DiceBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        if body.guess not in range(1, 7):
            raise ValueError('invalid_guess')
        def draw():
            roll, payout = games.roll_dice(body.stake, body.guess)
            return {'result': roll}, payout
        result, payout, balance = db.play_bet(user['id'], 'dice', body.stake, draw)
        return {**result, 'payout': payout, 'balance': balance}
    except ValueError as exc: return game_error(exc)


@app.post('/api/blackjack/start')
async def blackjack_start(body: StakeBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        player, dealer = games.new_blackjack_hand()
        db.session_start(user['id'], 'blackjack', body.stake, {'player': player, 'dealer': dealer})
        return {'player': player, 'dealer_visible': dealer[0], 'player_value': games.hand_value(player), 'balance': db.get_balance(user['id'])}
    except ValueError as exc: return game_error(exc)


def bj_finish(s, stake):
    payout, outcome = games.settle_blackjack(s['player'], s['dealer'], stake)
    return s, payout, {'player': s['player'], 'dealer': s['dealer'], 'payout': payout, 'outcome': outcome, 'finished': True}


@app.post('/api/blackjack/hit')
async def blackjack_hit(body: InitDataBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        def change(s, stake):
            s['player'].append(games.draw_card())
            value = games.hand_value(s['player'])
            if value > 21: return bj_finish(s, stake)
            return s, None, {'player': s['player'], 'player_value': value, 'dealer_visible': s['dealer'][0], 'finished': False}
        return db.session_mutate(user['id'], 'blackjack', change)
    except ValueError as exc: return game_error(exc)


@app.post('/api/blackjack/stand')
async def blackjack_stand(body: InitDataBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        def change(s, stake):
            s['dealer'] = games.dealer_play(s['dealer'])
            return bj_finish(s, stake)
        return db.session_mutate(user['id'], 'blackjack', change)
    except ValueError as exc: return game_error(exc)


@app.post('/api/crash/start')
async def crash_start(body: StakeBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        db.session_start(user['id'], 'crash', body.stake,
                         {'crash_point': games.generate_crash_point(), 'start_ts': time.time()})
        return {'ok': True, 'balance': db.get_balance(user['id'])}
    except ValueError as exc: return game_error(exc)


@app.get('/api/crash/status')
async def crash_status(initData: str):
    user, err = auth_or_error(initData)
    if err: return err
    try:
        def check(s, stake):
            current = games.crash_multiplier_at(time.time() - s['start_ts'])
            if current >= s['crash_point']:
                return s, 0, {'multiplier': s['crash_point'], 'crashed': True, 'crash_point': s['crash_point']}
            return s, None, {'multiplier': current, 'crashed': False}
        return db.session_mutate(user['id'], 'crash', check)
    except ValueError as exc: return game_error(exc)


@app.post('/api/crash/cashout')
async def crash_cashout(body: InitDataBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        def cash(s, stake):
            current = games.crash_multiplier_at(time.time() - s['start_ts'])
            if current >= s['crash_point']:
                return s, 0, {'busted': True, 'crash_point': s['crash_point']}
            payout = int(stake * current)
            return s, payout, {'busted': False, 'multiplier': current, 'payout': payout}
        return db.session_mutate(user['id'], 'crash', cash)
    except ValueError as exc: return game_error(exc)


@app.post('/api/mines/start')
async def mines_start(body: MinesStartBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        if body.mines_count not in range(1, 25): raise ValueError('bad_mines_count')
        db.session_start(user['id'], 'mines', body.stake,
                         {'mines_count': body.mines_count,
                          'mine_positions': sorted(games.generate_mine_positions(body.mines_count)), 'revealed': []})
        return {'ok': True, 'balance': db.get_balance(user['id'])}
    except ValueError as exc: return game_error(exc)


@app.post('/api/mines/reveal')
async def mines_reveal(body: MinesTileBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        if body.tile_index not in range(25): raise ValueError('invalid_tile')
        def change(s, stake):
            idx = body.tile_index
            if idx in s['revealed']: raise ValueError('already_revealed')
            if idx in s['mine_positions']:
                return s, 0, {'busted': True, 'mine_positions': s['mine_positions']}
            s['revealed'].append(idx)
            mult = games.mines_multiplier(len(s['revealed']), s['mines_count'])
            complete = len(s['revealed']) == 25 - s['mines_count']
            if complete:
                payout = int(stake * mult)
                return s, payout, {'busted': False, 'cleared_all': True, 'multiplier': mult, 'payout': payout}
            return s, None, {'busted': False, 'cleared_all': False, 'multiplier': mult, 'revealed_count': len(s['revealed'])}
        return db.session_mutate(user['id'], 'mines', change)
    except ValueError as exc: return game_error(exc)


@app.post('/api/mines/cashout')
async def mines_cashout(body: InitDataBody):
    user, err = auth_or_error(body.initData)
    if err: return err
    try:
        def change(s, stake):
            if not s['revealed']: raise ValueError('reveal_first')
            mult = games.mines_multiplier(len(s['revealed']), s['mines_count'])
            payout = int(stake * mult)
            return s, payout, {'payout': payout, 'multiplier': mult}
        return db.session_mutate(user['id'], 'mines', change)
    except ValueError as exc: return game_error(exc)


@app.get('/api/leaderboard')
async def leaderboard():
    return [{'username': row['username'], 'balance': row['balance']} for row in db.get_leaderboard(10)]


WEBAPP_DIR = Path(__file__).parent / 'webapp'
app.mount('/static', StaticFiles(directory=WEBAPP_DIR), name='static')


@app.get('/')
async def index():
    return FileResponse(WEBAPP_DIR / 'index.html')
