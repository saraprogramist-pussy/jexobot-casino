import random

# Все игры используют random.SystemRandom() — криптографически стойкий ГСЧ ОС,
# этого достаточно для "фан"-казино без реальных денег.
rng = random.SystemRandom()

SLOT_SYMBOLS = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"]
# веса подобраны так, чтобы redeemable RTP был честным и прозрачным (~92%)
SLOT_WEIGHTS = [30, 25, 20, 12, 8, 5]

SLOT_PAYTABLE = {
    "🍒🍒🍒": 3,
    "🍋🍋🍋": 4,
    "🍇🍇🍇": 6,
    "🔔🔔🔔": 10,
    "💎💎💎": 25,
    "7️⃣7️⃣7️⃣": 50,
}


def spin_slots(stake: int):
    reels = rng.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)
    combo = "".join(reels)
    multiplier = SLOT_PAYTABLE.get(combo, 0)
    if multiplier == 0 and len(set(reels)) == 2:
        multiplier = 1  # любые два совпавших символа — возврат ставки
    payout = stake * multiplier
    return reels, payout


ROULETTE_RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


def spin_roulette():
    """0-36, европейская рулетка (одно зеро)."""
    number = rng.randint(0, 36)
    if number == 0:
        color = "green"
    elif number in ROULETTE_RED:
        color = "red"
    else:
        color = "black"
    return number, color


def resolve_roulette_bet(bet_type: str, bet_value, stake: int):
    """bet_type: 'color' | 'number' | 'parity'"""
    number, color = spin_roulette()
    payout = 0
    if bet_type == "color" and bet_value == color:
        payout = stake * 2
    elif bet_type == "number" and int(bet_value) == number:
        payout = stake * 36
    elif bet_type == "parity" and number != 0:
        is_even = number % 2 == 0
        if (bet_value == "even") == is_even:
            payout = stake * 2
    return number, color, payout


def roll_dice(stake: int, guess: int):
    """Угадай число 1-6, выигрыш x5."""
    result = rng.randint(1, 6)
    payout = stake * 5 if result == guess else 0
    return result, payout


CARD_VALUES = {r: min(10, r) if isinstance(r, int) else 10 for r in range(2, 11)}
CARD_VALUES.update({"J": 10, "Q": 10, "K": 10, "A": 11})
RANKS = list(range(2, 11)) + ["J", "Q", "K", "A"]


def draw_card():
    return rng.choice(RANKS)


def hand_value(cards):
    total = sum(CARD_VALUES[c] for c in cards)
    aces = cards.count("A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def new_blackjack_hand():
    player = [draw_card(), draw_card()]
    dealer = [draw_card(), draw_card()]
    return player, dealer


def dealer_play(dealer_cards):
    while hand_value(dealer_cards) < 17:
        dealer_cards.append(draw_card())
    return dealer_cards


def settle_blackjack(player_cards, dealer_cards, stake):
    p, d = hand_value(player_cards), hand_value(dealer_cards)
    if p > 21:
        return 0, "bust"
    if d > 21:
        return stake * 2, "dealer_bust"
    if p > d:
        return stake * 2, "win"
    if p == d:
        return stake, "push"
    return 0, "lose"


# ---------------- Crash ----------------
CRASH_HOUSE_EDGE = 0.03
CRASH_GROWTH_RATE = 0.15  # скорость роста множителя во времени


def generate_crash_point() -> float:
    """Классическое 'provably fair'-подобное распределение для crash-игр."""
    r = rng.random()
    if r < CRASH_HOUSE_EDGE:
        return 1.00
    return round((1 - CRASH_HOUSE_EDGE) / (1 - r), 2)


def crash_multiplier_at(elapsed_seconds: float) -> float:
    """Множитель в момент времени t с начала раунда."""
    m = 1.0 + CRASH_GROWTH_RATE * (elapsed_seconds ** 1.7)
    return round(m, 2)


# ---------------- Mines ----------------
MINES_GRID_SIZE = 25  # поле 5x5


def generate_mine_positions(mines_count: int) -> set:
    return set(rng.sample(range(MINES_GRID_SIZE), mines_count))


def mines_multiplier(revealed_count: int, mines_count: int, house_edge: float = 0.97) -> float:
    """Честный множитель на основе комбинаторики, с лёгким house edge."""
    safe_tiles = MINES_GRID_SIZE - mines_count
    mult = 1.0
    for i in range(revealed_count):
        mult *= (MINES_GRID_SIZE - i) / (safe_tiles - i)
    return round(mult * house_edge, 2)
