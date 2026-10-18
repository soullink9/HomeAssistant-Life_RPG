"""Everything that comes in from outside the game: water units, the guard that holds back
impossible sensor jumps, corrections, and quests (water, stairs, sleep) logged by hand.

Part of the Game class (game.py), which mixes this in; `self` is that Game.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from . import content as C
from .rules import (
    DROP_CONFIRM,
    GUARD,
    MANUAL_LIMITS,
    QUEST_UNITS,
    SLEEP_MAX_H,
    SLEEP_MIN_H,
    WATER_UNITS,
    GameError,
    clock,
)


class InputsMixin:
    """Everything that comes in from outside the game: water units, the guard that holds back"""

    @property
    def water_label(self) -> str:
        """The name of the adventurer's water unit (mL or fl oz)."""
        return WATER_UNITS[self.water_unit][0]

    def water_out(self, ml: float) -> float:
        """mL to your water unit, for showing."""
        v = ml / WATER_UNITS[self.water_unit][1]
        v = round(v) if self.water_unit == "ml" else round(v, 1)
        return int(v) if v == int(v) else v

    def water_in(self, amount: float) -> float:
        """Your water unit to mL."""
        return float(amount) * WATER_UNITS[self.water_unit][1]

    def _guard(self, q: str, raw: float, now: datetime) -> tuple[float, bool]:
        """Believable value for today's sensor reading. Rises faster than a person could manage are held
        back (and you're told), the day has a ceiling, and a lower reading is followed once it has stuck
        for a while (a duplicate source removed). Returns (value, followed a drop)."""
        rate, burst, ceiling, notice = GUARD[q]
        raw = max(raw, 0.0)
        midnight = datetime.combine(now.date(), datetime.min.time(), tzinfo=now.tzinfo).isoformat()
        g = self.L.setdefault("guard", {}).setdefault(q, {"raw": None, "acc": 0.0, "held": 0.0, "t": midnight})
        if g["raw"] is not None and raw < g["raw"] and g["held"]:  # the source dropped: what we held back goes first
            g["held"] = max(0.0, g["held"] - (g["raw"] - raw))
        g["raw"] = raw
        value = max(raw - g["held"], 0.0)
        if value >= g["acc"]:
            g.pop("drop", None)
        if value > g["acc"]:
            minutes = max((now - datetime.fromisoformat(g["t"])).total_seconds() / 60, 0)
            allowed = min(g["acc"] + rate * minutes + burst, ceiling)
            if value > allowed:
                g["held"] += value - allowed
                value = allowed
                if g["held"] >= notice and self._once(f"held:{q}"):
                    held = self.water_out(g["held"]) if q == "hydration" else round(g["held"])
                    self._emit(
                        "reading_held",
                        quest=q,
                        name=C.QUEST_NAMES[q],
                        held=held,
                        unit=self.water_label if q == "hydration" else QUEST_UNITS[q],
                    )
            if value > g["acc"]:
                g["acc"], g["t"] = value, now.isoformat()
            return g["acc"], False
        if value < g["acc"]:
            d = g.get("drop")
            if d and now - datetime.fromisoformat(d["t"]) >= DROP_CONFIRM:
                g["acc"] = value
                g.pop("drop")
                return value, True
            if not d:
                g["drop"] = {"t": now.isoformat()}
        return g["acc"], False

    def _may_correct(self, quest: str) -> None:
        """Raise a GameError unless corrections are switched on for this quest."""
        if quest not in self.corrections:
            raise GameError(
                f"Corrections for {C.QUEST_NAMES.get(quest, quest)} are turned off. Turn them on under "
                "Configure → Quests and goals → Allow corrections, fix the count, then turn them off again."
            )

    def correct(self, quest: str, today: float | None = None, record: float | None = None) -> dict[str, Any]:
        """Set today's real count for a sensor quest, and/or your all-time best (both in the quest's unit,
        water in your water unit). Later readings follow the sensor from the corrected point."""
        L = self.L
        if quest not in GUARD or quest not in self.goals:
            raise GameError("Only steps, floors and water can be corrected.")
        self._may_correct(quest)
        conv = self.water_in if quest == "hydration" else float
        out: dict[str, Any] = {"quest": quest}
        try:
            today = None if today is None else conv(today)
            record = None if record is None else conv(record)
        except (TypeError, ValueError) as err:
            raise GameError("Give a number.") from err
        ceiling = GUARD[quest][2]
        if today is not None:
            if not 0 <= today <= ceiling:
                raise GameError("That's not a believable count for one day.")
            manual = L.get("manual") or {}
            logged = manual.get(quest, 0) if manual.get("date") == L["day"] else 0
            sensor = max(today - logged, 0.0)
            midnight = datetime.combine(self.now.date(), datetime.min.time(), tzinfo=self.now.tzinfo).isoformat()
            g = L.setdefault("guard", {}).setdefault(quest, {"raw": None, "acc": 0.0, "held": 0.0, "t": midnight})
            g.update(acc=sensor, held=max((g["raw"] or 0.0) - sensor, 0.0), t=self.now.isoformat())
            g.pop("drop", None)
            value = sensor + logged
            L["today"][quest] = [value, self.ratio(quest, value)]
            self._stat(f"corrected:{quest}")
            out["today"] = self.water_out(value) if quest == "hydration" else round(value)
        if record is not None:
            if not 0 <= record <= ceiling:
                raise GameError("That's not a believable record.")
            L["best"][quest] = record
            out["record"] = self.water_out(record) if quest == "hydration" else round(record)
        if len(out) == 1:
            raise GameError("Give today's count, a record, or both.")
        return out

    def accept_held(self, quest: str) -> float:
        """It really was that much: count what the sensor guard held back today."""
        self._may_correct(quest)
        g = self.L.get("guard", {}).get(quest)
        if not g or not g.get("held"):
            raise GameError("Nothing is held back for that quest.")
        g["acc"] = min(g["acc"] + g["held"], GUARD[quest][2])
        g["held"], g["t"] = 0.0, self.now.isoformat()
        manual = self.L.get("manual") or {}
        value = g["acc"] + (manual.get(quest, 0) if manual.get("date") == self.L["day"] else 0)
        self.L["today"][quest] = [value, self.ratio(quest, value)]
        return self.water_out(value) if quest == "hydration" else round(value)

    def log_quest(self, quest: str, amount: float) -> float:
        """Add (or, with a negative amount, take back) water (in your water unit) or flights of stairs.
        Returns today's logged total, in the same unit."""
        L = self.L
        if quest not in MANUAL_LIMITS or quest not in self.goals:
            raise GameError("That quest can't be logged here.")
        step, cap = MANUAL_LIMITS[quest]
        try:
            amount = float(amount)
        except (TypeError, ValueError) as err:
            raise GameError("Give an amount.") from err
        if quest == "hydration":
            amount = self.water_in(amount)
        if not amount or not -step <= amount <= step or amount != amount:
            most = f"{self.water_out(step):,g} {self.water_label}" if quest == "hydration" else f"{step:,}"
            raise GameError(f"Log up to {most} at a time.")
        m = L.setdefault("manual", {})
        if m.get("date") != L["day"]:
            m.clear()
            m["date"] = L["day"]
        old = m.get(quest, 0)
        new = round(min(max(old + amount, 0), cap), 1)
        m[quest] = new
        if new < old and (cur := L["today"].get(quest)):  # an undo takes it off today's progress too
            value = max(cur[0] - (old - new), 0)
            L["today"][quest] = [value, self.ratio(quest, value)]
        self._stat(f"logged:{quest}", max(new - old, 0))
        return self.water_out(new) if quest == "hydration" else new

    def log_sleep(self, start: datetime, end: datetime) -> float:
        """Record last night's sleep by hand (it counts toward the day you woke up). Returns hours."""
        hours = (end - start).total_seconds() / 3600
        if not SLEEP_MIN_H <= hours <= SLEEP_MAX_H:
            raise GameError(f"A night's sleep is between {SLEEP_MIN_H:g} and {SLEEP_MAX_H:g} hours.")
        if end.date() != self.now.date() or end > self.now + timedelta(minutes=5):
            raise GameError("Log the sleep you woke up from today.")
        if "sleep" not in self.goals:
            raise GameError("There's no Rest quest to log.")
        sessions = self.L["inputs"].setdefault("sleep", {})
        sessions[f"manual:{start.isoformat()}"] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "min": round(hours * 60, 1),
        }
        return round(hours, 2)

    def log_bedtime(self, start: datetime) -> str:
        """Record only when you fell asleep (Lights out), without adding to Rest: for when a sleep app reports how
        long you slept but not when, or you'd rather just log your bedtime. Returns the time, as shown."""
        if "bedtime" not in self.goals:
            raise GameError("There's no Lights out quest. Turn it on under Configure → Quests and goals.")
        if not self.now - timedelta(hours=24) <= start <= self.now + timedelta(minutes=5):
            raise GameError("Log when you fell asleep last night.")
        sessions = self.L["inputs"].setdefault("sleep", {})
        for k in [k for k in sessions if k.startswith("bed:")]:  # the latest one you logged counts
            del sessions[k]
        sessions[f"bed:{start.isoformat()}"] = {
            "start": start.isoformat(),
            "end": start.isoformat(),
            "min": 0,
            "bed": True,
        }
        return clock(start.hour * 60 + start.minute, self.twelve)

    @staticmethod
    def sleep_totals(sessions: dict[str, Any]) -> tuple[float | None, int | None]:
        """(hours slept, minute of day the main sleep began) from today's sessions. Sessions that overlap are
        the same sleep reported twice (two apps, a revised session, or logged by hand as well), so each
        overlapping group counts once, at its most complete report; separate naps add up."""
        if not sessions:
            return None, None
        timed, loose, bed = [], [], None
        for s in sessions.values():
            if isinstance(s, dict) and s.get("bed"):  # a bedtime logged on its own: it sets Lights out, adds no Rest
                bed = datetime.fromisoformat(s["start"]).replace(tzinfo=None)
                continue
            if not isinstance(s, dict):  # a bare duration with no times
                loose.append(float(s))
                continue
            start, end, minutes = datetime.fromisoformat(s["start"]), datetime.fromisoformat(s["end"]), float(s["min"])
            start, end = start.replace(tzinfo=None), end.replace(tzinfo=None)  # both local wall-clock times
            timed.append((start, max(end, start), max(minutes, 0.0)))
        bed_min = bed.hour * 60 + bed.minute if bed else None
        if not timed:
            return (max(loose) / 60 if loose else None), bed_min
        timed.sort(key=lambda t: t[0])
        groups: list[list[tuple]] = []
        for t in timed:
            if groups and t[0] < max(x[1] for x in groups[-1]):
                groups[-1].append(t)
            else:
                groups.append([t])
        best = [max(g, key=lambda t: t[2]) for g in groups]
        hours = min(sum(t[2] for t in best) / 60, SLEEP_MAX_H)
        main = max(best, key=lambda t: t[2])[0]
        return hours, bed_min if bed_min is not None else main.hour * 60 + main.minute
