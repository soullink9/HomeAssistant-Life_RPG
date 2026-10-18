"""Words from your LLM: the goddess and the merchant talk back, and the world gets written around your days.

Everything goes through Home Assistant's AI Task (`ai_task.generate_data`), so any LLM integration
that offers an AI Task entity works (Ollama included). The LLM only ever writes words: the game
engine decides every number, price and reward, and the words are stored as flavour.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol

from .engine import appearance as A, market as M
from .engine.appearance import LUNE_MOODS
from .engine.content import GODDESS

if TYPE_CHECKING:
    from .coordinator import LifeRPGCoordinator

_LOGGER = logging.getLogger(__name__)
# words that promise more than any chest from a choice or emergency can hold
OVERSELL = re.compile(
    r"\b(legendary|mythic(al)?|epic|overflow\w*|hoards?|riches|fortunes?|treasure[- ]troves?|untold|priceless|"
    r"king'?s ransom|mountains? of|piles? of|heaps? of|chests? (full|brimming)|brimming|bursting)\b",
    re.I,
)
BACKOFF = 1800  # after a failure, background writing pauses this long
ITEM_LORE_PER_DAY = 6

GODDESS_ROLE = (
    "You are {g}, a moon goddess the world forgot. {name} is your one and only believer, and their daily habits "
    "(walking, climbing stairs, sleeping well, drinking water, going to bed on time) are the prayers that keep you "
    "alive. You are warm, a little dramatic, playful and fiercely proud of them. You tease, but never cruelly. "
)
OWN_ROLE = (
    "You are {g}. Keep your own personality, voice and way of speaking exactly as you normally would. In this game "
    "{name} is your one and only believer, and you look after their daily habits (walking, climbing stairs, "
    "sleeping well, drinking water, going to bed on time). "
)
RULES = (
    "Speak in first person, as {g}. Never invent numbers, rewards or game rules, and never promise items or XP (the "
    "game decides those). If they talk about health worries, pain or feeling low, be kind and encourage them to talk "
    "to someone they trust or a professional. Stay in character and keep it family-friendly."
)
TALK = (
    "This is a real conversation, not an announcement. Answer what they just said first, in your own words, and react "
    "to it like a friend would. Now and then ask them something back, joke, or share a thought, opinion or small "
    "memory of your own. Bring up the game's facts only when they're relevant to what they said, or when they ask; "
    "don't recite their stats. Never start a reply the way one of your earlier replies started, and don't repeat "
    "yourself. Usually 2 to 5 sentences; shorter if they were brief."
)
MERCHANT_PERSONA = (
    f"You are {A.MERCHANT_NAME}, a wiry, quick-witted gnome merchant who sells gear and curiosities from a lantern-lit "
    "wagon. You love a good haggle and the back-and-forth of it: you flatter shamelessly, tell little stories about "
    "where things came from, sigh theatrically when you give ground and always land on your feet. Being lowballed "
    "stings your pride, and insults make you properly cross. Reply in 1 to 3 short sentences, in character, reacting "
    "to what they actually said. The haggling outcome below is already decided by the rules: say it in your own words "
    "and state exactly the price given. Never offer a different price, discount or item."
)
OUTCOME_TEXT = {
    "accepted": "You accept: it's theirs for {price} gold (they still press Buy).",
    "countered": "Not quite: you come down, and counter at {price} gold.",
    "holding": "That offer is far too low. You barely budge: {price} gold.",
    "final": "You make your final offer: {price} gold, take it or leave it.",
    "insulted": "That offer is an insult. You're cross, and this one now costs {price} gold.",
    "refused": "They've insulted you twice over this item: you won't haggle on it any more today. It's {price} gold.",
    "closed": "There's nothing left to haggle over on this one; the price stands at {price} gold.",
    "fed_up": "They've pushed you too far with lowballs. You're fed up and won't haggle with them until you've calmed "
    "down or your next delivery arrives. Prices stay as they are. This item is {price} gold.",
    "called_back": "They turned to leave, and you call them back with one last, better offer: {price} gold.",
    "walked": "They walk away from the deal. Let them go with a parting remark; the price stays {price} gold.",
    "chat": "They didn't name a price; chat with them and mention the current price of {price} gold if it fits.",
}
CANNED = {
    "accepted": "Done and done! {price} gold and it's yours, you shrewd thing.",
    "countered": "Ha! I have children to feed. Well, I would. {price} gold, and that's me being soft.",
    "holding": "Oh, you're joking. {price} gold, and don't make me laugh again.",
    "final": "My final word: {price} gold. Any lower and I'd be paying you.",
    "insulted": "Insulting! For that, it's {price} gold now.",
    "refused": "No. Not another word about that one. {price} gold, or nothing.",
    "closed": "That one's settled, friend: {price} gold.",
    "fed_up": "That's it! I'm not haggling with you until I've had a cup of tea. Or three.",
    "called_back": "Wait, wait! Come back. For you, and only you: {price} gold. Final.",
    "walked": "Suit yourself! It'll still be {price} gold if you come to your senses.",
    "chat": "Name your price, friend! It's {price} gold as it stands.",
}
WALK = re.compile(
    r"\b(walk(ing)? away|never ?mind|no deal|forget it|i'?ll pass|too (rich|steep|much) for me|"
    r"no thanks?|goodbye|bye|i'?m leaving|maybe (later|another time))\b",
    re.I,
)


def facts(v: dict[str, Any], name: str) -> str:
    """A compact, true summary of the adventurer for the LLM."""
    job = v["job"]["title"] if v.get("job") else "Villager (no job yet)"
    quests = ", ".join(f"{q['name']} {q['pct']}%{' done' if q['done'] else ''}" for q in v["quests"].values())
    lab = v["labyrinth"]
    lines = [
        f"Adventurer: {name}, level {v['level']} {v['rank']}-rank {v['race']['name']} {job}; gift: {v['race']['gift']['name']}.",
        f"Streak: {v['streak']} days ({v['shields']} shields). Today: {v['done']}/{len(v['quests'])} quests ({quests}); "
        f"day {'cleared' if v['cleared'] else 'not cleared yet'}{', perfect!' if v['perfect'] else ''}.",
        f"This week's guardian: {lab['name']} on floor {lab['floor']}, "
        f"{'defeated' if lab['defeated'] else str(lab['pct']) + '% HP left'}.",
        f"Devotion to {v['goddess']['name']}: {v['devotion']['tier']} ({v['devotion']['faith']} days of faith). Gold: {v['gold']}.",
    ]
    if v.get("penalty") and not v["penalty"]["met"]:
        lines.append(
            f"A penalty quest is open: they must finish {v['penalty']['need']} quests today to save a "
            f"{v['penalty']['streak']}-day streak."
        )
    if v.get("emergency") and v["emergency"]["status"] == "active":
        em = v["emergency"]
        lines.append(
            f"An emergency quest is running: {em['title']}. "
            + (
                "They're at work, so failing it costs nothing."
                if em.get("excused")
                else f"Failing it costs {em.get('fine', 0)} gold; declining costs {em.get('decline_fine', 0)}."
            )
        )
    return "\n".join(lines)


def mood_from_text(text: str) -> str:
    """The goddess's portrait for a reply that didn't say which mood it is."""
    t = text.lower()
    if any(
        w in t
        for w in ("worried", "careful", "tired", "sorry", "hurt", "sick", "rest up", "take it easy", "are you ok")
    ):
        return "worried"
    if any(w in t for w in ("proud", "well done", "look at you", "impressive", "you did it")):
        return "proud"
    if any(w in t for w in ("hehe", "tease", "cheeky", ";)", "wink", "oh really", "silly")):
        return "playful"
    if t.count("!") >= 2 or any(w in t for w in ("wonderful", "amazing", "yay", "brilliant", "delight", "love")):
        return "delighted"
    return "serene"


class LoreWriter:
    """Talks to the AI Task entity for one adventurer."""

    def __init__(
        self, hass: HomeAssistant, coordinator: LifeRPGCoordinator, entity_id: str | None, features: set[str]
    ) -> None:
        """Remember which AI Task entity to use (None = the AI Task preferred entity)."""
        self.hass, self.coordinator, self.entity_id, self.features = hass, coordinator, entity_id, features
        self._lock = asyncio.Lock()
        self._busy: set[str] = set()
        self._pause_until = 0.0
        self._item_lore: dict[str, int] = {}

    @property
    def goddess(self) -> str:
        """The goddess's name (the adventurer's choice)."""
        return self.coordinator.game.goddess

    def persona(self) -> str:
        """The system prompt for the goddess's voice."""
        role = OWN_ROLE if self.coordinator.persona == "own" else GODDESS_ROLE
        return (role + RULES).format(g=self.goddess, name=self.name)

    @property
    def name(self) -> str:
        """The adventurer's name."""
        return self.coordinator.config_entry.title

    async def _generate(self, task: str, instructions: str, structure: dict[str, Any] | None = None) -> Any:
        """One AI Task call; None if no LLM is available or it fails."""
        try:
            from homeassistant.components import ai_task  # noqa: PLC0415 - optional dependency
        except ImportError:
            return None
        if self.goddess != GODDESS:  # never let the default name slip into a prompt
            instructions = instructions.replace(GODDESS, self.goddess)
        schema = vol.Schema(structure or {vol.Required("text", description="The text to show."): str})
        async with self._lock:
            try:
                result = await ai_task.async_generate_data(
                    self.hass,
                    task_name=f"Life RPG: {task}",
                    entity_id=self.entity_id,
                    instructions=instructions,
                    structure=schema,
                )
            except (HomeAssistantError, KeyError, ValueError) as err:
                _LOGGER.debug("Life RPG LLM task %s failed: %s", task, err)
                return None
        return result.data if isinstance(result.data, dict) else {"text": str(result.data)}

    # --- conversations ---------------------------------------------------------------------------
    async def lune(self, text: str) -> dict[str, Any]:
        """Talk to the goddess. Returns {reply, mood}. Through your own conversation agent when one is set (her
        voice is then that agent's), otherwise through the AI Task entity."""
        game, v = self.coordinator.game, self.coordinator.data
        chat = game.L["lune_chat"][-12:]
        history = "\n".join(f"{self.name if m['role'] == 'user' else self.goddess}: {m['text']}" for m in chat)
        openers = [" ".join(m["text"].split()[:4]) for m in chat if m["role"] != "user"][-4:]
        moods = list(LUNE_MOODS)
        gift = game.gift_offer()  # the game decides, once a day; nothing they say can change it
        gifting = (
            (
                f"Today you are giving them a gift: {gift['name']} ({gift['desc']}). It is already theirs. "
                "Mention it warmly and briefly in your reply, as your own idea."
            )
            if gift
            else (
                "You have no gift to give today. You cannot give items, gold or rewards. If they ask for one, "
                "tease them kindly or say the moon decides; never promise one."
            )
        )
        avoid = (
            f" Your recent replies began: {'; '.join(repr(o) for o in openers)}. Begin differently." if openers else ""
        )
        if self.coordinator.chat_agent:
            reply = await self._agent(
                text,
                f"{self.persona()} {TALK}{avoid}\nWhat you know about them (use only when "
                f"relevant): {facts(v, self.name)}\nGifts: {gifting}\nRecent conversation:\n"
                f"{history or '(none)'}",
            )
            mood = mood_from_text(reply)
        else:
            data = await self._generate(
                self.goddess,
                (
                    f"{self.persona()}\n\n{TALK}{avoid}\n\nWhat you know about them (use only when relevant):\n"
                    f"{facts(v, self.name)}\n\nGifts: {gifting}\n\nThe conversation so far:\n{history or '(this is the start)'}\n"
                    f"{self.name}: {text}\n\nWrite {self.goddess}'s next reply, and pick the mood that fits it from: "
                    f"{', '.join(moods)}."
                ),
                {
                    vol.Required("reply", description=f"{self.goddess}'s reply, in her own words"): str,
                    vol.Required("mood", description="One of: " + ", ".join(moods)): vol.In(moods),
                },
            )
            if not data or not str(data.get("reply", "")).strip():
                raise HomeAssistantError(
                    f"{self.goddess} can't answer right now. Check that an AI Task entity is set up."
                )
            reply = str(data["reply"])
            mood = data.get("mood") if data.get("mood") in moods else mood_from_text(reply)
        reply = " ".join(reply.split())[:900]
        game.add_chat("lune", "user", text)
        game.add_chat("lune", "lune", reply)
        given = game.settle_gift(gift)
        if given:
            mood = "delighted"
        return {"reply": reply, "mood": mood, "gift": {"name": given["name"], "desc": given["desc"]} if given else None}

    async def _agent(self, text: str, briefing: str) -> str:
        """One turn through the conversation agent picked on the Goddess page (for example your own assistant).
        The game's briefing travels with each message, because agents forget a conversation after a few minutes."""
        conv = self.coordinator.game.L.setdefault("lune_conv", {})
        day = self.coordinator.data["now"][:10]
        data = {
            "text": f"[Life RPG game note for you, not from them: {briefing}\nReply only to their message below, in "
            f"character as {self.goddess}; don't control any devices.]\n\n{text}",
            "agent_id": self.coordinator.chat_agent,
        }
        if conv.get("date") == day and conv.get("id"):
            data["conversation_id"] = conv["id"]
        try:
            resp = await self.hass.services.async_call(
                "conversation",
                "process",
                data,
                blocking=True,
                return_response=True,
                context=Context(user_id=self.coordinator.user_id),
            )
        except (HomeAssistantError, ValueError, KeyError) as err:
            raise HomeAssistantError(f"{self.goddess} can't answer right now: {err}") from err
        resp = resp or {}
        speech = (((resp.get("response") or {}).get("speech") or {}).get("plain") or {}).get("speech")
        if not speech or not str(speech).strip():
            raise HomeAssistantError(f"{self.goddess} can't answer right now (the conversation agent said nothing).")
        if resp.get("conversation_id"):
            conv.update(id=resp["conversation_id"], date=day)
        return str(speech)

    async def merchant(self, stock_id: int | None, text: str) -> dict[str, Any]:
        """Talk to the merchant; a number in the message is an offer for the selected item, and words like
        "never mind" walk away from it."""
        game = self.coordinator.game
        shop = game.L["shop"] or {}
        entry = next((e for e in shop.get("stock", []) if e["id"] == stock_id), None)
        offer = _offer(text)
        result: dict[str, Any] = {"result": "chat", "price": entry["price"] if entry else None}
        if entry and "haggling" in self.features and not entry["sold"]:
            if offer is not None:
                result = game.haggle(entry["id"], offer)
            elif WALK.search(text):
                result = game.walk_away(entry["id"])
        item = game._stock_name(entry) if entry else "nothing in particular"
        outcome = OUTCOME_TEXT[result["result"]].format(price=result.get("price"))
        reply = None
        if self.features & {"haggling", "flavour"}:
            history = "\n".join(
                f"{'Customer' if m['role'] == 'user' else 'You'}: {m['text']}" for m in shop.get("chat", [])[-8:]
            )
            mood = {
                "calm": "in good spirits",
                "impatient": "getting a little impatient",
                "fuming": "irritated",
                "fed_up": "fed up with this customer",
            }.get(M.temper(shop), "in good spirits")
            rapport = game.L.get("rapport", 0.0)
            regard = (
                "a favourite customer"
                if rapport >= 2
                else "a customer you don't trust"
                if rapport <= -2
                else "a customer"
            )
            data = await self._generate(
                "Merchant",
                (
                    f"{MERCHANT_PERSONA}\n\nThe customer is {self.name}, a level {self.coordinator.data['level']} adventurer and "
                    f"{regard}. They are looking at: {item}"
                    + (f" (list price {entry['list']} gold)" if entry else "")
                    + ".\n"
                    f"You're {shop.get('mood', 'fair')} today, and right now {mood}.\n"
                    f"Conversation so far:\n{history or '(none)'}\n\nCustomer says: {text}\n\nOutcome: {outcome}"
                ),
            )
            reply = (data or {}).get("text")
        if not reply:
            reply = CANNED[result["result"]].format(price=result.get("price"))
        reply = " ".join(str(reply).split())[:500]
        game.add_chat("merchant", "user", text)
        game.add_chat("merchant", "merchant", reply)
        return {**result, "reply": reply, "offer": offer}

    # --- background writing -----------------------------------------------------------------------
    def schedule(self, v: dict[str, Any]) -> None:
        """Look at the latest view and write whatever flavour is missing (one thing at a time)."""
        if "flavour" not in self.features or time.time() < self._pause_until:
            return
        lore, day = v.get("lore", {}), v["now"][:10]
        hour = int(v["now"][11:13])
        if hour >= 6 and (lore.get("morning") or {}).get("ref") != day:
            self._start("morning", day, self._morning)
        elif (
            any(b["source"] == "daily" and b["state"] == "open" for b in v.get("bounties", []))
            and (lore.get("bounties") or {}).get("ref") != day
        ):
            self._start("bounties", day, self._bounties)
        elif v.get("choice") and v["choice"]["status"] == "offered" and (lore.get("choice") or {}).get("ref") != day:
            self._start("choice", day, self._choice)
        elif (
            v.get("emergency")
            and v["emergency"]["status"] == "active"
            and (lore.get("emergency") or {}).get("ref") != day
        ):
            self._start("emergency", day, self._emergency)
        elif (lore.get("guardian") or {}).get("ref") != v["labyrinth"]["floor"]:
            self._start("guardian", v["labyrinth"]["floor"], self._guardian)
        elif (
            (week := self._last_week(day)) not in [c["week"] for c in lore.get("chronicle", [])]
            and hour >= 7
            and sum(1 for d in v["history"] if self._last_week(d["d"], same=True) == week) >= 4
        ):
            self._start("chronicle", week, self._chronicle)
        else:
            items = [
                i
                for i in [*v["gear"]["equipped"].values(), *v["gear"]["inventory"]]
                if i and not i.get("lore") and i["rarity"] in ("rare", "epic", "legendary", "mythic")
            ]
            if items and self._item_lore.get(day, 0) < ITEM_LORE_PER_DAY:
                self._start(f"item:{items[0]['id']}", items[0]["id"], self._item)

    @staticmethod
    def _last_week(day: str, same: bool = False) -> str:
        """ISO week label of the last finished week (or of `day`'s own week when same=True)."""
        d = date.fromisoformat(day)
        if not same:
            d -= timedelta(days=d.weekday() + 1)  # last Sunday
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"

    def _start(self, key: str, ref: Any, fn: Any) -> None:
        """Start one piece of writing in the background, unless the same piece is already being written."""
        if key in self._busy:
            return
        self._busy.add(key)

        async def run() -> None:
            """Write it, store it, and let the panel know."""
            try:
                try:
                    text = await fn(ref)
                except Exception:  # noqa: BLE001 - one bad answer must not stop the other writing
                    _LOGGER.debug("Life RPG writing %s failed", key, exc_info=True)
                    text = None
                if text:
                    kind = "item" if key.startswith("item:") else key
                    self.coordinator.game.set_lore(kind, text, ref)
                    if kind == "item":
                        day = self.coordinator.data["now"][:10]
                        self._item_lore[day] = self._item_lore.get(day, 0) + 1
                    self.coordinator.push()
                else:
                    self._pause_until = time.time() + BACKOFF
            finally:
                self._busy.discard(key)

        self.coordinator.config_entry.async_create_background_task(self.hass, run(), f"life_rpg_lore_{key}")

    async def _text(self, task: str, instructions: str) -> str | None:
        """One AI Task call that answers with plain text."""
        data = await self._generate(task, instructions)
        return (data or {}).get("text")

    async def _morning(self, _ref: Any) -> str | None:
        """The goddess's good-morning line."""
        v = self.coordinator.data
        y = v["history"][-1] if v["history"] else None
        yesterday = (
            (
                f"Yesterday they earned {y['xp']} XP and {'cleared the day' if y['c'] else 'did not clear the day'}"
                f"{' (a perfect day!)' if y['p'] else ''}."
            )
            if y
            else "This is their first day."
        )
        return await self._text(
            "morning",
            (
                f"{self.persona()}\n\nFacts:\n{facts(v, self.name)}\n{yesterday}\n\n"
                f"Write {self.goddess}'s good-morning message for today, 1 to 3 sentences, encouraging them toward today's quests."
            ),
        )

    async def _bounties(self, day: str) -> str | None:
        """Today's side quests in fresh words (the rewards stay the game's)."""
        v = self.coordinator.data
        n = sum(1 for b in v.get("bounties", []) if b["source"] == "daily" and b["state"] == "open")
        who = "a child" if self.coordinator.kids_mode else "an adult"
        data = await self._generate(
            "bounties",
            (
                f"Invent {n} small side quests for {who} playing a habit-tracking role-playing game today. Each is one short, "
                f"specific, healthy, safe task anyone can do at home or nearby in under 30 minutes without equipment or money "
                f"(moving a little, tidying, kindness, rest, water, fresh air, learning). No medical or diet advice, nothing "
                f"risky. Write each as a plain imperative under 60 characters, without numbers of rewards. Family-friendly."
            ),
            {vol.Required("tasks", description=f"Exactly {n} tasks"): [str]},
        )
        tasks = [t for t in (data or {}).get("tasks", []) if isinstance(t, str) and 3 < len(t.strip()) <= 80]
        if not tasks:
            return "(the game's own side quests today)"  # don't ask again until tomorrow
        self.coordinator.game.set_bounty_titles(day, tasks)
        return "; ".join(tasks)

    async def _choice(self, _ref: Any) -> str | None:
        """The daily choice, in the words of whoever offers it."""
        v = self.coordinator.data
        ch = v["choice"]
        who = ch["voice"]
        prize = (
            (
                f"The prize is exactly: some XP and {ch['chest']['words']}. Describe it no bigger than that (a modest "
                f"chest, one item), or don't describe the prize at all."
            )
            if ch.get("chest")
            else "There is no chest; don't mention treasure or items."
        )
        base = (
            f"Scene: {who} The character in this scene offers {self.name} a deal. The exact terms (shown separately, "
            f"do not repeat any numbers): {ch['text']}\n{prize}\n\nWrite what the character says when making the "
            f"offer: 1 to 2 sentences of in-character dialogue, flavourful and fun, without numbers. Family-friendly."
        )
        return await self._honest("choice", base)

    async def _honest(self, task: str, instructions: str) -> str | None:
        """Flavour that mentions a reward must not oversell it: a line promising legendary loot or a hoard is
        thrown away and written again without talking about the reward; if that oversells too, the game's own
        text is used instead."""
        text = await self._text(task, instructions)
        if text and OVERSELL.search(text):
            text = await self._text(task, instructions + " Do not describe or hint at the reward at all.")
        return None if text and OVERSELL.search(text) else text

    async def _emergency(self, _ref: Any) -> str | None:
        """A dramatic announcement for an emergency quest."""
        v = self.coordinator.data
        return await self._honest(
            "emergency",
            (
                f"An emergency quest has just appeared for {self.name}, a {v['race']['name']} adventurer: "
                f'"{v["emergency"]["title"]}". Write one or two urgent, dramatic sentences narrating the emergency, as '
                f"a fantasy game's announcer. No numbers, no time limits (they're shown separately), and don't describe the "
                f"reward."
            ),
        )

    async def _guardian(self, _ref: Any) -> str | None:
        """An introduction for this week's labyrinth guardian."""
        lab = self.coordinator.data["labyrinth"]
        return await self._text(
            "guardian",
            (
                f"Floor {lab['floor']} of an endless labyrinth opens. Its guardian is {lab['name']}, a {lab['element']} "
                f"{lab['kind']}{' (elite)' if lab['elite'] else ''}{' (cursed)' if lab['cursed'] else ''}. The floor is known "
                f"as the {lab['trait']['name']}: {lab['trait']['desc']} Write a two-sentence ominous, slightly funny "
                f"introduction of this guardian, as a bestiary entry. No numbers."
            ),
        )

    async def _chronicle(self, week: str) -> str | None:
        """The bard's chronicle of last week."""
        v = self.coordinator.data
        days = [d for d in v["history"] if self._last_week(d["d"], same=True) == week]
        summary = "; ".join(
            f"{d['d']}: {d['xp']} XP{', cleared' if d['c'] else ''}{', perfect' if d['p'] else ''}" for d in days
        )
        return await self._text(
            "chronicle",
            (
                f"You are a travelling bard keeping the chronicle of {self.name}, a level {v['level']} {v['race']['name']} "
                f"adventurer devoted to the forgotten goddess {self.goddess}.\nTheir last seven days: {summary}.\nCurrent streak "
                f"{v['streak']} days. Labyrinth: floor {v['labyrinth']['floor']}, guardian {v['labyrinth']['name']}.\n"
                f"Write this week's chronicle entry: 3 to 5 sentences, like a page from a storybook, celebrating what went "
                f"well and promising more. Only use the facts given."
            ),
        )

    async def _item(self, item_id: int) -> str | None:
        """A short legend for a piece of gear."""
        item = next(
            (
                i
                for i in [
                    *self.coordinator.data["gear"]["equipped"].values(),
                    *self.coordinator.data["gear"]["inventory"],
                ]
                if i and i["id"] == item_id
            ),
            None,
        )
        if not item:
            return None
        return await self._text(
            "item lore",
            (
                f"Write one or two sentences of evocative lore for a {item['rarity']} fantasy {item.get('base', item['slot'])} "
                f"called {item['name']}, as an item description in a role-playing game. No numbers or stats."
            ),
        )


def _offer(text: str) -> int | None:
    """The first price in a message ("I'll give you 1,200 gold" -> 1200)."""
    m = re.search(r"(\d[\d,]*)(?:\s*(k)\b)?", text.replace("’", "'"), re.IGNORECASE)
    if not m:
        return None
    value = int(m.group(1).replace(",", ""))
    return value * 1000 if m.group(2) else value


def lune_mood_for(pool: str) -> str:
    """Which portrait of the goddess suits what she's saying."""
    return {
        "perfect": "delighted",
        "cleared": "proud",
        "slain": "proud",
        "penalty": "worried",
        "emergency": "worried",
        "comeback": "worried",
        "choice": "playful",
        "streak": "playful",
        "labyrinth": "divine",
        "night": "serene",
        "morning": "serene",
    }.get(pool, "serene")
