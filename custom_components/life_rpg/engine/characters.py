"""How you, the goddess and the merchant are painted (the Gallery's choices), and the words
the LLM writes: flavour text, chats, and the goddess's rare gifts.

Part of the Game class (game.py), which mixes this in; `self` is that Game.
"""

from __future__ import annotations

from datetime import date
import random
from typing import Any

from . import appearance as A, content as C, market as M
from .rules import (
    CHAT_MAX,
    GIFT_CONSUMABLES,
    GIFT_COOLDOWN,
    GIFT_MIN_DAYS,
    LORE_MAX,
    GameError,
)


class CharactersMixin:
    """How you, the goddess and the merchant are painted (the Gallery's choices), and the words"""

    def set_portrait_prefs(self, prefs: dict[str, Any]) -> dict[str, Any]:
        """How your portrait should look: age, framing, hair and eye colour, build and what you hold. Anything left
        out (or "") goes back to your rolled look and equipped weapon. Hair, eyes and build show in the pixel art too."""
        self.L["portrait_prefs"] = self._prefs(prefs, A.PORTRAIT_CHOICES)
        return self.L["portrait_prefs"]

    @staticmethod
    def _prefs(prefs: dict[str, Any], choices: dict[str, list]) -> dict[str, Any]:
        """Keep only the known choices with allowed values; raise a GameError for anything else."""
        clean: dict[str, Any] = {}
        for key, allowed in choices.items():
            val = prefs.get(key)
            if val in (None, ""):
                continue
            if val not in allowed:
                raise GameError(f"{key.capitalize()} can't be {val}.")
            clean[key] = val
        return clean

    def set_goddess_prefs(self, prefs: dict[str, Any]) -> dict[str, Any]:
        """How the goddess is painted: race, age, build, hair, eyes, outfit, backdrop and framing (anything left out: her
        usual look)."""
        self.L["goddess_prefs"] = self._prefs(prefs, A.GODDESS_CHOICES)
        return self.L["goddess_prefs"]

    def set_merchant_prefs(self, prefs: dict[str, Any]) -> dict[str, Any]:
        """How Marrow Fennick is painted: race, age, build, hair, outfit, accessory, backdrop and framing."""
        self.L["merchant_prefs"] = self._prefs(prefs, A.MERCHANT_CHOICES)
        return self.L["merchant_prefs"]

    def restyle(self) -> None:
        """A new look (hair, colours, features) for the same adventurer."""
        self.L["look"] += 1

    def repaint(self) -> None:
        """Ask for a fresh painting of the same adventurer."""
        self.L["portrait_v"] = self.L.get("portrait_v", 0) + 1

    def set_lore(self, kind: str, text: str, ref: Any = None) -> None:
        """Store LLM-written flavour text, trimmed and length-capped."""
        text = " ".join(str(text or "").split())[:LORE_MAX]
        if not text:
            return
        L = self.L
        if kind == "item":
            if item := self._item(ref):
                item["lore"] = text
        elif kind == "chronicle":
            L["lore"]["chronicle"] = (
                [c for c in L["lore"].get("chronicle", []) if c["week"] != ref] + [{"week": ref, "text": text}]
            )[-12:]
        else:
            L["lore"][kind] = {"ref": ref, "text": text}

    def gift_offer(self) -> dict[str, Any] | None:
        """Will the goddess give you something today? Decided once a day, by the game, from a seed: asking
        again (or asking nicely) never changes the answer. Returns the gift (not yet given) or None."""
        L, today = self.L, self.now.date()
        g = L.setdefault("gifts", {"last": None, "rolled": None, "log": []})
        if g["rolled"] == today.isoformat():
            return None
        days = sorted(set(L["lune_days"]) | {today.isoformat()})
        if len(days) < GIFT_MIN_DAYS:
            return None
        since = (today - date.fromisoformat(g["last"] or days[0])).days
        if g["last"] and since < GIFT_COOLDOWN:
            return None
        chance = min(0.3, 0.03 + 0.01 * min(L["devotion"], 5) + 0.004 * max(0, since - GIFT_COOLDOWN))
        rng = random.Random(f"{L['seed']}:gift:{today.isoformat()}")
        if rng.random() >= chance:
            return None
        owned = set(L["cosmetics"]["owned"])
        unowned = [c for c in M.COSMETICS if c not in owned]
        kinds = {"chest": 35, "potion": 45, "gold": 20, **({"cosmetic": 5} if unowned and L["devotion"] >= 2 else {})}
        kind = rng.choices(list(kinds), weights=list(kinds.values()))[0]
        if kind == "potion":
            cid = rng.choices(list(GIFT_CONSUMABLES), weights=list(GIFT_CONSUMABLES.values()))[0]
            return {"kind": kind, "id": cid, "name": M.CONSUMABLES[cid][0], "desc": M.CONSUMABLES[cid][1]}
        if kind == "cosmetic":
            cid = rng.choice(sorted(unowned))
            return {"kind": kind, "id": cid, "name": M.COSMETICS[cid][2], "desc": "A new look for your adventurer."}
        if kind == "gold":
            amount = round((100 + 10 * L["level"]) * rng.uniform(0.8, 1.3))
            return {
                "kind": kind,
                "id": "gold",
                "name": f"a purse of {amount:,} gold",
                "desc": "Spend it at the market.",
                "amount": amount,
            }
        return {"kind": kind, "id": "blessed", "name": "a blessed chest", "desc": "Better loot than most chests."}

    def settle_gift(self, gift: dict[str, Any] | None) -> dict[str, Any] | None:
        """After a conversation: today's roll is used up, and the gift (if any) is given."""
        L = self.L
        g = L.setdefault("gifts", {"last": None, "rolled": None, "log": []})
        today = self.now.date().isoformat()
        if g["rolled"] == today:
            return None
        g["rolled"] = today
        if not gift:
            return None
        g["last"] = today
        g["log"] = (g["log"] + [{"date": today, "kind": gift["kind"], "id": gift["id"]}])[-50:]
        if gift["kind"] == "potion":
            L["bag"][gift["id"]] = L["bag"].get(gift["id"], 0) + 1
        elif gift["kind"] == "cosmetic":
            if gift["id"] not in L["cosmetics"]["owned"]:
                L["cosmetics"]["owned"].append(gift["id"])
        elif gift["kind"] == "chest":
            self._chest("blessed")
        self._stat("goddess_gifts")
        self._emit(
            "goddess_gift",
            goddess=C.GODDESS,
            gift=gift["name"],
            kind=gift["kind"],
            desc=gift["desc"],
            purse=gift.get("amount", 0),
        )
        return gift

    def add_chat(self, who: str, role: str, text: str) -> None:
        """Remember a line of conversation with Lune (kept) or the merchant (today only)."""
        text = " ".join(str(text or "").split())[:LORE_MAX]
        if who == "lune":
            self.L["lune_chat"] = (self.L["lune_chat"] + [{"role": role, "text": text}])[-CHAT_MAX:]
            today = self.now.date().isoformat()
            if role == "user" and today not in self.L["lune_days"]:
                self.L["lune_days"] = (self.L["lune_days"] + [today])[-400:]
        elif self.L["shop"]:
            self.L["shop"]["chat"] = (self.L["shop"]["chat"] + [{"role": role, "text": text}])[-CHAT_MAX:]
