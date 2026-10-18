"""What everything looks like: an adventurer's traits, and the prompts that paint the game's art.

Traits are decided here (not in the browser) so the pixel fallback and the painted portrait agree:
the view carries palette indices that art.js uses, and the same traits are written into prompts.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

from . import content as C

# --- traits (index order matches the palettes in frontend/art.js) -------------------------------
SKIN = {
    "human": ["pale", "fair", "light tan", "warm brown", "dark brown", "deep ebony"],
    "elf": ["porcelain", "fair", "pale silvery-blue", "pale lavender-grey", "bronze"],
    "dwarf": ["ruddy", "weathered tan", "deep ruddy brown", "pale"],
    "beastkin": ["fair", "tan", "brown", "dark brown"],
    "dragonkin": ["emerald-green", "teal", "crimson", "slate-grey", "gold", "sapphire-blue", "violet"],
}
HAIR = [
    "black",
    "dark brown",
    "auburn",
    "golden blond",
    "platinum blond",
    "silver-grey",
    "crimson red",
    "deep blue",
    "forest green",
    "rose pink",
    "violet",
    "snow-white",
]
FUR = ["fox-orange", "snow-white", "grey", "black", "brown", "golden"]
EYES = ["blue", "green", "warm brown", "violet", "teal", "dark"]
HAIRSTYLES = {
    "human": ["short", "spiky", "long", "ponytail", "bob", "swept"],
    "elf": ["long", "long", "braid", "ponytail", "swept"],
    "dwarf": ["short", "bald", "swept", "braid", "spiky"],
    "beastkin": ["short", "spiky", "bob", "long", "swept"],
    "dragonkin": ["spiky", "short", "swept", "long", "bald"],
}
HAIRSTYLE_TEXT = {
    "short": "short {c} hair",
    "spiky": "tousled spiky {c} hair",
    "long": "long flowing {c} hair",
    "ponytail": "{c} hair tied in a high ponytail",
    "bob": "{c} hair in a chin-length bob",
    "swept": "{c} hair swept to one side",
    "braid": "{c} hair in a long thick braid",
    "bald": "a shaved head",
}
EARS = ["fox", "cat", "wolf", "rabbit", "bear"]
TAILS = ["fluffy", "thin", "bushy"]
HORNS = ["swept", "ram", "spire", "crown"]
HORN_TEXT = {
    "swept": "sleek swept-back horns",
    "ram": "curled ram horns",
    "spire": "tall spiralling horns",
    "crown": "a crown of small jagged horns",
}
BEARDS = ["long", "braided", "forked", "full"]
BODIES = {"masculine": "man", "feminine": "woman", "androgynous": "androgynous adventurer"}


# what you can choose for your portrait (Gallery → Your portrait); anything not chosen keeps your rolled look
BUILDS = {  # build -> (pixel-art shape: shoulders, legs, torso) and words for the painting
    "slender": ([-2, 1, 0], "a slender, lithe build"),
    "average": ([0, 0, 0], "an average build"),
    "athletic": ([0, 1, 1], "a lean athletic build"),
    "muscular": ([2, 0, 1], "a muscular, broad-shouldered build"),
    "stocky": ([2, -1, -1], "a short, stocky build"),
    "heavyset": ([4, -1, 0], "a big, heavyset build"),
}
# How a portrait is framed on screen. Every painting of you, the goddess and the merchant is full body, and the
# panel crops it, so choosing a framing never repaints anything.
FRAMINGS = ["full", "three_quarter", "half", "bust", "closeup"]
# Which choices change what: "view" only changes how a painting is shown; "edit" repaints from the base painting (the
# face stays); anything else is part of who they are, so it paints a new base (and everything after it).
PREF_TIERS = {"framing": "view", "weapon": "edit", "outfit": "edit", "accessory": "edit", "backdrop": "edit"}


def split_prefs(prefs: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """(identity choices, edit choices): framing is left out of both, since it never changes a painting."""
    p = prefs or {}
    who = {k: v for k, v in p.items() if PREF_TIERS.get(k) is None}
    look = {k: v for k, v in p.items() if PREF_TIERS.get(k) == "edit"}
    return who, look


PORTRAIT_WEAPONS = ["equipped", "none", "Shortsword", "Longbow", "Staff", "Warhammer", "Spear", "Dagger"]
AGES = ["kid", "teen", "young_adult", "adult", "elderly"]  # for you, the goddess and the merchant
AGE_NOUNS = {  # (masculine, feminine, androgynous)
    "kid": ("boy about nine years old", "girl about nine years old", "child about nine years old"),
    "teen": ("teenage boy about fifteen", "teenage girl about fifteen", "teenager about fifteen"),
    "young_adult": ("young man in his twenties", "young woman in her twenties", "young adventurer in their twenties"),
    "adult": ("man in his forties", "woman in her forties", "adventurer in their forties"),
    "elderly": ("old man", "old woman", "elderly adventurer"),
}
AGE_LOOK = {
    "kid": "a small, youthful build and a round, cheerful face",
    "teen": "a youthful face",
    "elderly": "a weathered, wrinkled face and greying hair",
}
PORTRAIT_CHOICES = {
    "age": AGES,
    "framing": ["full", "half", "closeup"],
    "hair": HAIR,
    "fur": FUR,
    "hairstyle": list(HAIRSTYLE_TEXT),
    "eyes": EYES,
    "build": list(BUILDS),
    "weapon": PORTRAIT_WEAPONS,
}


def with_prefs(app: dict[str, Any], prefs: dict[str, Any]) -> dict[str, Any]:
    """Your rolled look with your portrait choices applied (palette indices, so the pixel art follows too)."""
    out = dict(app)
    if prefs.get("hair") in HAIR:
        out["hair"] = HAIR.index(prefs["hair"])
    if prefs.get("fur") in FUR:  # beastkin: hair and tail are their fur
        out["fur"] = FUR.index(prefs["fur"])
    if prefs.get("hairstyle") in HAIRSTYLE_TEXT:
        out["hairstyle"] = prefs["hairstyle"]
    if prefs.get("eyes") in EYES:
        out["eyes"] = EYES.index(prefs["eyes"])
    if prefs.get("build") in BUILDS:
        out["build"], out["build_name"] = list(BUILDS[prefs["build"]][0]), prefs["build"]
    if prefs.get("age") in AGES:
        out["age"] = prefs["age"]
    return out


def appearance(race: str, seed: str, look: int = 0) -> dict[str, Any]:
    """Stable traits for an adventurer; `look` rerolls them ("Change look")."""
    r = random.Random(f"look:{race}:{seed}:{look}")
    return {
        "skin": r.randrange(len(SKIN.get(race, SKIN["human"]))),
        "hair": r.randrange(len(HAIR)),
        "fur": r.randrange(len(FUR)),
        "eyes": r.randrange(len(EYES)),
        "hairstyle": r.choice(HAIRSTYLES.get(race, HAIRSTYLES["human"])),
        "ears": r.choice(EARS),
        "tail": r.choice(TAILS),
        "horns": r.choice(HORNS),
        "wings": r.random() < 0.7,
        "beard": r.choice(BEARDS),
        "blush": r.random() < 0.35,
        "scar": r.random() < 0.15,
        "shirt_hue": r.randrange(360),
        "build": [2 * r.randint(-1, 1), r.randint(-1, 1), r.randint(-1, 0)],
    }


# --- shared prompt pieces --------------------------------------------------------------------------
STYLE = (
    "painterly high-fantasy role-playing game art, cinematic 3D render with realistic skin, metal and fabric "
    "materials, soft volumetric light, dramatic rim lighting, rich colour, sharp focus, highly detailed"
)
NEGATIVE = (
    "text, letters, words, watermark, signature, logo, frame, border, user interface, blurry, low resolution, "
    "jpeg artifacts, deformed, disfigured, extra limbs, extra fingers, bad hands, bad anatomy, cropped head, "
    "duplicate, nsfw, nudity, gore"
)
SIZES = {  # generate at (w, h), keep at (out_w, out_h); people are kept large so the panel can crop them
    "portrait": (832, 1216, 704, 1024),
    "goddess": (832, 1216, 704, 1024),
    "merchant": (832, 1216, 704, 1024),
    "npc": (1024, 1024, 512, 512),
    "item": (1024, 1024, 384, 384),
    "guardian": (1024, 1024, 640, 640),
}
BASE_SIZE = (896, 1344, 768, 1152)  # base paintings: bigger, with more steps (see art.py), for the edits to work from
FULL_BODY = "single character, the whole figure from head to feet in frame with a little space above the head, centred"
BASE_POSE = (
    "standing straight and relaxed, arms at the sides, calm neutral expression, facing the viewer, in front of "
    "a plain seamless light grey studio backdrop, soft even lighting, no props, no scenery"
)
BASE_STYLE = STYLE + ", ultra detailed, crisp clean edges, character reference sheet quality"


def seed_for(key: str) -> int:
    """A stable sampler seed for an art key, so redraws of the same thing stay close."""
    return int(hashlib.sha256(key.encode()).hexdigest()[:12], 16)


def _job(job: dict[str, Any] | None) -> str:
    """The adventurer's job as clothing words (a villager's plain clothes before they take one)."""
    if not job:
        return "a fledgling adventurer in simple traveller's clothes"
    return f"a {job['title'].lower()}, {JOB_LOOK.get(job['id'], '')}"


JOB_LOOK = {
    "ranger": "a weathered travelling cloak and a quiver of arrows, keen eyes scanning the horizon",
    "warrior": "battle scars and a confident fighter's stance",
    "druid": "leaves and small flowers woven into the clothing, a living vine curling around one arm",
    "mage": "faint glowing arcane runes and a ribbon of shimmering water magic circling one hand",
    "monk": "prayer beads, a calm meditative bearing and wrapped forearms",
    "paladin": "a holy sunburst sigil on the chest and a soft radiant light",
    "rogue": "a dark hooded mantle, hidden blades at the belt and a sly half-smile",
    "bard": "a lute slung across the back and a flamboyant feathered sash",
}
GIFT_LOOK = {
    "Restless Spirit": "wind tugging at the clothes as if always about to set off",
    "Unbound Wayfarer": "a faint trail of wind and golden road-dust swirling around the feet",
    "Iron Discipline": "an unshakeable posture and steady piercing gaze",
    "Unbreakable Will": "a faint silver ward glowing over the shoulders like armour of willpower",
    "Spring Whisperer": "tiny droplets of water orbiting the fingertips",
    "Tide Sovereign": "a slowly turning crown of floating water droplets above the head",
    "Starlit Sage": "tiny stars glittering in the hair",
    "Eternal Night Oracle": "a night-sky shimmer across the clothing and softly glowing eyes",
    "Mountain Breaker": "stone-grey dust on the knuckles and a powerful stance",
    "Worldforge Titan": "glowing forge-fire cracks running along the forearms",
    "Deep Rest Kin": "a calm, well-rested glow and a warm hearth-light on the face",
    "Hearthstone Elder": "a glowing hearthstone pendant and an aura of steady warmth",
    "Pack Runner": "a lean runner's build and windswept fur",
    "Alpha of the Endless Hunt": "a mane of wild windswept fur and fierce glowing eyes",
    "Cliff Stalker": "climbing chalk on the hands and coiled muscle",
    "Apex Predator": "a dangerous predator's poise and faintly glowing feral eyes",
    "Slumbering Wyrm": "soft ember-light breathing between the scales",
    "Ancient Dragon's Dream": "smouldering ember-light in the scales and wisps of dream-smoke",
    "Scaled Ascendant": "polished gleaming scales",
    "Draconic Sovereign": "a regal draconic aura and scales edged with molten gold",
}
RANK_LOOK = {
    "E": "humble beginnings",
    "D": "a promising newcomer",
    "C": "a capable seasoned adventurer",
    "B": "a veteran adventurer with quiet confidence",
    "A": "a renowned hero with a faint golden aura",
    "S": "a legendary hero surrounded by a powerful radiant aura and drifting magical particles",
}
RARITY_LOOK = {
    "common": "plain, worn and patched",
    "uncommon": "sturdy, well-made",
    "rare": "finely crafted, silver-trimmed",
    "epic": "ornate and enchanted, etched with softly glowing runes",
    "legendary": "legendary, gold-inlaid and glowing with inner light",
    "mythic": "mythic and otherworldly, crystalline and radiant with shifting prismatic light",
}
BASE_LOOK = {
    "Dagger": "dagger",
    "Shortsword": "shortsword",
    "Spear": "spear",
    "Warhammer": "warhammer",
    "Staff": "magic staff",
    "Longbow": "longbow",
    "Hood": "hooded cowl",
    "Circlet": "circlet",
    "Helm": "helmet",
    "Crown": "crown",
    "Tunic": "tunic",
    "Brigandine": "studded brigandine armour",
    "Chainmail": "chainmail hauberk",
    "Robe": "robes",
    "Plate": "plate armour",
    "Wraps": "hand wraps",
    "Gloves": "leather gloves",
    "Gauntlets": "gauntlets",
    "Bracers": "bracers",
    "Sandals": "sandals",
    "Boots": "boots",
    "Greaves": "greaves",
    "Treads": "heavy treads",
    "Ring": "ring",
    "Band": "band ring",
    "Signet": "signet ring",
    "Amulet": "amulet",
}
BACKGROUNDS = {  # cosmetic id -> setting; None means "the job's home"
    "shrine": "a moonlit ruined shrine",
    "forest": "an ancient sunlit forest",
    "pass": "a windswept mountain pass",
    "library": "a sunken library lit by floating candles",
    "ruins": "desert ruins at golden hour",
    "citadel": "a frozen citadel under the aurora",
    "harbor": "a harbour town at dusk",
    "tavern": "a cosy tavern hearth",
}
JOB_HOME = {
    None: "a quiet village square at morning",
    "ranger": "a forest road at dawn",
    "warrior": "a mountain pass",
    "druid": "a sacred grove",
    "mage": "a tower library beside a waterfall",
    "monk": "a mountaintop temple",
    "paladin": "a sunlit cathedral",
    "rogue": "moonlit city rooftops",
    "bard": "a lively tavern stage",
}
POSES = {
    None: "standing in a relaxed heroic pose",
    "heroic": "in a bold heroic stance",
    "casting": "mid-spell, one hand raised",
    "rest": "seated at rest, looking at the viewer",
    "battle": "battle-ready, weapon drawn",
    "triumph": "triumphant, fist raised",
}
DYES = {
    "crimson": "crimson",
    "midnight": "midnight-blue",
    "forest": "forest-green",
    "ivory": "ivory",
    "violet": "royal violet",
    "ash": "ash-grey",
}


def _rank_look(rank: str) -> str:
    """How grand the adventurer looks for their rank (every S rank looks the same)."""
    return RANK_LOOK["S"] if rank.startswith("S") else RANK_LOOK.get(rank, RANK_LOOK["E"])


def describe_body(race: str, app: dict[str, Any], body: str = "androgynous") -> str:
    """Race, body, age and features as words."""
    noun = BODIES.get(body, BODIES["androgynous"])
    age = app.get("age")
    if age in AGE_NOUNS:
        noun = AGE_NOUNS[age][("masculine", "feminine").index(body) if body in ("masculine", "feminine") else 2]
    skin = SKIN.get(race, SKIN["human"])[app["skin"] % len(SKIN.get(race, SKIN["human"]))]
    hair = HAIRSTYLE_TEXT[app["hairstyle"]].format(c=HAIR[app["hair"] % len(HAIR)])
    eyes = EYES[app["eyes"] % len(EYES)]
    fur = FUR[app["fur"] % len(FUR)]
    build = BUILDS[app["build_name"]][1] if app.get("build_name") in BUILDS else None
    if race == "elf":
        who = f"an elf {noun} with {skin} skin, long pointed elven ears, {build or 'a slender graceful build'}, {hair} and {eyes} eyes"
    elif race == "dwarf":
        beard = (
            ""
            if body == "feminine" or age in ("kid", "teen")
            else f", a {app['beard']} {HAIR[app['hair'] % len(HAIR)]} beard"
        )
        who = f"a dwarf {noun}, short and {build or 'stocky and powerfully built'}, with {skin} skin, {hair}{beard} and {eyes} eyes"
    elif race == "beastkin":
        hair = HAIRSTYLE_TEXT[app["hairstyle"]].format(c=fur)  # beastkin hair matches their fur
        who = (
            f"a {app['ears']}-eared beastkin {noun} with {skin} skin, {fur} {app['ears']} ears atop the head, "
            f"a {app['tail']} {fur} {app['ears']} tail, {hair} and {eyes} eyes"
        )
    elif race == "dragonkin":
        wings = ", leathery wings folded behind the back" if app["wings"] else ""
        who = (
            f"a dragonkin {noun}, a humanoid dragon-folk with {skin} scales, {HORN_TEXT[app['horns']]}, "
            f"slit-pupil {eyes} eyes, a long scaled tail{wings}"
        )
        if app["hairstyle"] != "bald":
            who += f" and {hair}"
    else:
        who = f"a human {noun} with {skin} skin, {hair} and {eyes} eyes"
    if build and race not in ("elf", "dwarf"):
        who += f", {build}"
    if age in AGE_LOOK:
        who += f", {AGE_LOOK[age]}"
    if app.get("scar"):
        who += ", a small scar across one cheek"
    return who


def outfit(equipped: dict[str, Any], dye: str | None = None, weapon: str | None = None) -> str:
    """What the adventurer is wearing and holding (`weapon`: a portrait choice; "none" for empty hands)."""
    worn, held = [], ""
    for slot in ("armor", "helm", "gloves", "boots", "ring"):
        item = equipped.get(slot)
        if item:
            worn.append(f"{RARITY_LOOK[item['rarity']]} {BASE_LOOK.get(item.get('base'), slot)}")
    w = equipped.get("weapon")
    if weapon in BASE_LOOK:
        held = f", holding a {RARITY_LOOK[w['rarity']] if w else 'well-made'} {BASE_LOOK[weapon]}"
    elif w and weapon != "none":
        held = f", holding a {RARITY_LOOK[w['rarity']]} {BASE_LOOK.get(w.get('base'), 'weapon')}"
    text = "wearing " + ", ".join(worn) if worn else "wearing simple linen travelling clothes"
    if dye in DYES:
        text += f", cloth dyed {DYES[dye]}"
    return text + held


def portrait_prompt(v: dict[str, Any], body: str = "androgynous") -> dict[str, Any]:
    """Full-body portrait of the adventurer as they are right now."""
    cos = (v.get("cosmetics") or {}).get("active", {})
    job = v.get("job")
    gift = v["race"]["gift"]["name"]
    setting = BACKGROUNDS.get(cos.get("background")) or JOB_HOME.get(job["id"] if job else None, JOB_HOME[None])
    prefs = v.get("portrait_prefs") or {}
    parts = [
        f"Full-body character portrait of {describe_body(v['race']['id'], v['appearance'], body)}",
        _job(job),
        outfit(v["gear"]["equipped"], cos.get("dye"), prefs.get("weapon")),
        GIFT_LOOK.get(gift, ""),
        f"{_rank_look(v['rank'])}, {POSES.get(cos.get('pose'), POSES[None])}, in {setting}",
        f"{FULL_BODY}, " + STYLE,
    ]
    return _pack("portrait", ". ".join(p for p in parts if p) + ".")


def portrait_base_prompt(v: dict[str, Any], body: str = "androgynous") -> dict[str, Any]:
    """The adventurer's base painting for an image-edit model: who they are, in plain clothes on a plain
    backdrop. Gear, job, pose and setting are added by editing it, so the face stays the same."""
    text = (
        f"Full-body character reference of {describe_body(v['race']['id'], v['appearance'], body)}, wearing simple "
        f"plain undyed linen clothes and soft boots, empty-handed, {BASE_POSE}. {FULL_BODY}, {BASE_STYLE}"
    )
    return _pack("portrait", text, base=True)


def portrait_edit(v: dict[str, Any]) -> str:
    """How to turn the base painting into the adventurer as they are now."""
    cos = (v.get("cosmetics") or {}).get("active", {})
    job = v.get("job")
    prefs = v.get("portrait_prefs") or {}
    setting = BACKGROUNDS.get(cos.get("background")) or JOB_HOME.get(job["id"] if job else None, JOB_HOME[None])
    gift = GIFT_LOOK.get(v["race"]["gift"]["name"], "")
    return (
        f"Keep this exact same person: the same face, age, race, hair, eyes, skin, ears and build. Dress them as "
        f"{_job(job)}, {outfit(v['gear']['equipped'], cos.get('dye'), prefs.get('weapon'))}"
        f"{', ' + gift if gift else ''}. Show them {POSES.get(cos.get('pose'), POSES[None])}, {_rank_look(v['rank'])}. "
        f"Replace the plain grey background with {setting}. Keep the whole figure in frame from head to feet, and the "
        f"same painterly fantasy art style."
    )


def item_prompt(item: dict[str, Any]) -> dict[str, Any]:
    """Inventory art for one item."""
    noun = BASE_LOOK.get(item.get("base"), item["slot"])
    text = (
        f"A single {RARITY_LOOK[item['rarity']]} {noun}, a fantasy treasure named {item['name']}. "
        f"Fantasy role-playing game inventory item art: the object alone, centred, isolated on a plain dark slate "
        f"background, studio lighting, no hands, no people, painterly 3D render, highly detailed"
    )
    return _pack("item", text)


TRINKET_LOOK = {  # potions, charms and the market's cosmetics
    "elixir": "a small round glass flask of shimmering golden elixir with a cork stopper and a wax seal",
    "greater_elixir": "an ornate crystal decanter of radiant golden elixir with silver filigree and swirling motes of light",
    "bane_oil": "a dark glass vial of thick violet oil with a skull-shaped stopper, faint smoke curling from it",
    "lucky_charm": "a four-leaf clover set in amber, hanging from a braided green cord",
    "reroll": "a rolled parchment scroll tied with a red ribbon, faint glowing runes along its edge",
    "hourglass": "a small brass hourglass filled with glowing blue sand",
    "shield_charm": "a small silver shield-shaped ward charm set with a glowing blue gem",
    "phoenix": "a single radiant phoenix feather of flame red and gold, glowing at its tip",
    "tonic_steps": "a round glass flask of bright green tonic with a tiny winged-boot charm tied to its neck",
    "tonic_floors": "a round glass flask of amber-orange draught with a tiny brass climbing pick tied to its neck",
    "tonic_sleep": "a small clay teapot and cup of lavender dreamleaf tea, wisps of steam curling up",
    "tonic_hydration": "a clear crystal flask of sparkling spring water with a silver droplet stopper",
    "tonic_bedtime": "a porcelain cup of pale blue moonflower tea with a single white flower floating on it",
    "crate": "a small sealed wooden shipping crate with rope handles and foreign stamps, a faint glow at its seams",
}
_PLACES = {
    "shrine": "a moonlit mountain shrine",
    "forest": "an ancient mossy forest",
    "pass": "a snowy mountain pass",
    "library": "a sunken library with drifting pages",
    "ruins": "sun-bleached desert ruins",
    "citadel": "a frozen citadel under aurora",
    "harbor": "a harbour at dusk with lanterns",
    "tavern": "a warm tavern hearth",
}
_POSES = {
    "heroic": "a heroic stance",
    "casting": "a spellcasting pose",
    "rest": "a relaxed resting pose",
    "battle": "a battle-ready crouch",
    "triumph": "a triumphant pose with arms raised",
}
_DYES = {
    "crimson": "crimson",
    "midnight": "midnight blue",
    "forest": "forest green",
    "ivory": "ivory",
    "violet": "royal violet",
    "ash": "ash grey",
}
_FRAMES = {
    "silver": "engraved silverwork",
    "gold": "gilded gold leaf",
    "moon": "pale moonstone",
    "thorn": "twisting thornwood",
    "dragon": "carved dragon bone",
}


def trinket_prompt(cid: str, cosmetic: tuple | None = None) -> dict[str, Any]:
    """Art for a potion or charm, or (given its (category, value, ...) entry) a cosmetic from the market."""
    if cosmetic:
        cat, value = cosmetic[0], cosmetic[1]
        thing = {
            "background": f"a small framed painted vignette of {_PLACES.get(value, value)}",
            "pose": f"a carved wooden artist's mannequin figurine in {_POSES.get(value, value)}",
            "dye": f"a corked glass bottle of {_DYES.get(value, value)} cloth dye beside a folded swatch of {_DYES.get(value, value)} fabric",
            "frame": f"an ornate empty portrait frame of {_FRAMES.get(value, value)}",
        }.get(cat, cid)
    else:
        thing = TRINKET_LOOK.get(cid, "a curious magical trinket")
    text = (
        f"{thing[0].upper()}{thing[1:]}. Fantasy role-playing game inventory item art: the object alone, centred, isolated "
        f"on a plain dark slate background, studio lighting, no hands, no people, painterly 3D render, highly detailed"
    )
    return _pack("item", text)


CREATURE_LOOK = {  # the subject first and concrete, so the model paints the right creature
    "slime": "a giant slime monster: a huge glossy translucent blob of jelly with bones and coins floating inside it",
    "golem": "a stone golem: a towering humanoid giant built from cracked boulders, held together by glowing carved runes",
    "wraith": "a wraith: a hooded floating ghost in tattered robes, no legs, skeletal hands, glowing eyes in a dark hood",
    "imp": "an imp: a small winged demon with curled horns, bat wings, clawed hands and a barbed tail",
    "hydra": "a hydra: a huge reptilian serpent monster with five long snake-like necks, each ending in a fanged snake head",
    "mimic": "a mimic: a treasure chest that is secretly a monster, its open lid lined with sharp teeth and a long tongue",
    "lich": "a lich: an undead skeletal sorcerer in rotting regal robes, a grinning skull face and a crackling staff",
    "beast": "a great beast: a massive four-legged feral monster with matted fur, tusks and huge claws",
    "wyrm": "a wyrm: a wingless dragon with a long coiling scaled serpent body, four short legs and a horned head",
    "treant": "a treant: a walking giant tree with a carved bark face, root legs and grasping branch arms",
    "watcher": "a watcher: a floating giant eyeball monster with a fanged mouth and many writhing eyestalks",
    "spider": "a spider queen: a gigantic eight-legged spider with a glossy armoured carapace and many eyes",
}
ELEMENT_LOOK = {
    "fire": "wreathed in roaring flames and embers, molten cracks glowing in its body",
    "frost": "armoured in jagged ice crystals, breathing freezing mist",
    "shadow": "made of living black shadow trailing wisps of darkness",
    "toxic": "dripping glowing green venom, surrounded by toxic fumes",
    "storm": "crackling with blue lightning under swirling storm clouds",
    "earth": "encrusted with rock and glittering crystals",
    "abyss": "deep-sea dark with glowing bioluminescent markings",
    "bone": "its body plated with bleached bone armour, spines of bone and old skulls",
    "blood": "crimson red and dripping blood-red ichor",
    "arcane": "glowing with magenta arcane runes and floating magic sigils",
    "tide": "dripping seawater, crusted with barnacles and coral",
    "verdant": "overgrown with moss, vines and flowers",
}
MONSTER_TRAITS = [
    "massive curved horns",
    "riveted iron armour plates",
    "a crude golden crown",
    "a jagged old scar",
    "rows of bony spikes",
    "glowing carved runes",
]


def guardian_prompt(g: dict[str, Any]) -> dict[str, Any]:
    """This week's labyrinth guardian. The creature and its element lead the prompt and the guardian's joke name
    is left out (models paint words like "crown" or "couch" literally, and lose the creature)."""
    r = random.Random(f"traits:{g['seed']}")
    traits = r.sample(MONSTER_TRAITS, r.randint(0, 2))
    kind = CREATURE_LOOK.get(g["kind"], "a fearsome monster")
    mod = (
        "elite, enormous and armoured"
        if g.get("elite")
        else "curse-corrupted, shrouded in crimson miasma"
        if g.get("cursed")
        else ""
    )
    trait = (g.get("trait") or {}).get("name") or "Deep Halls"
    text = (
        f"{kind[0].upper()}{kind[1:]}, {ELEMENT_LOOK.get(g['element'], '')}"
        f"{', ' + mod if mod else ''}{', with ' + ' and '.join(traits) if traits else ''}. "
        f"A single {g['kind']} monster, full body, the boss of a dungeon, in a vast underground chamber called the {trait}. "
        f"Dark fantasy creature concept art, {STYLE}"
    )
    out = _pack("guardian", text)
    out["negative"] += ", human, person, rider, knight, text"
    return out


GODDESS_RACES = {  # race -> (how she's called, what marks it)
    "human": ("human", ""),
    "elf": ("elven", "long pointed elven ears"),
    "half_elf": ("half-elven", "gently pointed ears"),
    "dwarf": ("dwarven", "a short, sturdy dwarven frame"),
    "beastkin": ("fox-eared beastkin", "soft fox ears atop her head and a fluffy fox tail"),
    "dragonkin": ("dragonkin", "small swept-back horns and a few iridescent scales along her cheekbones"),
    "celestial": ("celestial", "faintly luminous skin dusted with starlight freckles"),
}
GODDESS_AGES = {  # age -> how she looks
    "kid": "little girl about nine years old, with a round, cheerful face",
    "teen": "girl of about fifteen, with a bright, youthful face",
    "young_adult": "young woman in her early twenties, with a soft youthful face",
    "adult": "graceful woman in her late thirties, with a kind, mature face",
    "elderly": "serene old woman with gentle wrinkles and kind, knowing eyes",
}
GODDESS_BUILDS = {
    "petite": "a petite, delicate frame",
    "slender": "a slender frame",
    "average": "an average build",
    "athletic": "a lean, athletic build",
    "sturdy": "a sturdy, strong build",
    "full": "a soft, full figure",
}
GODDESS_HAIR = ["chestnut-brown", *HAIR]
GODDESS_HAIRSTYLES = {
    "ribbons": "long flowing {c} hair tied with two large lilac ribbon bows",
    "long": "long flowing {c} hair",
    "braid": "{c} hair in a long loose braid over one shoulder",
    "updo": "{c} hair in an elegant updo with loose strands",
    "twintails": "{c} hair in twin tails tied with lilac ribbons",
    "bob": "{c} hair in a soft chin-length bob",
    "short": "short tousled {c} hair",
    "crown_braid": "{c} hair braided into a crown around her head",
}
GODDESS_EYES = ["violet", *[e for e in EYES if e != "violet"], "golden", "silver"]
GODDESS_OUTFITS = {
    "moonlit": "a fitted indigo bodice with puffed lilac sleeves and a moonstone pendant, and a flowing white skirt "
    "trimmed in gold",
    "starlight": "a flowing midnight-blue gown scattered with tiny embroidered silver stars, with a sheer starry cape",
    "dawn": "a soft white and rose-gold gown with sheer flowing sleeves and a sash the colour of sunrise",
    "priestess": "layered white and gold temple priestess robes with wide sleeves, a moonstone brooch and a prayer-bead belt",
    "cosy": "a cosy lilac cable-knit cardigan over a simple white sundress, with fluffy socks and slippers",
    "armoured": "elegant silver crescent-moon plate armour with a flowing indigo skirt and a pale blue cape",
    "huntress": "a forest-green huntress tunic with leather bracers and soft boots, a silver moon-bow across her back",
    "winter": "a long snow-white fur-trimmed winter gown with a silver crescent clasp and white mittens",
    "festival": "a deep indigo festival yukata printed with silver moons and rabbits, with a lilac obi and a paper lantern",
    "scholar": "slate-blue scholar's robes with ink-stained cuffs, a satchel of rolled star charts and a quill behind one ear",
    "traveller": "a hooded dusky-violet travelling cloak over a simple tunic and leggings, belt pouches and a staff "
    "topped with a crescent",
    "ballgown": "a full ballgown of shimmering silver silk that ripples like moonlight on water, with long satin gloves",
    "modern": "a lilac hoodie with a little moon on it, jeans and white sneakers, as if she'd popped into the modern world",
    "ethereal": "layers of translucent pale veils that drift around her like mist and glow faintly at the edges",
}
GODDESS_BACKDROPS = {  # "shrine": her shrine, which grows with your devotion; "mood": a scene to suit each mood
    "shrine": None,
    "mood": None,
    "night_sky": "a vast moonlit night sky above drifting silver clouds",
    "garden": "a moonlit temple garden of white lilies and still ponds",
    "lake": "the shore of a still lake reflecting a huge full moon",
    "library": "a quiet tower library of star charts, brass telescopes and candles",
    "forest": "an ancient silver-birch forest with fireflies",
    "plain": "a plain soft grey backdrop",
}
MOOD_BACKDROPS = {
    "serene": "a quiet moonlit shrine with a single glowing lantern",
    "playful": "a starry sky full of drifting paper lanterns",
    "proud": "her temple hall, moonlit banners hanging between tall pillars",
    "worried": "a dim shrine under gathering storm clouds",
    "delighted": "a moonlit garden bursting with blooming flowers",
    "divine": "a radiant celestial temple floating above the clouds",
}
GODDESS_CHOICES = {
    "race": list(GODDESS_RACES),
    "age": AGES,
    "build": list(GODDESS_BUILDS),
    "hair": GODDESS_HAIR,
    "hairstyle": list(GODDESS_HAIRSTYLES),
    "eyes": GODDESS_EYES,
    "outfit": list(GODDESS_OUTFITS),
    "backdrop": list(GODDESS_BACKDROPS),
    "framing": ["three_quarter", "full", "half", "closeup"],
}
LUNE_MOODS = {
    "serene": "smiling serenely with hands folded",
    "playful": "leaning forward with a playful teasing grin",
    "proud": "beaming with pride, one hand on her heart",
    "worried": "looking worried, biting her lip",
    "delighted": "laughing with delight, eyes sparkling",
    "divine": "radiant and divine, glowing with moonlight, arms open",
}
LUNE_HOMES = [  # grows with devotion
    "a crumbling, overgrown forgotten shrine",
    "a small shrine with a single lit candle",
    "a restored shrine with fresh flowers",
    "a shrine lit by glowing paper lanterns",
    "a small moonstone temple with stained glass",
    "a grand radiant moon temple under a starlit sky",
]


def goddess_identity(name: str = "Lune", prefs: dict[str, Any] | None = None) -> str:
    """Who she is (race, age, build, hair, eyes): the same words in every painting of her, so she stays herself."""
    p = prefs or {}
    race, mark = GODDESS_RACES.get(p.get("race"), GODDESS_RACES["human"])
    age = GODDESS_AGES.get(p.get("age"), GODDESS_AGES["young_adult"])
    default_hair = "silver-white" if p.get("age") == "elderly" else "chestnut-brown"
    hair = GODDESS_HAIRSTYLES.get(p.get("hairstyle"), GODDESS_HAIRSTYLES["ribbons"]).format(
        c=p.get("hair") if p.get("hair") in GODDESS_HAIR else default_hair
    )
    eyes = p.get("eyes") if p.get("eyes") in GODDESS_EYES else "violet"
    build = GODDESS_BUILDS.get(p.get("build"))
    skin = "" if p.get("race") in ("dragonkin", "celestial") else "fair skin, "
    return (
        f"{name}, a forsaken moon goddess who looks like a {race} {age}{', with ' + mark if mark else ''}"
        f"{', ' + build if build else ''}, {skin}{hair}, big gentle {eyes} eyes, a small gold crescent-moon tiara "
        f"and a thin glowing crescent halo"
    )


def _goddess_negative(prefs: dict[str, Any] | None) -> str:
    """Keep her the age that was chosen (by default, young) and the race (no stray ears or horns)."""
    p = prefs or {}
    age = p.get("age") or "young_adult"
    neg = {
        "elderly": ", young girl, child",
        "adult": ", child, elderly",
        "kid": ", adult woman, elderly, wrinkles",
        "teen": ", adult woman, elderly, wrinkles",
    }.get(age, ", old woman, elderly, wrinkles, aged face")
    if p.get("race") in (None, "human", "celestial"):
        neg += ", pointed ears, animal ears, horns"
    return neg


def goddess_backdrop(mood: str, tier: int, prefs: dict[str, Any] | None = None) -> str:
    """Where she is: her shrine (grows with devotion), a scene for the mood, or a fixed backdrop."""
    choice = (prefs or {}).get("backdrop") or "shrine"
    if choice == "mood":
        return MOOD_BACKDROPS.get(mood, MOOD_BACKDROPS["serene"])
    return GODDESS_BACKDROPS.get(choice) or LUNE_HOMES[min(max(tier, 0), len(LUNE_HOMES) - 1)]


def goddess_prompt(mood: str, tier: int, name: str = "Lune", prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    """The goddess in a mood, painted from the prompt (without an image-edit model)."""
    dress = GODDESS_OUTFITS.get((prefs or {}).get("outfit"), GODDESS_OUTFITS["moonlit"])
    text = (
        f"Full-body portrait of {goddess_identity(name, prefs)}, wearing {dress}, a ribbon of lilac moonlight floating "
        f"around her, {LUNE_MOODS.get(mood, LUNE_MOODS['serene'])}, in {goddess_backdrop(mood, tier, prefs)}. "
        f"{FULL_BODY}, {STYLE}"
    )
    out = _pack("goddess", text)
    out["negative"] += _goddess_negative(prefs)
    return out


def goddess_base_prompt(name: str = "Lune", prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Her base painting for an image-edit model: who she is, in a plain shift, on a plain grey backdrop."""
    who, _ = split_prefs(prefs)
    out = _pack(
        "goddess",
        f"Full-body character reference of {goddess_identity(name, who)}, wearing a simple plain white "
        f"linen shift dress and soft slippers, {BASE_POSE}. {FULL_BODY}, {BASE_STYLE}",
        base=True,
    )
    out["negative"] += _goddess_negative(who)
    return out


def goddess_edit(mood: str, tier: int, prefs: dict[str, Any] | None = None) -> str:
    """How to turn her base painting into a mood: her outfit, her expression and pose, and where she is."""
    p = prefs or {}
    race = GODDESS_RACES.get(p.get("race"), GODDESS_RACES["human"])[0]
    age = GODDESS_AGES.get(p.get("age"), GODDESS_AGES["young_adult"]).split(",")[0]
    dress = GODDESS_OUTFITS.get(p.get("outfit"), GODDESS_OUTFITS["moonlit"])
    return (
        f"Keep this exact same {race} {age}: the same face, age, race, ears, hair, eye colour, skin, body, tiara and "
        f"halo. Dress her in {dress}, with a ribbon of lilac moonlight floating around her. Change her expression and "
        f"pose: {LUNE_MOODS.get(mood, LUNE_MOODS['serene'])}. Replace the plain grey background with "
        f"{goddess_backdrop(mood, tier, p)}. Keep the whole figure in frame from head to feet, and the same "
        f"painterly art style."
    )


NPC_LOOK = [
    "a cheerful travelling merchant with a wide-brimmed hat kneeling beside a cloth of curious wares on a country road",
    None,  # Lune herself: the playful goddess portrait is used instead
    "a prim adventurers' guild clerk with spectacles sliding a sealed envelope across a wooden desk",
    "a mysterious hooded stranger in a dark travelling cloak on a misty road, face half in shadow",
    "a small playful water spirit made of living water rising out of a cup",
    "a smug rival adventurer with a confident grin slapping a contract on a tavern table",
    "a glowing blue magical status window floating in the air above an empty road, soft chime of light",
    "a grizzled retired adventurer with an eyepatch and grey beard at a tavern table, raising an eyebrow",
    "a fortune teller in a candlelit tent turning over a tarot card",
    "a clever black crow wearing a tiny monocle perched on a windowsill",
    "a ghostly whispering face formed in the stone wall of a dark labyrinth corridor",
    "an excited village child holding up a crumpled quest flyer in a sunny street",
    "a muscular blacksmith woman wiping her hands on a leather apron beside a glowing forge",
    "a flamboyant bard with a lute and a feathered cap strumming a chord in a tavern",
    "two ornate bone dice rolling to a stop on a tavern table under candlelight",
    "a small, very polite blue slime wearing a tiny bow tie",
    "a wooden adventurers' quest board covered in notices, one of them glowing with magic",
    "a royal herald in a heraldic tabard unrolling a long scroll",
    "a rain puddle on cobblestones showing a shimmering mysterious reflection",
    "a warm, burly innkeeper setting down a frothing mug on a polished bar",
]
MERCHANT_NAME = "Marrow Fennick"
MERCHANT_RACES = {  # race -> (what he is, what marks it)
    "gnome": ("gnome", "a big nose and bright, mischievous eyes"),
    "halfling": ("halfling", "curly hair and a round, friendly face"),
    "dwarf": ("dwarf", "a broad, weathered face"),
    "human": ("human", ""),
    "elf": ("elf", "long pointed ears"),
    "goblin": ("goblin", "green skin, big pointed ears and sharp little teeth"),
    "beastkin": ("raccoon-eared beastkin", "round raccoon ears, a masked face and a striped tail"),
    "dragonkin": ("dragonkin", "stubby horns and bronze scales"),
}
MERCHANT_AGES = {
    "kid": "a boy about nine years old who minds the family stall",
    "teen": "a teenage apprentice of about fifteen",
    "young_adult": "a young man in his twenties",
    "adult": "a man in his prime",
    "elderly": "a very old man with deep wrinkles",
}
MERCHANT_BUILDS = {
    "wiry": "wiry",
    "slight": "slight and small",
    "average": "medium-built",
    "stout": "stout and round-faced",
    "broad": "broad-shouldered and barrel-chested",
    "heavyset": "big-bellied and heavyset",
    "lanky": "tall and lanky",
}
MERCHANT_HAIR = {
    "muttonchops": "bushy white mutton-chop whiskers",
    "ginger": "a neatly trimmed ginger beard",
    "grey": "a long grey beard tucked into his belt",
    "bald": "a shiny bald head and a clean-shaven chin",
    "moustache": "a curly black moustache",
    "wild": "a wild shock of white hair",
    "ponytail": "long grey hair tied back in a ponytail",
    "stubble": "short dark hair and a scruffy stubble",
}
MERCHANT_ACCESSORIES = {
    "monocle": "a brass magnifying monocle",
    "spectacles": "round wire spectacles",
    "goggles": "brass tinker's goggles pushed up on his forehead",
    "eyepatch": "a leather eyepatch",
    "pipe": "a long carved pipe",
    "hat": "a tall feathered hat",
    "scales": "a little set of brass merchant's scales hanging from his belt",
    "none": "",
}
MERCHANT_OUTFITS = {
    "waistcoat": "a patched plum velvet waistcoat over a rolled-sleeve linen shirt, with a brass pocket-watch chain",
    "coat": "a long dusty brown travelling coat with dozens of bulging pockets, over sturdy boots",
    "apron": "a scorched leather work apron over a linen shirt, sleeves rolled up, tools in the pockets",
    "finery": "a fine emerald coat embroidered with gold thread and gold buttons, with a lace cravat",
    "cloak": "a hooded moss-green travelling cloak pinned with a silver coin brooch",
    "sailor": "a salt-stained navy sailor's coat with brass buttons and a striped knitted scarf",
    "desert": "loose sand-coloured desert robes, a wrapped indigo headscarf and many jingling bangles",
    "winter": "a thick patchwork fur coat, a knitted bobble hat and fingerless mittens",
    "noble": "a tailored burgundy doublet with slashed sleeves, lace cuffs and a jewelled brooch",
    "tinker": "a tinker's leather harness hung with tools, little gears and tiny stoppered jars",
    "festival": "a garish festival jacket covered in tiny bells, ribbons and embroidered stars",
}
MERCHANT_BACKDROPS = {
    "wagon": "a cluttered lantern-lit merchant's wagon full of curiosities",
    "market": "a busy open-air market stall under a striped awning",
    "tavern": "a corner table of a cosy tavern, wares spread across it",
    "caravan": "a desert caravan tent full of rugs, lamps and brass",
    "shop": "a cramped shop with shelves of oddities up to the ceiling",
    "harbour": "a harbour-side stall with crates, nets and gulls",
    "plain": "a plain soft grey backdrop",
}
MERCHANT_CHOICES = {
    "race": list(MERCHANT_RACES),
    "age": AGES,
    "build": list(MERCHANT_BUILDS),
    "hair": list(MERCHANT_HAIR),
    "outfit": list(MERCHANT_OUTFITS),
    "accessory": list(MERCHANT_ACCESSORIES),
    "backdrop": list(MERCHANT_BACKDROPS),
    "framing": ["bust", "closeup", "half", "full"],
}


def merchant_identity(prefs: dict[str, Any] | None = None) -> str:
    """Who Marrow is (race, age, build, hair): the same words in every painting of him."""
    p = prefs or {}
    race, mark = MERCHANT_RACES.get(p.get("race"), MERCHANT_RACES["gnome"])
    build = MERCHANT_BUILDS.get(p.get("build"), MERCHANT_BUILDS["wiry"])
    age = MERCHANT_AGES.get(p.get("age"))
    hair = MERCHANT_HAIR.get(p.get("hair"))
    return (
        f"Marrow Fennick, a {build} {race} merchant{', ' + age if age else ''}"
        f"{', with ' + mark if mark else ''}{', ' + hair if hair else ''}, sharp eyes and a sly grin"
    )


def merchant_dress(prefs: dict[str, Any] | None = None) -> str:
    """What he wears and carries."""
    p = prefs or {}
    acc = MERCHANT_ACCESSORIES.get(p.get("accessory"), MERCHANT_ACCESSORIES["monocle"])
    return f"{MERCHANT_OUTFITS.get(p.get('outfit'), MERCHANT_OUTFITS['waistcoat'])}{', and ' + acc if acc else ''}"


def _merchant_negative(prefs: dict[str, Any] | None) -> str:
    """Extra negative-prompt words that keep a young merchant from being painted old and bearded."""
    return ", beard, old man, wrinkles" if (prefs or {}).get("age") in ("kid", "teen") else ""


MERCHANT_MOODS = {
    "generous": "beaming generously, arms spread over his wares",
    "fair": "polishing a trinket with a shrewd smile",
    "stubborn": "arms crossed, one eyebrow raised",
    "offended": "scowling and clutching his coin purse",
    # how the haggling is going
    "annoyed": "frowning with his arms crossed, tapping his foot impatiently, clearly losing patience",
    "angry": "angry and red-faced, scowling and jabbing a finger at the customer",
    "furious": "furious, face bright red, shouting and slamming his fist on the counter, coins bouncing",
}


def npc_prompt(index: int) -> dict[str, Any] | None:
    """The character who offers the daily choice (None for Lune, who has her own portraits)."""
    look = NPC_LOOK[index % len(NPC_LOOK)]
    if look is None:
        return None
    return _pack("npc", f"Character vignette: {look}. {STYLE}")


def merchant_prompt(mood: str, prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    """The shopkeeper in a mood, painted from the prompt (without an image-edit model)."""
    where = MERCHANT_BACKDROPS.get((prefs or {}).get("backdrop"), MERCHANT_BACKDROPS["wagon"])
    out = _pack(
        "merchant",
        f"Full-body portrait of {merchant_identity(prefs)}, wearing {merchant_dress(prefs)}, "
        f"{MERCHANT_MOODS.get(mood, MERCHANT_MOODS['fair'])}, in {where}. {FULL_BODY}, {STYLE}",
    )
    out["negative"] += _merchant_negative(prefs)
    return out


def merchant_base_prompt(prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    """His base painting for an image-edit model: who he is, in plain clothes, on a plain grey backdrop."""
    who, _ = split_prefs(prefs)
    out = _pack(
        "merchant",
        f"Full-body character reference of {merchant_identity(who)}, wearing a plain undyed linen shirt, "
        f"trousers and simple boots, {BASE_POSE}. {FULL_BODY}, {BASE_STYLE}",
        base=True,
    )
    out["negative"] += _merchant_negative(who)
    return out


def merchant_edit(mood: str, prefs: dict[str, Any] | None = None) -> str:
    """How to turn his base painting into a mood: his outfit, his expression and pose, and where he trades."""
    p = prefs or {}
    race = MERCHANT_RACES.get(p.get("race"), MERCHANT_RACES["gnome"])[0]
    where = MERCHANT_BACKDROPS.get(p.get("backdrop"), MERCHANT_BACKDROPS["wagon"])
    return (
        f"Keep this exact same {race} merchant: the same face, age, race, hair, skin and build. Dress him in "
        f"{merchant_dress(p)}. Change his expression and pose: {MERCHANT_MOODS.get(mood, MERCHANT_MOODS['fair'])}. "
        f"Replace the plain grey background with {where}. Keep the whole figure in frame from head to feet, and the "
        f"same painterly art style."
    )


def voice_index(voice: str) -> int:
    """Which choice character a voice line belongs to."""
    return C.CHOICE_VOICES.index(voice) if voice in C.CHOICE_VOICES else 0


def _pack(kind: str, prompt: str, base: bool = False) -> dict[str, Any]:
    """Wrap a prompt with its size and negative prompt; base paintings are flagged to paint at full quality."""
    w, h, ow, oh = BASE_SIZE if base else SIZES[kind]
    out = {
        "kind": kind,
        "prompt": " ".join(prompt.split()),
        "negative": NEGATIVE,
        "w": w,
        "h": h,
        "out_w": ow,
        "out_h": oh,
    }
    if base:  # painted at full quality whatever the painting speed: everything else is edited from it
        out["hq"] = True
    return out
