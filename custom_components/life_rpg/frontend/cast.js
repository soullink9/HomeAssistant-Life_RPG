/* Life RPG pixel cast: the goddess (Lune unless renamed), Marrow the merchant, the 20 characters who offer
 * daily choices, and icons for potions and cosmetics. These are the stand-ins whenever no painting exists
 * (no ComfyUI, pixel-art mode, or a painting still on its way). Everything is drawn from code; same input,
 * same picture. */
import { Buf, adventurerArt, monsterArt, ramp, rng, toImage, METALS, LEATHER, WOOD } from "./art.js?v=1.0.2";

const cache = new Map();
// Draw each picture once per page load.
const memo = (key, fn) => (cache.has(key) ? cache.get(key) : (cache.set(key, fn()), cache.get(key)));
// A made-up gear item so the cast can wear gear drawn by art.js.
const item = (base, rarity, slot, tag = "") => ({ id: `cast-${tag}${base}`, name: `${tag} ${base}`, base, rarity, slot, enh: 0 });
const outfit = (spec, tag) => Object.fromEntries(Object.entries(spec).map(([slot, [base, rarity]]) => [slot, item(base, rarity, slot, tag)]));
// A full look for adventurerArt, with defaults for anything not given.
const look = (o) => ({ skin: 1, hair: 1, fur: 0, eyes: 0, hairstyle: "short", ears: "fox", tail: "fluffy", horns: "swept",
  wings: false, beard: "full", blush: false, scar: false, shirt_hue: 30, build: [0, 0, 0], ...o });

// --- faces ---------------------------------------------------------------------------------------
function face(b, A, mood) {
  const y = A.eyeY;
  for (const x of [30, 31, 32, 33]) for (const dy of [2, 3, 4]) if (b.reg(x, y + dy) === "face" && b.mat(x, y + dy) === "mouth") b.set(x, y + dy, "skin", "face", 2);
  const m = (pts, tone = 1) => pts.forEach(([x, dy]) => b.set(x, y + dy, "mouth", "face", tone));
  const brow = (pts) => pts.forEach(([x, dy]) => b.set(x, y + dy, "lash", "face", 0));
  switch (mood) {
    case "playful": // wink and a lopsided grin
      for (const x of [28, 29]) for (const dy of [-2, -1, 0]) b.set(x, y + dy, "skin", "face", 2);
      brow([[28, 0], [29, 0]]); m([[31, 3], [32, 3], [33, 2]]); break;
    case "proud": m([[30, 2], [31, 3], [32, 3], [33, 2]]); break;
    case "delighted": m([[30, 2], [31, 3], [32, 3], [33, 2]]); m([[31, 4], [32, 4]], 0);
      b.set(27, y + 2, "blush", "face", 2); b.set(36, y + 2, "blush", "face", 2); break;
    case "worried": case "offended": case "stubborn":
      brow(mood === "worried" ? [[28, -4], [29, -3], [34, -3], [35, -4]] : [[28, -3], [29, -4], [34, -4], [35, -3]]);
      m(mood === "stubborn" ? [[30, 3], [31, 3], [32, 3], [33, 3]] : [[30, 4], [31, 3], [32, 3], [33, 4]]); break;
    default: m([[31, 3], [32, 3]]); b.set(30, y + 2, "mouth", "face", 2); b.set(33, y + 2, "mouth", "face", 2);
  }
}
/** A tiny ring of eight pixels (an earring, a ring, a coin). */
function ring(b, cx, cy, mat, tone = 3) {
  for (const [dx, dy] of [[-1, -2], [0, -2], [-2, -1], [1, -1], [-2, 0], [1, 0], [-1, 1], [0, 1]]) b.set(cx + dx, cy + dy, mat, "acc", tone);
}

// --- the goddess -----------------------------------------------------------------------------------
// Her own hand-built sprite (not the adventurer doll): a young goddess with long chestnut hair, lilac
// ribbons, a moon tiara, an indigo bodice and a white skirt trimmed in gold. Her halo grows with devotion.
const LUNE_GLOW = { serene: "#cdbbff", playful: "#ffc4ee", proud: "#ffe7a3", worried: "#9fc7ff", delighted: "#ffd6f0", divine: "#ffffff" };
const GODDESS_PAL = {
  skin: ["#d9a58c", "#efc4a8", "#fbdcc6", "#fff0e4"],
  hair: ["#3f2318", "#5f3424", "#7e4a31", "#a56a45"],
  ribbon: ["#9a5a9e", "#c27fc4", "#e2a8e0", "#f6d4f2"],
  dress: ["#1d1a4a", "#2c2a6e", "#3d3c94", "#5655b8"],
  skirt: ["#b9b4dc", "#d8d4f0", "#eeecfa", "#ffffff"],
  under: ["#2c2a6e", "#3d3c94", "#5655b8", "#7272cc"],
  trim: ["#a8781e", "#d4a53a", "#f2cf63", "#fff1b0"],
  boot: ["#1b1838", "#2a2652", "#3a356e", "#504a8e"],
  eye: ["#2b1d5a", "#5a3fa8", "#8b6fe0", "#ffffff"],
  lash: ["#2a1410", "#3a1d16", "#4a271d", "#5a3326"],
  mouth: ["#b4505a", "#d06a72", "#e88e92", "#f6b4b4"],
  blush: ["#f29aa6", "#f6aab4", "#f9bcc4", "#fcd0d6"],
  halo: ["#b9a6ff", "#d9ccff", "#f2ecff", "#ffffff"],
  stole: ["#8f7fd0", "#b3a6ec", "#d6cdfb", "#f1edff"],
  gem: ["#3c6fd8", "#5c96f0", "#9cc8ff", "#ffffff"],
};
const CX = 31.5, HEAD_TOP = 12, EYE_Y = 25;

/** The goddess's own face, in a mood. */
function goddessFace(b, mood) {
  const L = [25, 26, 27], R = [36, 37, 38]; // eye columns (3 wide), mirrored about 31.5
  const open = (xs, outer, lid = 0) => {
    xs.forEach((x) => b.set(x, EYE_Y + lid, "lash", "eye", 0)); // upper lashes
    b.set(outer, EYE_Y + lid, "lash", "eye", 0); b.set(outer, EYE_Y - 1 + lid, "lash", "eye", 0); // a flick at the outer corner
    for (let dy = 1 + lid; dy <= 4; dy++) xs.forEach((x, i) => b.set(x, EYE_Y + dy, "eye", "eye", dy === 4 ? 2 : dy === 1 + lid ? 0 : i === 1 ? 1 : 2));
    if (!lid) b.set(xs[0] === 25 ? 25 : 36, EYE_Y + 2, "eye", "eye", 3); // the catch-light
  };
  const closed = (xs) => { b.set(xs[0], EYE_Y + 3, "lash", "eye", 0); b.set(xs[1], EYE_Y + 2, "lash", "eye", 0); b.set(xs[2], EYE_Y + 3, "lash", "eye", 0); };
  const brow = (pts) => pts.forEach(([x, y]) => b.set(x, EYE_Y + y, "hair", "brow", 0));
  const mouth = (pts, tone = 1) => pts.forEach(([x, y]) => b.set(x, EYE_Y + y, "mouth", "face", tone));
  const blush = () => { for (const x of [25, 26, 37, 38]) b.set(x, EYE_Y + 6, "blush", "face", 1); };
  switch (mood) {
    case "delighted": closed(L); closed(R); blush(); mouth([[31, 7], [32, 7]], 1); mouth([[31, 8], [32, 8]], 0); break;
    case "playful": closed(L); open(R, 39); blush(); mouth([[32, 7], [33, 7]]); b.set(31, EYE_Y + 7, "mouth", "face", 2); break;
    case "proud": open(L, 24, 1); open(R, 39, 1); mouth([[31, 7], [32, 7]], 2); b.set(30, EYE_Y + 6, "mouth", "face", 2); b.set(33, EYE_Y + 6, "mouth", "face", 2); break;
    case "worried": open(L, 24); open(R, 39); brow([[25, -1], [26, -2], [37, -2], [38, -1]]); mouth([[31, 8], [32, 8]], 1); b.set(30, EYE_Y + 9, "mouth", "face", 2); b.set(33, EYE_Y + 9, "mouth", "face", 2); break;
    case "divine": open(L, 24); open(R, 39); for (const x of [...L, ...R]) b.set(x, EYE_Y + 3, "halo", "eye", 3); mouth([[31, 7], [32, 7]], 2); break;
    default: open(L, 24); open(R, 39); mouth([[31, 7], [32, 7]], 2); b.set(30, EYE_Y + 6, "mouth", "face", 2); b.set(33, EYE_Y + 6, "mouth", "face", 2);
  }
}

/** A ribbon bow in the goddess's hair. */
function bow(b, kx, ky, dir) {
  b.poly([[kx, ky], [kx - 4 * dir, ky - 4], [kx - 5 * dir, ky - 1], [kx - 4 * dir, ky + 2]], "ribbon", "bow");
  b.poly([[kx, ky], [kx + 3 * dir, ky - 3], [kx + 4 * dir, ky], [kx + 3 * dir, ky + 2]], "ribbon", "bow");
  b.line(kx, ky + 1, kx - 2 * dir, ky + 6, "ribbon", "bow", 1); b.line(kx + 1 * dir, ky + 1, kx + 2 * dir, ky + 5, "ribbon", "bow", 1);
  b.rect(Math.min(kx, kx + dir), ky - 1, 2, 2, "ribbon", "bow"); b.set(kx, ky - 1, "ribbon", "bow", 3);
}

/** The goddess in a mood (serene, playful, proud, worried, delighted, divine); her halo grows with devotion. */
export function luneArt(mood = "serene", tier = 0) {
  return memo(`lune|${mood}|${tier}`, () => {
    const b = new Buf(64, 84), glow = [], tint = LUNE_GLOW[mood] || "#ffffff";
    // long hair behind everything, falling to the hips in soft waves
    // a flowing stole that floats behind her
    for (const d of [-1, 1]) {
      for (let t = 0; t <= 1; t += 0.02) { // a ribbon of light from her elbows, billowing out and down
        const x = CX + d * (9 + 11 * Math.sin(t * 2.4) + 2 * t), y = 41 + 27 * t, w = 1.2 + 1.3 * Math.sin(t * Math.PI);
        for (let k = 0; k <= Math.round(w * 2); k++) b.set(x + d * (k * 0.5 - w / 2), y, "stole", "stole", k === 0 ? 3 : k > w * 1.5 ? 1 : 2);
      }
      glow.push([Math.round(CX + d * 21), 69, tint]);
    }
    const skullTop = (x) => 22 - 10 * Math.sqrt(Math.max(0, 1 - ((x - CX) / 11.5) ** 2));
    b.ellipse(CX, 22, 11.5, 10, "hair", "hairB");
    b.poly([[20.5, 22], [42.5, 22], [45, 40], [46, 52], [44, 58], [41, 56], [38, 59], [25, 59], [22, 56], [19, 58], [17, 52], [18, 40]], "hair", "hairB");
    for (const x of [21, 25, 38, 42]) b.line(x, 34, x + (x < 32 ? -1 : 1), 55, "hair", "hairB", 1);
    // legs and boots
    for (const x0 of [27, 34]) { b.rect(x0, 64, 3, 9, "skin", "leg"); b.rect(x0 - 1, 72, 5, 9, "boot", "boot"); b.rect(x0 - 1, 72, 5, 1, "trim", "boot"); b.set(x0 + (x0 < 31 ? -2 : 4), 80, "boot", "boot"); }
    // skirt: white layers over an indigo underskirt, gold hem
    b.poly([[25.5, 47], [37.5, 47], [45, 64], [18, 64]], "skirt", "skirt");
    b.rect(19, 64, 26, 2, "under", "skirt");
    for (let x = 18; x <= 45; x++) b.set(x, 63, "trim", "skirt", (x % 2) + 1);
    for (const [x0, x1] of [[28, 24], [31.5, 31.5], [35, 39]]) b.line(x0, 49, x1, 62, "skirt", "skirt", 1); // pleats
    // bodice, puffed sleeves, sash and moon pendant
    b.poly([[24.5, 36], [38.5, 36], [37, 47], [26, 47]], "dress", "dress");
    b.ellipse(23.5, 38.5, 3.3, 2.8, "ribbon", "sleeve"); b.ellipse(39.5, 38.5, 3.3, 2.8, "ribbon", "sleeve");
    b.rect(26, 46, 12, 2, "trim", "sash");
    for (let x = 27; x <= 36; x++) b.set(x, 36, "trim", "dress", 2);
    b.set(31, 39, "gem", "acc", 2); b.set(32, 39, "gem", "acc", 3); b.set(31, 40, "gem", "acc", 1); b.set(32, 40, "gem", "acc", 2);
    // slim arms, hands folded in front
    b.line(22, 41, 27, 49, "skin", "arm"); b.line(23, 41, 28, 49, "skin", "arm");
    b.line(41, 41, 36, 49, "skin", "arm"); b.line(40, 41, 35, 49, "skin", "arm");
    b.ellipse(CX, 49.5, 3, 1.8, "skin", "hand");
    // neck and face (kept flat and soft so she reads young)
    b.rect(30, 33, 4, 4, "skin", "neck"); b.set(30, 35, "skin", "neck", 1); b.set(33, 35, "skin", "neck", 1);
    const half = [6.5, 7.5, 8, 8.5, 8.5, 8.5, 8.5, 8.5, 8.5, 8.5, 8, 7.5, 7, 6, 4.5, 3];
    half.forEach((hw, k) => { for (let x = Math.ceil(CX - hw); x <= Math.floor(CX + hw); x++) b.set(x, 18 + k, "skin", "face", 2); });
    for (let y = 26; y <= 31; y++) b.set(Math.floor(CX + half[y - 18]), y, "skin", "face", 1); // soft shadow on her right cheek
    // fringe with a few longer locks, and side locks framing the face down past the shoulders
    const tips = [3, 4, 2, 5, 3, 2, 4, 6, 3, 2, 5, 3, 2, 4, 3, 5, 2, 3];
    tips.forEach((t, i) => { const x = 23 + i; for (let y = Math.ceil(skullTop(x)); y <= 19 + t; y++) b.set(x, y, "hair", "fringe", y > 18 + t ? 1 : null); });
    for (const [x, y0, y1] of [[27, 17, 22], [31, 16, 24], [36, 17, 22]]) b.line(x, y0, x + (x < 31 ? -1 : x > 32 ? 1 : 0), y1, "hair", "fringe", 1); // strands
    for (const [x, d] of [[22, -1], [41, 1]]) for (let y = 18; y <= 47; y++) { const w = y < 40 ? 2 : 1; b.rect(x + (y > 30 ? d : 0) - (d < 0 ? w - 1 : 0), y, w, 1, "hair", "lock"); }
    for (let x = 24; x <= 35; x++) b.set(x, Math.ceil(skullTop(x)) + 2, "hair", "fringe", 3); // the shine on her crown
    bow(b, 21, 17, 1); bow(b, 42, 17, -1);
    // moon tiara
    b.set(30, 14, "trim", "tiara", 2); b.set(33, 14, "trim", "tiara", 2); b.set(31, 13, "trim", "tiara", 3); b.set(32, 13, "trim", "tiara", 3);
    b.set(31, 14, "gem", "tiara", tier >= 3 ? 3 : 2); b.set(32, 14, "gem", "tiara", tier >= 3 ? 2 : 1);
    goddessFace(b, mood);
    // crescent halo; wider and brighter with devotion
    const hy = HEAD_TOP - 8, rad = 6 + Math.min(tier, 5) * 0.6;
    for (let a = 200; a <= 340; a += 5) {
      const x = Math.round(CX + Math.cos((a * Math.PI) / 180) * rad), y = Math.round(hy + 4 + Math.sin((a * Math.PI) / 180) * rad * 0.5);
      b.set(x, y, "halo", "acc", a > 250 && a < 290 ? 3 : 2);
      if (a % 15 === 0) glow.push([x, y - 1, tint]);
    }
    const r = rng(`lune:${mood}:${tier}`);
    for (let k = 0; k < 5 + tier * 2; k++) { const x = r.int(3, 60), y = r.int(3, 78); if (!b.mat(x, y) && !b.mat(x + 1, y) && !b.mat(x - 1, y)) glow.push([x, y, tint]); }
    return { src: toImage(b, GODDESS_PAL, { glowPx: glow, halo: "#b49cff" }), w: 64, h: 84, headTop: HEAD_TOP };
  });
}

// --- Marrow Fennick ----------------------------------------------------------------------------------
/** The merchant in a mood (generous, fair, stubborn, offended). */
export function merchantArt(mood = "fair") {
  return memo(`merchant|${mood}`, () => adventurerArt("dwarf", "marrow", outfit({ armor: ["Brigandine", "uncommon"], helm: ["Hood", "rare"], boots: ["Boots", "common"] }, "marrow"),
    look({ skin: 0, hair: 2, eyes: 2, hairstyle: "short", beard: "forked", shirt_hue: 330 }),
    { key: `merchant:${mood}`, extra(b, A, pal, glow) {
      face(b, A, { generous: "delighted", fair: "proud", annoyed: "stubborn", angry: "offended", furious: "offended" }[mood] || mood);
      if (mood === "angry" || mood === "furious") { // red in the face
        pal.flush = mood === "furious" ? ["#8a3a33", "#b4503f", "#d86a55", "#f08a70"] : ["#a14a3f", "#c8604f", "#e47c66", "#f59c82"];
        for (let y = A.eyeY - 4; y <= A.eyeY + 4; y++) for (let x = 26; x <= 37; x++)
          if (b.reg(x, y) === "head" && b.mat(x, y) === "skin" && (mood === "furious" || (y >= A.eyeY + 1 && (x <= 28 || x >= 35)))) b.set(x, y, "flush", "head");
      }
      if (mood === "furious") for (const [x, y] of [[22, A.headTop - 1], [21, A.headTop - 2], [22, A.headTop - 3], [21, A.headTop - 5], [41, A.headTop - 1],
        [42, A.headTop - 2], [41, A.headTop - 3], [42, A.headTop - 5], [23, A.headTop - 4], [40, A.headTop - 4]])
        glow.push([x, y, "#e8eef8"]); // steam
      pal.trim = METALS.gold;
      ring(b, 35, A.eyeY - 1, "trim"); // brass monocle
      b.line(36, A.eyeY + 1, 38, A.eyeY + 7, "trim", "acc", 2);
      const [hx, hy] = A.handR; // a fat coin purse
      pal.purse = LEATHER[0];
      b.ellipse(hx + 1, hy + 2, 2.5, 2.5, "purse", "acc");
      glow.push([hx + 1, hy - 1, "#ffe48a"]);
    } }));
}

// --- the cast who offer daily choices ----------------------------------------------------------------
const HUMANOID = {
  0: ["human", { hair: 1, hairstyle: "short", shirt_hue: 40 }, { helm: ["Hood", "uncommon"], armor: ["Tunic", "uncommon"], boots: ["Boots", "common"], weapon: ["Staff", "common"] }],
  2: ["human", { hair: 0, hairstyle: "bob", eyes: 0, shirt_hue: 215 }, { armor: ["Robe", "rare"] }, "spectacles"],
  3: ["human", { hair: 0, skin: 3, hairstyle: "short", shirt_hue: 260 }, { helm: ["Hood", "common"], armor: ["Robe", "common"], boots: ["Boots", "common"] }],
  5: ["human", { hair: 6, hairstyle: "spiky", eyes: 1, shirt_hue: 0 }, { armor: ["Brigandine", "rare"], weapon: ["Shortsword", "rare"], boots: ["Greaves", "uncommon"] }, "smug"],
  7: ["human", { hair: 5, hairstyle: "swept", skin: 2, scar: true, shirt_hue: 25 }, { armor: ["Chainmail", "common"], boots: ["Boots", "common"] }, "eyepatch"],
  8: ["elf", { hair: 10, hairstyle: "long", eyes: 3, skin: 3, shirt_hue: 290 }, { armor: ["Robe", "epic"], helm: ["Circlet", "epic"] }],
  11: ["human", { hair: 3, hairstyle: "bob", build: [-2, -1, -1], blush: true, shirt_hue: 120 }, { armor: ["Tunic", "common"] }, "delighted"],
  12: ["human", { hair: 2, hairstyle: "ponytail", skin: 3, shirt_hue: 20 }, { armor: ["Brigandine", "common"], gloves: ["Gauntlets", "uncommon"], weapon: ["Warhammer", "uncommon"] }],
  13: ["elf", { hair: 3, hairstyle: "swept", eyes: 1, shirt_hue: 140 }, { armor: ["Tunic", "epic"], helm: ["Hood", "rare"], weapon: ["Longbow", "uncommon"] }, "playful"],
  17: ["human", { hair: 1, hairstyle: "short", shirt_hue: 230 }, { armor: ["Tunic", "legendary"], helm: ["Circlet", "rare"], boots: ["Boots", "uncommon"] }, "proud"],
  19: ["dwarf", { hair: 2, hairstyle: "bald", beard: "full", skin: 0, shirt_hue: 30 }, { armor: ["Tunic", "common"] }, "delighted"],
};
// The daily-choice characters who are monsters: [kind, element].
const CREATURE = { 4: ["slime", "tide"], 10: ["wraith", "shadow"], 15: ["slime", "frost"] };

/** Portrait for the daily-choice character at `index` (order of CHOICE_VOICES). Returns {src, w, h}. */
export function npcArt(index) {
  return memo(`npc|${index}`, () => {
    if (index === 1) return luneArt("playful", 0);
    if (HUMANOID[index]) {
      const [race, l, gear, extraKind] = HUMANOID[index];
      return adventurerArt(race, `npc${index}`, outfit(gear, `npc${index}`), look(l), { key: `npc${index}`, extra(b, A, pal) {
        face(b, A, ["smug", "spectacles"].includes(extraKind) ? (extraKind === "smug" ? "playful" : "serene") : extraKind || "serene");
        if (extraKind === "spectacles") { pal.specs = METALS.iron; ring(b, 29, A.eyeY - 1, "specs"); ring(b, 35, A.eyeY - 1, "specs"); }
        if (extraKind === "eyepatch") {
          for (const x of [28, 29]) for (const dy of [-2, -1, 0]) b.set(x, A.eyeY + dy, "lash", "acc", 0);
          b.line(A.hl, A.eyeY - 4, 29, A.eyeY - 2, "lash", "acc", 0);
        }
      } });
    }
    if (CREATURE[index]) { const [k, e] = CREATURE[index]; return { ...monsterArt(k, e, `npc${index}`), w: 48, h: 48 }; }
    return { src: objectArt(index), w: 48, h: 48 };
  });
}

/** The few characters who aren't people: the System, a crow, dice, the quest board, a puddle. */
function objectArt(index) {
  const b = new Buf(48, 48);
  const pal = { default: ["#222", "#444", "#666", "#888"] };
  const glow = [];
  if (index === 6) { // the System's blue window
    pal.win = ["#0b2a4a", "#123a66", "#1c5590", "#2a74c0"]; pal.edge = ["#3a8fd8", "#4fb0ff", "#8fd3ff", "#e0f4ff"];
    b.rect(8, 12, 32, 22, "win", "w");
    for (let x = 8; x < 40; x++) { b.set(x, 12, "edge", "w", 3); b.set(x, 33, "edge", "w", 2); }
    for (let y = 12; y < 34; y++) { b.set(8, y, "edge", "w", 2); b.set(39, y, "edge", "w", 2); }
    for (const [y, w] of [[17, 18], [21, 12], [25, 22]]) b.rect(12, y, w, 1, "edge", "t");
    for (let x = 10; x < 38; x += 3) glow.push([x, 11, "#bfe6ff"]);
  } else if (index === 9) { // a crow with a monocle
    pal.crow = ["#0d0f18", "#1a1d2a", "#2b3042", "#46506a"]; pal.beak = ramp(40, 0.3, 0.55); pal.trim = METALS.gold; pal.sill = WOOD[1];
    b.rect(4, 38, 40, 4, "sill", "s");
    b.ellipse(24, 28, 9, 8, "crow", "c"); b.ellipse(29, 19, 6, 5, "crow", "c");
    b.poly([[34, 18], [40, 20], [34, 21]], "beak", "c");
    b.poly([[15, 28], [8, 36], [18, 34]], "crow", "c");
    b.set(30, 18, "beak", "e", 3); ring(b, 31, 19, "trim");
    b.line(21, 36, 21, 38, "beak", "l"); b.line(26, 36, 26, 38, "beak", "l");
  } else if (index === 14) { // two dice
    pal.die = ["#b9ae98", "#d8cfbb", "#efe8d8", "#ffffff"]; pal.pip = ["#3a1010", "#5a1818", "#7a2020", "#9a3030"];
    for (const [x, y, n] of [[8, 18, 5], [26, 24, 3]]) {
      b.rect(x, y, 14, 14, "die", "d");
      const pips = { 5: [[3, 3], [10, 3], [6, 7], [3, 10], [10, 10]], 3: [[3, 3], [6, 7], [10, 10]] }[n];
      pips.forEach(([px, py]) => { b.rect(x + px, y + py, 2, 2, "pip", "p"); });
    }
  } else if (index === 16) { // the quest board
    pal.board = WOOD[0]; pal.paper = ["#b8a77e", "#d3c398", "#eadcb4", "#fff6d8"]; pal.magic = ramp(200, 0.8, 0.6);
    b.rect(6, 8, 36, 30, "board", "b"); b.rect(10, 38, 3, 8, "board", "b"); b.rect(35, 38, 3, 8, "board", "b");
    for (const [x, y, w, h, m] of [[9, 11, 9, 11, "paper"], [20, 12, 8, 9, "paper"], [30, 10, 9, 12, "magic"], [11, 24, 10, 11, "paper"], [24, 23, 13, 12, "paper"]]) {
      b.rect(x, y, w, h, m, "n");
      if (m === "magic") for (let k = 0; k < 5; k++) glow.push([x + k * 2, y - 1, "#bfe6ff"]);
    }
  } else { // 18: a puddle with a reflection
    pal.stone = ramp(220, 0.08, 0.38); pal.water = ramp(205, 0.5, 0.42); pal.shine = ramp(270, 0.4, 0.7);
    for (let y = 30; y < 46; y += 4) for (let x = (y / 4) % 2 ? 0 : 4; x < 48; x += 8) b.rect(x, y, 7, 3, "stone", "s");
    b.ellipse(24, 36, 17, 7, "water", "w");
    b.ellipse(24, 34, 4, 4, "shine", "r"); b.rect(22, 37, 5, 4, "shine", "r");
    glow.push([22, 33, "#ffffff"], [27, 35, "#ffffff"]);
  }
  return toImage(b, pal, { glowPx: glow });
}

// --- potions, charms and cosmetics ------------------------------------------------------------------
const BACKDROP = { shrine: [265, 0.4], forest: [130, 0.5], pass: [210, 0.25], library: [35, 0.45], ruins: [40, 0.6], citadel: [195, 0.5], harbor: [20, 0.55], tavern: [25, 0.6] };
const DYE = { crimson: [355, 0.75], midnight: [228, 0.6], forest: [135, 0.5], ivory: [45, 0.25], violet: [275, 0.6], ash: [220, 0.06] };
const FRAME = { silver: "silver", gold: "gold", moon: "crystal", thorn: null, dragon: "ivory" };

/** 24x24 icon for a consumable id (elixir, ...) or a cosmetic id (bg_forest, dye_crimson, ...). */
export function trinketArt(id) {
  return memo(`trinket|${id}`, () => {
    const b = new Buf(24, 24);
    const pal = { default: ["#222", "#444", "#666", "#888"], glass: ["#7d8fa6", "#a9bbd0", "#d6e3f0", "#ffffff"], cork: WOOD[1] };
    const glow = [];
    const flask = (liq, round) => {
      pal.liq = liq;
      b.rect(10, 3, 4, 2, "cork", "c"); b.rect(10, 5, 4, 4, "glass", "g");
      if (round) b.ellipse(11.5, 14.5, 7, 7, "glass", "g"); else b.poly([[9, 9], [14, 9], [19, 20], [4, 20]], "glass", "g");
      if (round) b.ellipse(11.5, 15.5, 5.5, 5, "liq", "l"); else b.poly([[8, 13], [15, 13], [18, 19], [5, 19]], "liq", "l");
      glow.push([9, 14, "#ffffff"]);
    };
    const [kind, val] = id.includes("_") && !["greater_elixir", "bane_oil", "lucky_charm", "shield_charm"].includes(id) ? id.split(/_(.+)/) : [id, null];
    switch (kind) {
      case "elixir": flask(ramp(205, 0.85, 0.55), false); break;
      case "greater_elixir": flask(ramp(280, 0.8, 0.55), true); break;
      case "bane_oil": flask(ramp(352, 0.7, 0.35), false); pal.liq2 = ramp(352, 0.8, 0.5); b.set(11, 22, "liq2", "d", 2); b.set(11, 23, "liq2", "d", 1); break;
      case "tonic": flask(ramp({ steps: 130, floors: 25, sleep: 265, hydration: 190, bedtime: 235 }[val] ?? 160, 0.75, 0.55), true); break;
      case "crate":
        pal.wood = WOOD[1]; pal.band = WOOD[0];
        b.rect(4, 7, 16, 13, "wood", "w"); b.rect(4, 7, 16, 2, "band", "b"); b.rect(4, 18, 16, 2, "band", "b");
        b.line(4, 9, 19, 18, "band", "x", 1); b.line(19, 9, 4, 18, "band", "x", 1); break;
      case "lucky_charm":
        pal.leaf = ramp(130, 0.6, 0.45);
        for (const [x, y] of [[8, 7], [15, 7], [8, 14], [15, 14]]) b.ellipse(x, y, 3.4, 3.4, "leaf", "l");
        b.line(11, 16, 13, 22, "leaf", "s", 0); break;
      case "reroll":
        pal.paper = ["#b8a77e", "#d3c398", "#eadcb4", "#fff6d8"]; pal.seal = ramp(355, 0.7, 0.45);
        b.rect(5, 6, 14, 13, "paper", "p"); b.rect(3, 4, 18, 3, "paper", "r"); b.rect(3, 17, 18, 3, "paper", "r");
        b.ellipse(12, 15, 2.4, 2.4, "seal", "s"); for (let y = 9; y < 14; y += 2) b.line(7, y, 16, y, "seal", "t", 1); break;
      case "hourglass":
        pal.frame = WOOD[0]; pal.sand = ramp(42, 0.7, 0.62);
        b.rect(5, 2, 14, 2, "frame", "f"); b.rect(5, 20, 14, 2, "frame", "f");
        b.poly([[7, 4], [17, 4], [13, 12], [11, 12]], "glass", "g"); b.poly([[11, 12], [13, 12], [17, 20], [7, 20]], "glass", "g");
        b.poly([[10, 16], [14, 16], [16, 19], [8, 19]], "sand", "s"); b.line(12, 12, 12, 16, "sand", "s"); break;
      case "shield_charm":
        pal.m = METALS.silver; pal.gem = ramp(200, 0.8, 0.6);
        b.poly([[5, 4], [19, 4], [19, 12], [12, 21], [5, 12]], "m", "s"); b.ellipse(12, 10, 2.5, 2.5, "gem", "g"); glow.push([12, 9, "#e0f4ff"]); break;
      case "phoenix":
        pal.f1 = ramp(15, 0.9, 0.55); pal.f2 = ramp(42, 0.95, 0.6);
        b.poly([[18, 2], [21, 5], [8, 20], [5, 19]], "f1", "f"); b.poly([[18, 2], [14, 4], [6, 16], [8, 18]], "f2", "f");
        b.line(5, 19, 2, 22, "f1", "q", 0); for (const p of [[17, 4], [12, 10], [8, 15]]) glow.push([...p, "#fff1b8"]); break;
      case "bg": {
        const [h, sat] = BACKDROP[val] || [210, 0.3];
        pal.sky = ramp(h, sat * 0.6, 0.5); pal.land = ramp(h + 20, sat, 0.32); pal.sun = ramp(45, 0.9, 0.7);
        b.rect(2, 2, 20, 20, "sky", "s"); b.poly([[2, 22], [2, 14], [8, 8], [13, 14], [17, 10], [22, 16], [22, 22]], "land", "l");
        b.ellipse(17, 6, 2, 2, "sun", "u"); break;
      }
      case "pose":
        pal.fig = ramp(200, 0.4, 0.65);
        b.ellipse(12, 5, 2.5, 2.5, "fig", "h"); b.rect(11, 8, 3, 7, "fig", "b");
        b.line(11, 15, 8, 21, "fig", "l"); b.line(13, 15, 16, 21, "fig", "l");
        b.line(11, 9, 6, val === "triumph" || val === "casting" ? 3 : 13, "fig", "a"); b.line(13, 9, 18, val === "rest" ? 13 : 5, "fig", "a"); break;
      case "dye": {
        const [h, sat] = DYE[val] || [0, 0.5];
        pal.pot = METALS.iron; pal.dye = ramp(h, sat, 0.5);
        b.poly([[4, 9], [20, 9], [18, 21], [6, 21]], "pot", "p"); b.ellipse(12, 9, 8, 2.5, "dye", "d");
        b.line(14, 3, 17, 10, "cork", "s", 2); break;
      }
      case "frame": {
        const metal = FRAME[val];
        pal.fr = metal ? METALS[metal] : ramp(110, 0.4, 0.3); pal.in = ramp(220, 0.2, 0.25);
        b.rect(3, 3, 18, 18, "fr", "f"); b.rect(6, 6, 12, 12, "in", "i");
        if (val === "thorn") for (const [x, y] of [[3, 8], [20, 14], [9, 3], [14, 20]]) b.set(x, y, "fr", "t", 0);
        if (val === "moon") glow.push([4, 4, "#e9e2ff"], [19, 19, "#e9e2ff"]); break;
      }
      default: b.ellipse(12, 12, 6, 6, "glass", "g");
    }
    return toImage(b, pal, { glowPx: glow });
  });
}
