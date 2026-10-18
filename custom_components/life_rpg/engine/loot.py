"""Chests, gear and the effect totals that gear, titles, gifts and blessings add up to."""

from __future__ import annotations

import random
from typing import Any

RARITIES = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]
SLOTS = ["weapon", "helm", "armor", "gloves", "boots", "ring"]

# chest kind -> rarity weights (common .. mythic)
CHESTS = {
    "daily": (60, 28, 10, 1.8, 0.2, 0),
    "perfect": (35, 35, 22, 7, 1, 0),
    "level": (30, 35, 25, 8, 2, 0),
    "record": (20, 35, 30, 12, 3, 0),
    "emergency": (20, 35, 30, 12, 3, 0),
    "hidden": (0, 20, 45, 27, 7, 1),
    "rank": (0, 0, 0, 60, 35, 5),
    "choice": (25, 35, 28, 10, 2, 0),
    "wager": (0, 15, 40, 32, 11, 2),
    "blessed": (0, 10, 40, 35, 13, 2),  # a gift from the goddess
    "bounty": (25, 35, 28, 10, 2, 0),  # from the bounty board (the same as a choice's bounty chest)
    "crate": (40, 35, 18, 6, 1, 0),  # a sealed crate bought at the market
}
GUARDIAN_CHESTS = {  # by your rank when the guardian fell
    "E": (20, 40, 30, 9, 1, 0),
    "D": (10, 35, 38, 14, 3, 0),
    "C": (0, 25, 45, 23, 6, 1),
    "B": (0, 10, 45, 33, 10, 2),
    "A": (0, 0, 35, 42, 19, 4),
    "S": (0, 0, 20, 45, 28, 7),
    "S+": (0, 0, 10, 45, 35, 10),
}

BASES = {
    "weapon": ["Dagger", "Shortsword", "Spear", "Warhammer", "Staff", "Longbow"],
    "helm": ["Hood", "Circlet", "Helm", "Crown"],
    "armor": ["Tunic", "Brigandine", "Chainmail", "Robe", "Plate"],
    "gloves": ["Wraps", "Gloves", "Gauntlets", "Bracers"],
    "boots": ["Sandals", "Boots", "Greaves", "Treads"],
    "ring": ["Ring", "Band", "Signet", "Amulet"],
}
PREFIXES = [
    [
        "Worn",
        "Plain",
        "Rusty",
        "Patched",
        "Dented",
        "Second-Hand",
        "Simple",
        "Faded",
        "Crude",
        "Borrowed",
        "Scuffed",
        "Old",
    ],
    [
        "Sturdy",
        "Hunter's",
        "Polished",
        "Guild-Issue",
        "Tempered",
        "Traveller's",
        "Reliable",
        "Oiled",
        "Fine",
        "Ranger's",
        "Well-Made",
        "Balanced",
    ],
    [
        "Knight's",
        "Runed",
        "Moonsteel",
        "Silvered",
        "Duelist's",
        "Elven",
        "Dwarf-Forged",
        "Spellbound",
        "Starlit",
        "Captain's",
        "Windcut",
        "Tidewrought",
    ],
    [
        "Shadowforged",
        "Labyrinth-Born",
        "Stormwoven",
        "Dragonbone",
        "Abyssal",
        "Sunforged",
        "Phantom",
        "Warlord's",
        "Archmage's",
        "Wyrmscale",
        "Voidtouched",
        "Heartwood",
    ],
]
UNIQUES = {  # (legendary names, mythic names)
    "weapon": (
        ["Fang of the Forsaken Goddess", "Gatereaver", "Oathkeeper of the Long Road", "The Patient Edge"],
        ["Dawnblade of the First Adventurer", "Tidebreaker, Spear of the Deep Spring", "Starfall Staff"],
    ),
    "helm": (
        [
            "Diadem of Still Waters",
            "Crown of the Sleepless King",
            "Hood of the Wandering Sage",
            "Helm of the Ninth Floor",
        ],
        ["Halo of Lune", "Crown of a Thousand Mornings", "Circlet of the Clear Mind"],
    ),
    "armor": (
        ["Mantle of the Last Light", "Plate of the Unbowed", "Robe of Quiet Hours", "Coat of a Hundred Roads"],
        ["Raiment of the Endless Labyrinth", "Mail of the Forsaken Goddess", "Vestments of the Dawn"],
    ),
    "gloves": (
        [
            "Gauntlets of the Iron Ascent",
            "Wraps of the Patient Fist",
            "Gloves of the Lucky Draw",
            "Bracers of the Tide",
        ],
        ["Hands of the Abyssal Tide", "Grasp of Seven Floors", "Gauntlets of the Unbroken Streak"],
    ),
    "boots": (
        ["Sevenleague Treads", "Greaves of the Stair King", "Boots of the Early Riser", "Sandals of the Pilgrim"],
        ["Steps of the Endless Road", "Boots That Walked the World", "Treads of the Moonlit Path"],
    ),
    "ring": (
        ["Ring of the Lone Believer", "Signet of the Guild Master", "Band of Second Chances", "Amulet of the Spring"],
        ["Seal of Absolute Devotion", "Ring of the Thousandth Dawn", "Amulet of Lune's Tear"],
    ),
}
SUFFIX = {
    "xp:steps": ["of the Wanderer", "of the Long Road", "of Swift Feet", "of the Pilgrim"],
    "xp:floors": ["of the Summit", "of the Stair", "of the Mountain", "of the High Tower"],
    "xp:sleep": ["of Deep Slumber", "of the Dreamer", "of Restful Nights", "of the Hearth"],
    "xp:hydration": ["of the Spring", "of Water Magic", "of the Tide", "of the Wellspring"],
    "xp:bedtime": ["of the Quiet Night", "of the Clear Mind", "of the Moon", "of Early Candles"],
    "xp:all": ["of the Adventurer", "of Diligence", "of the Guild", "of Growth"],
    "boss": ["of Guardian Slaying", "of the Labyrinth", "of Ruin", "of the Breaker"],
    "luck": ["of Fortune", "of the Gambler", "of the Lucky Coin", "of Hidden Treasure"],
}
AFFIX_VALUES = {  # by rarity
    "quest": (2, 3, 5, 7, 10, 14),
    "xp:all": (1, 1, 2, 3, 4, 6),
    "boss": (3, 5, 7, 10, 14, 18),
    "luck": (4, 7, 10, 15, 20, 30),
}
AFFIX_COUNT = (1, 1, 1, 2, 2, 3)
SALVAGE = (1, 3, 8, 20, 50, 120)
ENHANCE_COST = (1, 2, 4, 8, 15, 30)
ENHANCE_MAX, ENHANCE_STEP = 10, 0.05
INVENTORY_MAX = 40

CAPS = {
    "xp:all": 25,
    "quest": 50,
    "boss": 120,
    "luck": 250,
    "over": 0.75,
    "shield": 4,
    "streak": 15,
    "perfect": 150,
    "record": 150,
    "emergency": 150,
    "choice": 150,
    "serenity": 1,
    "dmg": 300,
}


def roll_rarity(rng: random.Random, weights: tuple[float, ...], luck: float) -> int:
    """Pick a rarity index; luck scales up rare-and-better weights."""
    boosted = [w * (1 + luck / 100) if i >= 2 else w for i, w in enumerate(weights)]
    return rng.choices(range(len(RARITIES)), weights=boosted)[0]


def make_item(
    rng: random.Random, uid: int, rarity: int, quests: list[str], level: int, slot: str | None = None
) -> dict[str, Any]:
    """Generate a piece of gear (in `slot`, or a random one)."""
    slot = slot or rng.choice(SLOTS)
    pool = [f"xp:{q}" for q in quests] * 3 + ["xp:all", "boss", "luck"]
    keys: list[str] = []
    while len(keys) < AFFIX_COUNT[rarity]:
        key = rng.choice(pool)
        if key not in keys:
            keys.append(key)
    affixes = {k: AFFIX_VALUES["quest" if k.startswith("xp:") and k != "xp:all" else k][rarity] for k in keys}
    base = rng.choice(BASES[slot])
    if rarity >= 4:
        name = rng.choice(UNIQUES[slot][rarity - 4])
        for b in BASES[slot]:  # a unique's art follows its name when it names its type
            if b.lower() in name.lower():
                base = b
    else:
        name = f"{rng.choice(PREFIXES[rarity])} {base} {rng.choice(SUFFIX[keys[0]])}"
    return {
        "id": uid,
        "name": name,
        "slot": slot,
        "base": base,
        "rarity": RARITIES[rarity],
        "affixes": affixes,
        "enh": 0,
        "lvl": level,
    }


def item_effects(item: dict[str, Any]) -> dict[str, float]:
    """An item's affixes including enhancement."""
    mult = 1 + ENHANCE_STEP * item["enh"]
    return {k: round(v * mult, 1) for k, v in item["affixes"].items()}


def item_power(item: dict[str, Any]) -> int:
    """Gear score of one item."""
    return round((RARITIES.index(item["rarity"]) + 1) ** 2 * 10 * (1 + 0.1 * item["enh"]))


def enhance_cost(item: dict[str, Any]) -> int | None:
    """Shards to enhance once more, or None at max."""
    if item["enh"] >= ENHANCE_MAX:
        return None
    return (item["enh"] + 1) * ENHANCE_COST[RARITIES.index(item["rarity"])]


def enhance_spent(item: dict[str, Any]) -> int:
    """Shards put into an item's enhancement so far."""
    n = item["enh"]
    return ENHANCE_COST[RARITIES.index(item["rarity"])] * n * (n + 1) // 2


def salvage_value(item: dict[str, Any]) -> int:
    """Shards from salvaging: the item's own worth plus exactly the shards put into enhancing it (no more)."""
    return SALVAGE[RARITIES.index(item["rarity"])] + enhance_spent(item)


def add_effects(total: dict[str, float], effects: dict[str, float]) -> None:
    """Accumulate effects into total."""
    for k, v in effects.items():
        total[k] = total.get(k, 0) + v


def _cap_key(k: str) -> str:
    """Which cap an effect counts against (every single-quest XP bonus shares one)."""
    if k.startswith("xp:") and k != "xp:all":
        return "quest"
    return "dmg" if k.startswith("dmg:") else k


CAP_NAMES = {
    "quest": "XP for each quest",
    "xp:all": "XP from every quest",
    "boss": "guardian damage",
    "luck": "loot luck",
    "over": "goal cap",
    "shield": "streak shields",
    "streak": "streak days",
    "perfect": "perfect-day XP",
    "record": "record XP",
    "emergency": "emergency XP",
    "choice": "choice rewards",
    "dmg": "damage from each quest",
}


def cap_for(k: str) -> float | None:
    """The cap on one effect, or None."""
    return CAPS.get(_cap_key(k))


def cap_effects(total: dict[str, float]) -> dict[str, float]:
    """Apply the per-effect caps."""
    return {k: round(min(v, CAPS.get(_cap_key(k), 1000)), 2) for k, v in total.items() if v}
