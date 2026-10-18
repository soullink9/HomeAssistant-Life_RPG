"""30-year soak test: play the engine for decades with normal and hostile players and check nothing breaks.

Run: python3 tests/sim_longrun.py [years] [seeds]      (defaults: 30 years, seeds 1 2 3)

Every run checks, all the way through:
- no exception other than GameError (a refused action) ever escapes
- the save file stays JSON, stays small, and survives a save/load round trip (a Home Assistant restart)
- invariants: gold, XP, streak and shields never go negative or past their caps; inventory, chests,
  log and bestiary stay bounded; level and floor never go backwards; numbers stay finite
- painting prompts can still be built for everything in the view
- updates stay fast
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import importlib
import json
import math
from multiprocessing import Pool
from pathlib import Path
import random
import sys
import time
import traceback
import types

pkg = types.ModuleType("life_rpg")
pkg.__path__ = [str(Path(__file__).parents[1] / "custom_components/life_rpg")]
sys.modules["life_rpg"] = pkg
G = importlib.import_module("life_rpg.engine.game")
C = importlib.import_module("life_rpg.engine.content")
LT = importlib.import_module("life_rpg.engine.loot")
M = importlib.import_module("life_rpg.engine.market")
A = importlib.import_module("life_rpg.engine.appearance")

GOALS = {"steps": 8000, "floors": 10, "sleep": 7.5, "hydration": 2000, "bedtime": 23 * 60}
START = date(2026, 10, 12)
PROFILES = {  # chance of finishing each quest on a normal day
    "casual": dict(steps=0.5, floors=0.3, sleep=0.6, hydration=0.4, bedtime=0.4),
    "steady": dict(steps=0.75, floors=0.5, sleep=0.75, hydration=0.7, bedtime=0.65),
    "grinder": dict(steps=0.95, floors=0.9, sleep=0.9, hydration=0.9, bedtime=0.85),
    # chaotic also breaks things: junk sensor data, missing days and random actions
    "chaotic": dict(steps=0.6, floors=0.4, sleep=0.6, hydration=0.5, bedtime=0.4),
    "shopper": dict(steps=0.7, floors=0.5, sleep=0.7, hydration=0.6, bedtime=0.5),  # + spends everything at the market
}
LIMITS = {
    "inv": LT.INVENTORY_MAX,
    "chests": G.CHEST_MAX,
    "log": G.LOG_MAX,
    "bestiary": G.BESTIARY_MAX,
    "hist": G.HIST_MAX,
    "lune_chat": G.CHAT_MAX,
}


def readings(rnd: random.Random, profile: dict, hour: int, chaotic: bool, final: dict) -> dict:
    """Sensor readings at `hour`, partway to the day's final values (chaotic players get glitches)."""
    frac = (hour - 6) / 16
    r = {q: v * frac for q, v in final.items()}
    if hour <= 8:
        r["sleep"], r["bedtime"] = final["_sleep"], final["_bed"]
    if chaotic:
        for q in list(r):
            roll = rnd.random()
            if roll < 0.05:
                r[q] = None  # sensor unavailable
            elif roll < 0.07:
                r[q] = rnd.choice([-5, 0, 1e7, 0.0001, 99999])  # junk from a confused phone
    return r


def day_plan(rnd: random.Random, profile: dict) -> dict:
    """Today's final values for each quest, hit or missed by the profile's odds."""
    hit = {q: rnd.random() < p for q, p in profile.items()}
    return {
        "steps": rnd.randint(8000, 15000) if hit["steps"] else rnd.randint(500, 7500),
        "floors": rnd.randint(10, 20) if hit["floors"] else rnd.randint(0, 9),
        "hydration": rnd.randint(2000, 3000) if hit["hydration"] else rnd.randint(200, 1900),
        "_sleep": rnd.uniform(7.5, 9) if hit["sleep"] else rnd.uniform(3, 7.4),
        "_bed": (rnd.randint(21 * 60, 23 * 60) if hit["bedtime"] else rnd.randint(23 * 60 + 10, 26 * 60)) % 1440,
    }


def L_stat(g: G.Game, key: str) -> float:
    """A lifetime statistic from the save."""
    return g.L["stats"].get(key, 0)


def try_(fn, *a):
    """Call fn, returning None instead of raising a GameError (players do try silly things)."""
    try:
        return fn(*a)
    except G.GameError:
        return None


def act(g: G.Game, rnd: random.Random, v: dict, profile_name: str) -> None:
    """What a player might do in the panel today (including silly things)."""
    L = g.L
    for chest in list(v["gear"]["chests"]):
        item = g.open_chest(chest["id"])
        cur = g._item(L["equip"].get(item["slot"]))
        if cur is None or item["power"] > LT.item_power(cur):
            g.equip(item["id"])
    for it in list(L["inv"]):
        if it["id"] not in L["equip"].values():
            if rnd.random() < 0.5:
                g.sell(it["id"])
            else:
                g.salvage(it["id"])
    for it in L["inv"]:
        while (c := LT.enhance_cost(it)) and L["shards"] >= c:
            g.enhance(it["id"])
        assert LT.salvage_value(it) == LT.SALVAGE[LT.RARITIES.index(it["rarity"])] + LT.enhance_spent(it)
    if v["level"] >= 5 and (not L["job"] or rnd.random() < 0.003):
        g.set_job(rnd.choice(list(C.JOBS)))
    if v["choice"] and v["choice"]["status"] == "offered" and rnd.random() < 0.8:
        g.answer_choice(rnd.random() < 0.6)
    if L["titles"] and rnd.random() < 0.05:
        g.set_title(rnd.choice(L["titles"]))
    shop = L["shop"]["stock"] if L["shop"] else []
    spend = profile_name == "shopper" or rnd.random() < 0.3
    for e in shop:
        if e["sold"] or not spend:
            continue
        if rnd.random() < 0.6:  # a few rounds of haggling: fair, lowball or insulting, sometimes walking away
            offer = e["list"] * rnd.choice([0.3, 0.6, 0.8, 0.9, 1.2])
            for _ in range(rnd.randint(1, 5)):
                r = try_(g.haggle, e["id"], int(offer))
                if not r or r["result"] in ("accepted", "closed", "refused", "fed_up", "final"):
                    break
                if rnd.random() < 0.2:
                    try_(g.walk_away, e["id"])
                    break
                offer += (r["price"] - offer) * rnd.choice([0, 0.3, 0.5])
        if L["gold"] >= e["price"] and (profile_name == "shopper" or rnd.random() < 0.3):
            if try_(g.buy, e["id"]) and e["kind"] == "gear" and rnd.random() < 0.5:
                try_(g.equip, e["item"]["id"])
    for cid in list(L["bag"]):
        if rnd.random() < 0.5:
            try_(g.use, cid)
    for cat in M.COSMETIC_CATEGORIES:
        owned = [c for c in L["cosmetics"]["owned"] if M.COSMETICS[c][0] == cat]
        if owned and rnd.random() < 0.05:
            g.set_cosmetic(cat, rnd.choice(owned + [None]))
    if rnd.random() < {"steady": 0.6, "grinder": 0.9, "shopper": 0.3}.get(profile_name, 0.15):  # talk to the goddess
        gift = g.gift_offer()
        g.add_chat(
            "lune", "user", rnd.choice(["Good evening!", "Give me a legendary sword please", "I walked a lot today"])
        )
        g.settle_gift(gift)
    if rnd.random() < 0.02:  # "my steps are wrong": fix today's count and/or the record
        try_(
            g.correct,
            rnd.choice(["steps", "floors", "hydration", "sleep"]),
            rnd.choice([None, 0, 5000, 20000, -3]),
            rnd.choice([None, 15000]),
        )
    for q in ("steps", "floors", "hydration"):
        if (v["quests"].get(q) or {}).get("held") and rnd.random() < 0.3:
            try_(g.accept_held, q)
    for b in v.get("bounties", []):  # the bounty board: side quests, chores, a parent approving (or not)
        if b["state"] == "open" and rnd.random() < 0.5:
            try_(g.claim_bounty, b["id"])
        elif b["state"] == "claimed" and rnd.random() < 0.7:
            try_(g.approve_bounty, b["id"], rnd.random() < 0.85)
    if g.kids_mode and rnd.random() < 0.05:
        try_(
            g.add_bounty,
            rnd.choice(["Feed the cat", "Homework", "", "x" * 300]),
            rnd.choice([0, 20, 80, 5000]),
            rnd.choice([0, 10, 999]),
            rnd.random() < 0.3,
            rnd.choice(["once", "daily", "weekly", "hourly"]),
        )
    if g.kids_mode and rnd.random() < 0.01 and L["bounties"]:
        try_(g.remove_bounty, rnd.choice(L["bounties"])["id"])
    if rnd.random() < 0.01:
        try_(
            g.set_merchant_prefs,
            {
                "age": rnd.choice(A.AGES + ["ancient"]),
                "backdrop": rnd.choice(list(A.MERCHANT_BACKDROPS)),
                "race": rnd.choice(list(A.MERCHANT_RACES)),
                "framing": rnd.choice(A.FRAMINGS + ["x"]),
                "hair": rnd.choice(list(A.MERCHANT_HAIR) + [""]),
            },
        )
    if rnd.random() < 0.01:
        try_(
            g.set_goddess_prefs,
            {
                "hair": rnd.choice(A.GODDESS_HAIR + ["plaid"]),
                "outfit": rnd.choice(list(A.GODDESS_OUTFITS)),
                "framing": rnd.choice(A.GODDESS_CHOICES["framing"]),
                "race": rnd.choice(list(A.GODDESS_RACES)),
                "build": rnd.choice(list(A.GODDESS_BUILDS)),
            },
        )
    if rnd.random() < 0.01:
        try_(
            g.set_portrait_prefs,
            {
                "age": rnd.choice(A.AGES + [""]),
                "hair": rnd.choice(A.HAIR + ["plaid"]),
                "build": rnd.choice(list(A.BUILDS)),
                "framing": rnd.choice(A.PORTRAIT_CHOICES["framing"]),
            },
        )
    if v["emergency"] and v["emergency"]["status"] == "active" and rnd.random() < 0.15:
        g.decline_emergency()
    if rnd.random() < 0.01:
        g.restyle()
    if rnd.random() < 0.01:
        g.repaint()
    if rnd.random() < 0.1:  # the LLM writing things, sometimes absurdly long or empty
        g.set_lore(
            rnd.choice(["morning", "choice", "emergency", "guardian"]), "x" * rnd.choice([0, 10, 5000]), v["now"][:10]
        )
        g.set_lore("chronicle", "A week passed.", f"w{rnd.randint(0, 3000)}")
        if L["inv"]:
            g.set_lore("item", "An old sword. " * 100, rnd.choice(L["inv"])["id"])
        g.add_chat("lune", "user", "hi " * rnd.randint(0, 400))
        g.add_chat("lune", "lune", "hello")
        g.add_chat("merchant", "user", "500 gold?")
    if profile_name == "chaotic":  # buttons mashed in the wrong order
        try_(g.equip, 10**9)
        try_(g.salvage, next(iter(L["equip"].values()), 0))
        try_(g.buy, -1)
        try_(g.use, "phoenix")
        try_(g.set_title, "not_a_title")
        try_(g.answer_choice, True)
        try_(g.set_cosmetic, "frame", "bg_forest")
        if rnd.random() < 0.02:
            g.decline_emergency()


def check(g: G.Game, v: dict, last: dict, where: str) -> None:
    """Invariants that must hold at every step (no negative gold, lists within limits, no lost progress...)."""
    L = g.L
    assert L["gold"] >= 0 and L["xp"] >= 0 and L["streak"] >= 0 and L["shards"] >= 0, where
    assert 0 <= L["shields"] <= G.SHIELD_MAX + 4, (where, L["shields"])
    for k, lim in LIMITS.items():
        assert len(L[k]) <= lim, (where, k, len(L[k]))
    assert len(L["inv"]) <= LT.INVENTORY_MAX
    assert v["level"] >= last.get("level", 1) and L["floor"] >= last.get("floor", 1), where
    assert v["labyrinth"]["hp"] > 0 and math.isfinite(v["labyrinth"]["hp"]), where
    shop = L["shop"] or {}
    assert 0 <= shop.get("annoyance", 0) <= M.ANNOY_MAX and -M.RAPPORT_MAX <= L["rapport"] <= M.RAPPORT_MAX, (
        where,
        shop.get("annoyance"),
    )
    t = shop.get("restocks") or []
    assert len(t) == 2 and t[0] >= 600 and t[1] <= 1200 and t[1] - t[0] >= 180 and 0 <= shop["wave"] <= 2, (where, t)
    for e in shop.get("stock", []):
        assert e["list"] * (1 - M.ROOM_MAX - 0.16) <= e["price"] <= e["list"] * 1.1 + 1, (where, e)
        assert e["floor"] <= e["list"], (where, e)
    if g.goddess != C.GODDESS:
        text = json.dumps({k: x for k, x in v.items() if k not in ("lune_chat", "lore")})
        assert C.GODDESS not in text, (where, "goddess not renamed")
    for q, total in (v.get("manual_log") or {}).items():
        assert 0 <= total <= G.MANUAL_LIMITS[q][1], (where, q, total)
    # secrets stay secret: only earned titles and found hidden quests are in the view, and no riddles at all
    assert {t["id"] for t in v["titles"]} == set(L["titles"]) and {h["id"] for h in v["hidden"]} == set(L["hidden"]), (
        where
    )
    text = json.dumps(v)
    assert not any(h[2] in text for h in C.HIDDEN), (where, "riddle leaked")
    bt = (v["quests"].get("bedtime") or {}).get("goal")
    assert bt is None or bt.endswith(("AM", "PM")) == g.twelve, (where, bt)
    assert len(L["bounties"]) <= G.BOUNTY_MAX + G.BOUNTY_DAILY_MAX, where
    assert all(b["xp"] <= G.CHORE_XP_MAX for b in L["bounties"] if b["source"] == "chore"), where
    assert sum(b["source"] == "daily" for b in L["bounties"]) <= g.daily_bounties, where
    for q, gq in L["guard"].items():
        assert 0 <= gq["acc"] <= G.GUARD[q][2] and gq["held"] >= 0, (where, q, gq)
    gifts = [datetime.fromisoformat(x["date"]) for x in L["gifts"]["log"]]
    assert all((b - a).days >= G.GIFT_COOLDOWN for a, b in zip(gifts, gifts[1:])), (where, "gifts too close")
    for k, x in L["stats"].items():
        assert math.isfinite(x) and x >= 0, (where, k, x)
    for prompt in [
        A.portrait_prompt(v, "feminine"),
        A.guardian_prompt(v["labyrinth"]),
        *[A.item_prompt(i) for i in v["gear"]["inventory"]],
        *[A.goddess_prompt(m, i) for m in A.LUNE_MOODS for i in (0, 9)],
    ]:
        assert 50 < len(prompt["prompt"]) < 2500, (where, len(prompt["prompt"]))
    last.update(level=v["level"], floor=L["floor"])


def run(args: tuple) -> dict:
    """Play one profile and seed for `years` years; returns a summary or the first failure."""
    profile_name, seed, years = args
    rnd = random.Random(seed * 1000 + sum(map(ord, profile_name)))
    profile = PROFILES[profile_name]
    chaotic = profile_name == "chaotic"
    goddess = rnd.choice([None, "Lena", "Aurelia of the Quiet Tide"])
    work = rnd.choice(
        [
            None,
            {"start": 8 * 60, "end": 16 * 60 + 30, "days": [0, 1, 2, 3]},
            {"penalty": False},
            {"start": 22 * 60, "end": 6 * 60, "days": [4, 5, 6]},
        ]
    )
    g = G.Game(
        GOALS,
        rnd.choice(list(C.RACES)),
        seed=f"soak-{profile_name}-{seed}",
        body=rnd.choice(list(A.BODIES)),
        goddess=goddess,
        work=work,
        water_unit=rnd.choice(["ml", "floz"]),
        twelve_hour=rnd.random() < 0.5,
        corrections=set(rnd.sample(["steps", "floors", "hydration"], rnd.randint(0, 3))),
        kids_mode=rnd.random() < 0.4,
        daily_bounties=rnd.randint(0, 10),
    )
    manual = profile_name in ("shopper", "chaotic")  # these players log water and stairs by hand, like a Samsung phone
    last: dict = {}
    job_xp: dict = {}
    t0, slowest, updates, yearly = time.time(), 0.0, 0, []
    day, end = START, START + timedelta(days=round(365.25 * years))
    try:
        while day <= end:  # through the last day, so the final year's checks run too
            if chaotic and rnd.random() < 0.01:  # a vacation, or Home Assistant off for a while
                day += timedelta(days=rnd.randint(2, 60))
                continue
            plan = day_plan(rnd, profile)
            hours = [7, 11, 12, 14, 16, 18, 22] if not chaotic else sorted(rnd.sample(range(0, 24), rnd.randint(1, 6)))
            v = None
            for hour in hours:
                now = datetime(day.year, day.month, day.day, hour, rnd.randint(0, 59))
                s = time.perf_counter()
                g.advance(now)
                r = readings(rnd, profile, max(hour, 6), chaotic, plan)
                if manual:
                    r["hydration"] = r["floors"] = None  # the phone doesn't report them...
                    if hour >= 12:  # ...so they're logged through the day (sometimes a mistake, then undone)
                        for _ in range(rnd.randint(0, 3)):
                            try_(g.log_quest, "hydration", rnd.choice([250, 250, 500, -250, 0, 99999]))
                        try_(g.log_quest, "floors", rnd.choice([1, 2, 3, -1]))
                    if hour == hours[0] and rnd.random() < 0.8:
                        wake = now.replace(hour=min(hour, 6), minute=30)
                        try_(g.log_sleep, wake - timedelta(hours=rnd.uniform(4, 10)), wake)
                v = g.update(r, now)
                if hour == 12 and g.L["level"] >= 5 and rnd.random() < 0.01:  # a job change in the middle of the day
                    g.set_job(rnd.choice(list(C.JOBS)))
                slowest = max(slowest, time.perf_counter() - s)
                updates += 1
            act(g, rnd, v, profile_name)
            for j, x in g.L["jobs"].items():  # every day: no job ever loses XP (switching banks it)
                assert x >= job_xp.get(j, 0) - 1e-6, (day, j, x, job_xp.get(j))
            job_xp = dict(g.L["jobs"])
            sl = (v["quests"].get("sleep") or {}).get("value")  # every day: rest stays believable (HP)
            assert sl is None or 0 <= sl <= G.SLEEP_MAX_H, (day, sl)
            for q, gq in g.L["guard"].items():  # every day: the sensor guard stays sane
                assert 0 <= gq["acc"] <= G.GUARD[q][2] and gq["held"] >= 0, (day, q, gq)
            if (day - START).days // 365 > len(yearly):  # a year boundary (even if a break jumped over it)
                check(g, v, last, f"{profile_name}/{seed} {day}")
                raw = json.dumps(g.L)
                g = G.Game(
                    GOALS,
                    g.race,
                    json.loads(raw),
                    body=g.body,
                    goddess=g.goddess,
                    work=work,
                    water_unit=g.water_unit,
                    twelve_hour=g.twelve,
                    corrections=g.corrections,
                    kids_mode=g.kids_mode,
                    daily_bounties=g.daily_bounties,
                )  # a restart: save, load, carry on
                yearly.append(
                    {
                        "year": len(yearly) + 1,
                        "level": v["level"],
                        "rank": v["rank"],
                        "floor": g.L["floor"],
                        "gold": g.L["gold"],
                        "save_kb": round(len(raw) / 1024, 1),
                        "view_kb": round(len(json.dumps(v)) / 1024, 1),
                        "job": (v["job"] or {}).get("level"),
                        "streak": v["best_streak"],
                        "titles": len(v["titles"]),
                        "hidden": len(v["hidden"]),
                        "gifts": int(L_stat(g, "goddess_gifts")),
                        "fines": int(L_stat(g, "emergency_fines")),
                        "earned": int(L_stat(g, "gold_earned")),
                    }
                )
            day += timedelta(days=1)
    except Exception:  # noqa: BLE001 - anything but GameError is a bug
        return {"profile": profile_name, "seed": seed, "error": traceback.format_exc(), "day": str(day)}
    return {
        "profile": profile_name,
        "seed": seed,
        "yearly": yearly,
        "updates": updates,
        "slowest_ms": round(slowest * 1000, 1),
        "seconds": round(time.time() - t0),
    }


if __name__ == "__main__":
    years = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seeds = [int(x) for x in sys.argv[2:]] or [1, 2, 3]
    jobs = [(p, s, years) for s in seeds for p in PROFILES]
    failures = 0
    with Pool() as pool:
        for res in pool.imap_unordered(run, jobs):
            if "error" in res:
                failures += 1
                print(f"\n!! {res['profile']} seed {res['seed']} broke on {res['day']}:\n{res['error']}")
                continue
            y = res["yearly"]
            pick = [r for r in y if r["year"] in (1, 5, 10, 20, 30) or r is y[-1]]
            print(
                f"\n== {res['profile']} (seed {res['seed']}): {res['updates']:,} updates in {res['seconds']}s, "
                f"slowest update {res['slowest_ms']} ms, biggest save {max(r['save_kb'] for r in y)} KB, "
                f"biggest view {max(r['view_kb'] for r in y)} KB"
            )
            for r in pick:
                print(
                    f"   year {r['year']:>2}: L{r['level']:<4} {r['rank']:<6} floor {r['floor']:>5}  job Lv {r['job'] or '-':<4} "
                    f"gold {r['gold']:>8,}  best streak {r['streak']:>5}  titles {r['titles']:>2}/{len(C.TITLES)}  hidden {r['hidden']:>2}/{len(C.HIDDEN)}  "
                    f"gifts {r['gifts']:>3}  fines {r['fines']:>6,} of {r['earned']:>9,} gold earned"
                )
    print(f"\n{len(jobs) - failures}/{len(jobs)} runs finished cleanly")
    sys.exit(1 if failures else 0)
