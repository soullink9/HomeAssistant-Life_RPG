"""Engine rule checks and a multi-year simulation (plain python, no Home Assistant).

Run: python3 tests/test_game.py
"""

from collections import Counter
from datetime import date, datetime, timedelta
import importlib
import json
from pathlib import Path
import random
import re
import sys
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
MON = date(2026, 10, 12)


def at(day, hour, minute=0):
    """A datetime on `day` at hour:minute."""
    return datetime(day.year, day.month, day.day, hour, minute)


def play(g, now, readings):
    """Advance to `now`, apply readings, check everything is JSON-safe; returns the view and event types."""
    g.advance(now)
    view = g.update(readings, now)
    json.dumps(g.L)
    json.dumps(view)
    return view, [e["type"] for e in view["events"]]


def test_formulas():
    """XP, level, rank, skill and badge formulas."""
    assert G.quest_xp(0.5, False) == 30 and G.quest_xp(1, False) == 100 and G.quest_xp(1.5, True) == 125
    for lvl in range(1, 150):
        assert G.level_for(G.xp_for_level(lvl)) == lvl
    assert G.rank_for(1) == ("E", 10) and G.rank_for(59) == ("A", 60) and G.rank_for(60) == ("S", 70)
    assert G.rank_for(75) == ("S+1", 80) and G.rank_for(245) == ("S+18", 250)
    assert (
        G.skill_grade(0)[0] == "Beginner" and G.skill_grade(4000)[0] == "Saint" and G.skill_grade(9000)[0] == "Saint +2"
    )
    assert G.badge_tier(5_000_000, (100_000, 500_000, 1_000_000, 2_500_000, 5_000_000)) == 5
    assert G.badge_tier(20_000_000, (100_000, 500_000, 1_000_000, 2_500_000, 5_000_000)) == 7
    assert G.badge_tier_name(7) == "Diamond ★3"
    assert G.job_level(0) == 1 and G.job_level(150) == 2 and G.job_level(150 * 81) == 10


def test_no_repeat_bags():
    """Draws don't repeat until the whole pool has been used."""
    g = G.Game(GOALS, seed="bag")
    seen = [g._draw("x", list(range(25))) for _ in range(25)]
    assert sorted(seen) == list(range(25))
    nxt = g._draw("x", list(range(25)))
    assert nxt != seen[-1]


def test_day_flow_and_choice():
    """A full day: guardian appears, the choice is offered and accepted, the day clears and goes perfect."""
    g = G.Game(GOALS, "human", seed="t")
    v, ev = play(g, at(MON, 8), {"steps": 3000, "sleep": 8, "bedtime": 22 * 60 + 45})
    assert "guardian_appeared" in ev and v["labyrinth"]["floor"] == 1 and v["choice"]["status"] == "offered"
    g.answer_choice(True)
    v, ev = play(g, at(MON, 15), {"steps": 8500, "hydration": 2100})
    assert "day_cleared" in ev and v["daily_title"] in C.DAILY_TITLES
    v, ev = play(g, at(MON, 19), {"floors": 12})
    assert v["perfect"] and v["choice"]["status"] in ("won", "accepted", "lost")
    try:
        g.set_job("ranger")
        raise AssertionError("job before level 5")
    except G.GameError:
        pass


def test_jobs_and_skills():
    """Jobs level up and unlock skills; skills grow with practice."""
    g = G.Game({"steps": 8000}, seed="j")
    g.L["level"] = 5
    g.set_job("ranger")
    for i in range(30):
        play(g, at(MON + timedelta(days=i), 20), {"steps": 9000})
    v, ev = play(g, at(MON + timedelta(days=30), 9), {})
    ranger = next(j for j in v["jobs"] if j["id"] == "ranger")
    assert ranger["level"] >= 5 and ranger["active"] and ranger["skills"][0]["unlocked"]
    assert v["skills"]["steps"]["proficiency"] > 400 and v["effects"]["xp:steps"] > 10
    g.set_job("mage")  # switching keeps the ranger's level
    v, _ = play(g, at(MON + timedelta(days=30), 10), {})
    assert next(j for j in v["jobs"] if j["id"] == "ranger")["level"] == ranger["level"]
    assert any(b["source"] == "job" and "Mage" in b["name"] for b in v["bonus_sources"]), (
        "the job shows among the bonuses"
    )


def test_job_xp_counts_from_when_you_take_the_job():
    """Taking a job mid-day doesn't hand it the morning's XP; leaving a job keeps what it earned; coming back
    the same day doesn't count anything twice."""
    g = G.Game({"steps": 8000, "sleep": 7}, seed="jobday")
    g.L["level"] = 5
    v, _ = play(g, at(MON, 14), {"steps": 9000, "sleep": 8})
    assert v["xp_today"] > 100
    g.set_job("ranger")
    v, _ = play(g, at(MON, 14, 5), {"steps": 9000, "sleep": 8})
    ranger = next(j for j in v["jobs"] if j["id"] == "ranger")
    assert ranger["xp"] == 0 and ranger["level"] == 1, ranger
    v, _ = play(g, at(MON, 18), {"steps": 12000, "sleep": 8})  # more walking after taking the job
    earned = next(j for j in v["jobs"] if j["id"] == "ranger")["xp"]
    assert earned > 0
    g.set_job("druid")
    v, _ = play(g, at(MON, 18, 5), {"steps": 12000, "sleep": 8})
    assert next(j for j in v["jobs"] if j["id"] == "ranger")["xp"] == earned, "the job you leave keeps its XP"
    assert next(j for j in v["jobs"] if j["id"] == "druid")["xp"] == 0
    g.set_job("ranger")  # straight back: nothing is counted twice
    v, _ = play(g, at(MON, 18, 10), {"steps": 12000, "sleep": 8})
    assert next(j for j in v["jobs"] if j["id"] == "ranger")["xp"] == earned
    play(g, at(MON + timedelta(days=1), 9), {})  # the day closes: the ranger keeps exactly what it earned
    assert round(g.L["jobs"]["ranger"]) == earned and round(g.L["jobs"].get("druid", 0)) == 0


def test_penalty_and_labyrinth():
    """A missed day sets a penalty quest that saves the streak; the guardian takes damage."""
    g = G.Game({"steps": 1000, "sleep": 7}, seed="p")
    for i in range(5):
        play(g, at(MON + timedelta(days=i), 20), {"steps": 1200})
    v, ev = play(g, at(MON + timedelta(days=6), 9), {})
    assert "penalty_quest" in ev and v["penalty"]["need"] == 2
    v, _ = play(g, at(MON + timedelta(days=6), 20), {"steps": 1500, "sleep": 8})
    assert v["penalty"]["met"] and v["streak"] == 6
    v, ev = play(g, at(MON + timedelta(days=7), 8), {})
    assert "penalty_cleared" in ev
    # the floor-1 guardian falls, next week opens floor 2
    assert v["labyrinth"]["floor"] == 2 or v["bestiary_total"] >= 1


def test_emergency():
    """An emergency quest starts at its time and clears when the target is reached."""
    g = G.Game({"steps": 8000}, seed="e")
    g.advance(at(MON, 7))
    g.L["emergency"] = {
        "date": MON.isoformat(),
        "quest": "steps",
        "at": "12:00",
        "status": "scheduled",
        "minutes": 60,
        "title": C.EMERGENCY["steps"][3][0],
    }
    v, ev = play(g, at(MON, 12, 5), {"steps": 4000})
    assert v["emergency"]["status"] == "active" and "1,600" in v["emergency"]["title"]
    v, ev = play(g, at(MON, 12, 15), {"steps": 5700})
    assert v["emergency"]["status"] == "cleared" and any(h["id"] == "quick_draw" and h["found"] for h in v["hidden"])


def _emergency(g, day, hhmm="12:00"):
    """Plan a steps emergency on `day` at `hhmm`."""
    g.advance(at(day, 7))
    g.L["emergency"] = {
        "date": day.isoformat(),
        "quest": "steps",
        "at": hhmm,
        "status": "scheduled",
        "minutes": 60,
        "title": C.EMERGENCY["steps"][3][0],
    }


def test_emergency_penalty():
    """At work an emergency is free; outside working hours failing costs a little gold, declining half."""
    sat = MON + timedelta(days=5)
    # weekday at noon = working hours: no fine
    g = G.Game({"steps": 8000}, seed="pen")
    g.L["gold"] = 1000
    _emergency(g, MON)
    v, ev = play(g, at(MON, 12, 5), {"steps": 4000})
    assert v["emergency"]["excused"] and "emergency_quest" in ev
    v, ev = play(g, at(MON, 13, 10), {"steps": 4100})
    fail = next(e for e in v["events"] if e["type"] == "emergency_failed")
    assert fail["excused"] and fail["why"] == "work" and fail["would_be"] > 0 and g.L["gold"] == 1000
    # Saturday: a modest fine, capped by your gold
    _emergency(g, sat)
    v, _ = play(g, at(sat, 12, 5), {"steps": 4000})
    fine = v["emergency"]["fine"]
    assert not v["emergency"]["excused"] and 0 < fine <= 200 and v["emergency"]["decline_fine"] == fine // 2
    v, ev = play(g, at(sat, 13, 10), {"steps": 4100})
    assert g.L["gold"] == 1000 - fine and any(
        e["type"] == "emergency_failed" and e["fine"] == fine for e in v["events"]
    )
    # declining outside work costs half; with little gold the fine shrinks (15% of what you have)
    sun = sat + timedelta(days=1)
    g.L["gold"] = 100
    _emergency(g, sun)
    play(g, at(sun, 12, 5), {"steps": 4000})
    assert g.L["emergency"]["fine"] == 10 and g.decline_emergency() == 5 and g.L["gold"] == 95
    # Home Assistant away when it ended: no fine
    tue = MON + timedelta(days=8)
    g.L["gold"] = 1000
    _emergency(g, tue + timedelta(days=-1), "19:00")  # Monday 19:00, after work
    mon2 = MON + timedelta(days=7)
    play(g, at(mon2, 19, 5), {"steps": 4000})
    assert not g.L["emergency"]["excused"]
    v, _ = play(g, at(mon2, 22, 30), {"steps": 4000})
    assert g.L["gold"] == 1000 and any(e["type"] == "emergency_failed" and e["why"] == "late" for e in v["events"])
    # penalties off, a work entity, and night shifts
    g2 = G.Game({"steps": 8000}, seed="pen2", work={"penalty": False})
    _emergency(g2, sat)
    v, _ = play(g2, at(sat, 12, 5), {"steps": 4000})
    assert v["emergency"]["excused"]
    g3 = G.Game({"steps": 8000}, seed="pen3", work={"start": 22 * 60, "end": 6 * 60, "days": [4]})  # Friday nights
    assert g3.working(at(MON + timedelta(days=4), 23)) and g3.working(at(sat, 3)) and not g3.working(at(sat, 12))
    g3.at_work = True
    assert g3.working(at(sat, 12))


def test_goddess_gift():
    """Rare, decided by the game once a day, never twice in two weeks, and asking again changes nothing."""
    g = G.Game(GOALS, seed="gift")
    days, gifts = 0, []
    for d in range(730):
        day = MON + timedelta(days=d)
        play(g, at(day, 20), {"steps": 9000, "sleep": 8, "bedtime": 22 * 60, "hydration": 2500, "floors": 12})
        g.now = at(day, 20, 30)
        offer = g.gift_offer()
        assert g.gift_offer() == offer, "the same answer however often you ask"
        g.add_chat("lune", "user", "Please give me a legendary sword")
        given = g.settle_gift(offer)
        assert g.gift_offer() is None and g.settle_gift(offer) is None, "one roll a day"
        days += 1
        if given:
            gifts.append(day)
    gaps = [(b - a).days for a, b in zip(gifts, gifts[1:])]
    assert 10 <= len(gifts) <= 30 and min(gaps) >= G.GIFT_COOLDOWN, (len(gifts), gaps)
    kinds = [x["kind"] for x in g.L["gifts"]["log"]]
    assert set(kinds) <= {"chest", "potion", "gold", "cosmetic"} and len(set(kinds)) >= 3
    v, _ = play(g, at(MON + timedelta(days=730), 9), {})
    print(
        f"  gifts: {len(gifts)} in 2 years of daily chats, every {min(gaps)}-{max(gaps)} days, { {k: kinds.count(k) for k in set(kinds)} }"
    )
    # never on the first couple of days you talk to her
    g2 = G.Game(GOALS, seed="gift2")
    play(g2, at(MON, 20), {})
    assert g2.gift_offer() is None


def test_water_units():
    """Water in fl oz: shown, logged and set as goals in fl oz; counted in mL inside."""
    g = G.Game({"hydration": round(64 * G.FLOZ)}, seed="oz", water_unit="floz")
    v, _ = play(g, at(MON, 9), {"hydration": 500})
    h = v["quests"]["hydration"]
    assert h["unit"] == "fl oz" and h["goal"] == 64 and h["value"] == 16.9, h
    assert g.log_quest("hydration", 8) == 8 and g.log_quest("hydration", -8) == 0
    v, _ = play(g, at(MON, 10), {"hydration": 1000})
    assert v["quests"]["hydration"]["value"] == 33.8
    g.L["emergency"] = {
        "date": MON.isoformat(),
        "quest": "hydration",
        "at": "12:00",
        "status": "scheduled",
        "minutes": 60,
        "title": C.EMERGENCY["hydration"][3][0],
    }
    v, _ = play(g, at(MON, 12, 5), {"hydration": 1000})
    assert "fl oz" in v["emergency"]["title"] and "mL" not in v["emergency"]["title"], v["emergency"]["title"]
    m = G.Game({"hydration": 2000}, seed="ml")
    v, _ = play(m, at(MON, 9), {"hydration": 500})
    assert v["quests"]["hydration"]["unit"] == "mL" and v["quests"]["hydration"]["value"] == 500


def test_sensor_guard():
    """Impossible jumps are held back, a source fixed downward is followed, and counts can be corrected."""
    g = G.Game({"steps": 8000, "floors": 10}, seed="guard", corrections={"steps", "floors"})
    v, _ = play(g, at(MON, 9), {"steps": 3000, "floors": 2})
    # a second app starts writing the same steps: +9,000 in five minutes
    g.update({"steps": 12000}, at(MON, 9, 5))
    v = g.update({"steps": 12100}, at(MON, 9, 10))
    st = v["quests"]["steps"]
    assert st["value"] < 6500 and st["held"] >= 5000, st
    assert sum(e["type"] == "reading_held" for e in g.L["log"]) == 1
    # the duplicate is removed in Health Connect: the raw count drops, what we held goes first
    v = g.update({"steps": 3200}, at(MON, 9, 20))
    assert v["quests"]["steps"]["value"] == st["value"], "nothing double-subtracted"
    # a phone that syncs after hours offline is believed
    v = g.update({"steps": 15000}, at(MON, 14))
    assert v["quests"]["steps"]["value"] > 14000 and v["quests"]["steps"]["done"]
    # a lower reading that sticks is followed; a blip is not
    v = g.update({"steps": 9000}, at(MON, 14, 5))
    assert v["quests"]["steps"]["value"] > 14000, "a single low reading is ignored"
    v = g.update({"steps": 15100}, at(MON, 14, 10))
    v = g.update({"steps": 9000}, at(MON, 14, 15))
    v = g.update({"steps": 9100}, at(MON, 14, 35))
    assert 9000 <= v["quests"]["steps"]["value"] <= 9100, v["quests"]["steps"]
    # correcting by hand; later readings carry on from the corrected count
    assert g.correct("steps", today=7000, record=12000) == {"quest": "steps", "today": 7000, "record": 12000}
    v = g.update({"steps": 9600}, at(MON, 14, 45))
    assert v["quests"]["steps"]["value"] == 7500 and v["quests"]["steps"]["record"] == 12000
    for bad in ({"today": -1}, {"today": 10**6}, {}):
        try:
            g.correct("steps", **bad)
            raise AssertionError(bad)
        except G.GameError:
            pass
    # "they were real": count what was held
    g.update({"floors": 3}, at(MON, 14, 50))
    v = g.update({"floors": 60}, at(MON, 14, 55))
    assert v["quests"]["floors"]["held"] > 0
    assert g.accept_held("floors") == 60
    # a day has a ceiling, and tomorrow starts clean
    v = g.update({"steps": 10**7}, at(MON, 23, 50))
    assert v["quests"]["steps"]["value"] <= G.GUARD["steps"][2]
    v, _ = play(g, at(MON + timedelta(days=1), 8), {"steps": 2000})
    assert v["quests"]["steps"]["value"] == 2000 and "held" not in v["quests"]["steps"]


def test_corrections_switch():
    """Corrections are off unless turned on per quest; with them off nothing can be typed in or waved through."""
    g = G.Game({"steps": 8000, "hydration": 2000}, seed="cheat", corrections={"hydration"})
    v, _ = play(g, at(MON, 9), {"steps": 3000, "hydration": 500})
    assert not v["quests"]["steps"]["fixable"] and v["quests"]["hydration"]["fixable"]
    for fn, args in ((g.correct, ("steps", 20000)), (g.accept_held, ("steps",))):
        try:
            fn(*args)
            raise AssertionError("a correction went through while switched off")
        except G.GameError as err:
            assert "turned off" in str(err)
    assert g.correct("hydration", today=1500)["today"] == 1500
    assert G.Game(GOALS, seed="x").corrections == set(), "off by default"


def test_sleep_reported_twice():
    """Two apps (or one revising its session) report the same night: it counts once. A nap still adds up."""
    s = {
        "a": {"start": "2026-10-11T23:05:00", "end": "2026-10-12T06:40:00", "min": 420},
        "b": {"start": "2026-10-11T23:12:00", "end": "2026-10-12T06:38:00", "min": 410},
        "manual:2026-10-11T23:00:00": {"start": "2026-10-11T23:00:00", "end": "2026-10-12T06:45:00", "min": 465},
    }
    hours, bed = G.Game.sleep_totals(s)
    assert hours == 465 / 60 and bed == 23 * 60, (hours, bed)
    s["nap"] = {"start": "2026-10-12T13:00:00", "end": "2026-10-12T13:40:00", "min": 40}
    assert G.Game.sleep_totals(s)[0] == (465 + 40) / 60
    old = {"2026-10-11T23:05:00-04:00": 420.0, "2026-10-11T23:12:00-04:00": 410.0}  # a save from before the fix
    assert G.Game.sleep_totals(old)[0] == 7.0
    g = G.Game(GOALS, seed="hp")
    g.advance(at(MON, 7))
    g.L["inputs"]["sleep"] = {k: v for k, v in s.items() if k != "nap"}
    v, _ = play(g, at(MON, 7), {"sleep": G.Game.sleep_totals(g.L["inputs"]["sleep"])[0]})
    assert v["quests"]["sleep"]["pct"] <= 110, v["quests"]["sleep"]
    assert (
        G.Game.sleep_totals(
            {
                str(i): {"start": f"2026-10-12T{i:02d}:00:00", "end": f"2026-10-12T{i:02d}:59:00", "min": 59}
                for i in range(24)
            }
        )[0]
        == G.SLEEP_MAX_H
    ), "a day holds at most 16 hours of sleep"


def test_lights_out_and_rewards():
    """Lights out can be logged on its own (Rest left to the sensor); a choice says exactly what its chest holds;
    guardian paintings lead with the creature, not the joke name."""
    g = G.Game(GOALS, seed="bed", twelve_hour=True)
    g.advance(at(MON, 7))
    g.now = at(MON, 7)
    assert g.log_bedtime(at(MON - timedelta(days=1), 22, 40)) == "10:40 PM"
    g.L["inputs"]["sleep"]["sensor"] = 450.0  # the phone's duration, no times
    hours, bed = G.Game.sleep_totals(g.L["inputs"]["sleep"])
    assert hours == 7.5 and bed == 22 * 60 + 40
    assert g.log_bedtime(at(MON - timedelta(days=1), 23, 5)) == "11:05 PM"
    assert sum(k.startswith("bed:") for k in g.L["inputs"]["sleep"]) == 1, "the latest bedtime replaces the last one"
    try:
        g.log_bedtime(at(MON - timedelta(days=3), 22))
        raise AssertionError("a bedtime from days ago")
    except G.GameError:
        pass
    # choices: the chest and its odds are spelled out
    seen = set()
    for d in range(60):
        gg = G.Game(GOALS, seed=f"odds{d}")
        v, _ = play(gg, at(MON, 9), {"steps": 100})
        c = v["choice"]
        if c and c.get("chest"):
            assert sum(c["chest"]["odds"].values()) in (99, 100, 101) and c["chest"]["items"] == 1
            assert c["chest"]["name"] in c["text"] and "one item" in c["chest"]["words"]
            seen.add(c["chest"]["kind"])
    assert seen == {"choice", "wager"}, seen
    p = A.guardian_prompt(
        {
            "seed": "x",
            "kind": "hydra",
            "element": "bone",
            "name": "Procrastinating Hissing Crown who Waits",
            "floor": 1,
            "trait": {"name": "Echoing Vault"},
        }
    )
    assert p["prompt"].startswith("A hydra:") and "bone" in p["prompt"][:200] and "Procrastinating" not in p["prompt"]


def test_bounty_board():
    """Side quests each day (one with a chest); kids-mode chores wait for a parent; repeats reopen; caps hold."""
    g = G.Game({"steps": 8000}, seed="board", kids_mode=True, daily_bounties=3)
    v, _ = play(g, at(MON, 8), {"steps": 100})
    daily = [b for b in v["bounties"] if b["source"] == "daily"]
    assert len(daily) == 3 and sum(b["chest"] for b in daily) == 1 and all(b["xp"] > 0 for b in daily)
    b = g.add_bounty("Feed the dog", 999, 999, False, "weekly")
    assert b["xp"] == G.CHORE_XP_MAX and b["gold"] == G.CHORE_GOLD_MAX
    for bad in (("", 10), ("Nothing", 0)):
        try:
            g.add_bounty(*bad)
            raise AssertionError(bad)
        except G.GameError:
            pass
    assert g.claim_bounty(b["id"]) == "claimed"
    try:
        g.claim_bounty(b["id"])
        raise AssertionError("claimed twice")
    except G.GameError:
        pass
    assert g.approve_bounty(b["id"], ok=False) == "open" and g.claim_bounty(b["id"]) == "claimed"
    xp0, gold0 = g.L["bonus"], g.L["gold"]
    assert g.approve_bounty(b["id"]) == "done" and g.L["bonus"] == xp0 + 300 and g.L["gold"] == gold0 + 300
    v, _ = play(g, at(MON + timedelta(days=2), 8), {"steps": 100})
    assert next(x for x in v["bounties"] if x["id"] == b["id"])["state"] == "done", "weekly: not again this week"
    v, _ = play(g, at(MON + timedelta(days=7), 8), {"steps": 100})
    assert next(x for x in v["bounties"] if x["id"] == b["id"])["state"] == "open", "weekly: open again on Monday"
    assert len([x for x in v["bounties"] if x["source"] == "daily"]) == 3, "yesterday's side quests left"
    adult = G.Game({"steps": 8000}, seed="adult")
    try:
        adult.add_bounty("Chores", 10)
        raise AssertionError("chores without kids mode")
    except G.GameError:
        pass
    side = adult.L["bounties"][0] if adult.L["bounties"] else None
    v, _ = play(adult, at(MON, 8), {"steps": 100})
    side = v["bounties"][0]
    assert adult.claim_bounty(side["id"]) == "done"
    assert G.Game({"steps": 8000}, seed="none", daily_bounties=0).daily_bounties == 0


def test_portrait_choices_and_faces():
    """Portrait choices are checked, saved and reach the prompts; framing never changes the painting."""
    g = G.Game(GOALS, "beastkin", seed="pp")
    v, _ = play(g, at(MON, 9), {"steps": 100})
    g.set_portrait_prefs(
        {"framing": "half", "fur": "snow-white", "eyes": "violet", "build": "stocky", "weapon": "none"}
    )
    v, _ = play(g, at(MON, 10), {"steps": 100})
    assert v["appearance"]["fur"] == A.FUR.index("snow-white") and v["appearance"]["build"] == A.BUILDS["stocky"][0]
    p = A.portrait_prompt(v, "masculine")["prompt"]
    assert p.startswith("Full-body") and "snow-white" in p and "stocky" in p and "holding" not in p, (
        "framing only crops"
    )
    for bad in ({"hair": "plaid"}, {"weapon": "Bazooka"}, {"framing": "sideways"}):
        try:
            g.set_portrait_prefs(bad)
            raise AssertionError(bad)
        except G.GameError:
            pass
    assert g.set_portrait_prefs({}) == {} and "portrait_prefs" in g.L
    m = v["market"]
    assert m["face"] == m["mood"]
    shop = g.L["shop"]
    shop["restocks"] = []  # no deliveries in the middle of this
    shop["annoyance"], shop["calm_at"] = 4.5, at(MON, 11).timestamp()
    v, _ = play(g, at(MON, 11), {})
    assert v["market"]["face"] == "annoyed" and v["market"]["temper"] == "impatient"
    shop["annoyance"], shop["calm_at"] = 7.0, at(MON, 11, 30).timestamp()
    v, _ = play(g, at(MON, 11, 30), {})
    assert v["market"]["face"] == "angry"
    shop["fed_up"], shop["annoyance"], shop["calm_at"] = True, 10.0, at(MON, 11, 45).timestamp()
    v, _ = play(g, at(MON, 11, 45), {})
    assert v["market"]["face"] == "furious" and set(A.MERCHANT_MOODS) >= {"annoyed", "angry", "furious"}
    v, _ = play(g, at(MON, 13, 50), {})  # two hours later he has calmed down
    assert v["market"]["temper"] in ("calm", "impatient") and v["market"]["face"] != "furious"
    # the goddess has portrait choices too
    g.set_goddess_prefs({"framing": "closeup", "hair": "silver-grey", "outfit": "starlight", "eyes": "golden"})
    gp = A.goddess_prompt("proud", 2, "Lena", g.L["goddess_prefs"])["prompt"]
    assert (
        "silver-grey" in gp
        and "midnight-blue gown" in gp
        and "golden eyes" in gp
        and gp.startswith("Full-body")
        and "Lena" in gp
    )
    assert A.goddess_prompt("proud", 2, "Lune")["prompt"] == A.goddess_prompt("proud", 2, "Lune", {})["prompt"]
    for bad in ({"hair": "plaid"}, {"outfit": "spacesuit"}):
        try:
            g.set_goddess_prefs(bad)
            raise AssertionError(bad)
        except G.GameError:
            pass


def test_clock():
    """A 12-hour clock: bedtime, the choice's deadline and wording, and hidden-quest notes all read 11:00 PM style."""
    g = G.Game(GOALS, seed="clock", twelve_hour=True)
    v, _ = play(g, at(MON, 9), {"bedtime": 22 * 60 + 41, "sleep": 8})
    assert v["quests"]["bedtime"]["goal"] == "11:00 PM" and v["quests"]["bedtime"]["value"] == "10:41 PM", v["quests"][
        "bedtime"
    ]
    assert v["clock"] == "12" and G.clock(0, True) == "12:00 AM" and G.clock(12 * 60, True) == "12:00 PM"
    assert G.clock_text("finish Walk before 17:00 for 140 XP", True) == "finish Walk before 5:00 PM for 140 XP"
    assert G.clock_text("2026-10-13T14:05:00-04:00", True) == "2026-10-13T14:05:00-04:00", "timestamps are left alone"
    for d in range(30):  # a timed bounty shows its hour on the 12-hour clock
        day = MON + timedelta(days=d)
        v, _ = play(g, at(day, 9), {"steps": 100})
        if v["choice"]:
            assert v["choice"]["deadline"] == "2:00 PM" and not re.search(r"\b1[3-9]:00", v["choice"]["text"]), v[
                "choice"
            ]
    g24 = G.Game(GOALS, seed="clock")
    v, _ = play(g24, at(MON, 9), {"bedtime": 22 * 60 + 41, "sleep": 8})
    assert v["quests"]["bedtime"]["goal"] == "23:00" and v["clock"] == "24"


def test_save_with_missing_keys():
    """A save written before a feature existed loads with that feature's defaults and plays on."""
    g = G.Game(GOALS, seed="keys")
    play(g, at(MON, 9), {"steps": 9000})
    old = json.loads(json.dumps(g.L))
    for k in ("rapport", "job_start", "goddess_prefs", "bounties", "portrait_prefs"):
        old.pop(k, None)
    old["shop"] = None
    g2 = G.Game(GOALS, ledger=old, seed="keys")
    v, _ = play(g2, at(MON, 20), {"steps": 9500})
    assert v["market"]["delivery"] >= 1 and g2.L["rapport"] == 0.0 and v["goddess"]["prefs"] == {}


def test_market():
    """Market stock, prices, buying and selling."""
    g = G.Game(GOALS, "elf", seed="mkt")
    v, ev = play(g, at(MON, 9), {"steps": 9000, "sleep": 8, "bedtime": 22 * 60})
    assert v["gold"] == sum(M.gold_for(e) for e in v["events"]) > 0 and v["market"]["stock"]
    assert all("floor" not in e for e in v["market"]["stock"]), "the haggle floor stays secret"
    kinds = [e["kind"] for e in v["market"]["stock"]]
    assert kinds.count("gear") == 3 and kinds.count("consumable") == 3 and kinds.count("cosmetic") == 2
    g.L["gold"] = 100_000
    gear = next(e for e in g.L["shop"]["stock"] if e["kind"] == "gear")
    lst, floor = gear["list"], gear["floor"]
    offer, r = int(lst * 0.8), None
    for _ in range(G.M.HAGGLE_ROUNDS + 1):  # meet him partway, a little higher each time
        r = g.haggle(gear["id"], max(offer, 1))
        if r["result"] == "accepted":
            break
        assert r["result"] in ("countered", "holding", "final") and floor <= r["price"] <= lst, r
        if r["result"] == "final":
            r = g.haggle(gear["id"], r["price"])
            break
        offer = int(offer + (r["price"] - offer) * 0.4) + 1
    assert r["result"] in ("accepted", "closed") and floor <= gear["price"] < lst, (r, gear)
    out = g.buy(gear["id"])
    assert out["bought"]["id"] == gear["item"]["id"] and g.L["stats"]["deals"] == 1
    try:
        g.buy(gear["id"])
        raise AssertionError("bought twice")
    except G.GameError:
        pass
    other = next(e for e in g.L["shop"]["stock"] if e["kind"] == "gear" and not e["sold"])
    before = other["price"]
    r = g.haggle(other["id"], int(other["list"] * 0.3))
    assert r["result"] == "insulted" and before < r["price"] <= other["list"] * 1.1 and "thin_skin" in g.L["hidden"]
    assert g.haggle(other["id"], int(other["list"] * 0.3))["result"] in ("refused", "fed_up")
    assert g.haggle(other["id"], other["list"])["result"] == "closed", "no more haggling on that one"
    assert g.L["rapport"] < 0.5
    # consumables
    g.L["bag"] = {"elixir": 4, "reroll": 1, "shield_charm": 3, "phoenix": 1, "lucky_charm": 1}
    before = g.effects().get("xp:all", 0)
    g.use("elixir")
    assert g.effects()["xp:all"] == before + 10
    try:
        g.use("elixir")
        raise AssertionError("same elixir twice a day")
    except G.GameError:
        pass
    g.L["week"]["elixirs"] = G.M.ELIXIRS_PER_WEEK
    g.L["bag"]["greater_elixir"] = 1
    try:
        g.use("greater_elixir")
        raise AssertionError("weekly elixir limit")
    except G.GameError:
        pass
    g.use("shield_charm")
    g.use("shield_charm")
    try:
        g.use("shield_charm")
        raise AssertionError("shield cap")
    except G.GameError:
        pass
    g.use("reroll")
    assert g.L["choice"]["status"] == "offered"
    g.L["last_break"] = {"date": MON.isoformat(), "streak": 40}
    g.use("phoenix")
    assert g.L["streak"] >= 40 and g.L["phoenix_used"]
    g.use("lucky_charm")
    assert g.L["charms"]["luck"] == 100
    chest = g.L["chests"][0]["id"]
    g.open_chest(chest)
    assert "luck" not in g.L["charms"]
    # cosmetics and selling
    cos = next(e for e in g.L["shop"]["stock"] if e["kind"] == "cosmetic")
    g.buy(cos["id"])
    cat = M.COSMETICS[cos["cid"]][0]
    assert g.L["cosmetics"]["active"][cat] == cos["cid"]
    g.set_cosmetic(cat, None)
    spare = (
        next(i for i in g.L["inv"] if i["id"] not in g.L["equip"].values())
        if len(g.L["inv"]) > len(g.L["equip"])
        else None
    )
    if spare:
        gold = g.L["gold"]
        assert g.sell(spare["id"]) == M.sell_value(spare) and g.L["gold"] > gold
    # flavour text never touches numbers
    g.set_lore("morning", "  The moon   smiles. " * 100, ref=MON.isoformat())
    assert len(g.L["lore"]["morning"]["text"]) <= G.LORE_MAX
    for i in range(20):
        g.add_chat("lune", "user" if i % 2 == 0 else "lune", f"line {i}")
    assert len(g.L["lune_chat"]) == G.CHAT_MAX and g.L["lune_days"] == [MON.isoformat()]
    v, _ = play(g, at(MON, 10), {})
    json.dumps(v)
    assert v["appearance"]["hairstyle"] in A.HAIRSTYLES["elf"]


def _haggle_until_done(g, e, start, step):
    """A patient haggler: open at `start` x list, then close `step` of the gap to his price each round."""
    offer, rounds, results = int(e["list"] * start), 0, []
    while True:
        r = g.haggle(e["id"], max(offer, 1))
        rounds += 1
        results.append(r["result"])
        if r["result"] in ("accepted", "closed", "fed_up", "refused"):
            return rounds, results, r
        if r["result"] == "final":
            r = g.haggle(e["id"], r["price"])
            return rounds + 1, results + [r["result"]], r
        offer = int(offer + (r["price"] - offer) * step) + 1


def test_haggling():
    """Fair haggling is real back-and-forth he never minds; lowballs annoy him; insults put one price up a little;
    pushing too far ends haggling (no markup) until he has cooled down or the next delivery arrives."""
    rounds, prices, fed, grew = [], [], 0, 0
    for seed in range(60):
        g = G.Game(GOALS, seed=f"hag{seed}")
        play(g, at(MON, 9), {"steps": 9000})
        g.L["gold"] = 10**6
        for e in [x for x in g.L["shop"]["stock"] if not x["sold"]]:
            n, results, r = _haggle_until_done(g, e, 0.75, 0.35)
            rounds.append(n)
            fed += r["result"] == "fed_up"
            grew += any(x == "countered" for x in results)
            if r["result"] == "accepted":
                assert e["floor"] - e["list"] * 0.01 <= r["price"] <= e["list"], (e, r)
                prices.append(r["price"] / e["list"])
        assert G.M.temper(g.L["shop"]) in ("calm", "impatient"), "fair haggling doesn't make him angry"
    assert fed == 0 and max(rounds) >= 3 and sum(rounds) / len(rounds) >= 2, (fed, rounds)
    assert grew >= len(rounds) * 0.6 and min(prices) >= 0.72 and max(prices) < 1.0, (grew, min(prices), max(prices))
    print(
        f"  fair haggling: {sum(rounds) / len(rounds):.1f} rounds on average (up to {max(rounds)}), "
        f"{round(100 * (1 - sum(prices) / len(prices)))}% off on average, never fed up"
    )
    # a lowballer: annoyance builds, he stops haggling, prices never jump; he cools off with time
    snaps, closed_after = [], []
    for seed in range(40):
        g = G.Game(GOALS, seed=f"low{seed}")
        play(g, at(MON, 9), {"steps": 9000})
        lists = {e["id"]: e["list"] for e in g.L["shop"]["stock"]}
        n, r = 0, {"result": None}
        for e in g.L["shop"]["stock"] * 3:
            if e["closed"] or e["deal"]:
                continue
            n += 1
            r = g.haggle(e["id"], int(e["list"] * 0.62))
            assert r["result"] in ("holding", "countered", "final", "fed_up"), r
            if r["result"] == "fed_up":
                break
        snaps.append(n)
        assert all(x["price"] <= lists[x["id"]] for x in g.L["shop"]["stock"]), "fed up never marks prices up"
        if r["result"] == "fed_up":
            assert g.L["rapport"] < 0 and G.M.face(g.L["shop"].get("last_result"), g.L["shop"]) == "furious"
            assert g.haggle(g.L["shop"]["stock"][0]["id"], 1)["result"] == "closed"
            v, _ = play(g, at(MON, 9, 1) + timedelta(hours=3), {})
            assert not g.L["shop"].get("fed_up") or v["market"]["delivery"] > 1, "he cools down"
            closed_after.append(n)
    assert snaps and len(set(snaps)) >= 2 and min(snaps) >= 4, sorted(snaps)
    print(
        f"  steady lowballs at 62%: he stops haggling after {min(snaps)}-{max(snaps)} offers "
        f"({len(closed_after)}/40 days), with no price rises"
    )
    # walking away: sometimes he calls you back with a better (final) price
    called, total = 0, 0
    for seed in range(60):
        g = G.Game(GOALS, seed=f"walk{seed}")
        play(g, at(MON, 9), {"steps": 9000})
        e = next(x for x in g.L["shop"]["stock"] if x["kind"] == "gear")
        r = g.haggle(e["id"], int(e["floor"] * 0.95))
        if r["result"] in ("accepted", "fed_up"):
            continue
        ask = e["price"]
        r = g.walk_away(e["id"])
        total += 1
        if r["result"] == "called_back":
            called += 1
            assert e["floor"] - e["list"] * 0.01 <= r["price"] < ask and e["closed"]
        else:
            assert r["result"] == "walked" and e["price"] == ask
        assert g.walk_away(e["id"])["result"] == "walked", "only once per item"
    assert 0.2 * total <= called <= 0.8 * total, (called, total)
    print(f"  walking away: called back {called}/{total} times")


def test_market_deliveries():
    """Stock turns over three times a day at random, well-spaced times; a deal he agreed to waits for you."""
    seen_times, themes = [], set()
    for seed in range(30):
        g = G.Game(GOALS, seed=f"del{seed}")
        play(g, at(MON, 8), {"steps": 9000})
        shop = g.L["shop"]
        t1, t2 = shop["restocks"]
        assert 600 <= t1 <= 810 and 990 <= t2 <= 1200 and t2 - t1 >= 180, (t1, t2)
        seen_times.append((t1, t2))
        first = {e["id"] for e in shop["stock"]}
        themes.add(shop["theme"])
        e = next(x for x in shop["stock"] if x["kind"] == "consumable")
        g.L["gold"] = 10**6
        g.haggle(e["id"], e["list"])  # a deal, not yet bought
        v, ev = play(g, at(MON, t1 // 60, t1 % 60), {})
        assert "market_restocked" in ev and v["market"]["delivery"] == 2
        ids = {x["id"] for x in g.L["shop"]["stock"]}
        assert e["id"] in ids and len(ids & first) == 1, "only the agreed deal carries over"
        themes.add(g.L["shop"]["theme"])
        v, ev = play(g, at(MON, 23, 30), {})
        assert v["market"]["delivery"] == 3 and v["market"]["next_delivery"] is None
        themes.add(g.L["shop"]["theme"])
        v, ev = play(g, at(MON, 23, 45), {})
        assert "market_restocked" not in ev
    assert len(set(seen_times)) >= 25 and themes >= {"general", "armoury", "alchemy", "curios"}, themes
    g = G.Game({"steps": 8000}, seed="tonic")
    for seed in range(40):
        stock, _ = G.M.make_stock(random.Random(seed), 0, 10, ["steps"], False, [], "alchemy")
        assert all(G.M.TONICS.get(x.get("cid"), "steps") == "steps" for x in stock), "tonics only for your quests"


def test_logging():
    """Logging water, stairs and sleep by hand, and refusing impossible amounts."""
    g = G.Game({"steps": 8000, "hydration": 2000, "floors": 10, "sleep": 7.5, "bedtime": 23 * 60}, seed="log")
    play(g, at(MON, 9), {"steps": 1000})
    assert g.log_quest("hydration", 250) == 250 and g.log_quest("hydration", 1750) == 2000
    v, ev = play(g, at(MON, 10), {"steps": 1000, "hydration": None})
    assert v["quests"]["hydration"]["done"] and "quest_complete" in ev and v["manual_log"]["hydration"] == 2000
    g.log_quest("hydration", -500)
    v, _ = play(g, at(MON, 11), {})
    assert v["quests"]["hydration"]["value"] == 1500 and not v["quests"]["hydration"]["done"]
    for bad in [("hydration", 0), ("hydration", 9000), ("sleep", 5), ("steps", 100), ("floors", "lots")]:
        try:
            g.log_quest(*bad)
            raise AssertionError(f"accepted {bad}")
        except G.GameError:
            pass
    g.log_quest("floors", 4)
    v, _ = play(g, at(MON, 12), {"floors": 3})  # on top of a sensor
    assert v["quests"]["floors"]["value"] == 7
    start, end = datetime(2026, 10, 11, 22, 40), datetime(2026, 10, 12, 6, 50)
    g.now = at(MON, 12)
    assert g.log_sleep(start, end) == 8.17
    hours, bed = G.Game.sleep_totals(g.L["inputs"]["sleep"])
    assert round(hours, 2) == 8.17 and bed == 22 * 60 + 40
    for s0, e0 in [
        (end, start),
        (datetime(2026, 10, 10, 22), datetime(2026, 10, 11, 6)),
        (datetime(2026, 10, 12, 1), datetime(2026, 10, 12, 1, 5)),
    ]:
        try:
            g.log_sleep(s0, e0)
            raise AssertionError("bad sleep accepted")
        except G.GameError:
            pass
    v, _ = play(g, at(MON + timedelta(days=1), 9), {})
    assert v["manual_log"] == {} and "sleep" not in g.L["inputs"]


def test_goddess_name():
    """A custom goddess name replaces the default everywhere the player can see."""
    g = G.Game(GOALS, seed="name", goddess="Lena")
    for i in range(3):
        v, _ = play(
            g,
            at(MON + timedelta(days=i), 20),
            {"steps": 9000, "sleep": 8, "bedtime": 22 * 60, "hydration": 2500, "floors": 12},
        )
    g.add_chat("lune", "user", "Lune, is that you?")
    g.L["titles"].append("goddess_confidant")
    v, _ = play(g, at(MON + timedelta(days=3), 9), {})
    text = json.dumps({k: x for k, x in v.items() if k not in ("lune_chat", "lore")})
    assert v["goddess"]["name"] == "Lena" and "Lune" not in text, text[text.find("Lune") - 80 : text.find("Lune") + 40]
    assert any("Lena" in t["name"] or "Lena" in t["how"] for t in v["titles"])
    assert v["lune_chat"][-1]["text"] == "Lune, is that you?", "what people typed is never rewritten"


def test_secrets():
    """Hidden quests and titles are a surprise: nothing about one is sent until it's earned."""
    g = G.Game(GOALS, seed="secret")
    v, _ = play(g, at(MON, 20), {"steps": 3000})
    assert v["titles"] == [] and v["hidden"] == []
    text = json.dumps(v)
    assert not any(h[2] in text for h in C.HIDDEN), "no riddles"
    assert not any(t[2] in text for t in C.TITLES), "no title requirements"
    g.L["titles"] += ["rank_d", "guardian_slayer"]  # a retired title from an older version is dropped on load
    g.L["title"] = "rank_d"
    g2 = G.Game(GOALS, ledger=json.loads(json.dumps(g.L)))
    v, _ = play(g2, at(MON + timedelta(days=1), 9), {})
    assert [t["id"] for t in v["titles"]] == ["guardian_slayer"] and v["title"]["id"] == "guardian_slayer"
    # earning one reveals just that one, with the day it happened
    g2.L["stats"]["guardians"] = next(t[4] for t in C.TITLES if t[0] == "guardian_slayer")
    g2.L["titles"].remove("guardian_slayer")
    v, ev = play(g2, at(MON + timedelta(days=1), 10), {})
    assert "title_earned" in ev and v["titles"][0]["date"] == (MON + timedelta(days=1)).isoformat()


def test_prompts():
    """Portrait prompts describe the race, body and job, and stay short enough for the models."""
    g = G.Game(GOALS, "dragonkin", seed="art", body="feminine")
    g.L["level"] = 6
    g.set_job("mage")
    for c in list(g.L["chests"]):
        g.open_chest(c["id"])
    v, _ = play(g, at(MON, 9), {"steps": 9000})
    p = A.portrait_prompt(v, v["body"])
    assert "dragonkin woman" in p["prompt"] and "mage" in p["prompt"] and len(p["prompt"]) < 1500
    for race in ("human", "elf", "dwarf", "beastkin"):
        app = A.appearance(race, "s")
        assert A.describe_body(race, app, "masculine")
    assert "Lune" in A.goddess_prompt("playful", 9)["prompt"]
    assert A.npc_prompt(1) is None and A.npc_prompt(15)["kind"] == "npc"
    item = LT.make_item(random.Random(1), 1, 4, ["steps"], 10, slot="weapon")
    assert item["slot"] == "weapon" and A.BASE_LOOK[item["base"]] in A.item_prompt(item)["prompt"]
    gp = A.guardian_prompt({**v["labyrinth"]})
    assert (
        v["labyrinth"]["name"] not in gp["prompt"]
        and gp["prompt"].lower().startswith(("a ", "an "))
        and gp["w"] == 1024
    )


def simulate(profile, days=365 * 3, seed=3, race="human"):
    """Play `days` days with a player who hits each quest with the profile's odds; returns what happened."""
    rnd = random.Random(seed)
    g = G.Game(GOALS, race, seed=f"sim{seed}")
    counts, log, names, titles, lines, choices = Counter(), {}, [], [], [], Counter()
    for i in range(days):
        day = MON + timedelta(days=i)
        hit = {q: rnd.random() < p for q, p in profile.items()}
        final = {
            "steps": rnd.randint(8000, 12500) if hit["steps"] else rnd.randint(2000, 7500),
            "floors": rnd.randint(10, 16) if hit["floors"] else rnd.randint(0, 9),
            "hydration": rnd.randint(2000, 2500) if hit["hydration"] else rnd.randint(500, 1900),
        }
        sleep = rnd.uniform(7.5, 8.5) if hit["sleep"] else rnd.uniform(5, 7.4)
        bed = rnd.randint(21 * 60 + 30, 23 * 60) if hit["bedtime"] else rnd.randint(23 * 60 + 10, 25 * 60)
        for hour in range(7, 23, 2):
            r = {q: v * (hour - 6) / 16 for q, v in final.items()}
            if hour == 7:
                r.update(sleep=sleep, bedtime=bed % 1440)
            v, ev = play(g, at(day, hour, 10), r)
            counts.update(ev)
            if v["choice"] and v["choice"]["status"] == "offered":
                g.answer_choice(rnd.random() < 0.7)
                choices[v["choice"]["kind"]] += 1
            if hour == 7:
                lines.append(v["goddess"]["line"])
        if v["level"] >= 5 and not g.L["job"]:
            g.set_job(v["recommended_job"] or "paladin")
        names.append(v["labyrinth"]["name"])
        titles.append(v["daily_title"])
        for chest in list(v["gear"]["chests"]):
            item = g.open_chest(chest["id"])
            cur = g._item(g.L["equip"].get(item["slot"]))
            if cur is None or item["power"] > LT.item_power(cur):
                g.equip(item["id"])
        for it in list(g.L["inv"]):
            if it["id"] not in g.L["equip"].values():
                (g.sell if it["rarity"] in ("common", "uncommon") else g.salvage)(it["id"])
        shop(g, rnd)
        for it in g.L["inv"]:
            while (c := LT.enhance_cost(it)) and g.L["shards"] >= c:
                g.enhance(it["id"])
        if i + 1 in (7, 30, 90, 180, 365, 730, 1095):
            log[i + 1] = v
    return log, counts, g, names, titles, lines, choices


def shop(g, rnd):
    """A sensible shopper: haggle a little, buy upgrades and the odd elixir, keep a reserve."""
    for e in g.L["shop"]["stock"]:
        if e["sold"]:
            continue
        want = False
        if e["kind"] == "gear":
            cur = g._item(g.L["equip"].get(e["item"]["slot"]))
            want = LT.item_power(e["item"]) > (LT.item_power(cur) if cur else 0) and e["list"] <= g.L["gold"] * 0.6
        elif e["kind"] == "consumable":
            want = (e["cid"] in ("elixir", "bane_oil") and g.L["gold"] > 4 * e["list"]) or (
                e["cid"] == "shield_charm" and not g.L["shields"] and g.L["gold"] > 3 * e["list"]
            )
        elif e["kind"] == "cosmetic":
            want = g.L["gold"] > 6 * e["list"]
        if not want:
            continue
        for frac in (0.8, 0.88, 0.95):
            if g.haggle(e["id"], int(e["list"] * frac))["result"] in ("accepted", "closed", "final"):
                break
        if e["price"] <= g.L["gold"]:
            g.buy(e["id"])
            if e["kind"] == "gear":
                g.equip(e["item"]["id"])
            elif e["kind"] == "consumable":
                try:
                    g.use(e["cid"])
                except G.GameError:
                    pass


def min_gap(seq):
    """The smallest gap between two repeats of the same value in `seq`."""
    last, gap = {}, 10**9
    for i, x in enumerate(seq):
        if x in last:
            gap = min(gap, i - last[x])
        last[x] = i
    return gap


def test_shards_never_multiply():
    """Salvaging gives an item's own shards plus exactly what was spent enhancing it: enhancing and then
    salvaging never comes out ahead, at any rarity or level."""
    for r, rarity in enumerate(LT.RARITIES):
        for enh in range(LT.ENHANCE_MAX + 1):
            item = {"rarity": rarity, "enh": enh}
            spent = sum(LT.ENHANCE_COST[r] * k for k in range(1, enh + 1))
            assert LT.enhance_spent(item) == spent and LT.salvage_value(item) == LT.SALVAGE[r] + spent, (rarity, enh)
    g = G.Game({"steps": 8000}, seed="shards")
    play(g, at(MON, 9), {"steps": 9000})
    for r in range(len(LT.RARITIES)):
        g.L["uid"] += 1
        item = LT.make_item(random.Random(r), g.L["uid"], r, ["steps"], 10)
        g.L["inv"].append(item)
        g.L["shards"] = start = 10**6
        for _ in range(random.Random(r).randint(0, LT.ENHANCE_MAX)):
            g.enhance(item["id"])
        g.salvage(item["id"])
        assert g.L["shards"] == start + LT.SALVAGE[r], (LT.RARITIES[r], g.L["shards"] - start)


def test_bonus_caps_shown():
    """Bonus caps are listed, and effects past a cap are reported."""
    g = G.Game({"steps": 8000}, seed="caps")
    v, _ = play(g, at(MON, 9), {"steps": 9000})
    assert v["bonus_caps"]["capped"] == [] and any(
        l["name"] == "XP for each quest" and l["max"] == "+50%" for l in v["bonus_caps"]["limits"]
    )
    for slot in LT.SLOTS:  # gear piled high on Walk XP
        g.L["uid"] += 1
        g.L["inv"].append(
            {
                "id": g.L["uid"],
                "name": "x",
                "slot": slot,
                "base": LT.BASES[slot][0],
                "rarity": "mythic",
                "affixes": {"xp:steps": 20},
                "enh": 0,
                "lvl": 1,
            }
        )
        g.L["equip"][slot] = g.L["uid"]
    v, _ = play(g, at(MON, 10), {"steps": 9000})
    hit = {c["effect"]: c for c in v["bonus_caps"]["capped"]}
    assert hit["xp:steps"]["total"] >= 120 and hit["xp:steps"]["max"] == "+50%" and v["effects"]["xp:steps"] == 50


def test_more_side_quests():
    """1 to 10 daily side quests, with rewards that taper so more quests don't mean much more XP."""
    one = G.Game({"steps": 8000}, seed="sq", daily_bounties=3)
    ten = G.Game({"steps": 8000}, seed="sq", daily_bounties=10)
    assert (
        G.Game({"steps": 8000}, seed="sq", daily_bounties=50).daily_bounties == 10
        and G.Game({"steps": 8000}).daily_bounties == 5
    )
    v3, _ = play(one, at(MON, 9), {})
    v10, _ = play(ten, at(MON, 9), {})
    d3 = [b for b in v3["bounties"] if b["source"] == "daily"]
    d10 = [b for b in v10["bounties"] if b["source"] == "daily"]
    assert len(d10) == 10 and len({b["title"] for b in d10}) == 10 and sum(b["chest"] for b in d10) == 1
    total3, total10 = sum(b["xp"] for b in d3), sum(b["xp"] for b in d10)
    assert total3 < total10 <= total3 * 6.5 / 3 + 10, (total3, total10)  # more to do, a little more reward, not a flood


def test_old_market_replaced():
    """A market saved before deliveries existed (and left fed up and closed) is replaced by a fresh one."""
    g = G.Game(GOALS, seed="oldshop")
    play(g, at(MON, 9), {"steps": 9000})
    shop = g.L["shop"]
    for k in ("restocks", "wave", "theme", "annoyance", "calm_at"):
        shop.pop(k, None)
    shop.update(fed_up=True, markup=0.08, patience=0)
    for e in shop["stock"]:
        e["closed"] = True
    v, _ = play(g, at(MON, 15), {})
    assert (
        v["market"]["next_delivery"]
        and v["market"]["temper"] == "calm"
        and not any(e["closed"] for e in v["market"]["stock"])
    )
    e = next(x for x in g.L["shop"]["stock"] if x["kind"] == "gear")
    for _ in range(2):
        g.haggle(e["id"], int(e["list"] * 0.3))
    v, _ = play(g, at(MON, 15, 5), {})
    assert next(x for x in v["market"]["stock"] if x["id"] == e["id"])["why"] == "refused"


def test_ages_and_marrow():
    """Ages reach every prompt (no beards on kids), and Marrow's choices work."""
    g = G.Game(GOALS, "dwarf", seed="age", body="masculine")
    v, _ = play(g, at(MON, 9), {})
    g.set_portrait_prefs({"age": "kid"})
    v, _ = play(g, at(MON, 10), {})
    p = A.portrait_prompt(v, "masculine")["prompt"]
    assert "boy about nine years old" in p and "beard" not in p, p
    g.set_portrait_prefs({"age": "elderly"})
    v, _ = play(g, at(MON, 10, 5), {})
    assert (
        "old man" in A.portrait_prompt(v, "masculine")["prompt"]
        and "old man" in A.portrait_base_prompt(v, "masculine")["prompt"]
    )
    gp = A.goddess_prompt("serene", 0, "Lena", {"age": "elderly"})
    assert "serene old woman" in gp["prompt"] and "silver-white" in gp["prompt"] and "elderly" not in gp["negative"]
    assert "little girl" in A.goddess_prompt("serene", 0, "Lena", {"age": "kid"})["prompt"]
    assert A.merchant_prompt("fair", {})["prompt"] == A.merchant_prompt("fair")["prompt"]
    m = g.set_merchant_prefs(
        {
            "age": "elderly",
            "hair": "grey",
            "accessory": "spectacles",
            "outfit": "apron",
            "backdrop": "tavern",
            "framing": "full",
            "race": "goblin",
            "build": "lanky",
        }
    )
    mp = A.merchant_prompt("angry", m)["prompt"]
    assert (
        mp.startswith("Full-body portrait of Marrow Fennick, a tall and lanky goblin merchant, a very old man")
        and "spectacles" in mp
        and "tavern" in mp
        and "red-faced" in mp
    ), mp
    v, _ = play(g, at(MON, 11), {})
    assert v["market"]["prefs"] == m and set(v["market"]["choices"]) == {
        "race",
        "age",
        "build",
        "framing",
        "hair",
        "accessory",
        "outfit",
        "backdrop",
    }
    for bad in ({"backdrop": "moon"}, {"age": "ancient"}, {"race": "robot"}):
        try:
            g.set_merchant_prefs(bad)
            raise AssertionError(bad)
        except G.GameError:
            pass


def test_choices_change_only_what_they_should():
    """Framing changes no painting; outfit, accessory and backdrop change the edits but not the base; race, age, build,
    hair and eyes paint a new base. And every mood of a character carries the same words for who they are."""
    key = lambda spec: (spec["prompt"], spec["w"], spec["h"])  # what makes a painting
    for base_fn, full_fn, edit_fn, prefs, look, who in (
        (
            lambda p: A.goddess_base_prompt("Lena", p),
            lambda p, m: A.goddess_prompt(m, 2, "Lena", p),
            lambda p, m: A.goddess_edit(m, 2, p),
            {"race": "elf", "age": "adult", "build": "athletic"},
            {"outfit": "huntress", "backdrop": "mood"},
            {"race": "dragonkin"},
        ),
        (
            A.merchant_base_prompt,
            lambda p, m: A.merchant_prompt(m, p),
            lambda p, m: A.merchant_edit(m, p),
            {"race": "halfling", "build": "stout"},
            {"outfit": "sailor", "accessory": "pipe", "backdrop": "harbour"},
            {"age": "kid"},
        ),
    ):
        b = key(base_fn(prefs))
        assert key(base_fn({**prefs, "framing": "closeup"})) == b and key(base_fn({**prefs, **look})) == b
        assert key(base_fn({**prefs, **who})) != b
        moods = A.LUNE_MOODS if "Lena" in base_fn(prefs)["prompt"] else A.MERCHANT_MOODS
        for m in moods:
            assert key(full_fn({**prefs, "framing": "closeup"}, m)) == key(full_fn(prefs, m))
            assert edit_fn({**prefs, **look}, m) != edit_fn(prefs, m)
        assert (
            base_fn(prefs)["w"] > 832
            and base_fn(prefs)["hq"]
            and "plain seamless light grey" in base_fn(prefs)["prompt"]
        )
    ident = A.goddess_identity("Lena", {"race": "elf", "age": "adult"})
    assert all(
        ident in A.goddess_prompt(m, t, "Lena", {"race": "elf", "age": "adult"})["prompt"]
        for m in A.LUNE_MOODS
        for t in (0, 5)
    )
    assert all(
        "elven" in A.goddess_edit(m, 0, {"race": "elf"}) and "graceful woman" in A.goddess_edit(m, 0, {"age": "adult"})
        for m in A.LUNE_MOODS
    )
    assert (
        "pointed ears" in A.goddess_prompt("serene", 0)["negative"]
        and "pointed ears" not in A.goddess_prompt("serene", 0, "Lune", {"race": "elf"})["negative"]
    )
    assert A.goddess_backdrop("worried", 0, {"backdrop": "mood"}) != A.goddess_backdrop(
        "delighted", 0, {"backdrop": "mood"}
    )


def test_version_is_the_same_everywhere():
    """const.py, manifest.json and the panel's scripts all carry the version; a release changes them together."""
    root = Path(__file__).parents[1] / "custom_components/life_rpg"
    version = re.search(r'^VERSION = "([^"]+)"', (root / "const.py").read_text(), re.M).group(1)
    assert json.loads((root / "manifest.json").read_text())["version"] == version
    panel = (root / "frontend/life-rpg.js").read_text()
    assert f'const VERSION = "{version}";' in panel
    # imports carry ?v= so the app never mixes old and new files
    found = [
        v
        for js in (root / "frontend").glob("*.js")
        for v in re.findall(r'from "\./[\w-]+\.js\?v=([^"]+)"', js.read_text())
    ]
    assert len(found) >= 4 and set(found) == {version}, found


if __name__ == "__main__":
    # every test_ function in this file, in the order they're written (pytest finds them too)
    for t in [f for name, f in list(globals().items()) if name.startswith("test_") and callable(f)]:
        t()
    print("unit tests passed")
    for name, p in {
        "casual": dict(steps=0.5, floors=0.3, sleep=0.6, hydration=0.4, bedtime=0.4),
        "steady": dict(steps=0.75, floors=0.5, sleep=0.75, hydration=0.7, bedtime=0.65),
        "grinder": dict(steps=0.95, floors=0.9, sleep=0.9, hydration=0.9, bedtime=0.85),
    }.items():
        log, counts, g, names, titles, lines, choices = simulate(p)
        weekly = names[::7]
        print(
            f"\n== {name} == best streak {g.L['best_streak']}  floor {g.L['floor']}  bestiary {len(g.L['bestiary'])}  "
            f"hidden {len(g.L['hidden'])}/{len(C.HIDDEN)}  titles {len(g.L['titles'])}/{len(C.TITLES)}"
        )
        for d, v in log.items():
            job = v["job"]
            print(
                f"day {d:>4}: L{v['level']:<3} {v['rank']:<4} {(job['title'] + ' Lv' + str(job['level'])) if job else 'Villager':<26} "
                f"{v['race']['gift']['name']:<18} streak {v['streak']:>4}  GS {v['gear']['score']:>4}  floor {v['labyrinth']['floor']:>3}  "
                f"gold {v['gold']:>6} (earned {v['stats'].get('gold_earned', 0):>7}, spent {v['stats'].get('gold_spent', 0):>7}, "
                f"buys {v['stats'].get('purchases', 0):>3}, deals {v['stats'].get('deals', 0):>3})  "
                f"skills {[s['grade'][:5] for s in v['skills'].values()]}"
            )
        print(
            f"guardian names unique {len(set(weekly))}/{len(weekly)}; daily titles min repeat gap {min_gap(titles)} days; "
            f"goddess morning lines unique {len(set(lines))}; choices {dict(choices)}"
        )
        print("events/3yr:", dict(sorted(counts.items(), key=lambda x: -x[1])))
    print("\nall tests passed")
