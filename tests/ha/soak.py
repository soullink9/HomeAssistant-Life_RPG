"""Multi-year soak of the Home Assistant side: coordinator + art studio (fake ComfyUI) + LLM writer (fake AI Task).

Run: python3 tests/ha/soak.py [years] [model]      (defaults: 3 years, sdxl; model is sdxl or flux_unet)
"""

import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
import random
import sys
import time as _time
import types

sys.path.insert(0, str(Path(__file__).parent))
import test_integration as H  # noqa: E402  (installs the Home Assistant stand-ins)

YEARS = float(sys.argv[1]) if len(sys.argv) > 1 else 3
MODEL = sys.argv[2] if len(sys.argv) > 2 else "sdxl"
CLOCK = [1_800_000_000.0]
# the painting settings for each model type the soak can run with
MODELS = {
    "sdxl": {"model_family": "sdxl", "checkpoint": H.CKPTS[0]},
    "flux_unet": {
        "model_family": "flux_unet",
        "checkpoint": H.UNETS[0],
        "flux_clip_l": "clip_l.safetensors",
        "flux_t5": "t5xxl_fp16.safetensors",
        "flux_vae": "ae.safetensors",
    },
}
REFRESHES = [0]


async def main():
    """Set up one adventurer and play YEARS years in fast time, checking budgets and invariants on the way."""
    import life_rpg
    from life_rpg import art, coordinator as coord_mod, lore, websocket

    fake_time = types.SimpleNamespace(time=lambda: CLOCK[0], monotonic=_time.monotonic)
    art.time = fake_time
    lore.time = fake_time
    art.POLL, art.MAX_FILES = 0.001, 60
    hass = H.hass_factory()
    assert await life_rpg.async_setup(hass, {})
    studio = hass.data["life_rpg"]["studio"]
    options = {
        "user_id": "u1",
        "race": "beastkin",
        "body": "masculine",
        "steps_entity": "sensor.p_steps",
        "sleep_entity": "sensor.p_sleep",
        "hydration_entity": "sensor.p_water",
        "floors_entity": "sensor.p_floors",
        "steps_goal": 8000,
        "sleep_goal": 7.5,
        "bedtime_quest": True,
        "bedtime_goal": "23:00:00",
        "floors_goal": 10,
        "hydration_goal": 2000,
        "comfyui_url": "http://comfy:8188",
        **MODELS[MODEL],
        "paint": ["portrait", "items", "guardians", "characters"],
        "ai_task_entity": "ai_task.ollama",
        "llm_features": ["lune_chat", "flavour", "haggling"],
        "art_style": "painted",
    }
    entry = H.ConfigEntry(options, title="Kai")
    entry.entry_id = "soak1"
    c = coord_mod.LifeRPGCoordinator(hass, entry)
    entry.runtime_data = c

    async def _unload(e, p):
        return True

    hass.config_entries = types.SimpleNamespace(async_loaded_entries=lambda d: [entry], async_unload_platforms=_unload)
    await c._async_setup()
    orig = c.async_refresh

    async def counted():
        REFRESHES[0] += 1
        await orig()

    c.async_refresh = counted
    owner = H.Conn("u1")
    websocket.ws_subscribe(hass, owner, {"id": 1, "entry_id": "soak1"})
    rnd = random.Random(7)
    day0 = datetime(2026, 10, 12, tzinfo=H.TZ)
    days = int(365 * YEARS)
    max_queue, offline_days, errors, chats = 0, 0, [], 0
    t0 = _time.time()
    for d in range(days):
        day = day0 + timedelta(days=d)
        if rnd.random() < 0.01:
            offline_days = rnd.randint(2, 20)  # ComfyUI box off for a while
        H.COMFY.online = offline_days == 0
        offline_days = max(0, offline_days - 1)
        hit = rnd.random() < 0.75
        for hour in (8, 21):
            H.NOW[0] = day.replace(hour=hour, minute=rnd.randint(0, 59))
            CLOCK[0] = H.NOW[0].timestamp()
            frac = (hour - 6) / 16
            stamp = H.iso(H.NOW[0].astimezone(H.timezone.utc))
            S = hass._states
            S["sensor.p_steps"] = H.State(str(round((9500 if hit else 5000) * frac)), {"endTime": stamp})
            S["sensor.p_floors"] = H.State(str(round((12 if hit else 4) * frac)), {"endTime": stamp})
            S["sensor.p_water"] = H.State(
                str(round((2.2 if hit else 1.2) * frac, 2)), {"unit_of_measurement": "L", "endTime": stamp}
            )
            wake = day.replace(hour=6, minute=30).astimezone(H.timezone.utc)
            # two apps write last night into Health Connect, with slightly different times: it must count once
            drift = timedelta(minutes=rnd.choice([0, 7, -4])) if hour == 21 else timedelta(0)
            S["sensor.p_sleep"] = H.State(
                str(rnd.randint(380, 500)),
                {
                    "unit_of_measurement": "min",
                    "startTime": H.iso(wake - timedelta(hours=8) + drift),
                    "endTime": H.iso(wake + drift),
                },
            )
            await c.async_refresh()
            for _ in range(400):  # let the studio and the LLM writer catch up a little
                await asyncio.sleep(0)
                if not studio.queue or not H.COMFY.online:
                    break
                await asyncio.sleep(0.002)
            max_queue = max(max_queue, len(studio.queue))
        v = c.data
        assert v["quests"]["sleep"]["value"] <= 500 / 60 + 0.01, ("sleep counted twice", d, v["quests"]["sleep"])
        if d % 90 == 45 and v["art"]["portrait"]:  # now and then someone asks for a different portrait
            await c.async_action("repaint_art", url=v["art"]["portrait"])
        # the player, through the panel's websocket commands
        try:
            if v["gear"]["chests"]:
                await c.async_action("open_all")
            for it in list(c.game.L["inv"]):
                if it["id"] not in c.game.L["equip"].values() and rnd.random() < 0.5:
                    await c.async_action("sell", item_id=it["id"])
            if v["market"] and rnd.random() < 0.6:  # the Market opened in the panel
                await c.async_action("market_seen")
            stock = [e for e in (v["market"] or {}).get("stock", []) if not e["sold"]]
            if stock and rnd.random() < 0.3:
                e = rnd.choice(stock)
                if rnd.random() < 0.5:
                    await c.async_chat("merchant", f"I'll give you {int(e['list'] * 0.8)} gold", e["id"])
                    chats += 1
                if c.game.L["gold"] >= next(x for x in c.game.L["shop"]["stock"] if x["id"] == e["id"])["price"]:
                    await c.async_action("buy", stock_id=e["id"])
            if v["level"] >= 5 and not c.game.L["job"]:
                await c.async_action("set_job", job="bard")
            if rnd.random() < 0.05:
                await c.async_chat("lune", "How am I doing?")
                chats += 1
            if rnd.random() < 0.02:
                await c.async_action("restyle")
        except H.HomeAssistantError as err:
            errors.append(str(err))
        except Exception as err:  # noqa: BLE001
            if type(err).__name__ != "GameError":
                raise
        if d % 30 == 29:
            print(
                f"    day {d + 1}: {round(_time.time() - t0)}s refreshes {REFRESHES[0]} queue {len(studio.queue)} state {studio.status['state']} "
                f"index {len(studio.index)} jobs {len(H.COMFY.prompts)} llm {len(H.LLM_CALLS)}",
                flush=True,
            )
        if d % 365 == 364:
            files = {p.name for p in studio.dir.iterdir() if p.suffix in (".png", ".webp")}
            indexed = {e["file"] for e in studio.index.values() if e.get("file")}
            assert files == indexed, (len(files), len(indexed))
            assert len(indexed) <= art.MAX_FILES + 150, len(indexed)
            assert len(H.COMFY.prompts) < 2600 * (d // 365 + 1), "paintings are being redone over and over"
            raw = json.dumps(c.game.L)
            json.dumps(c.data)
            watched = owner.out[-1][2]["view"] if owner.out and owner.out[-1][0] == "event" else None
            print(
                f"  year {d // 365 + 1}: L{v['level']} {v['rank']} floor {v['labyrinth']['floor']} gold {v['gold']} | "
                f"paintings {len(indexed)} (cap {art.MAX_FILES}), queue now {len(studio.queue)} (max {max_queue}), "
                f"ComfyUI jobs {len(H.COMFY.prompts)}, LLM calls {len(H.LLM_CALLS)}, chronicle "
                f"{len(c.game.L['lore'].get('chronicle', []))}, save {len(raw) // 1024} KB, "
                f"pushes {sum(1 for o in owner.out if o[0] == 'event')}, {round(_time.time() - t0)}s"
            )
            assert watched is None or watched["level"] >= 1
    assert max_queue < 200, max_queue
    await life_rpg.async_unload_entry(hass, entry)
    await studio.async_stop()
    print(
        f"\nHA SOAK PASSED: {days} days, {len(H.COMFY.prompts)} paintings requested, {len(H.LLM_CALLS)} LLM calls, "
        f"{chats} chats, {len(errors)} refused chats/actions"
    )


asyncio.run(main())
