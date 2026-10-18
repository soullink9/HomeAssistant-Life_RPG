"""The bounty board: a few small daily side quests, and in kids mode the chores a parent posts
and approves.

Part of the Game class (game.py), which mixes this in; `self` is that Game.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from . import content as C
from .rules import (
    BOUNTY_MAX,
    BOUNTY_REPEATS,
    CHORE_GOLD_MAX,
    CHORE_XP_MAX,
    GameError,
)


class BountyMixin:
    """The bounty board: a few small daily side quests, and in kids mode the chores a parent posts"""

    def _bounty_reward(self) -> tuple[int, int]:
        """XP and gold for one daily side quest: a small boost, well below a day's quests. Up to three each pay
        in full; every one past three adds half as much again, shared out over all of them."""
        n = max(self.daily_bounties, 1)
        share = min(n, 3 + (n - 3) * 0.5) / n
        return round((30 + self.L["level"]) * share), round((15 + self.L["level"] // 2) * share)

    def _daily_bounties(self, today: date) -> None:
        """Yesterday's side quests go; today's arrive. One of them carries a bounty chest."""
        L = self.L
        L["bounties"] = [b for b in L.get("bounties", []) if b["source"] != "daily"]
        if not self.daily_bounties:
            return
        rng = self._rng("bounties")
        xp, gold = self._bounty_reward()
        for i in range(self.daily_bounties):
            L["uid"] += 1
            L["bounties"].append(
                {
                    "id": L["uid"],
                    "title": self._draw("bounties", C.DAILY_BOUNTIES, rng),
                    "xp": xp,
                    "gold": gold,
                    "chest": i == 0,
                    "source": "daily",
                    "repeat": "once",
                    "status": "open",
                    "date": today.isoformat(),
                    "done_on": None,
                }
            )

    def set_bounty_titles(self, day: str, titles: list[str]) -> None:
        """The LLM's wording for today's side quests (rewards stay the game's)."""
        open_daily = [
            b
            for b in self.L.get("bounties", [])
            if b["source"] == "daily" and b["date"] == day and b["status"] == "open"
        ]
        for b, t in zip(open_daily, titles):
            t = " ".join(str(t).split())[:80]
            if t:
                b["title"], b["written"] = t, True

    def _bounty(self, bounty_id: int) -> dict[str, Any]:
        """The bounty with this id, or a GameError if it has gone."""
        b = next((x for x in self.L.get("bounties", []) if x["id"] == bounty_id), None)
        if b is None:
            raise GameError("That bounty isn't on the board any more.")
        return b

    def _bounty_open(self, b: dict[str, Any]) -> bool:
        """Can it be done now? Repeating chores reopen each day (or each Monday)."""
        if b["status"] == "claimed" or not b.get("done_on"):
            return b["status"] == "open"
        done = date.fromisoformat(b["done_on"])
        today = self.now.date()
        if b["repeat"] == "daily":
            return done < today
        if b["repeat"] == "weekly":
            return done.isocalendar()[:2] < today.isocalendar()[:2]
        return False

    def add_bounty(
        self, title: str, xp: int, gold: int = 0, chest: bool = False, repeat: str = "once"
    ) -> dict[str, Any]:
        """A parent posts a chore (kids mode)."""
        if not self.kids_mode:
            raise GameError("Chores are for kids mode. Turn it on under Configure → Bounties.")
        title = " ".join(str(title or "").split())[:80]
        if not title:
            raise GameError("Name the chore.")
        if repeat not in BOUNTY_REPEATS:
            raise GameError("A chore is once, daily or weekly.")
        L = self.L
        if sum(b["source"] == "chore" for b in L["bounties"]) >= BOUNTY_MAX:
            raise GameError(f"The board holds {BOUNTY_MAX} chores. Remove one first.")
        xp, gold = max(0, min(int(xp), CHORE_XP_MAX)), max(0, min(int(gold), CHORE_GOLD_MAX))
        if not (xp or gold or chest):
            raise GameError("Give the chore a reward: XP, gold or a chest.")
        L["uid"] += 1
        b = {
            "id": L["uid"],
            "title": title,
            "xp": xp,
            "gold": gold,
            "chest": bool(chest),
            "source": "chore",
            "repeat": repeat,
            "status": "open",
            "date": self.now.date().isoformat(),
            "done_on": None,
        }
        L["bounties"].append(b)
        return b

    def remove_bounty(self, bounty_id: int) -> None:
        """Take a chore off the board (daily side quests can't be removed; they leave at midnight)."""
        b = self._bounty(bounty_id)
        if b["source"] != "chore":
            raise GameError("Daily side quests leave by themselves at midnight.")
        self.L["bounties"].remove(b)

    def claim_bounty(self, bounty_id: int) -> str:
        """ "I did it." A chore in kids mode waits for a parent; anything else pays out now. Returns the new status."""
        b = self._bounty(bounty_id)
        if not self._bounty_open(b):
            raise GameError(
                "That one's already done." if b["status"] != "claimed" else "That one is waiting for a parent."
            )
        if b["source"] == "chore" and self.kids_mode:
            b["status"] = "claimed"
            b["claimed_at"] = self.now.isoformat(timespec="minutes")
            self._emit("bounty_claimed", bounty=b["title"])
            return "claimed"
        self._pay_bounty(b)
        return "done"

    def approve_bounty(self, bounty_id: int, ok: bool = True) -> str:
        """A parent checks a claimed chore: approve to pay it, or send it back."""
        b = self._bounty(bounty_id)
        if b["status"] != "claimed":
            raise GameError("Nothing to approve there.")
        if not ok:
            b["status"] = "open"
            b.pop("claimed_at", None)
            return "open"
        self._pay_bounty(b)
        return "done"

    def _pay_bounty(self, b: dict[str, Any]) -> None:
        """Pay out a finished bounty: XP, gold and maybe a chest."""
        L = self.L
        L["bonus"] += b["xp"]
        if b["chest"]:
            self._chest("bounty")
        self._stat("bounties_done")
        self._emit("bounty_done", bounty=b["title"], xp=b["xp"], purse=b["gold"], chest=b["chest"], source=b["source"])
        if b["repeat"] == "once":
            L["bounties"].remove(b)
        else:
            b.update(status="open", done_on=self.now.date().isoformat())
            b.pop("claimed_at", None)

    def _bounty_view(self) -> list[dict[str, Any]]:
        """The board as the panel shows it, with each bounty's state (open, claimed or done)."""
        out = []
        for b in self.L.get("bounties", []):
            state = "claimed" if b["status"] == "claimed" else "open" if self._bounty_open(b) else "done"
            out.append({k: b[k] for k in ("id", "title", "xp", "gold", "chest", "source", "repeat")} | {"state": state})
        return out
