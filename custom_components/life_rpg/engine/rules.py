"""The numbers behind the game: tuning constants, formulas (XP, levels, ranks, badges, chests, clocks), the
shape of a new save file, and small helpers. Everything here is pure, with no state: the Game class in game.py
applies it to one adventurer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
import re
from typing import Any

from . import content as C, loot as LT


@dataclass(frozen=True)
class Quest:
    """A daily quest fed by one health sensor."""

    attr: str
    overachieve: bool
    record: bool


QUESTS = {
    "steps": Quest("stamina", True, True),
    "floors": Quest("strength", True, True),
    "sleep": Quest("vitality", False, False),
    "hydration": Quest("intelligence", False, False),
    "bedtime": Quest("wisdom", False, False),
}

# --- tuning -------------------------------------------------------------------------------
QUEST_XP, CLEAR_BONUS = 60, 40
OVER_XP, OVER_CAP = 25, 0.5
PERFECT_BONUS = 20
STREAK_STEP, STREAK_CAP = 0.05, 10
SHIELD_EVERY, SHIELD_MAX = 7, 2
RECORD_BONUS, RECORD_AFTER = 50, 7
LEVEL_BASE, LEVEL_EXP = 150, 2.2
ATTR_BASE, ATTR_XP = 10, 50
GUARD_FLOOR, GUARD_PACE, GUARD_REWARD = 50, 1.0, 0.25  # HP = your recent daily pace x the days left
ELITE_HP, CURSED_HP, PITY = 1.15, 1.05, 0.85  # a guardian that survives a week returns wounded
BEDTIME_WINDOW = 60
JOB_XP_STEP, JOB_PASSIVE_CAP = 150, 50
HIDDEN_XP = 250
CHOICE_FROM, CHOICE_UNTIL = 6, 14
LOG_MAX, HIST_MAX, CHEST_MAX, BESTIARY_MAX = 100, 40, 50, 400
MILESTONES = (3, 7, 14, 21, 30, 50, 75, 100, 150, 200, 250, 300, 365, 500, 730, 1000, 1500, 2000)

EVENT_TYPES = [
    "level_up",
    "rank_up",
    "quest_complete",
    "day_cleared",
    "perfect_day",
    "streak_milestone",
    "personal_record",
    "attribute_up",
    "skill_up",
    "job_change",
    "job_level",
    "race_evolved",
    "title_earned",
    "badge_earned",
    "hidden_quest",
    "emergency_quest",
    "emergency_cleared",
    "emergency_failed",
    "penalty_quest",
    "penalty_cleared",
    "streak_broken",
    "shield_earned",
    "shield_used",
    "guardian_appeared",
    "guardian_defeated",
    "chest_dropped",
    "devotion_up",
    "choice_offered",
    "choice_won",
    "choice_lost",
    "bargain_struck",
    "emergency_declined",
    "goddess_gift",
    "bounty_claimed",
    "bounty_done",
    "market_restocked",
    "reading_held",
]
# Emergency quests: outside working hours, failing one costs a little gold (declining half). At work, nothing.
WORK_DEFAULT = {"start": 9 * 60, "end": 17 * 60, "days": [0, 1, 2, 3, 4], "penalty": True}
FINE_BASE, FINE_PER_LEVEL, FINE_MAX, FINE_SHARE = 30, 2, 200, 0.10  # at most 200 gold, never more than 10% of your gold
LATE_GRACE = timedelta(minutes=60)  # Home Assistant was away when it ended: no fine
# The goddess's gifts: rare, decided by the game (never by the LLM), at most one roll per day you talk to her.
GIFT_COOLDOWN, GIFT_MIN_DAYS = 21, 3
# The bounty board: a parent's chores (kids mode, approved by the parent) and a few small daily side quests.
BOUNTY_MAX = 30  # chores on the board at once
CHORE_XP_MAX, CHORE_GOLD_MAX = 300, 300
BOUNTY_REPEATS = ("once", "daily", "weekly")
BOUNTY_DAILY_MAX = 10  # daily side quests; past three each is worth a little less, so ten don't swamp the quests
GIFT_CONSUMABLES = {
    "elixir": 30,
    "lucky_charm": 20,
    "bane_oil": 15,
    "hourglass": 15,
    "shield_charm": 12,
    "greater_elixir": 8,
}
LORE_MAX, CHAT_MAX = 600, 16
MANUAL_LIMITS = {"hydration": (5000, 10000), "floors": (100, 500)}  # (largest single entry, daily total), mL / flights
FLOZ = 29.5735  # mL in a US fluid ounce
WATER_UNITS = {"ml": ("mL", 1.0), "floz": ("fl oz", FLOZ)}
QUEST_UNITS = {"steps": "steps", "floors": "floors", "sleep": "h", "hydration": "mL", "bedtime": ""}
# Sensor sanity: a phone (or two apps writing to Health Connect at once) can report impossible jumps.
# (fastest believable rise per minute, rise allowed in one go, daily ceiling, jump worth telling you about)
GUARD = {"steps": (260, 1500, 100_000, 1000), "floors": (4, 15, 500, 5), "hydration": (150, 1500, 10_000, 500)}
DROP_CONFIRM = timedelta(minutes=15)  # a lower reading has to stick this long before progress goes down
SLEEP_MIN_H, SLEEP_MAX_H = 0.25, 16


class GameError(Exception):
    """An action the player can't take right now."""


KEEP_WORDS = {"lune_chat", "chat"}  # words people typed are left as they are


def rename(node: Any, old: str, new: str) -> Any:
    """Copy of `node` with every `old` in its strings replaced by `new` (except chats and LLM lore)."""
    if isinstance(node, str):
        return node.replace(old, new) if old in node else node
    if isinstance(node, dict):
        return {k: (v if k in KEEP_WORDS else rename(v, old, new)) for k, v in node.items()}
    if isinstance(node, list):
        return [rename(v, old, new) for v in node]
    return node


# --- formulas -------------------------------------------------------------------------------
def quest_xp(ratio: float, overachieve: bool, over_extra: float = 0) -> int:
    """Base XP for a quest at `ratio` of its goal."""
    xp = QUEST_XP * min(max(ratio, 0.0), 1.0)
    if ratio >= 1:
        xp += CLEAR_BONUS
        if overachieve:
            xp += OVER_XP * min(ratio - 1, OVER_CAP + over_extra) / OVER_CAP
    return round(xp)


def xp_for_level(level: int) -> int:
    """Total XP needed to reach `level`."""
    return round(LEVEL_BASE * (level - 1) ** LEVEL_EXP)


def level_for(xp: float) -> int:
    """Level reached with `xp` total XP."""
    level = 1 + int((max(xp, 0) / LEVEL_BASE) ** (1 / LEVEL_EXP))
    while xp_for_level(level + 1) <= xp:
        level += 1
    while level > 1 and xp_for_level(level) > xp:
        level -= 1
    return level


def rank_for(level: int) -> tuple[str, int]:
    """Adventurer rank at `level` (E..S, then S+1, S+2, ...) and the level of the next rank."""
    if level >= C.RANKS[-1][1]:
        n = (level - C.RANKS[-1][1]) // C.RANK_STEP_AFTER_S
        return ("S" if n == 0 else f"S+{n}"), C.RANKS[-1][1] + (n + 1) * C.RANK_STEP_AFTER_S
    for i, (name, _start) in enumerate(C.RANKS):
        if level < C.RANKS[i + 1][1]:
            return name, C.RANKS[i + 1][1]
    raise AssertionError


def attr_points(xp: float) -> int:
    """Attribute score from the XP its quest has earned."""
    return ATTR_BASE + math.isqrt(int(xp // ATTR_XP))


def job_level(xp: float) -> int:
    """Job level from job XP; it never stops."""
    return 1 + math.isqrt(int(xp // JOB_XP_STEP))


def job_level_xp(level: int) -> int:
    """Job XP needed for `level`."""
    return JOB_XP_STEP * (level - 1) ** 2


def skill_grade(prof: float) -> tuple[str, int, int]:
    """(grade name, grade index, proficiency of the next grade)."""
    grades = C.SKILL_GRADES
    if prof >= grades[-1][1]:
        n = int((prof - grades[-1][1]) // C.SKILL_SAINT_STEP)
        return ("Saint" if n == 0 else f"Saint +{n}"), len(grades) - 1 + n, grades[-1][1] + (n + 1) * C.SKILL_SAINT_STEP
    for i, (name, _at) in enumerate(grades):
        if prof < grades[i + 1][1]:
            return name, i, grades[i + 1][1]
    raise AssertionError


def skill_bonus(idx: int) -> int:
    """XP bonus from a skill grade: +2% a grade, +1% per Saint step, max +20%."""
    return min(20, 2 * min(idx, 6) + max(0, idx - 6))


def badge_thresholds(base: tuple[int, ...], upto: int) -> list[int]:
    """Five named tiers, then every further star doubles the last threshold."""
    out = list(base)
    while len(out) < upto:
        out.append(out[-1] * 2)
    return out


def badge_tier(value: float, base: tuple[int, ...]) -> int:
    """How many badge tiers `value` has reached (no upper limit)."""
    tier, t = 0, list(base)
    while True:
        if tier >= len(t):
            t.append(t[-1] * 2)
        if value < t[tier]:
            return tier
        tier += 1


def badge_tier_name(tier: int) -> str | None:
    """Bronze..Diamond, then Diamond ★2, ★3, ..."""
    if tier <= 0:
        return None
    return C.BADGE_TIERS[tier - 1] if tier <= 5 else f"Diamond ★{tier - 4}"


def bedtime_ratio(start: int, target: int) -> float:
    """1.0 if asleep by the target minute-of-day, fading to 0 over the window."""
    late = (start - target + 720) % 1440 - 720
    return 1.0 if late <= 0 else max(0.0, 1 - late / BEDTIME_WINDOW)


def hhmm(minutes: float) -> str:
    """Minute-of-day as HH:MM."""
    m = int(minutes) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


CHEST_NAMES = {"choice": "bounty chest", "wager": "wager chest", "bounty": "bounty chest", "crate": "sealed crate"}


def chest_odds(kind: str) -> dict[str, int]:
    """The chance of each rarity for the one item a chest of this kind holds, in whole percent."""
    w = LT.CHESTS.get(kind, LT.CHESTS["daily"])
    total = sum(w)
    return {r: round(100 * x / total) for r, x in zip(LT.RARITIES, w) if x}


def chest_words(kind: str) -> str:
    """An honest one-line description of a chest's prize, for the offer and for the LLM."""
    odds = chest_odds(kind)
    top = sorted(odds, key=odds.get, reverse=True)[:2]
    top = sorted(top, key=LT.RARITIES.index)
    return f"a {CHEST_NAMES.get(kind, kind + ' chest')} holding one item, usually {top[0]} or {top[1]}"


def clock(minutes: float, twelve: bool) -> str:
    """Minute-of-day for people: 23:00, or 11:00 PM on a 12-hour clock."""
    m = int(minutes) % 1440
    if not twelve:
        return hhmm(m)
    h = m // 60
    return f"{(h % 12) or 12}:{m % 60:02d} {'AM' if h < 12 else 'PM'}"


_HHMM = re.compile(r"(?<![\d:T+-])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])")


def clock_text(text: str, twelve: bool) -> str:
    """Rewrite the times of day inside a sentence for a 12-hour clock ("before 17:00" -> "before 5:00 PM")."""
    return _HHMM.sub(lambda m: clock(int(m[1]) * 60 + int(m[2]), True), text) if twelve and text else text


def moon_age(day: date) -> float:
    """Days since the last new moon."""
    return (
        (datetime(day.year, day.month, day.day, 12) - datetime(2000, 1, 6, 18, 14)).total_seconds() / 86400
    ) % 29.530588


def full_moon(day: date) -> bool:
    """True within a day of a full moon."""
    return abs(moon_age(day) - 14.765) < 1.0


def new_ledger() -> dict[str, Any]:
    """Empty save file."""
    return {
        "v": 3,
        "seed": None,
        "uid": 0,
        "day": None,
        "xp": 0,
        "today": {},
        "bonus": 0,
        "sent": [],
        "inputs": {},
        "streak": 0,
        "best_streak": 0,
        "shields": 0,
        "days": 0,
        "attr_xp": {},
        "qstreak": {},
        "best": {},
        "guardian": None,
        "pace": [],
        "floor": 1,
        "level": 1,
        "rank": "E",
        "recent": [],
        "points": {},
        "job": None,
        "jobs": {},
        "job_levels": {},
        "skills": {},
        "skill_grades": {},
        "gift": {"tier": 1, "branch": None},
        "titles": [],
        "title_dates": {},
        "title": None,
        "badges": {},
        "hidden": {},
        "stats": {},
        "week": {},
        "hist": [],
        "penalty": None,
        "last_break": None,
        "emergency": None,
        "choice": None,
        "chests": [],
        "inv": [],
        "equip": {},
        "shards": 0,
        "gifts": {"last": None, "rolled": None, "log": []},
        "bestiary": [],
        "log": [],
        "devotion": 0,
        "bags": {},
        "daily_title": None,
        "look": 0,
        "gold": 0,
        "bag": {},
        "buffs": [],
        "charms": {},
        "cosmetics": {"owned": [], "active": {}},
        "shop": None,
        "phoenix_used": None,
        "lore": {},
        "lune_chat": [],
        "lune_days": [],
        "manual": {},
        "guard": {},
        "bounties": [],
        "rapport": 0.0,
        "job_start": None,
        "goddess_prefs": {},
        "merchant_prefs": {},
    }
