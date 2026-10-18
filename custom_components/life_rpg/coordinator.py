"""Reads the health sensors and runs the game for one player."""

from __future__ import annotations

from datetime import date, datetime, time as time_, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .art import Studio, art_key
from .const import (
    CONF_AI_TASK,
    CONF_ART_STYLE,
    CONF_BEDTIME,
    CONF_BEDTIME_ON,
    CONF_BODY,
    CONF_CHAT_AGENT,
    CONF_CHECKPOINT,
    CONF_CLOCK,
    CONF_COMFY_URL,
    CONF_CORRECTIONS,
    CONF_DAILY_BOUNTIES,
    CONF_EDIT_MODEL,
    CONF_EDIT_PARTS,
    CONF_FAMILY,
    CONF_FAST_MODEL,
    CONF_GODDESS,
    CONF_KIDS,
    CONF_LLM,
    CONF_MANUAL,
    CONF_PAINT,
    CONF_PENALTY,
    CONF_PERSONA,
    CONF_RACE,
    CONF_SPEED,
    CONF_USER,
    CONF_WATER_UNIT,
    CONF_WORK_DAYS,
    CONF_WORK_END,
    CONF_WORK_ENTITY,
    CONF_WORK_START,
    DOMAIN,
    FLOZ_ML,
    FLUX_PARTS,
    GOALS,
    LLM_OPTIONS,
    PAINT_OPTIONS,
    SOURCES,
    TWELVE_HOUR_COUNTRIES,
    UNITS,
    WEEKDAYS,
    WORK_DEFAULTS,
)
from .engine import appearance as A
from .engine.content import GODDESS
from .engine.game import Game
from .engine.market import COSMETICS
from .engine.rules import GameError, rename
from .lore import LoreWriter, lune_mood_for

DEVOTION_NAMES = ["Stranger", "Believer", "Devotee", "Apostle", "Saint", "Hand of the Goddess"]

_LOGGER = logging.getLogger(__name__)


def _time(raw: Any) -> datetime | None:
    """Parse a timestamp attribute (Health Connect sends ISO instants)."""
    try:
        return dt_util.as_local(dt_util.parse_datetime(str(raw))) if raw else None
    except (TypeError, ValueError):
        return None


def work_hours(o: Any) -> dict[str, Any]:
    """Working hours from the entry's options, as the game wants them."""

    def minutes(raw: Any) -> int:
        """'HH:MM' to minutes after midnight; anything unreadable counts as midnight."""
        try:
            h, m = (int(x) for x in str(raw).split(":")[:2])
            return max(0, min(h * 60 + m, 1439))
        except ValueError:
            return 0

    days = o.get(CONF_WORK_DAYS, WORK_DEFAULTS[CONF_WORK_DAYS])
    return {
        "penalty": bool(o.get(CONF_PENALTY, WORK_DEFAULTS[CONF_PENALTY])),
        "start": minutes(o.get(CONF_WORK_START, WORK_DEFAULTS[CONF_WORK_START])),
        "end": minutes(o.get(CONF_WORK_END, WORK_DEFAULTS[CONF_WORK_END])),
        "days": [WEEKDAYS.index(d) for d in days if d in WEEKDAYS],
    }


class LifeRPGCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls every 5 minutes, on every source change, and at midnight."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Set up from the entry's options."""
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=timedelta(minutes=5))
        o = entry.options
        self.sources = {q: o[key] for q, key in SOURCES.items() if o.get(key)}
        self.manual = set(o.get(CONF_MANUAL, [])) & {"hydration", "floors", "sleep"}
        self.water_unit = o.get(CONF_WATER_UNIT, "ml") if o.get(CONF_WATER_UNIT) in ("ml", "floz") else "ml"
        clock = o.get(CONF_CLOCK) or ("12" if hass.config.country in TWELVE_HOUR_COUNTRIES else "24")
        self.twelve = clock == "12"
        self.corrections = set(o.get(CONF_CORRECTIONS, []))
        self.kids_mode = bool(o.get(CONF_KIDS, False))
        self.daily_bounties = int(o.get(CONF_DAILY_BOUNTIES, 5))
        self.chat_agent: str | None = o.get(CONF_CHAT_AGENT) or None
        goals = {
            q: float(o.get(key, default))
            for q, (key, default) in GOALS.items()
            if q in self.sources or q in self.manual
        }
        if "hydration" in goals and self.water_unit == "floz":  # the goal was entered in fl oz; the game counts mL
            goals["hydration"] = round(goals["hydration"] * FLOZ_ML)
        if ("sleep" in self.sources or "sleep" in self.manual) and o.get(CONF_BEDTIME_ON, True):
            h, m = (int(x) for x in str(o.get(CONF_BEDTIME, GOALS["bedtime"][1])).split(":")[:2])
            goals["bedtime"] = h * 60 + m
            if "sleep" in self.sources:
                self.sources["bedtime"] = self.sources["sleep"]
        self.race = o.get(CONF_RACE, "human")
        self.body = o.get(CONF_BODY, "androgynous")
        self.user_id: str | None = o.get(CONF_USER)
        self.goddess = (o.get(CONF_GODDESS) or "").strip() or None
        self.persona = o.get(CONF_PERSONA, "goddess")
        self.work = work_hours(o)
        self.work_entity: str | None = o.get(CONF_WORK_ENTITY) or None
        self.game = Game(
            goals,
            self.race,
            body=self.body,
            goddess=self.goddess,
            work=self.work,
            water_unit=self.water_unit,
            twelve_hour=self.twelve,
            corrections=self.corrections,
            kids_mode=self.kids_mode,
            daily_bounties=self.daily_bounties,
        )
        self.store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.studio: Studio = hass.data[DOMAIN]["studio"]
        url, family = (o.get(CONF_COMFY_URL) or "").strip(), o.get(CONF_FAMILY, "sdxl")
        parts = {k: o.get(key) for k, key in FLUX_PARTS.items()}
        self.art_cfg = (
            {
                "url": url,
                "family": family,
                "checkpoint": o.get(CONF_CHECKPOINT),
                "parts": parts,
                "speed": o.get(CONF_SPEED, "balanced"),
                "fast_model": bool(o.get(CONF_FAST_MODEL, False)),
            }
            if url.lower().startswith(("http://", "https://"))
            and (o.get(CONF_CHECKPOINT) or family == "custom")
            and (family != "flux_unet" or all(parts.values()))
            else None
        )
        self.paint = set(o.get(CONF_PAINT, PAINT_OPTIONS))
        edit_parts = o.get(CONF_EDIT_PARTS) or {}
        if self.art_cfg and o.get(CONF_EDIT_MODEL) and edit_parts and all(edit_parts.values()):
            self.art_cfg["edit"] = {"model": o[CONF_EDIT_MODEL], "parts": dict(edit_parts)}
        if o.get(CONF_ART_STYLE, "painted") == "pixel":  # pixel art everywhere; ComfyUI and saved paintings unused
            self.art_cfg, self.paint = None, set()
        features = set(o.get(CONF_LLM, LLM_OPTIONS))
        self.lore = LoreWriter(hass, self, o.get(CONF_AI_TASK) or None, features) if features else None
        self._carry: list[dict[str, Any]] = []

    async def _async_setup(self) -> None:
        """Load the save file and subscribe to the sources."""
        self.game = Game(
            self.game.goals,
            self.race,
            await self.store.async_load(),
            body=self.body,
            goddess=self.goddess,
            work=self.work,
            water_unit=self.water_unit,
            twelve_hour=self.twelve,
            corrections=self.corrections,
            kids_mode=self.kids_mode,
            daily_bounties=self.daily_bounties,
        )
        refresh = callback(
            lambda *_: self.config_entry.async_create_background_task(
                self.hass, self.async_request_refresh(), f"{DOMAIN}_refresh"
            )
        )
        self.config_entry.async_on_unload(
            async_track_state_change_event(self.hass, list(set(self.sources.values())), refresh)
        )
        self.config_entry.async_on_unload(async_track_time_change(self.hass, refresh, hour=0, minute=0, second=5))
        self.studio.listeners.append(self.push)
        self.config_entry.async_on_unload(lambda: self.studio.listeners.remove(self.push))

    async def _async_update_data(self) -> dict[str, Any]:
        """Every refresh: run the game on the sensor readings, attach art, queue the LLM's writing and save."""
        now = dt_util.now()
        self.game.at_work = self._at_work()
        self.game.advance(now)
        readings = {q: self._read(q, now.date()) for q in self.game.goals}
        data = self.game.update(readings, now)  # data["events"]: everything raised this cycle
        carried, self._carry = self._carry, []
        if self.game.goddess != GODDESS:  # events from actions and chats get her name too
            carried = rename(carried, GODDESS, self.game.goddess)
        data["events"] = carried + data["events"]
        data["manual"] = sorted(self.manual)
        self._decorate(data)
        if self.lore:
            self.lore.schedule(data)
        self.store.async_delay_save(lambda: self.game.L, 10)
        return data

    def _at_work(self) -> bool | None:
        """On/off from the work entity (schedule, calendar, binary sensor, input boolean); None = use the hours."""
        st = self.hass.states.get(self.work_entity) if self.work_entity else None
        return None if st is None or st.state not in ("on", "off") else st.state == "on"

    @callback
    def push(self) -> None:
        """Something changed outside the sensors (a painting finished, the LLM wrote something): refresh soon."""
        self.config_entry.async_create_background_task(self.hass, self.async_request_refresh(), f"{DOMAIN}_push")

    def _decorate(self, v: dict[str, Any]) -> None:
        """Attach painted art (or queue it) to everything in the view that can have a picture."""
        entry_id, studio, cfg = self.config_entry.entry_id, self.studio, self.art_cfg

        edit = bool(cfg and cfg.get("edit"))  # base paintings plus edits: faces stay the same
        shown = self.game.L.setdefault("art_shown", {})  # what each character showed last, until the new one is ready

        def want(cat: str, spec: dict[str, Any], prio: int, variant: str = "", seed: str | None = None) -> str | None:
            """Ask the painter for one picture, unless this kind of art is set to stay pixel art."""
            if cat not in self.paint:  # this kind of art stays pixel art
                return None
            key = art_key(spec, variant)
            return studio.want(key, spec, prio, cfg, A.seed_for(seed or key))

        def character(
            cat: str,
            slot: str,
            base: dict[str, Any],
            full: dict[str, Any],
            instruction: str,
            prio: int,
            seed: str | None = None,
        ) -> tuple[str | None, str]:
            """One picture of a recurring character: with an edit model, an edit of their base painting (queued
            once the base is ready), else painted from the prompt. Until it's ready, the last one shown."""
            if cat not in self.paint:
                return None, ""
            if edit:
                base_key = art_key(base)
                spec = {**full, "edit": {"base": base_key, "instruction": instruction}, "group": slot}
                key = art_key(spec, f"edit:{instruction}:{studio.file_of(base_key)}")
            else:
                spec, key = {**full, "group": slot}, art_key(full)
            url = studio.want(key, spec, prio, cfg, A.seed_for(seed or key))
            if url:
                shown[slot] = url
            elif (last := shown.get(slot)) and studio.key_for_url(last):
                url = last
            return url, key

        def base_of(cat: str, spec: dict[str, Any], prio: int, seed: str | None = None) -> str | None:
            """A character's base painting (only with an edit model)."""
            return want(cat, spec, prio, seed=seed) if edit else None

        # the adventurer: same seed across gear changes so new portraits stay recognisably them
        seed = f"{entry_id}:{v['seed']}:{v['look']}:{v['portrait_v']}"
        pbase = {**A.portrait_base_prompt(v, self.body), "owner": entry_id, "group": f"portrait-base:{entry_id}"}
        pbase_url = base_of("portrait", pbase, 0, seed)
        spec = {**A.portrait_prompt(v, self.body), "owner": entry_id, "group": f"portrait:{entry_id}"}
        if edit:
            spec["edit"] = {"base": art_key(pbase), "instruction": A.portrait_edit(v)}
            key = art_key(spec, f"{entry_id}:{v['portrait_v']}:edit:{studio.file_of(art_key(pbase))}")
        else:
            key = art_key(spec, f"{entry_id}:{v['portrait_v']}")
        url = studio.want(key, spec, 0, cfg, A.seed_for(seed)) if "portrait" in self.paint else None
        studio.forget_queue(lambda j: j["spec"].get("owner") != entry_id or j["key"] in (key, art_key(pbase)))
        if url:
            self.game.L["portrait_art"] = url
        last = self.game.L.get("portrait_art") if "portrait" in self.paint else None
        v["art"] = {
            "portrait": url or (last if last and studio.key_for_url(last) else None),
            "portrait_base": pbase_url,
            "portrait_current": bool(url),
            "portrait_pending": url is None and (studio.pending(key) or (edit and studio.pending(art_key(pbase)))),
            "edit": edit,
            "studio": studio.summary() if cfg else {"state": "off"},
            "style": "pixel" if not self.paint else "painted",
            "frame": (v["cosmetics"]["active"].get("frame") or "").replace("frame_", "") or None,
            "llm": bool(self.lore),
        }
        # gear: what you wear first, then the shop, then the backlog
        for item in v["gear"]["equipped"].values():
            if item:
                item["art"] = want("items", A.item_prompt(item), 2)
        # a delivery lasts a few hours, so its goods come before the backlog, but only once someone has opened
        # the Market (three deliveries a day nobody looks at would keep ComfyUI busy for nothing)
        seen = bool((v.get("market") or {}).get("seen"))
        for e in (v.get("market") or {}).get("stock", []):
            spec = (
                A.item_prompt(e["item"]) if e["kind"] == "gear" else A.trinket_prompt(e["cid"], COSMETICS.get(e["cid"]))
            )
            url = (
                want("items", spec, 2 if e["kind"] == "gear" else 3)
                if seen
                else studio.url(art_key(spec))
                if "items" in self.paint
                else None
            )
            if e["kind"] == "gear":
                e["item"]["art"] = url
            else:  # potions, charms and cosmetics
                e["art"] = url
        for b in v.get("bag", []):
            b["art"] = want("items", A.trinket_prompt(b["id"]), 4)
        fast = (cfg or {}).get("speed") == "fast"
        for item in v["gear"]["inventory"]:
            plain = item["rarity"] in ("common", "uncommon")
            if fast and plain and not item.get("equipped"):  # Fast: spare plain gear stays pixel art
                item["art"] = studio.url(art_key(A.item_prompt(item))) if "items" in self.paint else None
            else:
                item["art"] = want("items", A.item_prompt(item), 6 if plain else 5)
        lab = v["labyrinth"]
        lab["art"] = want("guardians", A.guardian_prompt(lab), 1)
        v["bestiary"] = [dict(b) for b in v["bestiary"]]  # don't write URLs into the save file
        for b in v["bestiary"][:12]:
            b["art"] = want("guardians", A.guardian_prompt(b), 7)
        for b in v["bestiary"][12:]:
            b["art"] = studio.url(art_key(A.guardian_prompt(b))) if "guardians" in self.paint else None
        # Lune: her shrine grows with your devotion; today's mood first
        base = v["devotion"]["tier"].split(" +")[0]
        tier = DEVOTION_NAMES.index(base) if base in DEVOTION_NAMES else 0
        mood = lune_mood_for(v["goddess"].get("pool", "default"))
        v["goddess"]["mood"], v["goddess"]["tier"] = mood, tier
        name, prefs = self.game.goddess, v["goddess"].get("prefs") or {}
        gbase = {**A.goddess_base_prompt(name, prefs), "group": f"goddess-base:{entry_id}"}
        v["goddess"]["base_art"] = base_of("characters", gbase, 2)
        # one seed for all her moods, so even painted from the prompt she stays the same person
        v["goddess"]["art"] = {
            m: character(
                "characters",
                f"goddess:{entry_id}:{m}",
                gbase,
                A.goddess_prompt(m, tier, name, prefs),
                A.goddess_edit(m, tier, prefs),
                2 if m == mood else 5,
                seed=art_key(gbase),
            )[0]
            for m in A.LUNE_MOODS
        }
        if ch := v.get("choice"):
            idx = ch.get("voice_index", 0)
            npc = A.npc_prompt(idx)
            ch["art"] = v["goddess"]["art"]["playful"] if npc is None else want("characters", npc, 2)
        if m := v.get("market"):
            # his face follows the haggling: the one showing now first, then the mood he arrived in
            mprefs = m.get("prefs") or {}
            mbase = {**A.merchant_base_prompt(mprefs), "group": f"merchant-base:{entry_id}"}
            m["base_art"] = base_of("characters", mbase, 2)
            m["art"] = {
                md: character(
                    "characters",
                    f"merchant:{entry_id}:{md}",
                    mbase,
                    A.merchant_prompt(md, mprefs),
                    A.merchant_edit(md, mprefs),
                    2 if md == m["face"] else 3 if md == m["mood"] else 6,
                    seed=art_key(mbase),
                )[0]
                for md in A.MERCHANT_MOODS
            }

    async def async_action(self, action: str, _admin: bool = False, **kwargs: Any) -> Any:
        """Run a player action (open a chest, equip, ...) and refresh everything. `_admin`: the person acting is a
        Home Assistant admin (in kids mode, the parent who posts and approves chores)."""
        if action in ("add_bounty", "remove_bounty", "approve_bounty") and not _admin:
            raise GameError("Only a parent (a Home Assistant admin) can post, remove or approve chores.")
        handler = {
            "open_chest": lambda: self.game.open_chest(int(kwargs["chest_id"])),
            "open_all": lambda: [self.game.open_chest(c["id"]) for c in list(self.game.L["chests"])],
            "equip": lambda: self.game.equip(int(kwargs["item_id"])),
            "unequip": lambda: self.game.unequip(str(kwargs["slot"])),
            "salvage": lambda: self.game.salvage(int(kwargs["item_id"])),
            "enhance": lambda: self.game.enhance(int(kwargs["item_id"])),
            "set_title": lambda: self.game.set_title(kwargs.get("title")),
            "set_job": lambda: self.game.set_job(str(kwargs["job"])),
            "answer_choice": lambda: self.game.answer_choice(bool(kwargs["accept"])),
            "decline_emergency": self.game.decline_emergency,
            "restyle": self.game.restyle,
            "repaint": self.game.repaint,
            "repaint_art": lambda: self._repaint_art(str(kwargs.get("url") or "")),
            "buy": lambda: self.game.buy(int(kwargs["stock_id"])),
            "sell": lambda: self.game.sell(int(kwargs["item_id"])),
            "haggle": lambda: self.game.haggle(int(kwargs["stock_id"]), int(kwargs["offer"])),
            "walk_away": lambda: self.game.walk_away(int(kwargs["stock_id"])),
            "market_seen": self.game.market_seen,
            "use": lambda: self.game.use(str(kwargs["consumable"])),
            "set_cosmetic": lambda: self.game.set_cosmetic(str(kwargs["category"]), kwargs.get("cosmetic")),
            "log": lambda: self.game.log_quest(str(kwargs["quest"]), kwargs["amount"]),
            "correct": lambda: self.game.correct(str(kwargs["quest"]), kwargs.get("today"), kwargs.get("record")),
            "accept_held": lambda: self.game.accept_held(str(kwargs["quest"])),
            "set_portrait_prefs": lambda: self.game.set_portrait_prefs(dict(kwargs.get("prefs") or {})),
            "set_goddess_prefs": lambda: self.game.set_goddess_prefs(dict(kwargs.get("prefs") or {})),
            "set_merchant_prefs": lambda: self.game.set_merchant_prefs(dict(kwargs.get("prefs") or {})),
            "add_bounty": lambda: self.game.add_bounty(
                str(kwargs.get("title") or ""),
                int(kwargs.get("xp") or 0),
                int(kwargs.get("gold") or 0),
                bool(kwargs.get("chest")),
                str(kwargs.get("repeat") or "once"),
            ),
            "remove_bounty": lambda: self.game.remove_bounty(int(kwargs["bounty_id"])),
            "claim_bounty": lambda: self.game.claim_bounty(int(kwargs["bounty_id"])),
            "approve_bounty": lambda: self.game.approve_bounty(int(kwargs["bounty_id"]), bool(kwargs.get("ok", True))),
            "log_sleep": lambda: (
                self.game.log_sleep(*resolve_sleep(str(kwargs["bedtime"]), str(kwargs["wake"]), dt_util.now()))
                if kwargs.get("wake")
                else self.game.log_bedtime(resolve_bedtime(str(kwargs["bedtime"]), dt_util.now()))
            ),
        }.get(action)
        if handler is None:
            raise GameError(f"Unknown action {action}.")
        self.game.now = dt_util.now()
        before = len(self.game.events)
        result = handler()
        self._carry += self.game.events[before:]  # events raised by the action reach the next update
        await self.async_refresh()
        return result

    def _repaint_art(self, url: str) -> bool:
        """Paint one picture again (the panel's Gallery). The old one stays until the new one is ready."""
        if not self.art_cfg:
            raise GameError("Paintings are off. Set up ComfyUI under Configure → Art and AI.")
        key = self.studio.key_for_url(url)
        if key is None or not self.studio.redo(key):
            raise GameError("That picture isn't a painting (or it's already gone).")
        return True

    async def async_chat(self, who: str, text: str, stock_id: int | None = None) -> dict[str, Any]:
        """Talk to Lune or the merchant."""
        if not self.lore:
            raise GameError("Conversations are turned off in this adventurer's Art and AI options.")
        text = " ".join(str(text).split())[:500]
        if not text:
            raise GameError("Say something first.")
        self.game.now = dt_util.now()
        before = len(self.game.events)
        if who == "lune":
            if "lune_chat" not in self.lore.features:
                raise GameError(f"Talking to {self.game.goddess} is turned off in the Art and AI options.")
            result = await self.lore.lune(text)
        else:
            result = await self.lore.merchant(stock_id, text)
        self._carry += self.game.events[before:]
        await self.async_refresh()
        return result

    def _read(self, quest: str, today: date) -> float | None:
        """Today's value for a quest, or None if the sensor has nothing for today."""
        if quest not in self.sources:  # logged by hand only
            return self._sleep(quest, None, 0, today) if quest in ("sleep", "bedtime") else None
        st = self.hass.states.get(self.sources[quest])
        if st is None or st.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        try:
            value = float(st.state)
        except ValueError:
            return None
        unit = st.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        value *= UNITS["sleep" if quest == "bedtime" else quest].get(unit, 1)
        if quest in ("sleep", "bedtime"):
            return self._sleep(quest, st, value, today)
        # Health Connect daily totals carry endTime = when the phone counted them
        stamp = _time(st.attributes.get("endTime")) or dt_util.as_local(st.last_reported)
        return value if stamp.date() == today else None

    def _sleep(self, quest: str, st: State | None, minutes: float, today: date) -> float | None:
        """Sleep sessions that ended today (naps and hand-logged nights add up); bedtime = the longest one's start."""
        sessions = self.game.L["inputs"].setdefault("sleep", {})
        if st is not None:
            start, end = self._session_times(st, self.sources.get("sleep", ""))
            if (end or dt_util.as_local(st.last_changed)).date() == today:
                if not minutes and start and end:  # no sleep stages recorded: use the session span
                    minutes = (end - start).total_seconds() / 60
                if start and end:
                    sessions[start.isoformat()] = {"start": start.isoformat(), "end": end.isoformat(), "min": minutes}
                else:
                    sessions["last"] = minutes
        hours, bedtime = Game.sleep_totals(sessions)
        return hours if quest == "sleep" else bedtime

    def _session_times(self, st: State, entity_id: str) -> tuple[datetime | None, datetime | None]:
        """When last night's sleep began and ended. Health Connect sensors report it in different ways: startTime /
        endTime attributes, a stage timeline (stageStartTimes / stageEndTimes), or the companion app's separate
        sleep start and sleep end sensors next to the duration sensor. Without a start there's no Lights out."""
        a = st.attributes
        start, end = _time(a.get("startTime")), _time(a.get("endTime"))
        if not (start and end):
            starts = [t for t in (_time(x) for x in (a.get("stageStartTimes") or [])) if t]
            ends = [t for t in (_time(x) for x in (a.get("stageEndTimes") or [])) if t]
            start, end = start or (min(starts) if starts else None), end or (max(ends) if ends else None)
        if not (start and end):
            for which in ("start", "end"):
                if (start if which == "start" else end) is None and (sib := self._sleep_sibling(entity_id, which)):
                    t = _time(sib.state)
                    start, end = (t, end) if which == "start" else (start, t)
        return start, end

    def _sleep_sibling(self, entity_id: str, which: str) -> State | None:
        """The companion app's sleep start / sleep end timestamp sensor that goes with a sleep duration sensor."""
        candidates = []
        if "sleep_duration" in entity_id:
            candidates.append(entity_id.replace("sleep_duration", f"sleep_{which}"))
        registry = er.async_get(self.hass)
        if (me := registry.async_get(entity_id)) and me.device_id:
            candidates += [
                e.entity_id
                for e in er.async_entries_for_device(registry, me.device_id)
                if e.entity_id.endswith(f"_sleep_{which}")
            ]
        for cand in candidates:
            st = self.hass.states.get(cand)
            if st is not None and st.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                return st
        return None


def resolve_bedtime(bedtime: str, now: datetime) -> datetime:
    """Turn "22:40" (or a full date-time) into the moment you fell asleep last night (or early this morning)."""
    text = bedtime.strip()
    if len(text) > 5 and (stamp := dt_util.parse_datetime(text)) is not None:
        when = dt_util.as_local(stamp)
    else:
        try:
            h, m = (int(x) for x in text.split(":")[:2])
            t = time_(h, m)
        except ValueError as err:
            raise GameError("Give the time you fell asleep, like 22:40.") from err
        when = datetime.combine(now.date(), t, tzinfo=now.tzinfo)
        if when > now:  # 22:40 means last night
            when -= timedelta(days=1)
    if not now - timedelta(hours=24) <= when <= now + timedelta(minutes=5):
        raise GameError("Log when you fell asleep last night.")
    return when


def resolve_sleep(bedtime: str, wake: str, now: datetime) -> tuple[datetime, datetime]:
    """Turn "22:40" / "06:30" (or full date-times) into last night's sleep, ending today."""

    def parse(text: str, label: str) -> datetime | time_:
        """Read one time (HH:MM or a full date-time); raises a clear error naming `label` if it can't."""
        text = text.strip()
        if len(text) > 5 and (stamp := dt_util.parse_datetime(text)) is not None:
            return dt_util.as_local(stamp)
        try:
            h, m = (int(x) for x in text.split(":")[:2])
            return time_(h, m)
        except (ValueError, TypeError) as err:
            raise GameError(f"{label} should look like 22:30.") from err

    start, end = parse(bedtime, "Bedtime"), parse(wake, "Wake-up time")
    if isinstance(end, time_):
        end = now.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if isinstance(start, time_):
        start = end.replace(hour=start.hour, minute=start.minute)
        if start >= end:
            start -= timedelta(days=1)
    return start, end
