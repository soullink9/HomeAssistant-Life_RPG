"""Life RPG engine: one adventurer's whole game, as pure Python over a JSON save file.

Daily loop: health sensors are quests -> quest XP (boosted by racial gift, job, skills, gear,
title, the floor's trait, the goddess's blessings and today's choice) -> clear the day for
the streak multiplier -> damage this week's labyrinth guardian -> level, rank, attributes.
Everything numeric is open-ended: level, rank (S+n), job levels, skill proficiency,
labyrinth floor, badge stars, devotion.

The Game class is split across a few files so each stays readable:
    game.py        the day loop, scoring, progression, labyrinth, choices, emergencies and the view
    shop.py        the market (ShopMixin)
    board.py       the bounty board (BountyMixin)
    inputs.py      sensors, corrections and hand logging (InputsMixin)
    characters.py  portrait choices, the LLM's words and the goddess's gifts (CharactersMixin)
    rules.py       constants and formulas shared by all of them
Content (names, lines, numbers) lives in content.py, loot in loot.py, market rules in market.py and
everything about looks and painting prompts in appearance.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import math
import random
from typing import Any

from . import appearance as A, content as C, loot as LT, market as M
from .board import BountyMixin
from .characters import CharactersMixin
from .inputs import InputsMixin
from .rules import (  # noqa: F401 - re-exported for tests and other modules
    ATTR_BASE,
    ATTR_XP,
    BESTIARY_MAX,
    BOUNTY_DAILY_MAX,
    BOUNTY_MAX,
    CHAT_MAX,
    CHEST_MAX,
    CHEST_NAMES,
    CHOICE_FROM,
    CHOICE_UNTIL,
    CHORE_GOLD_MAX,
    CHORE_XP_MAX,
    CURSED_HP,
    ELITE_HP,
    FINE_BASE,
    FINE_MAX,
    FINE_PER_LEVEL,
    FINE_SHARE,
    FLOZ,
    GIFT_COOLDOWN,
    GUARD,
    GUARD_FLOOR,
    GUARD_PACE,
    GUARD_REWARD,
    HIDDEN_XP,
    HIST_MAX,
    JOB_PASSIVE_CAP,
    LATE_GRACE,
    LOG_MAX,
    LORE_MAX,
    MANUAL_LIMITS,
    MILESTONES,
    PERFECT_BONUS,
    PITY,
    QUEST_UNITS,
    QUESTS,
    RECORD_AFTER,
    RECORD_BONUS,
    SHIELD_EVERY,
    SHIELD_MAX,
    SLEEP_MAX_H,
    STREAK_CAP,
    STREAK_STEP,
    WATER_UNITS,
    WORK_DEFAULT,
    GameError,
    attr_points,
    badge_thresholds,
    badge_tier,
    badge_tier_name,
    bedtime_ratio,
    chest_odds,
    chest_words,
    clock,
    clock_text,
    hhmm,
    job_level,
    job_level_xp,
    level_for,
    moon_age,
    new_ledger,
    quest_xp,
    rank_for,
    rename,
    skill_bonus,
    skill_grade,
    xp_for_level,
)
from .shop import ShopMixin


class Game(ShopMixin, BountyMixin, InputsMixin, CharactersMixin):
    """Applies the rules to one adventurer's ledger."""

    def __init__(
        self,
        goals: dict[str, float],
        race: str = "human",
        ledger: dict | None = None,
        seed: str | None = None,
        body: str = "androgynous",
        goddess: str | None = None,
        work: dict[str, Any] | None = None,
        water_unit: str = "ml",
        twelve_hour: bool = False,
        corrections: set[str] | frozenset[str] = frozenset(),
        kids_mode: bool = False,
        daily_bounties: int = 5,
    ) -> None:
        """`goals` maps active quests to goals (bedtime: minute of day). `work`: working hours
        {start, end (minutes), days (0 = Monday), penalty (bool)} for emergency-quest fines."""
        self.goals = goals
        self.work = {**WORK_DEFAULT, **{k: v for k, v in (work or {}).items() if v is not None}}
        self.at_work: bool | None = None  # set from a Home Assistant entity; None = go by the hours
        self.water_unit = water_unit if water_unit in WATER_UNITS else "ml"
        self.twelve = bool(twelve_hour)  # show times of day as 5:00 PM instead of 17:00
        self.kids_mode = bool(kids_mode)  # chores from a parent, which the parent approves
        self.daily_bounties = max(0, min(int(daily_bounties), BOUNTY_DAILY_MAX))  # small side quests each day
        # quests whose counts may be corrected by hand (off = no cheating)
        self.corrections = set(corrections) & set(GUARD)
        self.goddess = " ".join(str(goddess or C.GODDESS).split())[:30] or C.GODDESS
        self.body = body if body in A.BODIES else "androgynous"
        self.race = race if race in C.RACES else "human"
        self.L = new_ledger() | (ledger or {})  # keys added to the game later start at their defaults
        self.L["seed"] = self.L["seed"] or seed or f"{random.getrandbits(64):016x}"
        known = {t[0] for t in C.TITLES}  # a title no longer in the game simply drops away
        self.L["titles"] = [t for t in self.L["titles"] if t in known]
        if self.L["title"] not in self.L["titles"]:
            self.L["title"] = self.L["titles"][0] if self.L["titles"] else None
        self.now = datetime.now()
        self.events: list[dict[str, Any]] = []
        self._goddess_pool = "default"

    # --- plumbing ------------------------------------------------------------------------------
    def _rng(self, purpose: str) -> random.Random:
        """A fresh random generator for one purpose, reproducible from the save's seed and counter."""
        self.L["uid"] += 1
        return random.Random(f"{self.L['seed']}:{self.L['uid']}:{purpose}")

    def _draw(self, pool: str, items: list, rng: random.Random | None = None) -> Any:
        """Draw from `items` without repeats until the whole pool has been used."""
        bags, rng = self.L["bags"], rng or self._rng(pool)
        bag = [i for i in bags.get(pool, []) if i < len(items)]
        recent = bags.get(f"{pool}:recent", [])
        if not bag:
            bag = list(range(len(items)))
            rng.shuffle(bag)
            bag.sort(key=lambda i: i in recent)  # the last third drawn goes to the back of the new bag
        idx = bag.pop(0)
        bags[pool], bags[f"{pool}:recent"] = bag, (recent + [idx])[-max(1, len(items) // 3) :]
        return items[idx]

    def _emit(self, event_type: str, /, **data: Any) -> None:
        """Raise a game event (Home Assistant fires it as event.life_rpg_*); some events also pay gold."""
        if self.twelve and isinstance(data.get("text"), str):  # e.g. a choice's "before 17:00"
            data["text"] = clock_text(data["text"], True)
        event = {"type": event_type, **data}
        if gold := M.gold_for(event):
            event["gold"] = gold
            self.L["gold"] += gold
            self._stat("gold_earned", gold)
        self.events.append(event)
        self.L["log"] = (self.L["log"] + [{"t": self.now.isoformat(timespec="seconds"), **event}])[-LOG_MAX:]

    def _once(self, key: str) -> bool:
        """True the first time `key` is seen, False after (for one-off announcements)."""
        if key in self.L["sent"]:
            return False
        self.L["sent"].append(key)
        return True

    def _stat(self, key: str, add: float = 1) -> None:
        """Add to a lifetime statistic."""
        self.L["stats"][key] = self.L["stats"].get(key, 0) + add

    def _chest(self, kind: str, rank: str | None = None, special: bool = False) -> None:
        """Give the adventurer a chest (the oldest opens by itself when the pile is full)."""
        L = self.L
        if len(L["chests"]) >= CHEST_MAX:
            self.open_chest(L["chests"][0]["id"])
        L["uid"] += 1
        L["chests"].append(
            {"id": L["uid"], "kind": kind, "rank": rank, "red": special, "at": self.now.isoformat(timespec="minutes")}
        )
        self._emit("chest_dropped", chest=kind, rank=rank)

    # --- bonuses -------------------------------------------------------------------------------
    def gift(self) -> dict[str, Any]:
        """The current racial gift."""
        race, g = C.RACES[self.race], self.L["gift"]
        if g["tier"] == 1 or not g["branch"]:
            name, desc, eff = race["gift"]
        else:
            name, desc, eff = race["branches"][g["branch"]][g["tier"] - 2]
        return {"name": name, "desc": desc, "effects": eff, "tier": g["tier"], "branch": g["branch"]}

    def devotion_tier(self, faith: int) -> int:
        """Index into C.DEVOTION, continuing past the last tier every DEVOTION_STEP_AFTER days."""
        base = max(i for i, d in enumerate(C.DEVOTION) if faith >= d[1])
        top = len(C.DEVOTION) - 1
        return base + ((faith - C.DEVOTION[top][1]) // C.DEVOTION_STEP_AFTER if base == top else 0)

    def _job_xp(self, job: str) -> float:
        """Lifetime XP earned in a job."""
        return self.L["jobs"].get(job, 0)

    def job_effects(self, job: str | None, lvl: int | None = None) -> dict[str, float]:
        """Passive (scales with job level, capped) plus unlocked job skills."""
        if not job:
            return {}
        j = C.JOBS[job]
        lvl = lvl or job_level(self._job_xp(job))
        total: dict[str, float] = {k: v * min(lvl, JOB_PASSIVE_CAP) for k, v in j["per_level"].items()}
        for at, (_, _, eff) in zip(C.JOB_SKILLS_AT, j["skills"]):
            if lvl >= at:
                LT.add_effects(total, eff)
        return total

    def bonus_sources(self, job_lvl: int | None = None) -> list[dict[str, Any]]:
        """Where every bonus in force comes from: [{source, name, effects}], before the caps."""
        L, out = self.L, []

        def add(source: str, name: str, eff: dict[str, float]) -> None:
            """Record one bonus source, skipping effects that are zero."""
            eff = {k: v for k, v in (eff or {}).items() if v}
            if eff:
                out.append({"source": source, "name": name, "effects": eff})

        gift = self.gift()
        add("race", f"{C.RACES[self.race]['name']}: {gift['name']}", gift["effects"])
        if L["job"]:
            lvl = job_lvl or job_level(self._job_xp(L["job"]))
            add("job", f"{C.JOBS[L['job']]['name']}, job level {lvl}", self.job_effects(L["job"], lvl))
        if L["title"] and (t := next((t for t in C.TITLES if t[0] == L["title"]), None)):
            add("title", f"Title: {t[1]}", t[5])
        gear: dict[str, float] = {}
        for item_id in L["equip"].values():
            if item := self._item(item_id):
                LT.add_effects(gear, LT.item_effects(item))
        add("gear", "Equipped gear", gear)
        skills: dict[str, float] = {}
        for q in self.goals:
            _, idx, _ = skill_grade(L["skills"].get(q, 0))
            if idx:
                LT.add_effects(skills, {f"xp:{q}": skill_bonus(idx)})
        add("skills", "Skill grades", skills)
        dev, top, blessed = L["devotion"], len(C.DEVOTION) - 1, {}
        for _, _, _, _, eff in C.DEVOTION[: min(dev, top) + 1]:
            LT.add_effects(blessed, eff)
        if dev > top:
            LT.add_effects(blessed, {"xp:all": min(dev - top, 10)})
        add("devotion", f"{C.GODDESS}'s blessings", blessed)
        if L["guardian"]:
            add("floor", f"This floor: {L['guardian']['trait'][0]}", L["guardian"]["trait"][2])
        ch = L["choice"]
        if ch and ch["kind"] == "trade" and ch["status"] in ("accepted", "won") and ch["date"] == L["day"]:
            add("choice", "Today's trade", ch["effects"])
        for buff in L["buffs"]:  # today's potions sit on top of the caps (they're limited per week instead)
            if buff["date"] == L["day"]:
                add("potion", M.CONSUMABLES.get(buff["id"], (buff["id"],))[0], buff["effects"])
        return out

    @staticmethod
    def _caps_view(sources: list[dict[str, Any]]) -> dict[str, Any]:
        """Every cap that applies to your bonuses: its limit, what your sources add up to, and whether it holds you back."""
        raw: dict[str, float] = {}
        for src in sources:
            if src["source"] != "potion":
                LT.add_effects(raw, src["effects"])

        def show(k: str, v: float) -> str:
            """An effect's value as the panel writes it (+5%, +1 or +20%)."""
            return f"+{round(v * 100)}%" if k == "over" else f"+{v:g}" if k in ("shield", "streak") else f"+{v:g}%"

        hit = [
            {"effect": k, "total": round(v, 1), "cap": LT.cap_for(k), "max": show(LT._cap_key(k), LT.cap_for(k))}
            for k, v in raw.items()
            if LT.cap_for(k) is not None and v > LT.cap_for(k)
        ]
        return {
            "limits": [{"name": n, "max": show(k, LT.CAPS[k])} for k, n in LT.CAP_NAMES.items() if k in LT.CAPS],
            "capped": hit,
        }

    def effects(self, job_lvl: int | None = None) -> dict[str, float]:
        """Every bonus currently in force, capped (today's potions on top of the caps)."""
        total: dict[str, float] = {}
        sources = self.bonus_sources(job_lvl)
        for src in sources:
            if src["source"] != "potion":
                LT.add_effects(total, src["effects"])
        total = LT.cap_effects(total)
        for src in sources:
            if src["source"] == "potion":
                LT.add_effects(total, src["effects"])
        return total

    def _item(self, item_id: int | None) -> dict[str, Any] | None:
        """The inventory item with this id, or None."""
        return next((i for i in self.L["inv"] if i["id"] == item_id), None)

    # --- day boundaries --------------------------------------------------------------------------
    def advance(self, now: datetime) -> list[dict[str, Any]]:
        """Close every day before `now`'s date. Returns the events raised."""
        self.now, self.events = now, []
        L, today = self.L, now.date()
        if L["day"] is None:
            L["day"] = today.isoformat()
            self._new_guardian(today)
            self._new_day(today)
            return self.events
        last = date.fromisoformat(L["day"])
        if today <= last:
            if L["guardian"] is None:
                self._new_guardian(today)
            if L["daily_title"] is None:
                self._new_day(today)
            if not L["shop"] or L["shop"]["date"] != L["day"] or "restocks" not in L["shop"]:
                self._new_shop(today)
            else:
                self._deliveries(now)
            return self.events
        if L["guardian"] is None:
            self._new_guardian(last)
        eff = self.effects()
        s = self._summary(eff)
        self._resolve_choice(final=True, s=s)
        s = self._summary(eff)
        L["xp"] += s["xp"]
        L["guardian"]["dmg"] += s["dmg"]
        L["guardian"]["base"] = L["guardian"].get("base", 0) + s["base"]
        L["days"] += 1
        self._stat("days_played")
        for q, r in s["quests"].items():
            attr = QUESTS[q].attr
            L["attr_xp"][attr] = L["attr_xp"].get(attr, 0) + r["xp"]
            L["qstreak"][q] = L["qstreak"].get(q, 0) + 1 if r["done"] else 0
            L["skills"][q] = L["skills"].get(q, 0) + self._skill_gain(r)
            if r["done"]:
                self._stat(f"done:{q}")
            if QUESTS[q].record and r["value"] is not None:
                L["best"][q] = max(L["best"].get(q, 0), r["value"])
                self._stat(f"total:{q}", r["value"])
        if L["job"]:
            L["jobs"][L["job"]] = self._job_xp(L["job"]) + self._job_today(s)
        self._stat("cleared_days", s["cleared"])
        self._stat("perfect_days", s["perfect"])
        L["recent"] = (L["recent"] + [{QUESTS[q].attr: r["xp"] for q, r in s["quests"].items()}])[-28:]
        self._hist(last, s)
        self._close_day(last, s)
        for gap in range(1, min((today - last).days, 60)):
            self._hist(last + timedelta(days=gap), None)
            self._close_day(last + timedelta(days=gap), None)
            L["qstreak"] = {}
        self._rollover_hidden(today - timedelta(days=1))
        L.update(day=today.isoformat(), today={}, bonus=0, sent=[], inputs={}, manual={}, guard={}, job_start=None)
        if today.isocalendar()[:2] != date.fromisoformat(L["guardian"]["start"]).isocalendar()[:2]:
            self._new_guardian(today)
        self._new_day(today)
        return self.events

    def _new_day(self, today: date) -> None:
        """Set up a new day: title, side quests, a possible emergency and a fresh market."""
        self.L["daily_title"] = self._draw("daily_titles", C.DAILY_TITLES)
        self._daily_bounties(today)
        self._schedule_emergency(today)
        self._new_shop(today)
        self.L["buffs"] = [b for b in self.L["buffs"] if b["date"] == today.isoformat()]

    def _skill_gain(self, r: dict[str, Any]) -> int:
        """Skill proficiency earned by one quest today (more for doing more, plus a little for finishing)."""
        return round(10 * min(r["ratio"], 1.5)) + (5 if r["done"] else 0)

    def _job_today(self, s: dict[str, Any]) -> float:
        """Job XP the active job has earned today, counted from when you took it up (taking a job at noon
        doesn't hand it the morning's XP, and the job you leave keeps what it earned)."""
        L = self.L
        gain, start = self._job_gain(s), L.get("job_start") or {}
        if start.get("day") == L["day"] and start.get("job") == L["job"]:
            gain -= start.get("gain", 0)
        return max(0.0, gain)

    def _job_gain(self, s: dict[str, Any], job_id: str | None = None) -> float:
        """Job XP for the whole day: focus quests count double; Paladins get 1.5x on everything."""
        job_id = job_id or self.L["job"]
        job = C.JOBS[job_id]
        gain = 0.0
        for q, r in s["quests"].items():
            if job_id == "paladin":
                gain += r["xp"] * 1.5
            else:
                gain += r["xp"] * (2 if q in job["quests"] else 1)
        if job_id == "rogue":
            gain += 100 * self.L["week"].get("emergencies", 0) / 7 + 60 * len(self.L["hidden"]) / 40
        if job_id == "bard" and (self.L["choice"] or {}).get("status") == "won":
            gain += 150
        return gain

    def _hist(self, day: date, s: dict | None) -> None:
        """Add one day to the history the panel's calendar and charts use."""
        entry = {
            "d": day.isoformat(),
            "xp": s["xp"] if s else 0,
            "c": bool(s and s["cleared"]),
            "p": bool(s and s["perfect"]),
            "done": [q for q, r in s["quests"].items() if r["done"]] if s else [],
            "pct": {q: round(r["ratio"] * 100) for q, r in s["quests"].items()} if s else {},
        }
        self.L["hist"] = (self.L["hist"] + [entry])[-HIST_MAX:]

    def _close_day(self, day: date, s: dict | None) -> None:
        """End a day: settle the penalty quest, then grow the streak, spend a shield or set a penalty quest."""
        L, eff = self.L, self.effects()
        pen = L["penalty"]
        if pen and pen["date"] == day.isoformat():
            L["penalty"] = None
            if s and s["done"] >= pen["need"]:
                L["streak"] = pen["streak"]
                self._stat("penalties")
                self._emit("penalty_cleared", streak=pen["streak"] + 1)
            else:
                L["last_break"] = {"date": day.isoformat(), "streak": pen["streak"]}
                self._emit("streak_broken", streak=pen["streak"])
        if s and s["cleared"]:
            L["streak"] += 1
            L["best_streak"] = max(L["best_streak"], L["streak"])
            if L["streak"] % SHIELD_EVERY == 0 and L["shields"] < SHIELD_MAX + eff.get("shield", 0):
                L["shields"] += 1
                self._emit("shield_earned", shields=L["shields"])
        elif L["streak"] and L["shields"]:
            L["shields"] -= 1
            self._emit("shield_used", shields=L["shields"], streak=L["streak"])
        elif L["streak"]:
            n = len(self.goals)
            need = math.ceil(n / 2) if eff.get("serenity") else min(n, math.ceil(n / 2) + 1)
            L["penalty"] = {"streak": L["streak"], "need": need, "date": (day + timedelta(days=1)).isoformat()}
            self._emit("penalty_quest", streak=L["streak"], need=need)
            L["streak"] = 0

    def _new_guardian(self, today: date) -> None:
        """Open this week's floor. Its guardian is sized to ~95% of your recent daily damage."""
        L, old = self.L, self.L["guardian"]
        if old:
            days = max((today - date.fromisoformat(old["start"])).days, 1)
            L["pace"] = (L["pace"] + [old.get("base", old["dmg"]) / days])[-2:]
            L["week_fails"] = 0 if old["won"] else L.get("week_fails", 0) + 1
        pace = sum(L["pace"]) / len(L["pace"]) if L["pace"] else 0
        rng = self._rng("guardian")
        floor = L["floor"]
        elite = floor % C.ELITE_EVERY == 0
        cursed = not elite and bool(old) and rng.random() < C.CURSED_CHANCE
        hp = max(GUARD_FLOOR * len(self.goals), pace * GUARD_PACE) * (7 - today.weekday())
        hp *= (ELITE_HP if elite else CURSED_HP if cursed else 1) * PITY ** min(L.get("week_fails", 0), 4)
        if old:  # your gear and gifts keep up with the guardians; the floor's trait is the edge
            hp *= 1 + {k: v for k, v in self.effects().items() if k == "boss"}.get("boss", 0) / 100
        kind = self._draw("creatures", C.CREATURES, rng)
        element = self._draw("elements", C.ELEMENTS, rng)
        name = f"{self._draw('boss_adj', C.BOSS_ADJECTIVES, rng)} {rng.choice(C.CREATURE_NOUNS[kind])}"
        if elite or cursed or rng.random() < 0.5:
            name += " " + self._draw("boss_epithet", C.BOSS_EPITHETS, rng)
        trait = list(self._draw("traits", C.FLOOR_TRAITS, rng))
        L["guardian"] = {
            "name": name,
            "kind": kind,
            "element": element,
            "seed": f"{L['seed']}:{floor}:{L['uid']}",
            "floor": floor,
            "hp": max(10, int(round(hp, -1))),
            "dmg": 0,
            "base": 0,
            "won": False,
            "start": today.isoformat(),
            "rank": L["rank"],
            "elite": elite,
            "cursed": cursed,
            "trait": trait,
        }
        L["week"] = {}
        self._emit(
            "guardian_appeared",
            guardian=name,
            floor=floor,
            kind=kind,
            element=element,
            hp=L["guardian"]["hp"],
            elite=elite,
            cursed=cursed,
            trait=trait[0],
        )

    def _schedule_emergency(self, today: date) -> None:
        """Maybe plan a surprise emergency quest for today, at a random time between 10:00 and 18:30."""
        rng = self._rng("emergency")
        options = [q for q in C.EMERGENCY if q in self.goals]
        self.L["emergency"] = None
        if options and rng.random() < C.EMERGENCY_CHANCE:
            q = rng.choice(options)
            self.L["emergency"] = {
                "date": today.isoformat(),
                "quest": q,
                "at": hhmm(rng.randint(10 * 60, 18 * 60 + 30)),
                "status": "scheduled",
                "minutes": rng.choice(C.EMERGENCY[q][0]),
                "title": self._draw(f"emergency:{q}", C.EMERGENCY[q][3], rng),
            }

    def _rollover_hidden(self, day: date) -> None:
        """Hidden quests judged across days, checked as `day` closes."""
        L, hist = self.L, self.L["hist"]
        if day.weekday() == 6 and len(hist) >= 2 and hist[-1]["c"] and hist[-2]["c"]:
            self._discover("weekend_warrior", live=False)
        if len(hist) >= 7 and all(h["p"] for h in hist[-7:]):
            self._discover("flawless_week", live=False)
        brk = L["last_break"]
        if brk and L["streak"] == 3 and brk["streak"] >= 7 and (day - date.fromisoformat(brk["date"])).days <= 10:
            self._discover("phoenix", live=False)
        if len(hist) >= 8 and all(h["c"] for h in hist[-3:]) and not any(h["c"] for h in hist[-8:-3]):
            self._discover("comeback_kid", live=False)
        month = day.strftime("%Y-%m")
        if sum(1 for h in hist if h["d"].startswith(month) and h["p"]) >= 20:
            self._discover("perfect_month", live=False)

    def _discover(self, hidden_id: str, live: bool = True) -> None:
        """Mark a hidden achievement found: it pays XP (into today's total if found live) and a chest."""
        if hidden_id in self.L["hidden"]:
            return
        self.L["hidden"][hidden_id] = self.now.date().isoformat()
        self._stat("hidden_found")
        if live:
            self.L["bonus"] += HIDDEN_XP
        else:
            self.L["xp"] += HIDDEN_XP
        name = next(h[1] for h in C.HIDDEN if h[0] == hidden_id)
        self._emit("hidden_quest", quest=name, xp=HIDDEN_XP)
        self._chest("hidden")

    # --- the daily choice ------------------------------------------------------------------------
    def _offer_choice(self) -> None:
        """Offer today's daily choice (a wager or trade the adventurer can accept), once a day in the daytime."""
        L, now, qs = self.L, self.now, list(self.goals)
        if not qs or not CHOICE_FROM <= now.hour < CHOICE_UNTIL:
            return
        if L["choice"] and L["choice"]["date"] == L["day"]:
            return
        rng = self._rng("choice")
        kinds = [
            k
            for k in C.CHOICES
            if (k not in ("trade", "perfect") or len(qs) > 1)
            and (k != "push" or set(qs) & {"steps", "floors"})
            and (k != "early" or now.hour < 13)
        ]
        kind = rng.choices(kinds, weights=[C.CHOICES[k][0] for k in kinds])[0]
        boost = 1 + self.effects().get("choice", 0) / 100
        # bounties only target quests you can still move today (sleep and lights-out are settled by morning)
        open_qs = [x for x in qs if x in ("steps", "floors", "hydration") and L["today"].get(x, [0, 0])[1] < 1]
        if kind in ("quest", "early") and not open_qs:
            kind = "count"
        q = rng.choice(open_qs or qs)
        reward_xp, chest, effects = round(C.CHOICE_XP * boost), "choice", {}
        p: dict[str, Any] = {"q": q}
        if kind == "trade":
            q2 = rng.choice([x for x in qs if x != q])
            pct = rng.choice([20, 25, 30, 40])
            p = {"q": q, "q2": q2, "pct": round(pct * boost), "pct2": pct // 2}
            effects = {f"xp:{q}": p["pct"], f"xp:{q2}": -p["pct2"]}
            reward_xp, chest = 0, None
        elif kind == "early":
            p = {"q": q, "hour": rng.randint(max(now.hour + 2, 10), 16)}
            reward_xp = round(150 * boost)
        elif kind == "count":
            p = {"n": min(len(qs), math.ceil(len(qs) / 2) + 1)}
            reward_xp = round(150 * boost)
        elif kind == "perfect":
            p, reward_xp, chest = {"stake": 100}, round(300 * boost), "wager"
        elif kind == "push":
            q = rng.choice([x for x in qs if x in ("steps", "floors")])
            p, reward_xp, chest = {"q": q, "pct": rng.choice([130, 140, 150]), "stake": 60}, round(200 * boost), "wager"
        reward = f"{reward_xp} XP and a {'wager' if chest == 'wager' else 'bounty'} chest" if reward_xp else ""
        names = {k: C.QUEST_NAMES[v] for k, v in p.items() if k in ("q", "q2")}
        text = C.CHOICES[kind][1].format(**{**p, **names, "reward": reward})
        L["choice"] = {
            "date": L["day"],
            "kind": kind,
            "params": p,
            "effects": effects,
            "reward_xp": reward_xp,
            "chest": chest,
            "status": "offered",
            "voice": self._draw("voices", C.CHOICE_VOICES, rng),
            "text": text,
            "accept": C.CHOICES[kind][2],
        }
        self._emit("choice_offered", text=text)

    def _resolve_choice(self, final: bool = False, s: dict | None = None) -> None:
        """Settle the accepted daily choice when the day is decided (won or lost), or let an unanswered one expire."""
        L, ch = self.L, self.L["choice"]
        if not ch or ch["date"] != L["day"]:
            return
        if ch["status"] == "offered" and (final or self.now.hour >= CHOICE_UNTIL):
            ch["status"] = "expired"
            return
        if ch["status"] != "accepted" or s is None:
            return
        p = ch["params"]
        q = s["quests"].get(p.get("q", ""), {})
        if ch["kind"] == "trade":
            if final:
                ch["status"] = "done"
            return
        won = {
            "quest": q.get("done"),
            "early": q.get("done") and not final and self.now.hour < p.get("hour", 0),
            "count": s["done"] >= p.get("n", 99),
            "perfect": s["perfect"],
            "push": q.get("ratio", 0) * 100 >= p.get("pct", 999),
        }[ch["kind"]]
        if won:
            ch["status"] = "won"
            if final:
                L["xp"] += ch["reward_xp"]
            else:
                L["bonus"] += ch["reward_xp"]
            self._stat("choices_won")
            self._emit("choice_won", xp=ch["reward_xp"])
            if ch["chest"]:
                self._chest(ch["chest"])
        elif final or (ch["kind"] == "early" and self.now.hour >= p["hour"]):
            ch["status"] = "lost"
            stake = p.get("stake", 0)
            L["xp"] = max(0, L["xp"] - stake)
            self._emit("choice_lost", stake=stake)

    # --- scoring ------------------------------------------------------------------------------------
    def ratio(self, quest: str, value: float) -> float:
        """Progress toward the goal, 1.0 = done."""
        goal = self.goals[quest]
        if quest == "bedtime":
            return bedtime_ratio(int(value), int(goal))
        return value / goal if goal else 0.0

    def _summary(self, eff: dict[str, float]) -> dict[str, Any]:
        """Score today so far: each quest's XP and damage, how many are done, and whether the day is cleared."""
        L = self.L
        quests = {}
        dmg = 0.0
        for q in self.goals:
            value, ratio = L["today"].get(q, (None, 0.0))
            base = quest_xp(ratio, QUESTS[q].overachieve, eff.get("over", 0))
            boost = max(0.1, 1 + (eff.get(f"xp:{q}", 0) + eff.get("xp:all", 0)) / 100)
            xp = round(base * boost)
            quests[q] = {"value": value, "ratio": ratio, "done": ratio >= 1, "xp": xp}
            dmg += xp * (1 + eff.get(f"dmg:{q}", 0) / 100)
        n = len(quests)
        done = sum(r["done"] for r in quests.values())
        needed = math.ceil(n / 2) if n else 1
        base = sum(r["xp"] for r in quests.values())
        mult = 1 + min(L["streak"], STREAK_CAP + eff.get("streak", 0)) * STREAK_STEP
        perfect = n > 0 and done == n
        perfect_xp = round(PERFECT_BONUS * n * (1 + eff.get("perfect", 0) / 100)) if perfect else 0
        pen = L["penalty"] if L["penalty"] and L["penalty"]["date"] == L["day"] else None
        return {
            "quests": quests,
            "done": done,
            "needed": needed,
            "cleared": done >= needed,
            "perfect": perfect,
            "base": base,
            "mult": mult,
            "perfect_xp": perfect_xp,
            "bonus": L["bonus"],
            "xp": round(base * mult) + perfect_xp + L["bonus"],
            "dmg": round(dmg * (1 + eff.get("boss", 0) / 100)),
            "penalty": pen,
            "penalty_met": bool(pen and done >= pen["need"]),
        }

    def update(self, readings: dict[str, float | None], now: datetime) -> dict[str, Any]:
        """Fold in today's sensor readings and return the full game view (call advance(now) first)."""
        self.now = now
        L, eff = self.L, self.effects()
        if L["guardian"] is None:
            self._new_guardian(now.date())
        readings, follow = dict(readings), set()
        if readings.get("sleep") is not None:  # nobody sleeps more than 16 hours in a day, whatever a sensor says
            readings["sleep"] = min(max(float(readings["sleep"]), 0.0), SLEEP_MAX_H)
        for q in GUARD:  # sensor readings only; what you log by hand is added after
            if q in self.goals and readings.get(q) is not None:
                readings[q], dropped = self._guard(q, float(readings[q]), now)
                if dropped:
                    follow.add(q)
        manual = L.get("manual") or {}
        if manual.get("date") == L["day"]:  # quests logged by hand add on top of any sensor
            for q in MANUAL_LIMITS:
                if q in self.goals and manual.get(q):
                    readings[q] = (readings.get(q) or 0) + manual[q]
        for q, value in readings.items():
            if value is None or q not in self.goals:
                continue
            ratio = self.ratio(q, value)
            cur = L["today"].get(q)
            if q in follow:  # the source corrected itself downward (a duplicate removed): follow it
                L["today"][q] = [value, ratio]
            elif cur is None or ratio > cur[1]:
                if (
                    QUESTS[q].record
                    and L["days"] >= RECORD_AFTER
                    and value > L["best"].get(q, 0)
                    and self._once(f"record:{q}")
                ):
                    xp = round(RECORD_BONUS * (1 + eff.get("record", 0) / 100))
                    L["bonus"] += xp
                    self._stat("records")
                    self._emit(
                        "personal_record", quest=q, value=round(value), previous=round(L["best"].get(q, 0)), xp=xp
                    )
                    self._chest("record")
                L["today"][q] = [value, ratio]
        self._offer_choice()
        self._run_emergency(readings, eff)

        s = self._summary(eff)
        self._resolve_choice(s=s)
        for q, r in s["quests"].items():
            if r["done"] and self._once(f"done:{q}"):
                self._emit("quest_complete", quest=q, name=C.QUEST_NAMES[q], attribute=QUESTS[q].attr)
        streak = (s["penalty"]["streak"] if s["penalty_met"] else L["streak"]) + s["cleared"]
        if s["cleared"] and self._once("cleared"):
            self._emit("day_cleared", streak=streak)
            self._chest("daily")
            if streak in MILESTONES:
                self._emit("streak_milestone", streak=streak)
        if s["perfect"] and len(self.goals) > 1 and self._once("perfect"):
            self._emit("perfect_day", xp=s["perfect_xp"])
            today = now.date().isoformat()
            daily = next((c for c in L["chests"] if c["kind"] == "daily" and c["at"].startswith(today)), None)
            if daily:
                daily["kind"] = "perfect"
            else:
                self._chest("perfect")
        s = self._summary(eff)
        self._guardian_check(s)
        self._live_hidden(s, now)
        eff = self.effects()
        s = self._summary(eff)
        return self._progress(s, eff, streak)

    def _guardian_check(self, s: dict[str, Any]) -> None:
        """Beat this week's guardian once the damage reaches its HP: XP, a chest, a bestiary entry and the next floor."""
        L, g = self.L, self.L["guardian"]
        if g["won"] or g["dmg"] + s["dmg"] < g["hp"]:
            return
        g["won"] = True
        reward = round(g["hp"] * GUARD_REWARD * (2 if g["elite"] or g["cursed"] else 1))
        L["bonus"] += reward
        self._stat("guardians")
        self._stat(f"kills:{g['kind']}")
        self._stat("elites", g["elite"])
        self._stat("cursed", g["cursed"])
        L["bestiary"] = (
            L["bestiary"]
            + [
                {
                    "name": g["name"],
                    "kind": g["kind"],
                    "element": g["element"],
                    "seed": g["seed"],
                    "floor": g["floor"],
                    "date": self.now.date().isoformat(),
                    "trait": {"name": g["trait"][0]},
                    "elite": g["elite"],
                    "cursed": g["cursed"],
                }
            ]
        )[-BESTIARY_MAX:]
        L["floor"] = max(L["floor"], g["floor"] + 1)
        self._emit(
            "guardian_defeated",
            guardian=g["name"],
            floor=g["floor"],
            xp=reward,
            elite=g["elite"],
            cursed=g["cursed"],
            next_floor=L["floor"],
        )
        self._chest("guardian", g["rank"], g["elite"] or g["cursed"])
        if self.now.weekday() <= 2:
            self._discover("swift_hunt")

    def _run_emergency(self, readings: dict[str, float | None], eff: dict[str, float]) -> None:
        """Run today's emergency quest: start it at its time, track progress, then clear or fail it."""
        e, now = self.L["emergency"], self.now
        if not e or e["date"] != now.date().isoformat():
            return
        q = e["quest"]
        if e["status"] == "scheduled" and now.strftime("%H:%M") >= e["at"]:
            if now.hour >= 20:
                e["status"] = "skipped"
                return
            if readings.get(q) is None:
                return
            _, share, low, _ = C.EMERGENCY[q]
            step = 100 if q == "steps" else 50 if q == "hydration" else 1
            target = max(low, round(self.goals[q] * share / step) * step)
            minutes = e.get("minutes", 60)
            shown = f"{self.water_out(target):,g} {self.water_label}" if q == "hydration" else f"{target:,}"
            title = e.get("title", "Emergency! {target}").format(target=shown)
            excused = not self.work["penalty"] or self.working(now)
            e.update(
                status="active",
                base=readings[q],
                target=target,
                progress=0,
                title=title,
                start=now.isoformat(timespec="seconds"),
                excused=excused,
                fine=self._fine(),
                end=(now + timedelta(minutes=minutes)).isoformat(timespec="seconds"),
            )
            self._emit(
                "emergency_quest",
                quest=q,
                title=title,
                target=target,
                minutes=minutes,
                excused=excused,
                fine=0 if excused else e["fine"],
            )
        if e["status"] == "active":
            if readings.get(q) is not None:
                e["progress"] = max(e["progress"], readings[q] - e["base"])
            if e["progress"] >= e["target"]:
                e["status"] = "cleared"
                xp = round(C.EMERGENCY_XP * (1 + eff.get("emergency", 0) / 100))
                self.L["bonus"] += xp
                self._stat("emergencies")
                self.L["week"]["emergencies"] = self.L["week"].get("emergencies", 0) + 1
                self._emit("emergency_cleared", quest=q, xp=xp)
                self._chest("emergency")
                if now - datetime.fromisoformat(e["start"]) <= timedelta(minutes=15):
                    self._discover("quick_draw")
                if self.L["week"]["emergencies"] >= 3:
                    self._discover("alarm_week")
            elif now >= datetime.fromisoformat(e["end"]):
                e["status"] = "failed"
                late = now - datetime.fromisoformat(e["end"]) > LATE_GRACE  # we weren't watching when it ended
                if e.get("excused", True) or late:
                    why = (
                        "late" if late and not e.get("excused", True) else "off" if not self.work["penalty"] else "work"
                    )
                    self._emit("emergency_failed", quest=q, fine=0, excused=True, why=why, would_be=e.get("fine", 0))
                else:
                    fine = min(e.get("fine", 0), self.L["gold"])
                    self.L["gold"] -= fine
                    self._stat("emergency_fines", fine)
                    self._emit("emergency_failed", quest=q, fine=fine, excused=False)

    def _live_hidden(self, s: dict[str, Any], now: datetime) -> None:
        """Check today's readings for the hidden achievements that can be found during the day."""
        q, L, d = s["quests"], self.L, now.date()
        val = lambda k: q.get(k, {}).get("value") or 0  # noqa: E731
        if "steps" in q and q["steps"]["done"] and now.hour < 9:
            self._discover("dawn_patrol")
            if "bedtime" in q and q["bedtime"]["done"]:
                self._discover("dawn_to_dusk")
        if "steps" in q and q["steps"]["ratio"] >= 2:
            self._discover("beyond_limit")
        if val("steps") >= 20000:
            self._discover("marathon")
        if val("steps") >= 30000:
            self._discover("ultra")
        if "floors" in q and q["floors"]["ratio"] >= 3:
            self._discover("touch_sky")
        if val("floors") >= 50:
            self._discover("tower")
        if "hydration" in q and q["hydration"]["done"] and now.hour < 12:
            self._discover("morning_spring")
        if "bedtime" in q and q["bedtime"]["value"] is not None and 18 * 60 <= q["bedtime"]["value"] <= 21 * 60 + 30:
            self._discover("early_lights")
        if s["perfect"] and len(q) >= 2:
            if d.weekday() == 0:
                self._discover("mondays_bane")
            if d.weekday() == 4 and d.day == 13:
                self._discover("unlucky")
            if len(q) >= 3 and all(r["ratio"] <= 1.2 for r in q.values()):
                self._discover("harmony")
        if s["cleared"]:
            age = moon_age(d)
            if abs(age - 14.765) < 1.0:
                self._discover("moonlight")
            if age < 1.0 or age > 28.53:
                self._discover("dark_moon")
            md = (d.month, d.day)
            if md in ((6, 20), (6, 21), (12, 21), (12, 22)):
                self._discover("solstice")
            if md in ((3, 20), (3, 21), (9, 22), (9, 23)):
                self._discover("equinox")
            if md == (1, 1):
                self._discover("new_year")
            if md == (2, 29):
                self._discover("leap_day")
            if md == (10, 31):
                self._discover("hallow")
        streaks = {k: L["qstreak"].get(k, 0) + r["done"] for k, r in q.items()}
        if streaks.get("sleep", 0) >= 7:
            self._discover("rest_week")
        if streaks.get("hydration", 0) >= 14:
            self._discover("wellspring")
        if streaks.get("floors", 0) >= 7:
            self._discover("stair_week")
        if len(q) >= 3 and all(v >= 7 for v in streaks.values()):
            self._discover("sevenfold")
        hist = L["hist"]
        if (
            "bedtime" in q
            and q["bedtime"]["done"]
            and len(hist) >= 3
            and all("bedtime" in h["pct"] and "bedtime" not in h["done"] for h in hist[-3:])
        ):
            self._discover("night_owl")
        st = L["stats"]
        if st.get("choices_won", 0) >= 5:
            self._discover("gambler")
        if st.get("choices_declined", 0) >= 10:
            self._discover("contrarian")
        if L["floor"] > 10:
            self._discover("floor_ten")
        if st.get("elites", 0):
            self._discover("elite_hunt")
        if all(st.get(f"kills:{k}", 0) for k in C.CREATURES):
            self._discover("full_bestiary")
        equipped = [i for i in (self._item(x) for x in L["equip"].values()) if i]
        rar = {i["rarity"] for i in equipped}
        if len(equipped) == 6 and len(rar) == 1 and LT.RARITIES.index(next(iter(rar))) >= 2:
            self._discover("matched_set")
        if any(i["enh"] >= LT.ENHANCE_MAX for i in L["inv"]):
            self._discover("perfect_ten")
        if sum(job_level(x) >= 10 for x in L["jobs"].values()) >= 3:
            self._discover("job_hopper")

    # --- progression ------------------------------------------------------------------------------
    def _counters(self, s: dict[str, Any], streak: int, level: int, live_job_xp: dict[str, float]) -> dict[str, float]:
        """Lifetime counters including today, for titles and badges."""
        L = self.L
        c = dict(L["stats"])
        c["cleared_days"] = c.get("cleared_days", 0) + s["cleared"]
        c["perfect_days"] = c.get("perfect_days", 0) + s["perfect"]
        c["best_streak"] = max(L["best_streak"], streak)
        c["level"], c["floor"] = level, L["floor"] - 1
        for q, r in s["quests"].items():
            c[f"done:{q}"] = c.get(f"done:{q}", 0) + r["done"]
            c[f"qstreak:{q}"] = L["qstreak"].get(q, 0) + r["done"]
            if QUESTS[q].record and r["value"] is not None:
                c[f"total:{q}"] = c.get(f"total:{q}", 0) + r["value"]
            c[f"skill:{q}"] = L["skills"].get(q, 0)
        c["skill_total"] = sum(L["skills"].values())
        levels = {j: job_level(x) for j, x in live_job_xp.items()}
        for j, lv in levels.items():
            c[f"job:{j}"] = lv
        c["job_levels"] = sum(levels.values())
        c["jobs_at_10"] = sum(lv >= 10 for lv in levels.values())
        c["jobs_at_20"] = sum(lv >= 20 for lv in levels.values())
        for h in L["hidden"]:
            c[f"hidden:{h}"] = 1
        c["lune_days"] = len(L["lune_days"])
        return c

    def _progress(self, s: dict[str, Any], eff: dict[str, float], streak: int) -> dict[str, Any]:
        """Apply today's progress (attributes, skills, job, level, rank, gift, titles, badges, devotion) and build the view."""
        L = self.L
        attr_xp = {QUESTS[q].attr: L["attr_xp"].get(QUESTS[q].attr, 0) + r["xp"] for q, r in s["quests"].items()}
        for attr, xp in attr_xp.items():
            pts = attr_points(xp)
            if attr in L["points"] and pts > L["points"][attr]:
                self._emit("attribute_up", attribute=attr, value=pts)
            L["points"][attr] = max(pts, L["points"].get(attr, 0))
        for q, r in s["quests"].items():  # skills, with today's practice counted live
            prof = L["skills"].get(q, 0) + self._skill_gain(r)
            name, idx, _ = skill_grade(prof)
            if q in L["skill_grades"] and idx > L["skill_grades"][q]:
                self._emit("skill_up", skill=C.SKILLS[q][0], grade=name, proficiency=prof)
            L["skill_grades"][q] = max(idx, L["skill_grades"].get(q, 0))
        live_job_xp = dict(L["jobs"])
        if L["job"]:
            live_job_xp[L["job"]] = self._job_xp(L["job"]) + self._job_today(s)
            lv = job_level(live_job_xp[L["job"]])
            if L["job"] in L["job_levels"] and lv > L["job_levels"][L["job"]]:
                tier = C.JOBS[L["job"]]["titles"][sum(lv >= t for t in C.JOB_TITLES_AT) - 1]
                self._emit("job_level", job=C.JOBS[L["job"]]["name"], level=lv, title=tier)
            L["job_levels"][L["job"]] = max(lv, L["job_levels"].get(L["job"], 0))
        total = L["xp"] + s["xp"]
        level = max(level_for(total), L["level"])
        for lvl in range(L["level"] + 1, level + 1):
            self._emit("level_up", level=lvl)
            self._chest("level")
        L["level"] = level
        rank, next_rank_at = rank_for(level)
        if rank != L["rank"]:
            self._emit("rank_up", rank=rank, previous=L["rank"])
            self._chest("rank")
            L["rank"] = rank
        g = L["gift"]
        while g["tier"] < 3 and level >= C.EVOLVE_AT[g["tier"] - 1]:
            if not g["branch"]:
                g["branch"] = self._branch(attr_xp)
            g["tier"] += 1
            self._emit("race_evolved", gift=self.gift()["name"], tier=g["tier"], race=C.RACES[self.race]["name"])
        counters = self._counters(s, streak, level, live_job_xp)
        for tid, name, _how, counter, threshold, _eff in C.TITLES:
            if tid not in L["titles"] and counters.get(counter, 0) >= threshold:
                L["titles"].append(tid)
                L.setdefault("title_dates", {})[tid] = self.now.date().isoformat()
                self._emit("title_earned", title=name)
                L["title"] = L["title"] or tid
        for bid, name, _icon, counter, tiers in C.BADGES:
            tier = badge_tier(counters.get(counter, 0), tiers)
            if tier > L["badges"].get(bid, 0):
                self._emit("badge_earned", badge=name, tier=badge_tier_name(tier))
                L["badges"][bid] = tier
        dtier = self.devotion_tier(int(counters["cleared_days"]))
        if dtier > L["devotion"]:
            L["devotion"] = dtier
            self._emit(
                "devotion_up", tier=self._devotion_name(dtier), blessing=C.DEVOTION[min(dtier, len(C.DEVOTION) - 1)][2]
            )
        eff = self.effects(job_level(live_job_xp[L["job"]]) if L["job"] else None)
        return self._view(s, eff, streak, attr_xp, counters, total, level, rank, next_rank_at, live_job_xp)

    def _devotion_name(self, tier: int) -> str:
        """A devotion tier's name (past the last named tier: the last name +n)."""
        top = len(C.DEVOTION) - 1
        return C.DEVOTION[tier][0] if tier <= top else f"{C.DEVOTION[top][0]} +{tier - top}"

    def _branch(self, attr_xp: dict[str, float]) -> str:
        """Which branch the racial gift evolves into: the attribute trained most recently (or ever)."""
        branches = list(C.RACES[self.race]["branches"])
        recent: dict[str, float] = {}
        for day in self.L["recent"]:
            for a, xp in day.items():
                recent[a] = recent.get(a, 0) + xp
        score = recent if any(recent.get(b) for b in branches) else attr_xp
        return max(branches, key=lambda b: score.get(b, 0))

    def recommended_job(self) -> str | None:
        """What the last 28 days suggest (balanced players get Paladin)."""
        recent: dict[str, float] = {}
        for day in self.L["recent"]:
            for a, xp in day.items():
                recent[a] = recent.get(a, 0) + xp
        if len(self.L["recent"]) < 3 or not recent:
            return None
        ranked = sorted(recent.values(), reverse=True)
        if len(ranked) > 1 and ranked[0] < ranked[1] * 1.15:
            return "paladin"
        top = max(recent, key=recent.get)
        return next((k for k, j in C.JOBS.items() if j["attr"] == top), None)

    # --- view ---------------------------------------------------------------------------------------
    def _goddess_line(self, s: dict[str, Any], streak: int) -> str:
        """Pick what the goddess says right now, from the pool that fits the moment."""
        L, now = self.L, self.now
        e, g, ch = L["emergency"], L["guardian"], L["choice"]
        if e and e.get("status") == "active":
            pool = "emergency"
        elif s["penalty"] and not s["penalty_met"]:
            pool = "penalty"
        elif g["won"] and L["bestiary"] and L["bestiary"][-1]["date"] == now.date().isoformat():
            pool = "slain"
        elif s["perfect"]:
            pool = "perfect"
        elif s["cleared"]:
            pool = "cleared"
        elif ch and ch["date"] == L["day"] and ch["status"] == "offered":
            pool = "choice"
        elif now.hour >= 21 and "bedtime" in self.goals:
            pool = "night"
        elif L["hist"] and not L["hist"][-1]["c"] and L["days"] > 2 and now.hour < 12:
            pool = "comeback"
        elif g["start"] == now.date().isoformat():
            pool = "labyrinth"
        elif now.hour < 10:
            pool = "morning"
        elif streak >= 7 and now.toordinal() % 3 == 0:
            pool = "streak"
        else:
            pool = "default"
        self._goddess_pool = pool
        key = f"{L['day']}:{pool}:{now.hour // 12}"
        said = L["bags"].get("goddess:said")
        if not said or said[0] != key:
            said = [key, self._draw(f"goddess:{pool}", list(range(len(C.GODDESS_LINES[pool]))))]
            L["bags"]["goddess:said"] = said
        job = C.JOBS[L["job"]]["name"] if L["job"] else C.START_JOB
        return C.GODDESS_LINES[pool][said[1]].format(streak=streak, guardian=g["name"], floor=g["floor"], job=job)

    def _view(self, *args: Any) -> dict[str, Any]:
        """The view for the panel and sensors, with the goddess called by your chosen name."""
        view = self._view_raw(*args)
        if self.goddess != C.GODDESS:  # the goddess goes by your chosen name everywhere
            view = rename(view, C.GODDESS, self.goddess)
        return view

    def _view_raw(
        self, s, eff, streak, attr_xp, counters, total, level, rank, next_rank_at, live_job_xp
    ) -> dict[str, Any]:
        """Build the whole view: everything the panel, sensors and LLM tools show."""
        L, now = self.L, self.now
        lo, hi = xp_for_level(level), xp_for_level(level + 1)
        quests = {}
        for q, r in s["quests"].items():
            show = (
                (lambda v: clock(v, self.twelve))
                if q == "bedtime"
                else (lambda v: int(v) if v == int(v) else round(v, 2))
            )
            quests[q] = {
                "name": C.QUEST_NAMES[q],
                "attr": QUESTS[q].attr,
                "pct": round(r["ratio"] * 100),
                "xp": r["xp"],
                "done": r["done"],
                "value": None if r["value"] is None else show(r["value"]),
                "goal": show(self.goals[q]),
                "streak": L["qstreak"].get(q, 0) + r["done"],
                "record": round(L["best"][q]) if q in L["best"] else None,
                "unit": QUEST_UNITS[q],
                "fixable": q in self.corrections,
            }
            if (gq := L.get("guard", {}).get(q)) and gq.get("held", 0) >= 1:
                quests[q]["held"] = round(gq["held"])
            if q == "hydration":  # shown in your water unit
                hq = quests[q]
                hq["unit"] = self.water_label
                for k in ("value", "goal", "record", "held"):
                    if hq.get(k) is not None:
                        hq[k] = self.water_out(hq[k])
        attrs = {
            a: {
                "short": C.ATTR_SHORT[a],
                "points": attr_points(x),
                "xp": x,
                "next_point_xp": ATTR_XP * (attr_points(x) - ATTR_BASE + 1) ** 2 - x,
            }
            for a, x in attr_xp.items()
        }
        skills = {}
        for q, r in s["quests"].items():
            prof = L["skills"].get(q, 0) + self._skill_gain(r)
            grade, idx, nxt = skill_grade(prof)
            prev = C.SKILL_GRADES[idx][1] if idx < len(C.SKILL_GRADES) else nxt - C.SKILL_SAINT_STEP
            skills[q] = {
                "name": C.SKILLS[q][0],
                "desc": C.SKILLS[q][1],
                "proficiency": prof,
                "grade": grade,
                "next": nxt,
                "progress": round(100 * (prof - prev) / max(nxt - prev, 1), 1),
                "bonus": skill_bonus(idx),
            }
        jobs = []
        for jid, j in C.JOBS.items():
            jx = live_job_xp.get(jid, 0)
            lv = job_level(jx)
            tier = j["titles"][sum(lv >= t for t in C.JOB_TITLES_AT) - 1]
            jobs.append(
                {
                    "id": jid,
                    "name": j["name"],
                    "title": tier,
                    "desc": j["desc"],
                    "level": lv,
                    "xp": round(jx),
                    "next_xp": job_level_xp(lv + 1),
                    "level_xp": job_level_xp(lv),
                    "progress": round(
                        100 * (jx - job_level_xp(lv)) / max(job_level_xp(lv + 1) - job_level_xp(lv), 1), 1
                    ),
                    "active": jid == L["job"],
                    "effects": self.job_effects(jid, lv),
                    "skills": [
                        {"name": n, "desc": d, "effects": e, "at": at, "unlocked": lv >= at}
                        for at, (n, d, e) in zip(C.JOB_SKILLS_AT, j["skills"])
                    ],
                    "quests": j["quests"],
                }
            )
        g = L["guardian"]
        dmg = g["dmg"] + s["dmg"]
        start = date.fromisoformat(g["start"])
        e = L["emergency"]
        emergency = None
        if e and e["date"] == now.date().isoformat() and e["status"] != "scheduled":
            emergency = {k: e.get(k) for k in ("quest", "status", "title", "target", "progress", "start", "end")}
            emergency.update(excused=e.get("excused", True), fine=e.get("fine", 0), decline_fine=e.get("fine", 0) // 2)
            if e["quest"] == "hydration":
                for k in ("target", "progress"):
                    if emergency.get(k) is not None:
                        emergency[k] = self.water_out(emergency[k])
        ch = L["choice"]
        choice = None
        if ch and ch["date"] == L["day"]:
            choice = {k: ch[k] for k in ("kind", "text", "voice", "status", "accept", "reward_xp", "params")}
            choice["voice_index"] = C.CHOICE_VOICES.index(ch["voice"]) if ch["voice"] in C.CHOICE_VOICES else 0
            choice["deadline"] = clock(CHOICE_UNTIL * 60, self.twelve)
            if ch.get("chest"):  # exactly what the prize can be, so no offer (or LLM) oversells it
                choice["chest"] = {
                    "kind": ch["chest"],
                    "name": CHEST_NAMES.get(ch["chest"], "chest"),
                    "items": 1,
                    "odds": chest_odds(ch["chest"]),
                    "words": chest_words(ch["chest"]),
                }
            choice["text"] = clock_text(choice["text"], self.twelve)
        race = C.RACES[self.race]
        gift = self.gift()
        tree = {
            "gift": dict(zip(("name", "desc", "effects"), race["gift"])),
            "branches": {
                b: [dict(zip(("name", "desc", "effects"), t)) for t in tiers] for b, tiers in race["branches"].items()
            },
        }
        title = next((t for t in C.TITLES if t[0] == L["title"]), None)
        equipped = {slot: self._item(L["equip"].get(slot)) for slot in LT.SLOTS}
        dev, top = L["devotion"], len(C.DEVOTION) - 1
        nxt_at = C.DEVOTION[dev + 1][1] if dev < top else C.DEVOTION[top][1] + (dev - top + 1) * C.DEVOTION_STEP_AFTER
        return {
            "events": self.events,
            "now": now.isoformat(timespec="seconds"),
            "clock": "12" if self.twelve else "24",
            "seed": L["seed"],
            "look": L["look"],
            "portrait_v": L.get("portrait_v", 0),
            "level": level,
            "xp": total,
            "level_xp": total - lo,
            "level_span": hi - lo,
            "progress": round(100 * max(total - lo, 0) / (hi - lo), 1),
            "next_level_xp": hi,
            "rank": rank,
            "next_rank_level": next_rank_at,
            "job": next((j for j in jobs if j["active"]), None),
            "jobs": jobs,
            "job_unlock_level": C.JOB_UNLOCK_LEVEL,
            "recommended_job": self.recommended_job(),
            "title": {"id": title[0], "name": title[1], "effects": title[5]} if title else None,
            "race": {
                "id": self.race,
                "name": race["name"],
                "lore": race["lore"],
                "gift": gift,
                "next_evolution": C.EVOLVE_AT[gift["tier"] - 1] if gift["tier"] < 3 else None,
                "tree": tree,
            },
            "xp_today": s["xp"],
            "base_xp": s["base"],
            "multiplier": round(s["mult"], 2),
            "bonus_xp": s["bonus"],
            "perfect_xp": s["perfect_xp"],
            "done": s["done"],
            "needed": s["needed"],
            "cleared": s["cleared"],
            "perfect": s["perfect"],
            "streak": streak,
            "best_streak": max(L["best_streak"], streak),
            "shields": L["shields"],
            "shield_max": SHIELD_MAX + int(eff.get("shield", 0)),
            "penalty": {"streak": s["penalty"]["streak"], "need": s["penalty"]["need"], "met": s["penalty_met"]}
            if s["penalty"]
            else None,
            "emergency": emergency,
            "choice": choice,
            "daily_title": L["daily_title"],
            "quests": quests,
            "attrs": attrs,
            "skills": skills,
            "effects": eff,
            "bonus_sources": (srcs := self.bonus_sources(job_level(live_job_xp[L["job"]]) if L["job"] else None)),
            "bonus_caps": self._caps_view(srcs),
            "labyrinth": {
                "floor": g["floor"],
                "deepest": L["floor"],
                "name": g["name"],
                "kind": g["kind"],
                "element": g["element"],
                "seed": g["seed"],
                "rank": g["rank"],
                "elite": g["elite"],
                "cursed": g["cursed"],
                "hp": g["hp"],
                "damage": min(dmg, g["hp"]),
                "pct": round(100 * max(g["hp"] - dmg, 0) / g["hp"]),
                "defeated": g["won"],
                "reward": round(g["hp"] * GUARD_REWARD * (2 if g["elite"] or g["cursed"] else 1)),
                "trait": {"name": g["trait"][0], "desc": g["trait"][1]},
                "ends": (start + timedelta(days=6 - start.weekday())).isoformat(),
            },
            "bestiary": L["bestiary"][-120:][::-1],
            "bestiary_total": int(L["stats"].get("guardians", 0)),
            "bestiary_kinds": {k: int(L["stats"].get(f"kills:{k}", 0)) for k in C.CREATURES},
            # titles and hidden quests stay secret until earned: only the ones you have are sent at all
            "titles": [
                {
                    "id": t[0],
                    "name": t[1],
                    "how": t[2],
                    "effects": t[5],
                    "earned": True,
                    "equipped": t[0] == L["title"],
                    "date": L.get("title_dates", {}).get(t[0]),
                }
                for t in C.TITLES
                if t[0] in L["titles"]
            ],
            "badges": [self._badge_view(b, counters) for b in C.BADGES],
            "hidden": sorted(
                (
                    {
                        "id": h[0],
                        "found": True,
                        "date": L["hidden"][h[0]],
                        "name": h[1],
                        "desc": clock_text(h[3], self.twelve),
                    }
                    for h in C.HIDDEN
                    if h[0] in L["hidden"]
                ),
                key=lambda h: h["date"],
                reverse=True,
            ),
            "gear": {
                "equipped": {slot: self._item_view(i) if i else None for slot, i in equipped.items()},
                "inventory": [self._item_view(i) for i in L["inv"]],
                "shards": L["shards"],
                "chests": L["chests"],
                "score": sum(LT.item_power(i) for i in equipped.values() if i),
            },
            "devotion": {
                "tier": self._devotion_name(dev),
                "faith": int(counters["cleared_days"]),
                "next_at": nxt_at,
                "next_tier": self._devotion_name(dev + 1),
                "blessings": [
                    {"tier": d[0], "at": d[1], "name": d[2], "desc": d[3], "unlocked": i <= dev}
                    for i, d in enumerate(C.DEVOTION)
                    if d[2]
                ],
            },
            "goddess": {
                "name": C.GODDESS,
                "title": C.GODDESS_TITLE,
                "line": self._goddess_line(s, streak),
                "pool": self._goddess_pool,
                "prefs": dict(L.get("goddess_prefs") or {}),
                "choices": A.GODDESS_CHOICES,
            },
            "gold": L["gold"],
            "market": self._market_view(),
            "bag": self._bag_view(),
            "manual_log": {
                k: self.water_out(v) if k == "hydration" else v
                for k, v in (L.get("manual") or {}).items()
                if k != "date"
            }
            if (L.get("manual") or {}).get("date") == L["day"]
            else {},
            "cosmetics": {
                "owned": L["cosmetics"]["owned"],
                "active": L["cosmetics"]["active"],
                "catalog": {
                    cid: {"category": c[0], "value": c[1], "name": c[2]}
                    for cid, c in M.COSMETICS.items()
                    if cid in L["cosmetics"]["owned"]
                },
            },
            "buffs": [
                {"id": b["id"], "name": M.CONSUMABLES[b["id"]][0], "effects": b["effects"]}
                for b in L["buffs"]
                if b["date"] == L["day"]
            ],
            "charms": L["charms"],
            "elixirs_left": max(0, M.ELIXIRS_PER_WEEK - L["week"].get("elixirs", 0)),
            "appearance": A.with_prefs(A.appearance(self.race, L["seed"], L["look"]), L.get("portrait_prefs") or {}),
            "portrait_prefs": dict(L.get("portrait_prefs") or {}),
            "portrait_choices": A.PORTRAIT_CHOICES,
            "body": self.body,
            "bounties": self._bounty_view(),
            "kids_mode": self.kids_mode,
            "lore": L["lore"],
            "lune_chat": L["lune_chat"],
            "history": L["hist"][-30:],
            "log": L["log"][-60:][::-1],
            "stats": {k: round(v) for k, v in counters.items() if not k.startswith(("hidden:", "qstreak:"))},
        }

    def _item_view_raw(self, item: dict[str, Any]) -> dict[str, Any]:
        """A gear item as the market shows it: its effects, power and price."""
        return {**item, "effects": LT.item_effects(item), "power": LT.item_power(item), "price": M.gear_price(item)}

    def _badge_view(self, b: tuple, counters: dict[str, float]) -> dict[str, Any]:
        """A badge with its tier and progress toward the next."""
        bid, name, icon, counter, base = b
        value = counters.get(counter, 0)
        tier = badge_tier(value, base)
        th = badge_thresholds(base, tier + 1)
        return {
            "id": bid,
            "name": name,
            "icon": icon,
            "tier": tier,
            "tier_name": badge_tier_name(tier),
            "value": round(value),
            "next": th[tier],
            "prev": th[tier - 1] if tier else 0,
        }

    def _item_view(self, item: dict[str, Any]) -> dict[str, Any]:
        """A gear item as the inventory shows it: effects, power, enhance cost, salvage and sale values."""
        return {
            **item,
            "effects": LT.item_effects(item),
            "power": LT.item_power(item),
            "enhance_cost": LT.enhance_cost(item),
            "salvage": LT.salvage_value(item),
            "sell": M.sell_value(item),
            "equipped": self.L["equip"].get(item["slot"]) == item["id"],
        }

    # --- player actions ------------------------------------------------------------------------------
    def open_chest(self, chest_id: int) -> dict[str, Any]:
        """Open a chest; returns the item."""
        L = self.L
        chest = next((c for c in L["chests"] if c["id"] == chest_id), None)
        if chest is None:
            raise GameError("That chest is gone.")
        L["chests"].remove(chest)
        if chest["kind"] == "guardian":
            rank = chest["rank"] or "E"
            weights = LT.GUARDIAN_CHESTS.get(rank, LT.GUARDIAN_CHESTS["S+"])
        else:
            weights = LT.CHESTS.get(chest["kind"], LT.CHESTS["daily"])
        if chest.get("red"):
            weights = (0, *weights[:-2], weights[-2] + weights[-1])
        rng = self._rng("chest")
        rarity = LT.roll_rarity(rng, weights, self.effects().get("luck", 0) + L["charms"].pop("luck", 0))
        L["uid"] += 1
        item = LT.make_item(rng, L["uid"], rarity, list(self.goals), L["level"])
        L["inv"].append(item)
        self._stat("chests_opened")
        self._stat("legendaries", rarity >= 4)
        self._stat("mythics", rarity >= 5)
        if not L["equip"].get(item["slot"]):
            L["equip"][item["slot"]] = item["id"]
        while len(L["inv"]) > LT.INVENTORY_MAX:
            spare = [i for i in L["inv"] if i["id"] not in L["equip"].values() and i is not item]
            self.salvage(min(spare, key=LT.item_power)["id"])
        return self._item_view(item)

    def equip(self, item_id: int) -> None:
        """Equip an item in its slot."""
        if not (item := self._item(item_id)):
            raise GameError("No such item.")
        self.L["equip"][item["slot"]] = item_id

    def unequip(self, slot: str) -> None:
        """Empty a slot."""
        self.L["equip"].pop(slot, None)

    def salvage(self, item_id: int) -> int:
        """Break an unequipped item into shards."""
        item = self._item(item_id)
        if not item or item_id in self.L["equip"].values():
            raise GameError("Unequip it first.")
        self.L["inv"].remove(item)
        shards = LT.salvage_value(item)
        self.L["shards"] += shards
        return shards

    def enhance(self, item_id: int) -> None:
        """Spend shards to enhance an item (+5% to its affixes per level)."""
        if not (item := self._item(item_id)):
            raise GameError("No such item.")
        cost = LT.enhance_cost(item)
        if cost is None:
            raise GameError("Already at maximum enhancement.")
        if self.L["shards"] < cost:
            raise GameError(f"Needs {cost} shards.")
        self.L["shards"] -= cost
        item["enh"] += 1
        self._stat("enhancements")

    def set_title(self, title_id: str | None) -> None:
        """Equip an earned title (or none)."""
        if title_id and title_id not in self.L["titles"]:
            raise GameError("Title not earned yet.")
        self.L["title"] = title_id

    def set_job(self, job_id: str) -> None:
        """Change job. Every job keeps its own level, so switching never loses progress."""
        if job_id not in C.JOBS:
            raise GameError("No such job.")
        if self.L["level"] < C.JOB_UNLOCK_LEVEL:
            raise GameError(f"Jobs unlock at level {C.JOB_UNLOCK_LEVEL}.")
        L = self.L
        if L["job"] != job_id:
            s = self._summary(self.effects())
            if L["job"]:  # the job you leave banks what it earned today
                L["jobs"][L["job"]] = self._job_xp(L["job"]) + self._job_today(s)
            L["job"] = job_id  # counted with the new job's own bonuses, so they don't add to the morning's XP
            L["job_start"] = {
                "day": L["day"],
                "job": job_id,
                "gain": self._job_gain(self._summary(self.effects()), job_id),
            }
            L["job_levels"].setdefault(job_id, job_level(self._job_xp(job_id)))
            self._emit("job_change", job=C.JOBS[job_id]["name"])

    def answer_choice(self, accept: bool) -> None:
        """Say yes or no to today's choice."""
        ch = self.L["choice"]
        if not ch or ch["date"] != self.L["day"] or ch["status"] != "offered":
            raise GameError("There is no open choice right now.")
        ch["status"] = "accepted" if accept else "declined"
        if not accept:
            self._stat("choices_declined")

    # --- sensor sanity ---------------------------------------------------------------------------
    def working(self, when: datetime) -> bool:
        """Are you at work? A Home Assistant entity decides when one is set, otherwise the working hours."""
        if self.at_work is not None:
            return self.at_work
        w, minute, day = self.work, when.hour * 60 + when.minute, when.weekday()
        if w["start"] == w["end"]:
            return False
        if w["start"] < w["end"]:
            return day in w["days"] and w["start"] <= minute < w["end"]
        # a night shift past midnight: the part after midnight belongs to the day the shift started
        return (day in w["days"] and minute >= w["start"]) or ((day - 1) % 7 in w["days"] and minute < w["end"])

    def _fine(self) -> int:
        """What failing an emergency outside working hours costs: modest, and never more than 10% of your gold."""
        return int(min(FINE_BASE + FINE_PER_LEVEL * self.L["level"], FINE_MAX, self.L["gold"] * FINE_SHARE))

    def decline_emergency(self) -> int:
        """Turn down today's emergency quest. Returns the gold it cost (half the fine, outside working hours)."""
        e = self.L["emergency"]
        if not e or e["status"] not in ("scheduled", "active"):
            return 0
        fine = 0
        if e["status"] == "active" and not e.get("excused", True):
            fine = min(e.get("fine", 0) // 2, self.L["gold"])
            self.L["gold"] -= fine
            self._stat("emergency_fines", fine)
        e["status"] = "declined"
        if e.get("start"):
            self._emit("emergency_declined", quest=e["quest"], fine=fine, excused=e.get("excused", True))
        return fine
