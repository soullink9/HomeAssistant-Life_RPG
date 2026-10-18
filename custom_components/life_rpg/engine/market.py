"""Gold, Marrow Fennick's market, consumables, cosmetics and haggling (pure rules, no I/O).

Design: gold comes from the same moments as XP, so effort is still what pays. Prices scale with your
level so the market stays relevant for years. Potions are limited per week and their bonuses are
modest, so the shop speeds you up a little but never replaces doing the quests.
"""

from __future__ import annotations

import random
from typing import Any

from . import loot as LT

# --- income -------------------------------------------------------------------------------------
GOLD_FOR = {  # event type -> gold (int, or a function of the event)
    "quest_complete": 5,
    "day_cleared": 15,
    "perfect_day": 30,
    "personal_record": 25,
    "hidden_quest": 100,
    "emergency_cleared": 40,
    "choice_won": 30,
    "penalty_cleared": 20,
    "title_earned": 25,
    "badge_earned": 25,
    "rank_up": 250,
    "level_up": lambda e: 10 + 2 * e["level"],
    "guardian_defeated": lambda e: (60 + 6 * e["floor"]) * (2 if e.get("elite") or e.get("cursed") else 1),
    "streak_milestone": lambda e: min(5 * e["streak"], 1000),
    "goddess_gift": lambda e: e.get("purse", 0),
    "bounty_done": lambda e: e.get("purse", 0),
}


def gold_for(event: dict[str, Any]) -> int:
    """Gold paid for an event."""
    g = GOLD_FOR.get(event["type"], 0)
    return int(g(event) if callable(g) else g)


def level_mult(level: int) -> float:
    """Prices and sale values grow with your level."""
    return 1 + level / 25


GEAR_PRICE = (60, 150, 400, 1000, 2600, 6500)  # by rarity index
SELL_SHARE = 0.25


def gear_price(item: dict[str, Any]) -> int:
    """List price for a piece of gear."""
    return int(
        round(GEAR_PRICE[LT.RARITIES.index(item["rarity"])] * level_mult(item["lvl"]) * (1 + 0.1 * item["enh"]), -1)
    )


def sell_value(item: dict[str, Any]) -> int:
    """Gold the merchant pays for an item."""
    return max(1, round(gear_price(item) * SELL_SHARE))


# --- consumables: (name, description, base price, icon, stock weight) ------------------------------
CONSUMABLES = {
    "elixir": ("XP Elixir", "+10% XP from every quest for the rest of today.", 150, "mdi:flask", 5),
    "greater_elixir": (
        "Greater Elixir",
        "+20% XP from every quest for the rest of today.",
        400,
        "mdi:flask-round-bottom",
        2,
    ),
    "bane_oil": (
        "Guardian Bane Oil",
        "+25% damage to this week's guardian for the rest of today.",
        200,
        "mdi:water-opacity",
        4,
    ),
    "tonic_steps": ("Swiftfoot Tonic", "+25% Walk XP for the rest of today.", 110, "mdi:shoe-sneaker", 3),
    "tonic_floors": ("Climber's Draught", "+25% Climb XP for the rest of today.", 110, "mdi:stairs-up", 3),
    "tonic_sleep": ("Dreamleaf Tea", "+25% Rest XP for tonight's sleep (counted today).", 110, "mdi:tea", 3),
    "tonic_hydration": ("Wellspring Draught", "+25% Water XP for the rest of today.", 110, "mdi:cup-water", 3),
    "tonic_bedtime": ("Moonflower Tea", "+25% Lights-out XP for the rest of today.", 110, "mdi:flower", 3),
    "lucky_charm": ("Lucky Charm", "Your next chest rolls with +100% loot luck.", 250, "mdi:clover", 4),
    "crate": (
        "Sealed Crate",
        "A crate from far away. Open it like a chest: one item, usually common or uncommon.",
        180,
        "mdi:package-variant-closed",
        3,
    ),
    "reroll": ("Fate Scroll", "Swap today's offered choice for a new one.", 60, "mdi:script-text", 4),
    "hourglass": ("Sand of Hours", "Adds 20 minutes to an active emergency quest.", 120, "mdi:timer-sand", 3),
    "shield_charm": ("Ward Charm", "Gain one streak shield (up to your shield limit).", 600, "mdi:shield-half-full", 2),
    "phoenix": (
        "Phoenix Feather",
        "Restores a streak broken in the last 3 days. Once every 30 days.",
        2500,
        "mdi:feather",
        1,
    ),
}
TONICS = {f"tonic_{q}": q for q in ("steps", "floors", "sleep", "hydration", "bedtime")}  # each needs its quest
ELIXIRS = ("elixir", "greater_elixir", "bane_oil", *TONICS)  # bonuses for today, limited per week
ELIXIRS_PER_WEEK = 4
BUFFS = {
    "elixir": {"xp:all": 10},
    "greater_elixir": {"xp:all": 20},
    "bane_oil": {"boss": 25},
    **{cid: {f"xp:{q}": 25} for cid, q in TONICS.items()},
}
PHOENIX_DAYS, PHOENIX_COOLDOWN = 3, 30


def consumable_price(cid: str, level: int) -> int:
    """List price for a consumable."""
    return int(round(CONSUMABLES[cid][2] * level_mult(level), -1))


# --- cosmetics: change the painted portrait (and the panel frame) ----------------------------------
COSMETICS = {  # id -> (category, value, name, price)
    "bg_shrine": ("background", "shrine", "Backdrop: Moonlit Shrine", 500),
    "bg_forest": ("background", "forest", "Backdrop: Ancient Forest", 500),
    "bg_pass": ("background", "pass", "Backdrop: Mountain Pass", 500),
    "bg_library": ("background", "library", "Backdrop: Sunken Library", 500),
    "bg_ruins": ("background", "ruins", "Backdrop: Desert Ruins", 500),
    "bg_citadel": ("background", "citadel", "Backdrop: Frozen Citadel", 500),
    "bg_harbor": ("background", "harbor", "Backdrop: Harbour at Dusk", 500),
    "bg_tavern": ("background", "tavern", "Backdrop: Tavern Hearth", 500),
    "pose_heroic": ("pose", "heroic", "Pose: Heroic Stance", 400),
    "pose_casting": ("pose", "casting", "Pose: Spellcasting", 400),
    "pose_rest": ("pose", "rest", "Pose: At Rest", 400),
    "pose_battle": ("pose", "battle", "Pose: Battle-Ready", 400),
    "pose_triumph": ("pose", "triumph", "Pose: Triumphant", 400),
    "dye_crimson": ("dye", "crimson", "Dye: Crimson", 300),
    "dye_midnight": ("dye", "midnight", "Dye: Midnight Blue", 300),
    "dye_forest": ("dye", "forest", "Dye: Forest Green", 300),
    "dye_ivory": ("dye", "ivory", "Dye: Ivory", 300),
    "dye_violet": ("dye", "violet", "Dye: Royal Violet", 300),
    "dye_ash": ("dye", "ash", "Dye: Ash Grey", 300),
    "frame_silver": ("frame", "silver", "Frame: Silverwork", 350),
    "frame_gold": ("frame", "gold", "Frame: Gilded", 350),
    "frame_moon": ("frame", "moon", "Frame: Moonstone", 350),
    "frame_thorn": ("frame", "thorn", "Frame: Thornwood", 350),
    "frame_dragon": ("frame", "dragon", "Frame: Dragonbone", 350),
}
COSMETIC_CATEGORIES = ("background", "pose", "dye", "frame")

# --- the shop -----------------------------------------------------------------------------------------
# New stock arrives three times a day: at midnight, around midday and in the evening (random, a few hours
# apart), each time with a theme, so it's worth looking in now and then.
STOCK_RARITY = (25, 35, 25, 11, 4, 0)
ARMOURY_RARITY = (12, 33, 33, 16, 6, 0)
FEATURED_RARITY = (0, 0, 0, 70, 27, 3)  # Sunday's featured piece
THEMES = {  # theme -> (weight, gear, consumables, cosmetics, what the cart holds)
    "general": (4, 3, 3, 2, "his usual mix of gear, potions and finery"),
    "armoury": (2, 5, 1, 0, "a cart of arms and armour"),
    "alchemy": (2, 1, 5, 0, "bubbling potions, tonics and charms"),
    "tailor": (1, 2, 1, 4, "dyes, frames, backdrops and poses"),
    "curios": (2, 2, 4, 1, "odd curios and sealed crates from far away"),
}
RESTOCK_WINDOWS = ((10 * 60, 13 * 60 + 30), (16 * 60 + 30, 20 * 60))  # minute of day: midday and evening deliveries
MOODS = (("generous", 1), ("fair", 2), ("stubborn", 1))


def restock_times(rng: random.Random) -> list[int]:
    """Minutes of the day when the next two deliveries arrive (at least three hours apart)."""
    first = rng.randint(*RESTOCK_WINDOWS[0])
    second = rng.randint(max(RESTOCK_WINDOWS[1][0], first + 180), RESTOCK_WINDOWS[1][1])
    return [first, second]


def pick_theme(rng: random.Random, wave: int, owned: list[str]) -> str:
    """What this delivery is about. The first of the day is usually his general mix."""
    if wave == 0 and rng.random() < 0.6:
        return "general"
    themes = [t for t in THEMES if t != "tailor" or len(owned) < len(COSMETICS) - 3]
    return rng.choices(themes, weights=[THEMES[t][0] for t in themes])[0]


def make_stock(
    rng: random.Random,
    uid: int,
    level: int,
    quests: list[str],
    sunday: bool,
    owned: list[str],
    theme: str = "general",
    rapport: float = 0.0,
) -> tuple[list[dict[str, Any]], int]:
    """One delivery's stock. Returns (stock, next uid)."""
    _, n_gear, n_cons, n_cos, _ = THEMES.get(theme, THEMES["general"])
    stock: list[dict[str, Any]] = []

    def entry(kind: str, price: int, **data: Any) -> dict[str, Any]:
        """One line of stock, with a secret floor price the merchant won't go below."""
        nonlocal uid
        uid += 1
        return {
            "id": uid,
            "kind": kind,
            "list": price,
            "price": price,
            "floor": round(price * (1 - room(rng, rapport))),
            "rounds": 0,
            "deal": False,
            "closed": False,
            "sold": False,
            **data,
        }

    slots = [rng.choice(LT.SLOTS) for _ in range(n_gear)] if n_gear > len(LT.SLOTS) else rng.sample(LT.SLOTS, n_gear)
    for slot in slots + (["featured"] if sunday else []):
        weights = FEATURED_RARITY if slot == "featured" else ARMOURY_RARITY if theme == "armoury" else STOCK_RARITY
        rarity = rng.choices(range(len(LT.RARITIES)), weights=weights)[0]
        uid += 1
        item = LT.make_item(rng, uid, rarity, quests, level, slot=None if slot == "featured" else slot)
        stock.append(entry("gear", gear_price(item), item=item, featured=slot == "featured"))
    pool = [
        c for c in CONSUMABLES if (c != "phoenix" or rng.random() < 0.15) and (c not in TONICS or TONICS[c] in quests)
    ]
    weights = [
        CONSUMABLES[c][4] * (3 if theme == "curios" and c in ("crate", "lucky_charm", "reroll") else 1) for c in pool
    ]
    for cid in _weighted_sample(rng, pool, weights, n_cons):
        stock.append(entry("consumable", consumable_price(cid, level), cid=cid))
    left = [c for c in COSMETICS if c not in owned]
    for cid in rng.sample(left, min(n_cos, len(left))):
        stock.append(entry("cosmetic", COSMETICS[cid][3], cid=cid))
    return stock, uid


def _weighted_sample(rng: random.Random, items: list[str], weights: list[int], k: int) -> list[str]:
    """Pick up to k different items, each with its own weight."""
    items, weights, out = list(items), list(weights), []
    while items and len(out) < k:
        i = rng.choices(range(len(items)), weights=weights)[0]
        out.append(items.pop(i))
        weights.pop(i)
    return out


# --- haggling ------------------------------------------------------------------------------------------
# Marrow enjoys a haggle; what he hates is being taken for a fool. Every item has a hidden lowest price
# (8-22% under list, more when you're on good terms). Offers near it get real back-and-forth: he comes down
# a little each round and meets you partway. Lowballs and insults annoy him; annoyance fades over an hour
# or two. If you push him too far he stops haggling until the next delivery (prices don't go up), and
# he remembers: rapport (-5..+5) carries over and widens or narrows the room he gives you.
ROOM_BASE, ROOM_SPREAD, ROOM_RAPPORT, ROOM_MAX = 0.08, 0.10, 0.012, 0.30
HAGGLE_ROUNDS = 6  # counter-offers per item before his final word
ANNOY_MAX, ANNOY_DECAY = 10.0, 3.0  # annoyance that ends haggling; how much fades per hour
INSULT_BELOW, LOWBALL_BELOW = 0.5, 0.85  # share of list; share of his lowest price
INSULT_BUMP = 0.04  # an insult puts that item's price up a little (never past list + 10%)
RAPPORT_MAX = 5.0
# share of the gap he gives up each round
MOOD_GIVE = {"generous": 0.55, "fair": 0.42, "stubborn": 0.3, "offended": 0.25}
MOOD_ROOM = {"generous": 0.04, "fair": 0.0, "stubborn": -0.03, "offended": -0.04}
CALLBACK = {"generous": 0.6, "fair": 0.45, "stubborn": 0.3, "offended": 0.2}  # chance he calls you back when you walk


def room(rng: random.Random, rapport: float) -> float:
    """How far under list his lowest price is, for one item."""
    return min(ROOM_MAX, max(0.02, ROOM_BASE + rng.random() * ROOM_SPREAD + rapport * ROOM_RAPPORT))


def new_mood(rng: random.Random, rapport: float) -> str:
    """The mood he arrives in (good rapport makes a generous mood likelier, bad a stubborn one)."""
    w = [max(0.2, 1 + rapport * 0.2), 2, max(0.2, 1 - rapport * 0.2)]
    return rng.choices([m for m, _ in MOODS], weights=w)[0]


def cool(shop: dict[str, Any], now_ts: float) -> None:
    """Annoyance fades with time; once it has mostly faded he'll haggle again."""
    last = shop.get("calm_at")
    if last is not None and now_ts > last:
        shop["annoyance"] = round(max(0.0, shop.get("annoyance", 0.0) - (now_ts - last) / 3600 * ANNOY_DECAY), 2)
        if shop.get("fed_up") and shop["annoyance"] < ANNOY_MAX * 0.4:
            shop["fed_up"] = False
    shop["calm_at"] = now_ts


def temper(shop: dict[str, Any]) -> str:
    """How the merchant is taking your haggling right now."""
    if shop.get("fed_up"):
        return "fed_up"
    a = shop.get("annoyance", 0.0) / ANNOY_MAX
    return "calm" if a < 0.3 else "impatient" if a < 0.6 else "fuming"


def _annoy(shop: dict[str, Any], amount: float) -> None:
    """Change the merchant's annoyance, kept between zero and the limit."""
    shop["annoyance"] = round(min(ANNOY_MAX, max(0.0, shop.get("annoyance", 0.0) + amount)), 2)


def haggle(
    entry: dict[str, Any],
    offer: int,
    bonus: float = 0.0,
    shop: dict[str, Any] | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Make an offer on one item. Results:
    accepted   - a deal at the returned price (press Buy to take it home)
    countered  - he comes down to the returned price
    holding    - a lowball: he barely moves
    insulted   - under half the list price: that item costs a little more now
    refused    - insulted twice over the same item: no more haggling on it until the next delivery
    final      - his last word on this item (you can still buy at it)
    fed_up     - he's had enough: no haggling at all until the next delivery
    closed     - nothing to haggle (sold, a deal already, or he's fed up)
    `bonus` (0..0.15, Bards) lowers his lowest price by that share of the list."""
    shop = shop if shop is not None else {}
    rng = rng or random.Random()
    if shop.get("fed_up") or entry["sold"] or entry["deal"] or entry["closed"]:
        return {"result": "closed", "price": entry["price"]}
    lst, ask = entry["list"], entry["price"]
    floor = max(round(lst * (1 - ROOM_MAX - bonus)), round(entry["floor"] - lst * bonus))
    last = entry.get("last_offer")
    rising = last is None or offer > last
    entry["last_offer"] = int(offer)
    mood = shop.get("mood", "fair")
    temper_left = 1 - shop.get("annoyance", 0.0) / ANNOY_MAX  # an annoyed merchant gives less ground

    if offer >= ask:
        entry["deal"] = True
        return {"result": "accepted", "price": ask}
    if offer < lst * INSULT_BELOW:  # taking him for a fool
        _annoy(shop, 3.0)
        shop["insults"] = shop.get("insults", 0) + 1
        entry["insults"] = entry.get("insults", 0) + 1
        if entry["insults"] >= 2:
            entry.update(closed=True, why="refused")
            result = "refused"
        else:
            entry["price"] = min(round(lst * 1.1), round(ask * (1 + INSULT_BUMP)))
            result = "insulted"
        return _check_fed_up(shop, entry, result)
    entry["rounds"] += 1
    if offer >= floor:  # a fair offer: real back-and-forth
        _annoy(shop, -0.3 if rising else 0.2)
        gap = ask - offer
        near = gap <= max(2, lst * 0.025)
        tired = entry["rounds"] >= HAGGLE_ROUNDS or rng.random() < 0.12 * entry["rounds"] * temper_left
        if near or tired:
            entry.update(price=int(offer), deal=True)
            return {"result": "accepted", "price": int(offer)}
        give = MOOD_GIVE.get(mood, 0.42) * temper_left * rng.uniform(0.8, 1.2)
        entry["price"] = max(int(offer), round(ask - gap * give))
        if entry["price"] - offer <= max(2, lst * 0.025):
            entry.update(price=int(offer), deal=True)
            return {"result": "accepted", "price": int(offer)}
        return {"result": "countered", "price": entry["price"]}
    if offer >= floor * LOWBALL_BELOW:  # a little under what he can do: he gives a little
        _annoy(shop, 0.15 if rising else 0.6)
        give = MOOD_GIVE.get(mood, 0.42) * 0.45 * temper_left * rng.uniform(0.8, 1.2)
        entry["price"] = max(floor, round(ask - (ask - floor) * give))
        result = "countered"
    else:  # a lowball: he holds firm
        _annoy(shop, (1.0 if rising else 1.8) + (floor * LOWBALL_BELOW - offer) / lst * 6)
        entry["price"] = max(floor, round(ask - (ask - floor) * 0.05))
        result = "holding"
    if entry["rounds"] >= HAGGLE_ROUNDS:
        entry["price"] = max(floor, entry["price"])
        entry.update(closed=True, why="final")
        result = "final"
    return _check_fed_up(shop, entry, result)


def _check_fed_up(shop: dict[str, Any], entry: dict[str, Any], result: str) -> dict[str, Any]:
    """End the haggle if he's had enough of you today; otherwise return the result as it stands."""
    if shop.get("annoyance", 0.0) >= ANNOY_MAX:
        shop["fed_up"] = True
        return {"result": "fed_up", "price": entry["price"]}
    return {"result": result, "price": entry["price"]}


def walk_away(
    entry: dict[str, Any], shop: dict[str, Any], rapport: float, rng: random.Random, bonus: float = 0.0
) -> dict[str, Any]:
    """You turn to leave mid-haggle. Sometimes he calls you back with a better price (once per item)."""
    lst, ask = entry["list"], entry["price"]
    floor = max(round(lst * (1 - ROOM_MAX - bonus)), round(entry["floor"] - lst * bonus))
    if (
        entry["sold"]
        or entry["deal"]
        or entry.get("walked")
        or not entry["rounds"]
        or shop.get("fed_up")
        or ask <= floor * 1.02
        or entry.get("insults")
    ):
        return {"result": "walked", "price": ask}
    entry["walked"] = True
    chance = (
        CALLBACK.get(shop.get("mood", "fair"), 0.45) - shop.get("annoyance", 0.0) / ANNOY_MAX * 0.3 + rapport * 0.03
    )
    if rng.random() < chance:
        entry["price"] = max(floor, round(floor + (ask - floor) * rng.uniform(0.15, 0.45)))
        entry.update(closed=True, why="parting")  # his parting offer: take it or leave it
        _annoy(shop, -1.0)
        return {"result": "called_back", "price": entry["price"]}
    return {"result": "walked", "price": ask}


def face(result: str | None, shop: dict[str, Any]) -> str:
    """Which painting of Marrow fits right now: how the last offer went, then how annoyed he still is."""
    t = temper(shop)
    if t == "fed_up":
        return "furious"
    by_result = {
        "accepted": "generous",
        "called_back": "generous",
        "countered": "fair",
        "final": "stubborn",
        "holding": "stubborn",
        "insulted": "angry",
        "refused": "angry",
        "walked": "stubborn",
    }.get(result or "")
    if t == "fuming":
        return "angry" if by_result != "generous" else "annoyed"
    if t == "impatient" and by_result in (None, "fair", "stubborn"):
        return "annoyed"
    return by_result or shop.get("mood", "fair")
