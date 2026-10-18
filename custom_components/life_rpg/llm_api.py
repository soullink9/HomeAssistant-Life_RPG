"""Life RPG tools for Assist: ask how you're doing, take the daily choice, shop and haggle by voice.

Turn it on in your conversation agent's options (e.g. Ollama → Configure → "Control Home Assistant":
tick "Life RPG" alongside "Assist"). The tools act for the adventurer linked to whoever is talking;
voice satellites without a signed-in user act for the only adventurer, or the one you name.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType
import voluptuous as vol

from .const import DOMAIN
from .engine.market import CONSUMABLES
from .engine.rules import GameError

PROMPT = (
    "Life RPG turns the user's health habits into a role-playing game. Use the life_rpg tools when they ask about "
    "their level, quests, streak, labyrinth guardian, daily choice, chests, gear, gold or the market, or want to "
    "talk to their goddess (her name is in the status). When they say they drank water, climbed stairs or slept, "
    "log it with life_rpg_log or life_rpg_log_sleep (water goes in the adventurer's water unit from the status, mL or fl oz; a glass is about 250 mL or 8 fl oz). If they say a count is wrong (for example steps counted twice), fix it with life_rpg_fix_count. Speak briefly, like a game's System voice. Only state numbers the tools return. "
    "Haggling: offer a price with life_rpg_haggle; the merchant's answer and price come back from the tool."
)
ADVENTURER = vol.Optional("adventurer", description="Adventurer name, only if the household has several")


def _coordinators(hass: HomeAssistant) -> list[Any]:
    """Every loaded adventurer's coordinator."""
    return [e.runtime_data for e in hass.config_entries.async_loaded_entries(DOMAIN)]


async def _pick(hass: HomeAssistant, ctx: llm.LLMContext, name: str | None, act: bool) -> Any:
    """The adventurer this request is about, checking the speaker may act for them."""
    coords = [c for c in _coordinators(hass) if c.data]
    if not coords:
        raise HomeAssistantError("No Life RPG adventurers are set up.")
    user_id = ctx.context.user_id if ctx.context else None
    if name:
        found = [c for c in coords if c.config_entry.title.casefold() == name.casefold()] or [
            c for c in coords if name.casefold() in c.config_entry.title.casefold()
        ]
    elif user_id and (mine := [c for c in coords if c.user_id == user_id]):
        found = mine
    else:
        found = coords if len(coords) == 1 else []
    if not found:
        raise HomeAssistantError("Which adventurer? " + ", ".join(c.config_entry.title for c in coords))
    coord = found[0]
    if act and user_id and coord.user_id and coord.user_id != user_id:
        user = await hass.auth.async_get_user(user_id)
        if not (user and user.is_admin):
            raise HomeAssistantError(f"Only {coord.config_entry.title} can do that.")
    return coord


def _match(items: list[dict[str, Any]], ref: str, label: str) -> dict[str, Any]:
    """Find an item by id or (part of) its name."""
    ref = str(ref).strip()
    if ref.isdigit():
        hit = [i for i in items if str(i["id"]) == ref]
    else:
        hit = [i for i in items if i["name"].casefold() == ref.casefold()] or [
            i for i in items if ref.casefold() in i["name"].casefold()
        ]
    if not hit:
        raise HomeAssistantError(f"No {label} matches '{ref}'.")
    return hit[0]


def _stock(v: dict[str, Any]) -> list[dict[str, Any]]:
    """Today's market stock in a shape the LLM can read."""
    out = []
    for e in (v.get("market") or {}).get("stock", []):
        name = e["item"]["name"] if e["kind"] == "gear" else e["name"]
        out.append(
            {
                "id": e["id"],
                "name": name,
                "kind": e["kind"],
                "price": e["price"],
                "list_price": e["list"],
                "sold": e["sold"],
                "deal_struck": e["deal"],
                "haggling_over": e["closed"],
                **(
                    {"rarity": e["item"]["rarity"], "slot": e["item"]["slot"], "gear_score_change": e["upgrade"]}
                    if e["kind"] == "gear"
                    else {"description": e.get("desc", e.get("category", ""))}
                ),
            }
        )
    return out


class _Tool(llm.Tool):
    """Base class for the tools: picks the adventurer, checks permission and turns game errors into answers."""

    act = False

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        """Called by Home Assistant: find the adventurer, then run the tool."""
        args = dict(tool_input.tool_args)
        coord = await _pick(hass, llm_context, args.pop("adventurer", None), self.act)
        try:
            return await self.run(coord, **args)
        except GameError as err:
            return {"success": False, "error": str(err)}

    async def run(self, coord: Any, **args: Any) -> JsonObjectType:
        """The tool's work; each tool overrides this."""
        raise NotImplementedError


class Status(_Tool):
    """Tool: the adventurer's status."""

    name = "life_rpg_status"
    description = (
        "The adventurer's level, rank, streak, today's quests, labyrinth guardian, daily choice, chests and gold."
    )
    parameters = vol.Schema({ADVENTURER: str})

    async def run(self, coord: Any) -> JsonObjectType:
        """Collect the status from the current view."""
        v = coord.data
        return {
            "adventurer": coord.config_entry.title,
            "level": v["level"],
            "rank": v["rank"],
            "xp_to_next_level": v["next_level_xp"] - v["xp"],
            "job": v["job"]["title"] if v["job"] else "Villager",
            "streak_days": v["streak"],
            "shields": v["shields"],
            "xp_today": v["xp_today"],
            "quests": {
                q["name"]: {
                    "percent": q["pct"],
                    "done": q["done"],
                    "value": q["value"],
                    "goal": q["goal"],
                    "unit": q.get("unit"),
                }
                for q in v["quests"].values()
            },
            "quests_done": v["done"],
            "quests_needed_to_clear_day": v["needed"],
            "day_cleared": v["cleared"],
            "penalty_quest": v["penalty"] if v["penalty"] and not v["penalty"]["met"] else None,
            "emergency_quest": v["emergency"] if v["emergency"] and v["emergency"]["status"] == "active" else None,
            "daily_choice": {"offer": v["choice"]["text"], "status": v["choice"]["status"]} if v["choice"] else None,
            "guardian": {
                "name": v["labyrinth"]["name"],
                "floor": v["labyrinth"]["floor"],
                "hp_left_percent": v["labyrinth"]["pct"],
                "defeated": v["labyrinth"]["defeated"],
            },
            "unopened_chests": len(v["gear"]["chests"]),
            "gold": v["gold"],
            "bag": {b["name"]: b["count"] for b in v["bag"]},
            "goddess": v["goddess"]["name"],
            "goddess_says": v["goddess"]["line"],
        }


class AnswerChoice(_Tool):
    """Tool: accept or decline the daily choice."""

    name = "life_rpg_answer_choice"
    description = "Accept or decline today's daily choice."
    parameters = vol.Schema(
        {vol.Required("accept", description="true to accept, false to decline"): bool, ADVENTURER: str}
    )
    act = True

    async def run(self, coord: Any, accept: bool) -> JsonObjectType:
        """Answer the choice."""
        await coord.async_action("answer_choice", accept=accept)
        return {"success": True, "choice": (coord.data["choice"] or {}).get("status")}


class OpenChests(_Tool):
    """Tool: open every chest."""

    name = "life_rpg_open_chests"
    description = "Open every waiting chest and say what was inside."
    parameters = vol.Schema({ADVENTURER: str})
    act = True

    async def run(self, coord: Any) -> JsonObjectType:
        """Open the chests and list the finds."""
        items = await coord.async_action("open_all") or []
        return {"opened": len(items), "found": [f"{i['rarity']} {i['name']}" for i in items]}


class Inventory(_Tool):
    """Tool: list gear and consumables."""

    name = "life_rpg_inventory"
    description = "List gear (equipped and spare) with sale values, plus consumables in the bag."
    parameters = vol.Schema({ADVENTURER: str})

    async def run(self, coord: Any) -> JsonObjectType:
        """List the inventory."""
        v = coord.data
        return {
            "gear": [
                {
                    "id": i["id"],
                    "name": i["name"],
                    "rarity": i["rarity"],
                    "slot": i["slot"],
                    "power": i["power"],
                    "equipped": i["equipped"],
                    "sells_for": i["sell"],
                }
                for i in v["gear"]["inventory"]
            ],
            "bag": [{"id": b["id"], "name": b["name"], "count": b["count"], "effect": b["desc"]} for b in v["bag"]],
            "gold": v["gold"],
        }


class Equip(_Tool):
    """Tool: equip a piece of gear."""

    name = "life_rpg_equip"
    description = "Equip a piece of gear by name or id."
    parameters = vol.Schema({vol.Required("item", description="Item name or id"): str, ADVENTURER: str})
    act = True

    async def run(self, coord: Any, item: str) -> JsonObjectType:
        """Equip the matching item."""
        it = _match(coord.data["gear"]["inventory"], item, "item")
        await coord.async_action("equip", item_id=it["id"])
        return {"success": True, "equipped": it["name"]}


class Sell(_Tool):
    """Tool: sell spare gear."""

    name = "life_rpg_sell"
    description = "Sell a spare (unequipped) item to the merchant for gold. Use item 'junk' to sell all common spares."
    parameters = vol.Schema({vol.Required("item", description="Item name or id, or 'junk'"): str, ADVENTURER: str})
    act = True

    async def run(self, coord: Any, item: str) -> JsonObjectType:
        """Sell the matching item, or every common spare for 'junk'."""
        inv = [i for i in coord.data["gear"]["inventory"] if not i["equipped"]]
        targets = (
            [i for i in inv if i["rarity"] == "common"]
            if item.strip().casefold() == "junk"
            else [_match(inv, item, "spare item")]
        )
        gold = 0
        for it in targets:
            gold += await coord.async_action("sell", item_id=it["id"])
        return {"sold": [t["name"] for t in targets], "gold_received": gold, "gold": coord.data["gold"]}


class Shop(_Tool):
    """Tool: show the market."""

    name = "life_rpg_shop"
    description = "What the merchant Marrow Fennick is selling today, with prices."
    parameters = vol.Schema({ADVENTURER: str})

    async def run(self, coord: Any) -> JsonObjectType:
        """List today's stock."""
        m = coord.data.get("market") or {}
        return {
            "merchant_mood": m.get("mood"),
            "merchant_temper": m.get("temper"),
            "today's cart": m.get("theme_text"),
            "next_delivery": m.get("next_delivery") or "midnight",
            "stock": _stock(coord.data),
            "gold": coord.data["gold"],
        }


class Buy(_Tool):
    """Tool: buy from the market."""

    name = "life_rpg_buy"
    description = "Buy something from today's market at its current price."
    parameters = vol.Schema({vol.Required("item", description="Name or id from the shop list"): str, ADVENTURER: str})
    act = True

    async def run(self, coord: Any, item: str) -> JsonObjectType:
        """Buy the matching item."""
        e = _match([s for s in _stock(coord.data) if not s["sold"]], item, "item for sale")
        await coord.async_action("buy", stock_id=e["id"])
        return {"success": True, "bought": e["name"], "paid": e["price"], "gold_left": coord.data["gold"]}


class Haggle(_Tool):
    """Tool: haggle or walk away."""

    name = "life_rpg_haggle"
    description = (
        "Haggle with the merchant over an item in today's market: offer a price (he accepts, counters, holds "
        "firm or takes offence at a lowball; raising the offer a little each round works best), or walk away "
        "(he sometimes calls you back with a better price)."
    )
    parameters = vol.Schema(
        {
            vol.Required("item", description="Name or id from the shop list"): str,
            vol.Optional("offer", description="Gold offered"): vol.Coerce(int),
            vol.Optional("walk_away", description="True to turn away from the deal"): bool,
            ADVENTURER: str,
        }
    )
    act = True

    async def run(self, coord: Any, item: str, offer: int | None = None, walk_away: bool = False) -> JsonObjectType:
        """Make the offer, or walk away."""
        e = _match([s for s in _stock(coord.data) if not s["sold"]], item, "item for sale")
        if walk_away or offer is None:
            res = await coord.async_action("walk_away", stock_id=e["id"])
        else:
            res = await coord.async_action("haggle", stock_id=e["id"], offer=offer)
        return {**res, "item": e["name"], "note": "accepted or called_back means they can now buy at this price"}


class UseItem(_Tool):
    """Tool: use a consumable."""

    name = "life_rpg_use"
    description = "Use a consumable from the bag (elixir, charm, scroll, feather...)."
    parameters = vol.Schema({vol.Required("item", description="Consumable name or id"): str, ADVENTURER: str})
    act = True

    async def run(self, coord: Any, item: str) -> JsonObjectType:
        """Use the matching consumable."""
        bag = [{"id": cid, "name": CONSUMABLES[cid][0]} for cid in coord.game.L["bag"]]
        it = _match(bag, item, "consumable")
        msg = await coord.async_action("use", consumable=it["id"])
        return {"success": True, "used": it["name"], "effect": msg}


class LogQuest(_Tool):
    """Tool: log water or stairs by hand."""

    name = "life_rpg_log"
    description = (
        "Log water drunk (in the adventurer's water unit: mL or fl oz) or flights of stairs climbed toward "
        "today's quest. Negative amounts undo."
    )
    parameters = vol.Schema(
        {
            vol.Required("quest", description="water or stairs"): vol.In(["water", "stairs"]),
            vol.Required("amount", description="water in the adventurer's unit, or number of flights"): vol.Coerce(
                float
            ),
            ADVENTURER: str,
        }
    )
    act = True

    async def run(self, coord: Any, quest: str, amount: float) -> JsonObjectType:
        """Log the amount."""
        q = "hydration" if quest == "water" else "floors"
        total = await coord.async_action("log", quest=q, amount=amount)
        return {
            "success": True,
            "logged": amount,
            "today_total": total,
            "unit": coord.data["quests"][q]["unit"] if q == "hydration" else "flights",
            "quest_percent": coord.data["quests"][q]["pct"],
        }


class FixCount(_Tool):
    """Tool: fix a wrong count."""

    name = "life_rpg_fix_count"
    description = (
        "Set today's real count for steps, floors or water when the sensor got it wrong (for example two "
        "apps counting the same steps). Water is in the adventurer's water unit."
    )
    parameters = vol.Schema(
        {
            vol.Required("quest"): vol.In(["steps", "floors", "water"]),
            vol.Required("today", description="the real count for today"): vol.Coerce(float),
            ADVENTURER: str,
        }
    )
    act = True

    async def run(self, coord: Any, quest: str, today: float) -> JsonObjectType:
        """Set today's real count."""
        q = {"water": "hydration"}.get(quest, quest)
        res = await coord.async_action("correct", quest=q, today=today)
        return {
            "success": True,
            **res,
            "unit": coord.data["quests"][q]["unit"],
            "quest_percent": coord.data["quests"][q]["pct"],
        }


class Bounties(_Tool):
    """Tool: the bounty board, and marking a bounty done."""

    name = "life_rpg_bounties"
    description = (
        "The bounty board: today's side quests and chores. Pass `done` with the task they say they finished "
        "to mark it done (chores in kids mode then wait for a parent's approval)."
    )
    parameters = vol.Schema(
        {vol.Optional("done", description="The bounty they finished, in their words"): str, ADVENTURER: str}
    )
    act = True

    async def run(self, coord: Any, done: str | None = None) -> JsonObjectType:
        """Mark the best-matching open bounty done (if `done` is given), then list the board."""
        board = coord.data.get("bounties", [])
        out: JsonObjectType = {}
        if done:
            words = {w for w in done.lower().split() if len(w) > 2}
            best = max(
                (b for b in board if b["state"] == "open"),
                key=lambda b: len(words & set(b["title"].lower().split())),
                default=None,
            )
            if best is None or not words & set(best["title"].lower().split()):
                return {
                    "success": False,
                    "error": "No open bounty matches that.",
                    "open": [b["title"] for b in board if b["state"] == "open"],
                }
            out["result"] = await coord.async_action("claim_bounty", bounty_id=best["id"])
            out["bounty"] = best["title"]
            board = coord.data.get("bounties", [])
        out["board"] = [
            {
                "title": b["title"],
                "state": b["state"],
                "xp": b["xp"],
                "gold": b["gold"],
                "chest": b["chest"],
                "kind": "chore" if b["source"] == "chore" else "side quest",
            }
            for b in board
        ]
        return out


class LogSleep(_Tool):
    """Tool: log last night's sleep."""

    name = "life_rpg_log_sleep"
    description = (
        "Log last night's sleep from bedtime and wake-up time (24-hour HH:MM). Without a wake-up time only the "
        "bedtime (Lights out quest) is logged."
    )
    parameters = vol.Schema(
        {
            vol.Required("bedtime", description="e.g. 22:45"): str,
            vol.Optional("wake", description="e.g. 06:30"): str,
            ADVENTURER: str,
        }
    )
    act = True

    async def run(self, coord: Any, bedtime: str, wake: str | None = None) -> JsonObjectType:
        """Log bedtime and, if given, wake-up time."""
        res = await coord.async_action("log_sleep", bedtime=bedtime, wake=wake)
        if not wake:
            return {
                "success": True,
                "fell_asleep": res,
                "lights_out_percent": coord.data["quests"].get("bedtime", {}).get("pct"),
            }
        return {"success": True, "hours": res, "rest_quest_percent": coord.data["quests"].get("sleep", {}).get("pct")}


class TalkToGoddess(_Tool):
    """Tool: talk to the goddess."""

    name = "life_rpg_talk_to_goddess"
    description = "Pass a message to the user's goddess and get her reply (read it out in her words)."
    parameters = vol.Schema({vol.Required("message"): str, ADVENTURER: str})
    act = True

    async def run(self, coord: Any, message: str) -> JsonObjectType:
        """Pass the message on and return her reply (and any gift)."""
        res = await coord.async_chat("lune", message)
        out: JsonObjectType = {"goddess": coord.game.goddess, "she_says": res["reply"]}
        if res.get("gift"):
            out["gift"] = f"{res['gift']['name']}: {res['gift']['desc']} (already in their inventory)"
        return out


class LifeRPGAPI(llm.API):
    """The Life RPG toolset."""

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        """Tools for this conversation."""
        tools = [
            Status(),
            AnswerChoice(),
            OpenChests(),
            Inventory(),
            Equip(),
            Sell(),
            Shop(),
            Buy(),
            Haggle(),
            UseItem(),
            LogQuest(),
            FixCount(),
            LogSleep(),
            Bounties(),
            TalkToGoddess(),
        ]
        return llm.APIInstance(api=self, api_prompt=PROMPT, llm_context=llm_context, tools=tools)
