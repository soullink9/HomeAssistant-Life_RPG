"""Marrow Fennick's market: deliveries three times a day, buying, selling, haggling, and using
what you bought (potions, tonics, charms, crates, cosmetics). The haggling rules themselves are in market.py.

Part of the Game class (game.py), which mixes this in; `self` is that Game.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from . import appearance as A, loot as LT, market as M
from .rules import (
    SHIELD_MAX,
    GameError,
    clock,
    job_level,
)


class ShopMixin:
    """Marrow Fennick's market: deliveries three times a day, buying, selling, haggling, and using"""

    def _new_shop(self, today: date, wave: int = 0) -> None:
        """A delivery: the day's first at midnight, then two more at random times (M.restock_times)."""
        L = self.L
        rng = self._rng("shop")
        rapport = L.get("rapport", 0.0)
        old = L["shop"] if wave and L["shop"] and L["shop"].get("date") == today.isoformat() else None
        theme = M.pick_theme(rng, wave, L["cosmetics"]["owned"])
        stock, L["uid"] = M.make_stock(
            rng,
            L["uid"],
            L["level"],
            list(self.goals),
            today.weekday() == 6 and not wave,
            L["cosmetics"]["owned"],
            theme,
            rapport,
        )
        if old:  # a deal he agreed to waits for you; his mood usually carries on and his annoyance half fades
            stock = [e for e in old["stock"] if e["deal"] and not e["sold"]] + stock
            mood = old["mood"] if rng.random() < 0.6 else M.new_mood(rng, rapport)
            annoyance, restocks, chat = old.get("annoyance", 0.0) / 2, old.get("restocks", []), old.get("chat", [])
        else:
            mood, annoyance, restocks, chat = M.new_mood(rng, rapport), 0.0, M.restock_times(rng), []
            # opened late in the day (Home Assistant was off): deliveries already past count
            if self.now.date() == today:
                wave = sum(self.now.hour * 60 + self.now.minute >= t for t in restocks)
        L["shop"] = {
            "date": today.isoformat(),
            "wave": wave,
            "theme": theme,
            "mood": mood,
            "stock": stock,
            "chat": chat,
            "annoyance": round(annoyance, 2),
            "calm_at": self.now.timestamp(),
            "restocks": restocks,
        }

    def market_seen(self) -> bool:
        """Someone opened the Market: this delivery's goods are worth painting."""
        if self.L["shop"]:
            self.L["shop"]["seen"] = True
        return True

    def _deliveries(self, now: datetime) -> None:
        """New stock once a delivery time has passed (only the latest, if Home Assistant was away)."""
        shop = self.L["shop"]
        times, wave = shop.get("restocks") or [], shop.get("wave", 0)
        minute = now.hour * 60 + now.minute
        due = [i + 1 for i, t in enumerate(times) if minute >= t and i + 1 > wave]
        if due and now.date().isoformat() == shop["date"]:
            self._new_shop(now.date(), due[-1])
            theme = self.L["shop"]["theme"]
            self._emit("market_restocked", theme=theme, what=M.THEMES[theme][4])

    def _market_view(self) -> dict[str, Any] | None:
        """Today's market as the panel shows it (floor prices stay secret)."""
        shop = self.L["shop"]
        if not shop:
            return None
        stock = []
        for e in shop["stock"]:
            out = {k: e[k] for k in ("id", "kind", "list", "price", "rounds", "deal", "closed", "sold")}
            out["rounds_left"] = max(0, M.HAGGLE_ROUNDS - e["rounds"])
            out["offer"] = e.get("last_offer")
            out["why"] = e.get("why") if e["closed"] and not e["deal"] else None  # why he won't haggle on it
            if e["kind"] == "gear":
                out["item"] = {**self._item_view_raw(e["item"]), "sell": M.sell_value(e["item"])}
                out["featured"] = e.get("featured", False)
                cur = self._item(self.L["equip"].get(e["item"]["slot"]))
                out["upgrade"] = LT.item_power(e["item"]) - (LT.item_power(cur) if cur else 0)
            elif e["kind"] == "consumable":
                name, desc, _, icon, _ = M.CONSUMABLES[e["cid"]]
                out.update(cid=e["cid"], name=name, desc=desc, icon=icon)
            else:
                cat, _, name, _ = M.COSMETICS[e["cid"]]
                out.update(cid=e["cid"], name=name, category=cat)
            stock.append(out)
        M.cool(shop, self.now.timestamp())
        times, wave = shop.get("restocks") or [], shop.get("wave", 0)
        theme = shop.get("theme", "general")
        return {
            "date": shop["date"],
            "mood": shop["mood"],
            "face": M.face(shop.get("last_result"), shop),
            "prefs": dict(self.L.get("merchant_prefs") or {}),
            "choices": A.MERCHANT_CHOICES,
            "merchant": A.MERCHANT_NAME,
            "stock": stock,
            "temper": M.temper(shop),
            "annoyance": round(100 * shop.get("annoyance", 0.0) / M.ANNOY_MAX),
            "rapport": round(self.L.get("rapport", 0.0), 1),
            "theme": theme,
            "theme_text": M.THEMES.get(theme, M.THEMES["general"])[4],
            "delivery": wave + 1,
            "seen": bool(shop.get("seen")),
            "next_delivery": clock(times[wave], self.twelve) if wave < len(times) else None,
            "chat": shop.get("chat", []),
            "haggle_bonus": round(100 * self._haggle_bonus()),
        }

    def _bag_view(self) -> list[dict[str, Any]]:
        """The consumables in the bag, with names and counts."""
        out = []
        for cid, n in self.L["bag"].items():
            name, desc, _, icon, _ = M.CONSUMABLES[cid]
            out.append({"id": cid, "name": name, "desc": desc, "icon": icon, "count": n})
        return out

    def _stock(self, stock_id: int) -> dict[str, Any]:
        """A line of today's stock that's still for sale, or a GameError."""
        shop = self.L["shop"]
        entry = next((e for e in (shop or {}).get("stock", []) if e["id"] == stock_id), None)
        if entry is None or shop["date"] != self.L["day"]:
            raise GameError("That's no longer for sale.")
        if entry["sold"]:
            raise GameError("Already sold.")
        return entry

    def _spend(self, gold: int) -> None:
        """Take gold, or raise a GameError if there isn't enough."""
        if self.L["gold"] < gold:
            raise GameError(f"Needs {gold:,} gold (you have {self.L['gold']:,}).")
        self.L["gold"] -= gold
        self._stat("gold_spent", gold)

    def buy(self, stock_id: int) -> dict[str, Any]:
        """Buy something from today's stock at its current price."""
        L, entry = self.L, self._stock(stock_id)
        if entry["kind"] == "gear" and len(L["inv"]) >= LT.INVENTORY_MAX:
            raise GameError("Your inventory is full. Sell or salvage something first.")
        if entry["kind"] == "cosmetic" and entry["cid"] in L["cosmetics"]["owned"]:
            raise GameError("You already own that.")
        self._spend(entry["price"])
        entry["sold"] = True
        self._stat("purchases")
        # he likes a customer who pays a fair price, haggled or not
        self._rapport(0.5 if entry["price"] >= entry["floor"] else 0.2)
        if entry["price"] < entry["list"]:
            self._stat("deals")
            if entry["price"] <= entry["list"] * 0.75:
                self._discover("bargain_hunter")
        if entry["kind"] == "gear":
            item = dict(entry["item"], lvl=entry["item"]["lvl"])
            L["inv"].append(item)
            if not L["equip"].get(item["slot"]):
                L["equip"][item["slot"]] = item["id"]
            return {"bought": self._item_view(item)}
        if entry["kind"] == "consumable":
            L["bag"][entry["cid"]] = L["bag"].get(entry["cid"], 0) + 1
        else:
            L["cosmetics"]["owned"].append(entry["cid"])
            cat = M.COSMETICS[entry["cid"]][0]
            L["cosmetics"]["active"].setdefault(cat, entry["cid"])
        return {"bought": entry["cid"]}

    def sell(self, item_id: int) -> int:
        """Sell an unequipped item for gold."""
        item = self._item(item_id)
        if not item or item_id in self.L["equip"].values():
            raise GameError("Unequip it first.")
        self.L["inv"].remove(item)
        gold = M.sell_value(item)
        self.L["gold"] += gold
        self._stat("gold_earned", gold)
        self._stat("items_sold")
        return gold

    def _haggle_bonus(self) -> float:
        """Bards talk prices down a little further (0.5% a job level, at most 15%)."""
        return min(0.15, job_level(self._job_xp("bard")) * 0.005) if self.L["job"] == "bard" else 0.0

    def _rapport(self, change: float) -> None:
        """Change how much the merchant likes you, kept within limits."""
        self.L["rapport"] = round(max(-M.RAPPORT_MAX, min(M.RAPPORT_MAX, self.L.get("rapport", 0.0) + change)), 2)

    def haggle(self, stock_id: int, offer: int) -> dict[str, Any]:
        """Offer a price for something in the market (see M.haggle for what can happen)."""
        entry = self._stock(stock_id)
        if offer < 1:
            raise GameError("Offer at least 1 gold.")
        shop = self.L["shop"]
        M.cool(shop, self.now.timestamp())
        res = M.haggle(entry, int(offer), self._haggle_bonus(), shop, self._rng("haggle"))
        if res["result"] in ("insulted", "refused", "fed_up"):
            self._discover("thin_skin")
            self._rapport(-1.0 if res["result"] == "fed_up" else -0.3)
        if res["result"] == "fed_up":
            self._stat("merchant_fed_up")
        if res["result"] != "closed":
            shop["last_result"] = res["result"]
        if res["result"] == "accepted" and entry["price"] < entry["list"]:
            self._emit("bargain_struck", item=self._stock_name(entry), price=entry["price"], list=entry["list"])
        return self._haggle_reply(res, entry, shop)

    def walk_away(self, stock_id: int) -> dict[str, Any]:
        """Turn to leave mid-haggle. Sometimes he calls you back with a better price."""
        entry = self._stock(stock_id)
        shop = self.L["shop"]
        M.cool(shop, self.now.timestamp())
        res = M.walk_away(entry, shop, self.L.get("rapport", 0.0), self._rng("walk"), self._haggle_bonus())
        shop["last_result"] = res["result"]
        if res["result"] == "called_back":
            self._emit("bargain_struck", item=self._stock_name(entry), price=entry["price"], list=entry["list"])
        return self._haggle_reply(res, entry, shop)

    def _haggle_reply(self, res: dict[str, Any], entry: dict[str, Any], shop: dict[str, Any]) -> dict[str, Any]:
        """A haggle result with what the panel needs to show his answer."""
        return {
            **res,
            "list": entry["list"],
            "rounds_left": max(0, M.HAGGLE_ROUNDS - entry["rounds"]),
            "closed": entry["closed"] or entry["deal"],
            "temper": M.temper(shop),
            "face": M.face(res["result"], shop),
            "item": self._stock_name(entry),
        }

    def _stock_name(self, entry: dict[str, Any]) -> str:
        """The display name of a line of stock."""
        if entry["kind"] == "gear":
            return entry["item"]["name"]
        return (M.CONSUMABLES.get(entry.get("cid")) or M.COSMETICS.get(entry.get("cid")))[
            0 if entry["kind"] == "consumable" else 2
        ]

    def use(self, cid: str) -> str:
        """Use a consumable from the bag. Returns what happened."""
        L = self.L
        if not L["bag"].get(cid):
            raise GameError("You don't have one of those.")
        if cid in M.ELIXIRS:
            if L["week"].get("elixirs", 0) >= M.ELIXIRS_PER_WEEK:
                raise GameError(f"Only {M.ELIXIRS_PER_WEEK} elixirs, oils or tonics a week. More would stop working.")
            if cid in M.TONICS and M.TONICS[cid] not in self.goals:
                raise GameError("That tonic is for a quest you don't have.")
            if any(b["date"] == L["day"] and b["id"] == cid for b in L["buffs"]):
                raise GameError("That's already working today.")
            L["buffs"].append({"id": cid, "date": L["day"], "effects": M.BUFFS[cid]})
            L["week"]["elixirs"] = L["week"].get("elixirs", 0) + 1
            msg = M.CONSUMABLES[cid][1]
        elif cid == "lucky_charm":
            L["charms"]["luck"] = L["charms"].get("luck", 0) + 100
            msg = "Your next chest is blessed with luck."
        elif cid == "crate":
            self._chest("crate")
            msg = "The crate is in your chests, waiting to be opened."
        elif cid == "reroll":
            ch = L["choice"]
            if not ch or ch["date"] != L["day"] or ch["status"] != "offered":
                raise GameError("There's no open choice to swap.")
            L["choice"] = None
            self._offer_choice()
            if not L["choice"]:
                L["choice"] = ch
                raise GameError("Too late in the day for a new choice.")
            msg = "A new choice appears."
        elif cid == "hourglass":
            e = L["emergency"]
            if not e or e.get("status") != "active":
                raise GameError("There's no active emergency quest.")
            e["end"] = (datetime.fromisoformat(e["end"]) + timedelta(minutes=20)).isoformat(timespec="seconds")
            msg = "20 more minutes on the emergency quest."
        elif cid == "shield_charm":
            cap = SHIELD_MAX + int(self.effects().get("shield", 0))
            if L["shields"] >= cap:
                raise GameError(f"You already hold {cap} shields.")
            L["shields"] += 1
            msg = f"You now hold {L['shields']} streak shields."
        elif cid == "phoenix":
            brk, used = L["last_break"], L["phoenix_used"]
            if not brk or (self.now.date() - date.fromisoformat(brk["date"])).days > M.PHOENIX_DAYS:
                raise GameError(f"Only works within {M.PHOENIX_DAYS} days of losing a streak.")
            if used and (self.now.date() - date.fromisoformat(used)).days < M.PHOENIX_COOLDOWN:
                raise GameError(f"The feather needs {M.PHOENIX_COOLDOWN} days between uses.")
            L["streak"] += brk["streak"]
            L["best_streak"] = max(L["best_streak"], L["streak"])
            L["last_break"], L["phoenix_used"] = None, self.now.date().isoformat()
            msg = f"Your streak rises again: {L['streak']} days."
        else:
            raise GameError("Nothing happens.")
        L["bag"][cid] -= 1
        if not L["bag"][cid]:
            del L["bag"][cid]
        self._stat("potions_used")
        return msg

    def set_cosmetic(self, category: str, cid: str | None) -> None:
        """Wear an owned cosmetic (or none) in its category."""
        if category not in M.COSMETIC_CATEGORIES:
            raise GameError("No such cosmetic slot.")
        if cid is None:
            self.L["cosmetics"]["active"].pop(category, None)
            return
        if cid not in self.L["cosmetics"]["owned"] or M.COSMETICS[cid][0] != category:
            raise GameError("You don't own that.")
        self.L["cosmetics"]["active"][category] = cid
