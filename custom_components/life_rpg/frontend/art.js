/* Life RPG art: the pixel art for adventurers (a paper doll wearing their gear), item icons and monsters.
 * Everything is generated from a seed, so every adventurer and every item looks different
 * and always looks the same on every screen. Pure functions; returns PNG data URLs.
 * The adventurer's traits (skin, hair, eyes, build...) come from the engine's appearance.py, so the
 * pixel art and the paintings agree. */

// ------------------------------------------------------------------ seeded random
// Both adapted from public-domain code collected by bryc (github.com/bryc/code, jshash/PRNGs.md).
/** A 32-bit string hash (xmur3's mixing step), never 0: the seed for everything drawn from a name. */
export function hash(str) {
  let h = 1779033703 ^ str.length;
  for (let i = 0; i < str.length; i++) {
    h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return (h >>> 0) || 1;
}
/** A seeded random generator (mulberry32) with int, pick and chance helpers: same seed, same sequence. */
/** mulberry32: a small seeded random generator with int, pick and chance helpers. Same seed, same sequence. */
export function rng(seed) {
  let a = typeof seed === "number" ? seed >>> 0 : hash(String(seed));
  const r = () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  r.int = (lo, hi) => lo + Math.floor(r() * (hi - lo + 1));
  r.pick = (arr) => arr[Math.floor(r() * arr.length)];
  r.chance = (p) => r() < p;
  return r;
}

// ------------------------------------------------------------------ color
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
// HSL (0-360, 0-1, 0-1) to a #rrggbb colour.
function hsl2hex(h, s, l) {
  h = ((h % 360) + 360) % 360; s = clamp(s, 0, 1); l = clamp(l, 0, 1);
  const k = (n) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return "#" + [f(0), f(8), f(4)].map((x) => Math.round(x * 255).toString(16).padStart(2, "0")).join("");
}
const toward = (h, target, maxDeg) => { const d = ((target - h + 540) % 360) - 180; return h + clamp(d, -maxDeg, maxDeg); };
/** 4-step ramp, dark to light, hue-shifted the way pixel artists do (cool shadows, warm lights). */
export function ramp(h, s, l) {
  return [
    hsl2hex(toward(h, 250, 14), s * 0.85, l - 0.27),
    hsl2hex(toward(h, 250, 7), s * 0.95, l - 0.13),
    hsl2hex(h, s, l),
    hsl2hex(toward(h, 55, 8), s * 0.9, l + 0.13),
  ];
}
const R = (h, s, l) => ramp(h, s, l);
/** Mythic material: the hue drifts across the sprite. */
export function prism(h0, s, l) {
  const cache = {};
  return (x, y) => { const h = Math.round((h0 + x * 9 + y * 5) / 15) * 15; return (cache[h] = cache[h] || ramp(h, s, l)); };
}

// Palettes: each entry is a 4-step ramp from ramp(); the engine's appearance indexes pick one.
export const SKIN = {
  human: [R(30, .55, .8), R(27, .5, .7), R(24, .45, .6), R(20, .42, .48), R(18, .4, .38), R(15, .38, .3)],
  elf: [R(32, .45, .84), R(28, .4, .74), R(205, .22, .82), R(270, .16, .7), R(22, .35, .55)],
  dwarf: [R(14, .5, .66), R(22, .45, .58), R(18, .4, .46), R(25, .35, .72)],
  beastkin: [R(30, .5, .78), R(25, .45, .64), R(20, .4, .5), R(18, .38, .38)],
  dragonkin: [R(145, .45, .45), R(172, .5, .44), R(355, .55, .46), R(250, .2, .3), R(45, .65, .55), R(212, .55, .5), R(285, .4, .45)],
};
export const HAIR = [R(25, .3, .18), R(25, .45, .3), R(15, .6, .38), R(40, .7, .62), R(45, .25, .85), R(210, .08, .7),
  R(2, .7, .45), R(215, .6, .45), R(150, .45, .38), R(330, .55, .65), R(275, .45, .45), R(0, 0, .92)];
export const FUR = [R(25, .75, .5), R(0, 0, .9), R(210, .06, .55), R(25, .25, .2), R(30, .5, .35), R(42, .65, .6)];
const EYES = [R(210, .7, .5), R(130, .55, .45), R(30, .6, .35), R(280, .5, .55), R(180, .6, .45), R(0, .0, .25)];
const METALS = {
  iron: R(210, .07, .46), steel: R(212, .12, .62), bronze: R(30, .55, .46), silver: R(215, .1, .76),
  mithril: R(193, .38, .7), obsidian: R(262, .3, .24), gold: R(44, .85, .56), ivory: R(40, .35, .84),
  crystal: R(188, .75, .74), bloodsteel: R(352, .55, .42), jade: R(155, .45, .5),
};
const LEATHER = [R(25, .45, .36), R(20, .3, .26), R(32, .4, .46), R(10, .35, .3)];
const WOOD = [R(28, .45, .32), R(35, .35, .45), R(20, .3, .22)];

// what each rarity is made of
const RARITY_STYLE = {
  common: { metals: ["iron", "iron", "bronze"], sat: [.12, .28], lum: [.32, .5], trim: null, gem: false },
  uncommon: { metals: ["steel", "bronze", "iron"], sat: [.35, .5], lum: [.38, .52], trim: "bronze", gem: false },
  rare: { metals: ["silver", "mithril", "steel"], sat: [.45, .62], lum: [.38, .55], trim: "silver", gem: true },
  epic: { metals: ["obsidian", "mithril", "bloodsteel", "jade"], sat: [.5, .7], lum: [.3, .45], trim: "gold", gem: true },
  legendary: { metals: ["gold", "ivory", "obsidian", "mithril"], sat: [.6, .78], lum: [.32, .48], trim: "gold", gem: true },
  mythic: { metals: ["crystal", "ivory", "gold"], sat: [.7, .85], lum: [.45, .6], trim: "crystal", gem: true },
};
export const RARITY_GLOW = { common: null, uncommon: null, rare: "#45b8ff", epic: "#b072ff", legendary: "#ffa640", mythic: "#ff4d6d" };

// ------------------------------------------------------------------ pixel buffer
class Buf {
  constructor(w, h) { this.w = w; this.h = h; this.m = new Array(w * h).fill(null); this.r = new Array(w * h).fill(null); this.t = new Array(w * h).fill(null); }
  in(x, y) { return x >= 0 && y >= 0 && x < this.w && y < this.h; }
  set(x, y, mat, reg = undefined, tone = null) {
    x = Math.round(x); y = Math.round(y);
    if (!this.in(x, y)) return;
    const i = y * this.w + x;
    this.m[i] = mat; this.t[i] = tone;
    if (reg !== undefined) this.r[i] = reg;
  }
  mat(x, y) { return this.in(x, y) ? this.m[y * this.w + x] : null; }
  reg(x, y) { return this.in(x, y) ? this.r[y * this.w + x] : null; }
  rect(x, y, w, h, mat, reg) { for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) this.set(x + i, y + j, mat, reg); }
  line(x0, y0, x1, y1, mat, reg, tone = null) {
    x0 = Math.round(x0); y0 = Math.round(y0); x1 = Math.round(x1); y1 = Math.round(y1);
    const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
    let err = dx + dy;
    for (;;) {
      this.set(x0, y0, mat, reg, tone);
      if (x0 === x1 && y0 === y1) break;
      const e2 = 2 * err;
      if (e2 >= dy) { err += dy; x0 += sx; }
      if (e2 <= dx) { err += dx; y0 += sy; }
    }
  }
  ellipse(cx, cy, rx, ry, mat, reg) {
    for (let y = Math.floor(cy - ry); y <= Math.ceil(cy + ry); y++)
      for (let x = Math.floor(cx - rx); x <= Math.ceil(cx + rx); x++)
        if (((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0) this.set(x, y, mat, reg);
  }
  poly(points, mat, reg) { // scanline fill
    const ys = points.map((p) => p[1]);
    for (let y = Math.floor(Math.min(...ys)); y <= Math.ceil(Math.max(...ys)); y++) {
      const xs = [];
      for (let i = 0; i < points.length; i++) {
        const [ax, ay] = points[i], [bx, by] = points[(i + 1) % points.length];
        if ((ay <= y && by > y) || (by <= y && ay > y)) xs.push(ax + ((y - ay) / (by - ay)) * (bx - ax));
      }
      xs.sort((a, b) => a - b);
      for (let k = 0; k + 1 < xs.length; k += 2) for (let x = Math.round(xs[k]); x <= Math.round(xs[k + 1]); x++) this.set(x, y, mat, reg);
    }
  }
  /** repaint pixels in `regs` with mat (keeps region labels) */
  recolor(regs, mat, test = () => true) {
    for (let y = 0; y < this.h; y++) for (let x = 0; x < this.w; x++) {
      const i = y * this.w + x;
      if (this.m[i] && regs.includes(this.r[i]) && test(x, y)) { this.m[i] = mat; this.t[i] = null; }
    }
  }
  bbox(regs) {
    let x0 = 1e9, y0 = 1e9, x1 = -1, y1 = -1;
    for (let y = 0; y < this.h; y++) for (let x = 0; x < this.w; x++) if (this.m[y * this.w + x] && regs.includes(this.r[y * this.w + x])) {
      x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
    }
    return { x0, y0, x1, y1 };
  }
}

/** Shade by neighbours (light from top-left), add coloured outlines, return a data URL. */
function toImage(buf, pal, { outline = true, glowPx = [], halo = null } = {}) {
  const { w, h } = buf;
  const out = new Uint8ClampedArray(w * h * 4);
  const hex = (c, i) => { out[i] = parseInt(c.slice(1, 3), 16); out[i + 1] = parseInt(c.slice(3, 5), 16); out[i + 2] = parseInt(c.slice(5, 7), 16); out[i + 3] = 255; };
  // per material row extents, for the broad left-lit / right-shadow pass
  for (let y = 0; y < h; y++) {
    const ext = {};
    for (let x = 0; x < w; x++) { const m = buf.m[y * w + x]; if (m) { ext[m] = ext[m] || [x, x]; ext[m][1] = x; } }
    for (let x = 0; x < w; x++) {
      const i = y * w + x, m = buf.m[i];
      if (!m) continue;
      let rmp = pal[m] || pal.default;
      if (typeof rmp === "function") rmp = rmp(x, y);
      let tone = buf.t[i];
      if (tone == null) {
        const dn = buf.mat(x, y + 1) !== m, rt = buf.mat(x + 1, y) !== m, up = buf.mat(x, y - 1) !== m, lf = buf.mat(x - 1, y) !== m;
        tone = 2;
        if ((up || lf) && !dn && !rt) tone = 3;
        if (dn || rt) tone = 1;
        if (dn && rt) tone = 0;
        const [a, b] = ext[m], span = b - a;
        if (span >= 4 && x > a + span * 0.72 && tone > 0) tone -= 1;
        if (span >= 4 && x < a + span * 0.2 && tone === 2) tone = 3;
      }
      hex(rmp[clamp(tone, 0, 3)], i * 4);
    }
  }
  if (outline) {
    const src = out.slice();
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = y * w + x;
      if (buf.m[i]) continue;
      const n = [[1, 0], [-1, 0], [0, 1], [0, -1]].map(([dx, dy]) => buf.mat(x + dx, y + dy)).find(Boolean);
      if (!n) continue;
      let rmp = pal[n] || pal.default;
      if (typeof rmp === "function") rmp = rmp(x, y);
      const c = rmp[0];
      const r = parseInt(c.slice(1, 3), 16), g = parseInt(c.slice(3, 5), 16), b = parseInt(c.slice(5, 7), 16);
      out[i * 4] = r * 0.35 + 8; out[i * 4 + 1] = g * 0.35 + 6; out[i * 4 + 2] = b * 0.35 + 18; out[i * 4 + 3] = 255;
    }
    void src;
  }
  if (halo) { // a soft glow baked into the picture (a CSS filter on an animated image leaves ghosts in some browsers)
    const solid = (x, y) => x >= 0 && y >= 0 && x < w && y < h && out[(y * w + x) * 4 + 3] === 255;
    const [hr, hg, hb] = [1, 3, 5].map((i) => parseInt(halo.slice(i, i + 2), 16));
    const fade = [0, 120, 60, 24];
    const add = [];
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      if (out[(y * w + x) * 4 + 3]) continue;
      for (let d = 1; d <= 3; d++) {
        let near = false;
        for (let dy = -d; dy <= d && !near; dy++) for (let dx = -d; dx <= d && !near; dx++) near = solid(x + dx, y + dy);
        if (near) { add.push([(y * w + x) * 4, fade[d]]); break; }
      }
    }
    for (const [i, a] of add) { out[i] = hr; out[i + 1] = hg; out[i + 2] = hb; out[i + 3] = a; }
  }
  for (const [x, y, c] of glowPx) if (buf.in(x, y)) hex(c, (y * w + x) * 4);  // sparkles after the halo, so they stay specks
  const cv = document.createElement("canvas");
  cv.width = w; cv.height = h;
  cv.getContext("2d").putImageData(new ImageData(out, w, h), 0, 0);
  return cv.toDataURL();
}

// ------------------------------------------------------------------ adventurers
const BUILD = { // head w/h, shoulders, waist, torso h, leg h, arm w, leg w (widths even: the body is symmetric about x = 31.5)
  human: { hw: 12, hh: 12, sh: 16, wa: 12, th: 13, lh: 14, aw: 3, lw: 4 },
  elf: { hw: 12, hh: 12, sh: 14, wa: 10, th: 14, lh: 17, aw: 3, lw: 3 },
  dwarf: { hw: 14, hh: 12, sh: 20, wa: 16, th: 12, lh: 8, aw: 4, lw: 5 },
  beastkin: { hw: 12, hh: 12, sh: 14, wa: 10, th: 13, lh: 15, aw: 3, lw: 4 },
  dragonkin: { hw: 12, hh: 12, sh: 18, wa: 12, th: 14, lh: 15, aw: 4, lw: 4 },
};
const HAIRSTYLES = {
  human: ["short", "spiky", "long", "ponytail", "bob", "swept"],
  elf: ["long", "long", "braid", "ponytail", "swept"],
  dwarf: ["short", "bald", "swept", "braid", "spiky"],
  beastkin: ["short", "spiky", "bob", "long", "swept"],
  dragonkin: ["spiky", "short", "swept", "long", "bald"],
};

/** Stable look for an adventurer. `app` (from the game engine) decides the traits, so the pixel art
 * matches the painted portrait; without it the look is rolled from the seed. */
export function lookFor(race, seed, app = null) {
  const r = rng(`look:${race}:${seed}`);
  const b = { ...BUILD[race] || BUILD.human };
  if (app) {
    const skins = SKIN[race] || SKIN.human, at = (arr, i) => arr[((i % arr.length) + arr.length) % arr.length];
    b.sh += app.build[0]; b.lh += app.build[1]; b.th += app.build[2];
    return {
      race, build: b, skin: at(skins, app.skin), hair: at(HAIR, app.hair), eyes: at(EYES, app.eyes), fur: at(FUR, app.fur),
      hairstyle: app.hairstyle, ears: app.ears, tail: app.tail, horns: app.horns, wings: app.wings, beard: app.beard,
      shirt: ramp(app.shirt_hue, 0.28, 0.42), pants: ramp(220, 0.15, 0.3), blush: app.blush, scar: app.scar,
    };
  }
  b.sh += 2 * r.int(-1, 1); b.lh += r.int(-1, 1); b.th += r.int(-1, 0);
  return {
    race, build: b,
    skin: r.pick(SKIN[race] || SKIN.human), hair: r.pick(HAIR), eyes: r.pick(EYES), fur: r.pick(FUR),
    hairstyle: r.pick(HAIRSTYLES[race] || HAIRSTYLES.human),
    ears: r.pick(["fox", "cat", "wolf", "rabbit", "bear"]), tail: r.pick(["fluffy", "thin", "bushy"]),
    horns: r.pick(["swept", "ram", "spire", "crown"]), wings: r.chance(0.7), beard: r.pick(["long", "braided", "forked", "full"]),
    shirt: ramp(r.int(0, 359), 0.18 + r() * 0.2, 0.42), pants: ramp(r.int(180, 260), 0.15, 0.3), blush: r.chance(0.35),
    scar: r.chance(0.15),
  };
}

// The paper doll's canvas: 64x84 pixels, centred on x = 32, feet on row 79.
const W = 64, H = 84, CX = 32, FOOT = 79;

/** Legs, torso, arms, neck and head for a look's build. */
function drawBody(b, L) {
  const p = L.build;
  const hipY = FOOT - 2 - p.lh, shY = hipY - p.th, headBot = shY - 2, headTop = headBot - p.hh + 1;
  const hl = 32 - p.hw / 2, hr = 31 + p.hw / 2;
  const A = { hipY, shY, headTop, headBot, hl, hr, eyeY: headTop + Math.round(p.hh * 0.58) };
  // legs (with a seam) and feet
  for (const [lx, side] of [[31 - p.lw, -1], [33, 1]]) {
    b.rect(lx, hipY, p.lw, p.lh, "pants", "leg");
    b.rect(side < 0 ? lx - 1 : lx, FOOT - 2, p.lw + 1, 3, "shoe", "foot");
  }
  b.rect(31 - p.lw, hipY, 2 * p.lw + 2, 2, "pants", "hip");
  // torso: shoulders taper to waist, flare a little at the hips
  for (let y = shY; y < hipY; y++) {
    const t = (y - shY) / (hipY - shY);
    let w = 2 * Math.round((p.sh + (p.wa - p.sh) * Math.min(t / 0.75, 1)) / 2);
    if (t > 0.85) w = p.wa + 2;
    if (y === shY) w -= 4;
    b.rect(32 - w / 2, y, w, 1, "shirt", "torso");
  }
  // collar
  b.rect(30, shY, 4, 1, "skin", "neck");
  b.set(30, shY + 1, "skin", "neck"); b.set(33, shY + 1, "skin", "neck");
  // arms hang slightly away from the body, hands at the hips
  const handY = hipY + 1;
  for (const side of [-1, 1]) {
    const x0 = side < 0 ? 32 - p.sh / 2 - p.aw : 32 + p.sh / 2;
    for (let y = shY + 1; y <= handY; y++) {
      const drift = y > shY + p.th * 0.5 ? side : 0;
      const reg = y <= shY + Math.round(p.th * 0.5) ? "armU" : "armL";
      b.rect(x0 + drift, y, p.aw, 1, "shirt", reg);
    }
    b.rect(x0 + side, handY + 1, p.aw, 3, "skin", "hand");
    A[side < 0 ? "handL" : "handR"] = [x0 + side + Math.floor(p.aw / 2), handY + 2];
  }
  // neck + head with rounded corners
  b.rect(30, headBot + 1, 4, 2, "skin", "neck");
  for (let y = headTop; y <= headBot; y++) {
    const k = y - headTop, kb = headBot - y;
    const cut = k === 0 ? 3 : k === 1 ? 1 : kb === 0 ? 3 : kb === 1 ? 1 : 0;
    b.rect(hl + cut, y, p.hw - 2 * cut, 1, "skin", "head");
  }
  b.set(hl - 1, A.eyeY + 1, "skin", "head"); b.set(hr + 1, A.eyeY + 1, "skin", "head"); // ears
  b.set(hl - 1, A.eyeY, "skin", "head"); b.set(hr + 1, A.eyeY, "skin", "head");
  return A;
}

/** The eyes, in the look's eye colour. */
function drawEyes(b, L, A) {
  const y = A.eyeY;
  for (const x of [28, 34]) { // big 2x3 eyes: lash, iris, shine
    b.set(x, y - 2, "lash", "face", 0); b.set(x + 1, y - 2, "lash", "face", 0);
    b.set(x, y - 1, "iris", "face", 2); b.set(x + 1, y - 1, "iris", "face", 1);
    b.set(x, y, "iris", "face", 1); b.set(x + 1, y, "iris", "face", 0);
    b.set(x + (x < 31 ? 0 : 1), y - 1, "white", "face", 3);
    if (L.race === "dragonkin") { b.set(x + (x < 31 ? 1 : 0), y - 1, "iris", "face", 0); b.set(x + (x < 31 ? 1 : 0), y, "iris", "face", 0); }
  }
  b.set(31, y + 3, "mouth", "face", 1); b.set(32, y + 3, "mouth", "face", 1);
}
/** Eyes, nose shading and the face's extras (blush, scar, dragonkin scales). */
function drawFace(b, L, A) {
  drawEyes(b, L, A);
  const y = A.eyeY;
  b.set(31, y + 1, "skin", "face", 1); // nose shade
  if (L.blush) { b.set(27, y + 2, "blush", "face", 2); b.set(36, y + 2, "blush", "face", 2); }
  if (L.scar) b.line(35, y - 3, 36, y + 1, "skin", "face", 0);
  if (L.race === "dragonkin") for (const [x, dy] of [[26, 1], [26, 2], [27, 3], [37, 1], [37, 2], [36, 3]]) b.set(x, y + dy, "skin", "face", 1);
}

function blob(b, pts, radii, mat, reg) { // thick stroke along a polyline with varying radius
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1], steps = Math.max(Math.abs(bx - ax), Math.abs(by - ay)) * 2 + 1;
    for (let k = 0; k <= steps; k++) {
      const t = k / steps, x = ax + (bx - ax) * t, y = ay + (by - ay) * t;
      const rr = radii[i] + (radii[i + 1] - radii[i]) * t;
      b.ellipse(x, y, Math.max(rr, 0.5), Math.max(rr, 0.5), mat, reg);
    }
  }
}
function curve(p0, p1, p2, n = 8) { // quadratic bezier sample
  return Array.from({ length: n + 1 }, (_, i) => { const t = i / n, u = 1 - t; return [u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0], u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]]; });
}

/** The hair that falls behind the head (drawn before the body). */
function drawHairBack(b, L, A) {
  const s = L.hairstyle;
  if (s === "long" || s === "braid") {
    const len = s === "long" ? A.shY + 10 : A.shY + 4;
    for (let y = A.headTop + 2; y < len; y++) { const inset = y > A.shY + 6 ? 1 : 0; b.rect(A.hl - 2 + inset, y, A.hr - A.hl + 5 - 2 * inset, 1, "hair", "hairB"); }
    for (let y = A.headTop + 4; y < len; y += 1) if (y % 3 === 0) { b.set(A.hl - 1, y, "hair", "hairB", 1); b.set(A.hr + 1, y, "hair", "hairB", 1); }
  }
  if (s === "ponytail") blob(b, curve([A.hr, A.headTop + 3], [A.hr + 7, A.headTop + 4], [A.hr + 5, A.shY + 8]), [2.2, 2.5, 2, 1.8, 1.6, 1.4, 1.2, 1, .8], "hair", "hairB");
  if (s === "braid") for (let i = 0; i < 6; i++) { b.ellipse(A.hr + 2, A.shY + 1 + i * 3, 1.6, 1.4, "hair", "hairB"); b.set(A.hr + 2, A.shY + 2 + i * 3, "hair", "hairB", 0); }
}
/** Fringe and the hair over the head, with a shine. */
function drawHairFront(b, L, A, r) {
  const s = L.hairstyle, top = A.headTop - 1, l = A.hl - 1, rr = A.hr + 1;
  if (s === "bald") { b.line(A.hl + 2, A.headTop + 1, A.hl + 4, A.headTop, "skin", "head", 3); return; }
  b.rect(l + 2, top - 1, rr - l - 3, 1, "hair", "hair");
  b.rect(l, top, rr - l + 1, 3, "hair", "hair");
  const sideDown = { bob: A.headBot - 1, long: A.shY + 3, braid: A.eyeY + 3, short: A.eyeY - 2, spiky: A.eyeY - 1, swept: A.eyeY, ponytail: A.eyeY - 1 }[s] ?? A.eyeY;
  b.rect(l, top + 2, 2, sideDown - top - 1, "hair", "hair");
  b.rect(rr - 1, top + 2, 2, sideDown - top - 1, "hair", "hair");
  // fringe
  for (let x = A.hl + 1; x <= A.hr - 1; x++) {
    let d;
    if (s === "swept") d = x < 31 ? 3 : x < 34 ? 2 : 1;
    else if (s === "bob") d = 2;
    else if (s === "spiky") d = x % 3 === 0 ? 2 : 1;
    else if (s === "long" || s === "braid") d = x === 31 || x === 32 ? 0 : x % 2 ? 2 : 1;
    else d = x % 2 ? 1 : 2;
    for (let k = 0; k < d; k++) b.set(x, top + 3 + k, "hair", "hair", k === d - 1 ? 1 : null);
  }
  if (s === "spiky") for (let i = 0; i < 5; i++) {
    const x = A.hl + 1 + i * 2 + r.int(0, 1), hgt = r.int(2, 4), dir = i < 2 ? -1 : i > 2 ? 1 : 0;
    b.poly([[x - 1, top + 1], [x + 1, top + 1], [x + dir * 2, top - hgt]], "hair", "hair");
  }
  if (s === "swept") b.poly([[rr - 1, top], [rr + 3, top + 3], [rr, top + 4]], "hair", "hair");
  if (s === "braid") for (let y = A.eyeY; y < A.shY + 6; y += 2) { b.rect(A.hl - 2, y, 2, 2, "hair", "hair"); b.set(A.hl - 2, y, "hair", "hair", 1); }
  // shine
  b.line(A.hl + 1, top + 1, A.hl + 3, top, "hair", "hair", 3);
  b.set(A.hl + 5, top, "hair", "hair", 3);
}

/** Race parts behind the body (tails, dragonkin wings). */
function drawRaceBack(b, L, A) {
  if (L.race === "dragonkin" && L.wings) for (const s of [-1, 1]) {
    const ox = s < 0 ? 28 : 35, y = A.shY + 1, P = (dx, dy) => [ox + s * dx, y + dy];
    b.poly([P(0, 0), P(10, -12), P(16, -9), P(15, -1), P(12, -2), P(12, 4), P(8, 2), P(7, 7), P(3, 4)], "wing", "wing");
    b.line(...P(0, 0), ...P(10, -12), "bone", "wing"); b.line(...P(10, -12), ...P(16, -9), "bone", "wing");
    b.line(...P(9, -11), ...P(15, -1), "bone", "wing", 1); b.line(...P(8, -10), ...P(12, 4), "bone", "wing", 1); b.line(...P(6, -7), ...P(7, 7), "bone", "wing", 1);
  }
  if (L.race === "dragonkin") {
    const pts = curve([33, A.hipY], [44, FOOT + 1], [56, FOOT - 6], 10);
    blob(b, pts, pts.map((_, i) => 3.2 - i * 0.26), "skin", "tail");
    for (let i = 2; i < pts.length - 1; i += 2) b.set(Math.round(pts[i][0]), Math.round(pts[i][1]) - 3 + (i > 6 ? 1 : 0), "horn", "tail");
  }
  if (L.race === "beastkin") {
    const t = L.tail;
    const pts = t === "thin" ? curve([34, A.hipY], [48, A.hipY + 4], [45, A.hipY - 12], 10) : curve([34, A.hipY], [49, A.hipY + 2], [46, A.hipY - 12], 8);
    const radii = t === "fluffy" ? pts.map((_, i) => 1.5 + Math.sin((i / (pts.length - 1)) * Math.PI) * 3) : t === "bushy" ? pts.map((_, i) => 2.5 + i * 0.25) : pts.map(() => 1);
    blob(b, pts, radii, "fur", "tail");
    if (t === "fluffy") { const [ex, ey] = pts[pts.length - 1]; b.ellipse(ex, ey + 1, 1.8, 1.4, "furtip", "tail"); }
  }
}
/** Race parts in front of the head (elf ears, beastkin ears, dragonkin horns). */
function drawRaceFront(b, L, A) {
  if (L.race === "elf") for (const s of [-1, 1]) {
    const x = s < 0 ? A.hl - 1 : A.hr + 1;
    b.poly([[x, A.eyeY - 1], [x, A.eyeY + 2], [x + s * 6, A.eyeY - 4]], "skin", "ear");
    b.line(x, A.eyeY, x + s * 4, A.eyeY - 2, "skin", "ear", 1);
  }
  if (L.race === "beastkin") {
    const e = L.ears, top = A.headTop - 1;
    const tall = { fox: 7, cat: 5, wolf: 6, rabbit: 10, bear: 3 }[e];
    for (const s of [-1, 1]) {
      const bx = s < 0 ? A.hl + 2 : A.hr - 2;
      if (e === "bear") { b.ellipse(bx, top - 1, 2.6, 2.6, "fur", "ear"); b.ellipse(bx, top - 1, 1, 1, "inner", "ear"); continue; }
      const w = e === "rabbit" ? 2 : 3, lean = e === "wolf" || e === "fox" ? s * 2 : 0;
      b.poly([[bx - w, top + 1], [bx + w, top + 1], [bx + lean, top - tall]], "fur", "ear");
      b.poly([[bx - w + 2, top], [bx + w - 2, top], [bx + lean * 0.7, top - tall + 3]], "inner", "ear");
      if (e === "fox") b.set(bx + lean, top - tall + 1, "furtip", "ear");
    }
  }
  if (L.race === "dragonkin") {
    const top = A.headTop + 1;
    for (const s of [-1, 1]) {
      const bx = s < 0 ? A.hl + 1 : A.hr - 1, P = (dx, dy) => [bx + s * dx, top + dy];
      if (L.horns === "swept") blob(b, [P(0, 0), P(3, -4), P(8, -6), P(11, -5)], [1.6, 1.3, .9, .5], "horn", "horn");
      if (L.horns === "ram") { blob(b, [P(0, 0), P(3, -3), P(6, -1), P(6, 3), P(3, 4)], [1.6, 1.5, 1.3, 1.1, .8], "horn", "horn"); }
      if (L.horns === "spire") blob(b, [P(0, 0), P(1, -6), P(1, -10)], [1.4, 1, .5], "horn", "horn");
      if (L.horns === "crown") for (let i = 0; i < 3; i++) blob(b, [P(i * 2, 0), P(i * 2 + 1, -3 - i)], [.9, .5], "horn", "horn");
    }
  }
}
/** A dwarf's beard (other races have none). */
function drawBeard(b, L, A) {
  if (L.race !== "dwarf") return;
  const y = A.eyeY + 2, x0 = A.hl, x1 = A.hr;
  const len = { long: 15, braided: 16, forked: 13, full: 10 }[L.beard];
  b.rect(x0, y, x1 - x0 + 1, 4, "hair", "beard");
  if (L.beard === "full") b.ellipse(31.5, y + 5, 8, 6, "hair", "beard");
  else b.poly([[x0, y + 3], [x1, y + 3], [34.5, y + len], [28.5, y + len]], "hair", "beard");
  if (L.beard === "forked") { b.rect(31, y + len - 4, 2, 5, null, "beard"); }
  if (L.beard === "braided") for (let k = 6; k < len; k += 3) b.rect(30, y + k, 4, 1, "trim", "beard");
  b.line(x0 + 1, y, 30, y, "hair", "beard", 3); b.line(33, y, x1 - 1, y, "hair", "beard", 3); // moustache
  b.set(31, y + 1, "mouth", "face", 1); b.set(32, y + 1, "mouth", "face", 1);
  for (let k = 4; k < len - 2; k += 3) b.set(29 + (k % 2) * 4, y + k, "hair", "beard", 1);
}

// ------------------------------------------------------------------ gear on the doll
function itemMats(item) {
  const r = rng(`item:${item.id}:${item.name}`);
  const st = RARITY_STYLE[item.rarity] || RARITY_STYLE.common;
  return {
    r, st,
    metal: METALS[r.pick(st.metals)], leather: r.pick(LEATHER), wood: r.pick(WOOD),
    cloth: item.rarity === "mythic" ? prism(r.int(0, 359), 0.7, 0.55) : ramp(r.int(0, 359), st.sat[0] + r() * (st.sat[1] - st.sat[0]), st.lum[0] + r() * (st.lum[1] - st.lum[0])),
    trim: st.trim ? METALS[st.trim] : null, gem: ramp(r.pick([0, 120, 200, 275, 45, 320, 170]), 0.8, 0.55),
  };
}
// The base type of an item: its own `base`, else read from its name, else the slot's default.
const baseOf = (item) => item.base || (item.name.match(/(Dagger|Shortsword|Spear|Warhammer|Staff|Longbow|Hood|Circlet|Helm|Crown|Tunic|Brigandine|Chainmail|Robe|Plate|Wraps|Gloves|Gauntlets|Bracers|Sandals|Boots|Greaves|Treads|Ring|Band|Signet|Amulet)/) || [])[1]
  || { weapon: "Shortsword", helm: "Helm", armor: "Tunic", gloves: "Gloves", boots: "Boots", ring: "Ring" }[item.slot];

/** Body armour over the torso and arms. */
function wearArmor(b, A, item, pal, key) {
  const M = itemMats(item), base = baseOf(item);
  pal[key] = base === "Chainmail" || base === "Plate" ? M.metal : base === "Brigandine" ? M.leather : M.cloth;
  pal[key + "2"] = base === "Brigandine" ? M.metal : M.trim || M.leather;
  const regs = base === "Tunic" ? ["torso", "armU"] : ["torso", "armU", "armL"];
  b.recolor(regs, key);
  const { x0, x1 } = b.bbox(["torso"]);
  if (base === "Tunic") for (let x = x0; x <= x1; x++) b.set(x, A.hipY - 3, key + "2", "torso", 1);
  if (base === "Tunic" && M.trim) b.set(CX, A.hipY - 3, "trimx", "torso", 3);
  if (base === "Robe") {
    b.recolor(["leg", "hip"], key, (x, y) => y < FOOT - 3);
    for (let y = A.hipY; y < FOOT - 3; y++) { b.set(x0 - 1 + (y > A.hipY + 4 ? -1 : 0) + 1, y, key, "robe"); b.set(x1 + (y > A.hipY + 4 ? 1 : 0), y, key, "robe"); for (let x = x0; x <= x1; x++) if (!b.mat(x, y) || b.reg(x, y) === "leg") b.set(x, y, key, "robe"); }
    for (let y = A.shY + 1; y < FOOT - 3; y++) b.set(CX, y, key + "2", "robe", 2);
    for (let x = x0 - 1; x <= x1 + 1; x++) b.set(x, FOOT - 4, key + "2", "robe", 1);
    for (let x = x0; x <= x1; x++) b.set(x, A.hipY - 2, key + "2", "torso", 2);
  }
  if (base === "Chainmail") for (let y = A.shY; y < A.hipY + 2; y++) for (let x = x0 - 4; x <= x1 + 4; x++)
    if (b.mat(x, y) === key && (x + y) % 2 === 0) b.set(x, y, key, b.reg(x, y), (y % 3 === 0) ? 1 : 2);
  if (base === "Brigandine") for (let y = A.shY + 2; y < A.hipY; y += 3) for (let x = x0 + 1; x < x1; x += 3) if (b.mat(x, y) === key) b.set(x, y, key + "2", "torso", 3);
  if (base === "Plate") {
    for (let y = A.shY + Math.round((A.hipY - A.shY) * 0.55); y < A.hipY; y += 2) for (let x = x0; x <= x1; x++) if (b.mat(x, y) === key) b.set(x, y, key, "torso", 1);
    for (let y = A.shY + 1; y < A.shY + 7; y++) b.set(CX, y, key, "torso", 3);
    for (const s of [-1, 1]) b.ellipse(s < 0 ? x0 - 1 : x1 + 1, A.shY + 2, 3, 2.4, key, "pauldron");
  }
  if (M.trim && base !== "Tunic") { // trim along the collar
    for (let x = CX - 3; x <= CX + 3; x++) b.set(x, A.shY, key + "2", "torso", 3);
  }
  if (M.st.gem) b.rect(CX - 1, A.shY + 4, 2, 2, "gem", "torso");
  if (item.rarity === "mythic" || item.rarity === "legendary") for (let y = A.shY + 3; y < A.hipY - 1; y += 4) { b.set(x0 + 2, y, "trimx", "torso", 3); b.set(x1 - 2, y, "trimx", "torso", 3); }
  pal.gem = pal.gem || M.gem; pal.trimx = M.trim || METALS.gold;
}
/** A helm, hood, circlet or crown over the head. */
function wearHelm(b, A, item, pal) {
  const M = itemMats(item), base = baseOf(item);
  const top = A.headTop - 1, l = A.hl - 1, r = A.hr + 1;
  if (base === "Hood") {
    pal.helm = M.cloth;
    b.poly([[l - 1, A.eyeY + 3], [l, top + 1], [CX, top - 4], [r, top + 1], [r + 1, A.eyeY + 3], [r - 1, A.headBot + 3], [l + 1, A.headBot + 3]], "helm", "helm");
    // cut the face back out
    for (let y = A.eyeY - 3; y <= A.headBot; y++) for (let x = A.hl + 1; x < A.hr; x++) { if (b.reg(x, y) === "helm") b.set(x, y, "skin", "head"); }
    drawFaceOnly(b, A, A.L);
    if (M.trim) b.line(l, A.eyeY - 4, r, A.eyeY - 4, "helm2", "helm", 3);
    pal.helm2 = M.trim || M.leather;
  }
  if (base === "Circlet" || base === "Crown") {
    pal.helm = M.trim || M.metal;
    b.rect(A.hl, A.eyeY - 5, A.hr - A.hl + 1, 2, "helm", "helm");
    if (base === "Crown") for (let i = 0; i < 4; i++) { const x = A.hl + 1 + i * Math.round((A.hr - A.hl - 2) / 3); b.line(x, A.eyeY - 6, x, A.eyeY - 9 - (i % 3 === 0 ? 0 : 1), "helm", "helm"); b.set(x, A.eyeY - 10 - (i % 3 === 0 ? 0 : 1), "gem", "helm"); }
    b.set(CX, A.eyeY - 5, "gem", "helm"); b.set(CX - 1, A.eyeY - 5, "gem", "helm");
  }
  if (base === "Helm") {
    pal.helm = M.metal;
    b.poly([[l, A.eyeY - 2], [l, top + 2], [l + 3, top - 1], [r - 3, top - 1], [r, top + 2], [r, A.eyeY - 2]], "helm", "helm");
    b.rect(l, A.eyeY - 2, 2, 5, "helm", "helm"); b.rect(r - 1, A.eyeY - 2, 2, 5, "helm", "helm");
    b.rect(CX - 1, A.eyeY - 3, 2, 4, "helm", "helm");
    if (M.r.chance(0.5)) b.line(CX, top - 1, CX, top - 4, "helm2", "helm"); // crest
    pal.helm2 = M.trim ? M.cloth : M.leather;
    if (M.trim) b.line(l, top + 2, r, top + 2, "trimx", "helm", 3);
  }
  pal.gem = pal.gem || M.gem; pal.trimx = pal.trimx || M.trim || METALS.gold;
}
function drawFaceOnly(b, A, L) { drawEyes(b, L, A); }
/** Gloves over the hands. */
function wearGloves(b, A, item, pal) {
  const M = itemMats(item), base = baseOf(item);
  pal.glove = base === "Gauntlets" ? M.metal : base === "Wraps" ? M.cloth : M.leather;
  if (base === "Bracers") { b.recolor(["armL"], "glove", (x, y) => y >= A.hipY - 3); return; }
  b.recolor(["hand"], "glove");
  if (base === "Gauntlets") { b.recolor(["armL"], "glove", (x, y) => y >= A.hipY - 4); for (const [hx, hy] of [A.handL, A.handR]) b.rect(hx - 2, hy - 4, 5, 1, "glove", "armL"); }
  if (base === "Wraps") for (const [hx, hy] of [A.handL, A.handR]) b.set(hx, hy - 1, "glove", "hand", 3);
}
/** Boots over the feet. */
function wearBoots(b, A, item, pal) {
  const M = itemMats(item), base = baseOf(item);
  pal.boot = base === "Greaves" ? M.metal : base === "Treads" ? M.cloth : M.leather;
  const h = { Sandals: 0, Boots: 4, Greaves: 8, Treads: 6 }[base] ?? 4;
  b.recolor(["foot"], "boot");
  b.recolor(["leg"], "boot", (x, y) => y >= FOOT - 2 - h);
  if (base === "Sandals") b.recolor(["foot"], "skin", (x, y) => y === FOOT - 2);
  if (base === "Greaves") { const y = FOOT - 2 - h; for (const s of [-1, 1]) b.rect(CX + (s < 0 ? -5 : 2), y + 2, 3, 2, "boot2", "leg"); pal.boot2 = M.trim || M.metal; }
  if (base === "Treads") for (let y = FOOT - 2 - h; y < FOOT - 2; y += 2) b.recolor(["leg"], "boot2", (x, yy) => yy === y);
  if (base === "Boots") b.recolor(["leg"], "boot2", (x, y) => y === FOOT - 2 - h);
  pal.boot2 = pal.boot2 || M.trim || M.leather;
}

/** Weapon sprite drawn into a buffer with its grip at (gx, gy). */
export function drawWeapon(b, item, gx, gy, pal, prefix = "w") {
  const M = itemMats(item), base = baseOf(item), r = M.r;
  const blade = prefix + "b", grip = prefix + "g", guard = prefix + "u", gem = prefix + "e";
  pal[blade] = M.metal; pal[grip] = base === "Staff" || base === "Spear" || base === "Longbow" ? M.wood : M.leather;
  pal[guard] = M.trim || METALS.iron; pal[gem] = M.gem;
  if (base === "Dagger" || base === "Shortsword") {
    const len = base === "Dagger" ? r.int(7, 9) : r.int(14, 18), wid = base === "Dagger" ? 2 : r.int(2, 3);
    b.rect(gx, gy - 1, 1, 4, grip, "weapon");
    b.rect(gx - 2, gy - 2, 5, 1, guard, "weapon");
    if (r.chance(0.5)) { b.set(gx - 2, gy - 3, guard, "weapon"); b.set(gx + 2, gy - 3, guard, "weapon"); }
    b.rect(gx - Math.floor(wid / 2), gy - 2 - len, wid, len, blade, "weapon");
    b.set(gx, gy - 3 - len, blade, "weapon");
    if (wid >= 2) for (let y = gy - len; y < gy - 2; y++) b.set(gx, y, blade, "weapon", 3);
    b.set(gx, gy + 3, M.st.gem ? gem : guard, "weapon");
  } else if (base === "Spear") {
    b.rect(gx, gy - 26, 1, 34, grip, "weapon");
    b.poly([[gx, gy - 34], [gx - 2, gy - 29], [gx, gy - 26], [gx + 2, gy - 29]], blade, "weapon");
    b.rect(gx - 1, gy - 26, 3, 1, guard, "weapon");
    if (r.chance(0.6)) { pal[prefix + "c"] = M.cloth; b.rect(gx + 1, gy - 25, 1, 4, prefix + "c", "weapon"); }
  } else if (base === "Warhammer") {
    b.rect(gx, gy - 16, 1, 22, grip, "weapon");
    const hw = r.int(3, 4);
    b.rect(gx - hw, gy - 22, 2 * hw + 1, 6, blade, "weapon");
    b.rect(gx - hw - 1, gy - 21, 1, 4, blade, "weapon"); b.rect(gx + hw + 1, gy - 21, 1, 4, blade, "weapon");
    b.rect(gx - hw, gy - 19, 2 * hw + 1, 1, guard, "weapon");
    if (r.chance(0.6)) b.poly([[gx, gy - 27], [gx - 1, gy - 22], [gx + 1, gy - 22]], blade, "weapon");
    if (M.st.gem) b.set(gx, gy - 20, gem, "weapon");
  } else if (base === "Staff") {
    b.rect(gx, gy - 24, 1, 32, grip, "weapon");
    const t = r.int(0, 2);
    if (t === 0) { b.ellipse(gx, gy - 28, 3, 3, gem, "weapon"); b.line(gx - 3, gy - 25, gx - 2, gy - 31, guard, "weapon"); b.line(gx + 3, gy - 25, gx + 2, gy - 31, guard, "weapon"); }
    if (t === 1) { b.line(gx, gy - 24, gx + 4, gy - 30, grip, "weapon"); b.line(gx + 4, gy - 30, gx + 2, gy - 33, grip, "weapon"); b.ellipse(gx + 1, gy - 29, 2, 2, gem, "weapon"); }
    if (t === 2) { b.poly([[gx, gy - 34], [gx - 3, gy - 28], [gx, gy - 24], [gx + 3, gy - 28]], gem, "weapon"); b.rect(gx - 2, gy - 24, 5, 1, guard, "weapon"); }
  } else if (base === "Longbow") {
    for (let i = -16; i <= 16; i++) { const x = gx + 2 + Math.round(4 * Math.cos((i / 16) * Math.PI / 2)); b.set(x, gy - 6 + i, grip, "weapon"); b.set(x + 1, gy - 6 + i, grip, "weapon"); }
    pal[prefix + "s"] = ["#d8e4ee", "#d8e4ee", "#eef4fa", "#ffffff"];
    b.line(gx + 2, gy - 22, gx + 2, gy + 10, prefix + "s", "weapon", 2);
    b.rect(gx + 5, gy - 7, 2, 3, guard, "weapon");
  }
}

/** Full paper doll for an adventurer wearing `equipped` gear. Returns {src, w, h, glow}. */
const cache = new Map();
export function adventurerArt(race, seed, equipped = {}, app = null, opts = {}) {
  const key = `${race}|${seed}|${app ? JSON.stringify(app) : ""}|${opts.key || ""}|${["weapon", "helm", "armor", "gloves", "boots", "ring"].map((s) => equipped[s] ? equipped[s].id + equipped[s].rarity + equipped[s].enh : "-").join(",")}`;
  if (cache.has(key)) return cache.get(key);
  const L = lookFor(race, seed, app);
  const r = rng(`draw:${seed}`);
  const pal = {
    skin: L.skin, hair: L.hair, fur: L.race === "beastkin" ? L.hair : L.fur, furtip: ["#c8cfd8", "#e6ebf0", "#f6f8fb", "#ffffff"],
    inner: ramp(350, .45, .72), lash: ["#1a1020", "#2a1830", "#3a2440", "#4a3050"], mouth: ramp(355, .4, .55), iris: L.race === "dragonkin" ? ramp(45, .85, .5) : L.eyes, white: ["#cfd8e6", "#dfe6f0", "#eef2f8", "#ffffff"],
    blush: ramp(352, .55, .66), shirt: L.shirt, pants: L.pants, shoe: LEATHER[1], horn: ramp(40, .2, .78), wing: ramp(L.skin === SKIN.dragonkin[3] ? 260 : 350, .35, .32),
    trim: METALS.gold, bone: ramp(30, .25, .7), default: ["#222", "#444", "#666", "#888"],
  };
  if (race === "dragonkin") pal.wing = [L.skin[0], L.skin[0], L.skin[1], L.skin[2]];
  // the back layer needs real anchors, so draw the body into a scratch buffer first
  const scratch = new Buf(W, H);
  const A = drawBody(scratch, L);
  A.L = L;
  const back = new Buf(W, H);
  drawRaceBack(back, L, A);
  drawHairBack(back, L, A);
  // compose: back layer, then body on top
  const doll = new Buf(W, H);
  for (let i = 0; i < W * H; i++) if (back.m[i]) { doll.m[i] = back.m[i]; doll.r[i] = back.r[i]; doll.t[i] = back.t[i]; }
  drawBody(doll, L);
  if (equipped.armor) wearArmor(doll, A, equipped.armor, pal, "arm");
  if (equipped.boots) wearBoots(doll, A, equipped.boots, pal);
  if (equipped.gloves) wearGloves(doll, A, equipped.gloves, pal);
  drawFace(doll, L, A);
  drawBeard(doll, L, A);
  const hood = equipped.helm && baseOf(equipped.helm) === "Hood";
  if (!hood) drawHairFront(doll, L, A, r);
  drawRaceFront(doll, L, A);
  if (equipped.helm) wearHelm(doll, A, equipped.helm, pal);
  const glowPx = [];
  if (equipped.weapon) drawWeapon(doll, equipped.weapon, A.handR[0] + 1, A.handR[1], pal);
  if (equipped.ring) { const [hx, hy] = A.handL; const M = itemMats(equipped.ring); pal.ring = M.trim || M.metal; doll.set(hx, hy - 1, "ring", "ring", 3); glowPx.push([hx - 1, hy - 1, M.gem[3]]); }
  if (opts.extra) opts.extra(doll, A, pal, glowPx, L);  // faces, halos, monocles... for the cast of characters
  const best = ["mythic", "legendary", "epic", "rare"].find((rar) => Object.values(equipped).some((i) => i && i.rarity === rar));
  if (best === "legendary" || best === "mythic") {
    const sr = rng(`spark:${key}`), col = best === "mythic" ? "#ffd6f0" : "#fff1b8";
    for (let k = 0; k < 7; k++) { const x = sr.int(8, 56), y = sr.int(10, 76); if (!doll.mat(x, y)) { glowPx.push([x, y, col]); if (sr.chance(0.5)) { glowPx.push([x + 1, y, col + "99"]); } } }
  }
  const glow = best ? RARITY_GLOW[best] : null;
  const out = { src: toImage(doll, pal, { glowPx, halo: glow }), w: W, h: H, glow, look: L, headTop: A.headTop };
  cache.set(key, out);
  return out;
}


// ------------------------------------------------------------------ item icons
/** 24x24 icon for any item, drawn from its base type, rarity and seed. */
export function itemIconArt(item) {
  const key = `icon|${item.id}|${item.name}|${item.rarity}|${item.enh}`;
  if (cache.has(key)) return cache.get(key);
  const M = itemMats(item), r = M.r, base = baseOf(item);
  const b = new Buf(24, 24);
  const pal = { m: M.metal, c: M.cloth, l: M.leather, w: M.wood, t: M.trim || M.leather, g: M.gem, x: M.trim || METALS.iron,
    s: ["#c9d5e0", "#d8e2ec", "#e8eef5", "#ffffff"], default: ["#222", "#444", "#666", "#888"] };
  const diag = (x0, y0, x1, y1, mat, thick = 1) => { for (let k = 0; k < thick; k++) b.line(x0 + k, y0, x1 + k, y1, mat, "i"); };
  switch (base) {
    case "Dagger": case "Shortsword": {
      const len = base === "Dagger" ? r.int(7, 9) : r.int(11, 14), gx = 6, gy = 17;
      diag(gx + 2, gy - 2, gx + 2 + len, gy - 2 - len, "m", 2);
      b.line(gx + 3, gy - 3, gx + 2 + len, gy - 2 - len, "m", "i", 3);
      b.line(gx - 1, gy - 4, gx + 4, gy + 1, "x", "i"); b.line(gx, gy - 4, gx + 5, gy + 1, "x", "i");
      diag(gx - 2, gy + 3, gx + 1, gy, "l", 2);
      b.ellipse(gx - 3, gy + 4, 1.2, 1.2, M.st.gem ? "g" : "x", "i");
      if (r.chance(0.4)) { b.set(gx - 2, gy - 5, "x", "i"); b.set(gx + 6, gy + 2, "x", "i"); }
      break;
    }
    case "Spear":
      diag(3, 21, 17, 7, "w", 1); diag(4, 21, 18, 7, "w", 1);
      b.poly([[21, 2], [16, 6], [17, 9], [19, 8]], "m", "i"); b.poly([[21, 2], [15, 5], [18, 4]], "m", "i");
      b.line(15, 9, 18, 6, "x", "i");
      if (r.chance(0.5)) b.rect(14, 10, 2, 3, "c", "i");
      break;
    case "Warhammer":
      diag(4, 21, 13, 12, "w", 2);
      b.rect(10, 3, 11, 7, "m", "i"); b.rect(9, 4, 1, 5, "m", "i"); b.rect(21, 4, 1, 5, "m", "i");
      b.rect(10, 6, 11, 1, "x", "i");
      if (M.st.gem) b.rect(15, 5, 2, 2, "g", "i");
      break;
    case "Staff": {
      diag(4, 22, 15, 9, "w", 2);
      const t = r.int(0, 2);
      if (t === 0) { b.ellipse(17.5, 6, 3.5, 3.5, "g", "i"); b.line(14, 10, 13, 4, "x", "i"); b.line(14, 10, 20, 11, "x", "i"); }
      if (t === 1) { b.poly([[18, 1], [14, 6], [18, 11], [22, 6]], "g", "i"); b.rect(14, 9, 4, 2, "x", "i"); }
      if (t === 2) { b.line(15, 9, 20, 3, "w", "i"); b.line(20, 3, 17, 1, "w", "i"); b.ellipse(17, 5, 2, 2, "g", "i"); }
      break;
    }
    case "Longbow":
      for (let i = 0; i <= 18; i++) { const t = i / 18, x = 3 + 18 * t + 4 * Math.sin(t * Math.PI), y = 21 - 18 * t + 4 * Math.sin(t * Math.PI); b.set(x, y, "w", "i"); b.set(x + 1, y, "w", "i"); }
      b.line(3, 21, 21, 3, "s", "i", 2);
      b.rect(13, 13, 2, 2, "x", "i");
      break;
    case "Hood":
      b.poly([[12, 2], [4, 10], [3, 20], [21, 20], [20, 10]], "c", "i");
      b.ellipse(12, 13, 5, 5.5, null, "i"); b.ellipse(12, 13.5, 4, 4.5, "l", "i");
      for (let x = 7; x <= 17; x++) b.set(x, 13 + Math.round(Math.abs(x - 12) * 0.2) - 6, "c", "i", 3);
      if (M.trim) b.line(3, 20, 21, 20, "t", "i", 3);
      break;
    case "Circlet":
      b.ellipse(12, 13, 9, 5, "t", "i"); b.ellipse(12, 13, 7.5, 3.5, null, "i");
      b.poly([[12, 5], [10, 9], [12, 11], [14, 9]], "t", "i"); b.ellipse(12, 8.5, 1.4, 1.4, "g", "i");
      break;
    case "Crown":
      b.rect(4, 13, 16, 6, "t", "i");
      for (const [x, h] of [[4, 6], [8, 9], [12, 11], [16, 9], [20, 6]]) { b.poly([[x - 2, 13], [x + 1, 13], [x, 13 - h]], "t", "i"); b.set(x, 13 - h + 1, "g", "i"); }
      for (let x = 6; x < 20; x += 4) b.rect(x, 15, 2, 2, "g", "i");
      break;
    case "Helm":
      b.ellipse(12, 12, 8, 8, "m", "i"); b.rect(4, 12, 16, 8, "m", "i");
      b.rect(7, 13, 10, 2, null, "i"); b.rect(11, 13, 2, 6, "m", "i");
      if (r.chance(0.6)) { b.rect(11, 1, 2, 4, "c", "i"); b.rect(10, 2, 1, 2, "c", "i"); }
      if (M.trim) b.line(4, 11, 20, 11, "t", "i", 3);
      break;
    case "Tunic": case "Robe": case "Chainmail": case "Brigandine": case "Plate": {
      const mat = base === "Chainmail" || base === "Plate" ? "m" : base === "Brigandine" ? "l" : "c";
      const bottom = base === "Robe" ? 22 : 19;
      b.poly([[7, 3], [17, 3], [22, 7], [20, 11], [17, 9], [17, bottom], [7, bottom], [7, 9], [4, 11], [2, 7]], mat, "i");
      if (base === "Robe") b.poly([[7, 14], [17, 14], [19, 22], [5, 22]], mat, "i");
      b.ellipse(12, 3, 2.5, 1.5, null, "i");
      if (base === "Tunic") b.rect(7, 14, 10, 1, "l", "i", 1);
      if (base === "Robe") b.line(12, 4, 12, 22, "t", "i", 3);
      if (base === "Chainmail") for (let y = 4; y < bottom; y++) for (let x = 2; x < 23; x++) if (b.mat(x, y) === "m" && (x + y) % 2) b.set(x, y, "m", "i", 1);
      if (base === "Brigandine") for (let y = 6; y < bottom; y += 3) for (let x = 8; x < 17; x += 3) b.set(x, y, "m", "i", 3);
      if (base === "Plate") { b.line(12, 4, 12, 13, "m", "i", 3); for (let y = 14; y < bottom; y += 2) b.line(7, y, 17, y, "m", "i", 1); b.ellipse(4, 7, 3, 2.5, "m", "i"); b.ellipse(20, 7, 3, 2.5, "m", "i"); }
      if (M.st.gem) b.rect(11, 7, 2, 2, "g", "i");
      if (M.trim && base !== "Robe") b.line(9, 4, 15, 4, "t", "i", 3);
      break;
    }
    case "Wraps": case "Gloves": case "Gauntlets": case "Bracers": {
      const mat = base === "Gauntlets" ? "m" : base === "Wraps" ? "c" : "l";
      if (base !== "Bracers") {
        b.rect(7, 9, 10, 9, mat, "i");
        for (let i = 0; i < 4; i++) b.rect(7 + i * 2 + (i > 1 ? 1 : 0), 4 + (i === 1 || i === 2 ? 0 : 1), 2, 6, mat, "i");
        b.poly([[17, 12], [21, 9], [21, 11], [17, 15]], mat, "i");
        if (base === "Gauntlets") for (let x = 7; x < 17; x += 2) b.set(x, 9, "m", "i", 3);
        if (base === "Wraps") for (let y = 10; y < 18; y += 2) b.line(7, y, 16, y, "c", "i", 1);
      }
      b.rect(6, 17, 12, 5, base === "Bracers" ? "m" : "x", "i");
      if (base === "Bracers") { b.rect(6, 9, 12, 5, "l", "i"); if (M.st.gem) b.rect(11, 18, 2, 2, "g", "i"); }
      break;
    }
    case "Sandals": case "Boots": case "Greaves": case "Treads": {
      const mat = base === "Greaves" ? "m" : base === "Treads" ? "c" : "l";
      const top = base === "Greaves" ? 2 : base === "Sandals" ? 13 : 5;
      b.rect(7, top, 7, 19 - top, mat, "i");
      b.poly([[7, 15], [14, 15], [20, 18], [20, 21], [7, 21]], mat, "i");
      b.rect(6, 21, 15, 2, "l", "i", 0);
      if (base === "Sandals") { b.rect(7, 13, 7, 6, null, "i"); b.line(7, 16, 18, 19, "l", "i"); b.line(7, 13, 13, 18, "l", "i"); }
      if (base === "Greaves") { b.ellipse(10.5, 7, 3.5, 2.5, "x", "i"); }
      if (base === "Treads") for (let y = top + 1; y < 19; y += 2) b.line(7, y, 13, y, "c", "i", 1);
      if (base === "Boots") b.rect(6, top, 9, 2, "x", "i");
      break;
    }
    default: { // rings and amulets
      if (base === "Amulet") {
        b.line(5, 2, 12, 12, "t", "i"); b.line(19, 2, 12, 12, "t", "i");
        b.poly([[12, 10], [7, 15], [12, 22], [17, 15]], "t", "i"); b.poly([[12, 12], [9, 15], [12, 19], [15, 15]], "g", "i");
      } else {
        const thick = base === "Band" ? 2.8 : 2;
        b.ellipse(12, 14, 7, 7, "t", "i"); b.ellipse(12, 14, 7 - thick, 7 - thick, null, "i");
        if (base === "Signet") b.rect(9, 5, 7, 5, "t", "i");
        b.poly([[12, 3], [9, 7], [12, 10], [15, 7]], "g", "i");
      }
    }
  }
  if (item.enh >= 5) b.set(20, 3, "g", "i", 3);
  const out = toImage(b, pal);
  cache.set(key, out);
  return out;
}

// ------------------------------------------------------------------ monsters
export const ELEMENTS = {
  fire: [12, .8], frost: [192, .65], shadow: [272, .45], toxic: [100, .6], storm: [52, .85], earth: [30, .45],
  abyss: [228, .55], bone: [42, .2], blood: [352, .65], arcane: [300, .6], tide: [182, .7], verdant: [135, .55],
};
export const CREATURES = ["slime", "golem", "wraith", "imp", "hydra", "mimic", "lich", "beast", "wyrm", "treant", "watcher", "spider"];

/** 48x48 monster for a labyrinth boss; same seed, same monster. */
export function monsterArt(kind, element, seed) {
  const key = `mon|${kind}|${element}|${seed}`;
  if (cache.has(key)) return cache.get(key);
  const r = rng(key);
  const [hue, sat] = ELEMENTS[element] || ELEMENTS.shadow;
  const b = new Buf(48, 48);
  const pal = {
    a: ramp(hue + r.int(-12, 12), sat, 0.45), b2: ramp(hue + 30, sat * 0.8, 0.32), e: ramp(hue + 180, 0.9, 0.65),
    k: ["#2a2028", "#3a2c34", "#d8d0c0", "#f6f0e2"], h: ramp(40, .25, .75), m: METALS[r.pick(["iron", "gold", "obsidian", "bronze"])],
    t: ["#601a2a", "#7a2234", "#b03048", "#d84a5e"], default: ["#222", "#444", "#666", "#888"],
  };
  const glow = [];
  const eye = (x, y, big = false) => { b.ellipse(x, y, big ? 2 : 1.2, big ? 2 : 1.2, "e", "eye"); glow.push([Math.round(x), Math.round(y), pal.e[3]]); };
  const pair = (fn) => { fn(1); fn(-1); }; // draw mirrored about x = 23.5
  const X = (s, dx) => 23.5 + s * dx;
  switch (kind) {
    case "slime": {
      const rx = r.int(14, 18), ry = r.int(10, 13), cy = 46 - ry;
      b.ellipse(23.5, cy, rx, ry, "a", "body"); b.rect(23.5 - rx, cy, 2 * rx, ry, "a", "body");
      for (let i = 0; i < 4; i++) { const x = r.int(10, 37); b.ellipse(x, 46, 1.5, 1.5, "a", "body"); }
      for (let i = 0; i < 5; i++) b.ellipse(r.int(14, 34), r.int(cy, 44), 1.2, 1.2, "a", "body"); // bubbles
      pair((s) => eye(X(s, 5), cy - 1, true));
      b.line(20, cy + 5, 27, cy + 5, "b2", "mouth");
      if (r.chance(0.5)) { b.rect(16, cy - ry - 3, 16, 3, "m", "crown"); for (let x = 16; x < 32; x += 5) b.line(x, cy - ry - 3, x + 1, cy - ry - 7, "m", "crown"); }
      break;
    }
    case "golem": {
      const w = r.int(9, 11);
      b.rect(23.5 - w, 18, 2 * w, 18, "a", "body");
      b.rect(19, 9, 10, 9, "a", "head");
      pair((s) => { b.rect(s > 0 ? 24 + w : 23 - w - 6, 18, 7, 20, "b2", "arm"); b.rect(s > 0 ? 25 + w : 22 - w - 6, 37, 7, 5, "a", "fist"); b.rect(s > 0 ? 26 : 15, 36, 7, 10, "b2", "leg"); });
      pair((s) => eye(X(s, 2.5), 13));
      b.ellipse(23.5, 26, 3, 3, "e", "core"); glow.push([23, 26, pal.e[3]], [24, 26, pal.e[3]]);
      for (let i = 0; i < 3; i++) b.line(r.int(16, 30), r.int(19, 24), r.int(16, 30), r.int(28, 34), "b2", "crack", 0);
      break;
    }
    case "wraith": {
      b.poly([[23.5, 4], [12, 16], [9, 40], [14, 36], [17, 44], [21, 38], [26, 44], [30, 38], [33, 44], [36, 36], [38, 40], [35, 16]], "a", "cloak");
      b.ellipse(23.5, 15, 6, 7, "k", "void");
      pair((s) => eye(X(s, 2.5), 15));
      pair((s) => { b.line(X(s, 12), 22, X(s, 19), 30, "h", "hand"); b.line(X(s, 19), 30, X(s, 21), 34, "h", "hand"); });
      break;
    }
    case "imp": {
      b.ellipse(23.5, 30, 7, 8, "a", "body"); b.ellipse(23.5, 18, 8, 7, "a", "head");
      pair((s) => { b.poly([[X(s, 6), 12], [X(s, 9), 2], [X(s, 3), 11]], "h", "horn"); b.poly([[X(s, 6), 26], [X(s, 20), 16], [X(s, 22), 24], [X(s, 16), 26], [X(s, 17), 32]], "b2", "wing"); b.rect(X(s, 4) - 1, 37, 3, 8, "a", "leg"); });
      pair((s) => eye(X(s, 3), 17));
      b.line(19, 22, 28, 22, "k", "mouth"); b.set(20, 23, "k", "fang", 3); b.set(27, 23, "k", "fang", 3);
      b.line(30, 34, 40, 40, "b2", "tail"); b.poly([[40, 37], [43, 41], [39, 42]], "b2", "tail");
      break;
    }
    case "hydra": {
      b.ellipse(23.5, 38, 14, 9, "a", "body");
      const n = r.pick([3, 5]);
      for (let i = 0; i < n; i++) {
        const t = n === 1 ? 0 : i / (n - 1) - 0.5, hx = 23.5 + t * 30, hy = 10 + Math.abs(t) * 10;
        blob(b, curve([23.5 + t * 10, 34], [23.5 + t * 22, 22], [hx, hy], 6), [3, 2.8, 2.6, 2.4, 2.2, 2.2, 2.2], "b2", "neck");
        b.ellipse(hx, hy, 3.5, 2.6, "a", "head"); eye(hx + (t < 0 ? -1 : 1), hy - 1);
      }
      break;
    }
    case "mimic": {
      b.rect(10, 26, 28, 18, "l", "box"); pal.l = LEATHER[0];
      b.poly([[10, 26], [12, 12], [36, 12], [38, 26]], "l", "lid");
      b.rect(10, 24, 28, 3, "m", "band"); b.rect(22, 22, 4, 6, "m", "lock");
      b.rect(12, 26, 24, 6, "k", "maw");
      for (let x = 12; x < 36; x += 3) { b.poly([[x, 26], [x + 2, 26], [x + 1, 29]], "k", "tooth", 3); b.poly([[x + 1, 32], [x + 3, 32], [x + 2, 29]], "k", "tooth", 3); }
      b.ellipse(23.5, 31, 3, 1.5, "t", "tongue");
      pair((s) => eye(X(s, 6), 18));
      break;
    }
    case "lich": {
      b.poly([[23.5, 16], [12, 44], [35, 44]], "a", "robe");
      b.ellipse(23.5, 12, 6, 6.5, "k", "skull"); b.rect(20, 15, 8, 4, "k", "jaw");
      pal.k = ["#7a7060", "#a89c84", "#d8d0c0", "#f6f0e2"];
      pair((s) => eye(X(s, 2.5), 12));
      b.rect(19, 3, 10, 3, "m", "crown"); for (let x = 19; x < 29; x += 3) b.line(x, 3, x, 0, "m", "crown");
      b.line(38, 6, 38, 44, "w", "staff"); pal.w = WOOD[0]; b.ellipse(38, 5, 2.5, 2.5, "e", "orb"); glow.push([38, 5, pal.e[3]]);
      break;
    }
    case "beast": {
      b.ellipse(23.5, 24, 14, 13, "a", "mane"); b.ellipse(23.5, 26, 10, 10, "b2", "face");
      pair((s) => b.poly([[X(s, 7), 15], [X(s, 13), 4], [X(s, 13), 15]], "a", "ear"));
      b.ellipse(23.5, 31, 5, 4, "h", "snout"); b.rect(22, 28, 3, 2, "k", "nose");
      pair((s) => { eye(X(s, 5), 23); b.poly([[X(s, 2), 34], [X(s, 4), 34], [X(s, 3), 39]], "k", "fang", 3); });
      break;
    }
    case "wyrm": {
      const pts = curve([8, 44], [44, 40], [24, 26], 10);
      blob(b, pts, pts.map((_, i) => 6 - i * 0.2), "a", "coil");
      b.ellipse(24, 16, 8, 7, "a", "head"); b.ellipse(24, 21, 5, 4, "b2", "jaw");
      pair((s) => { b.line(X(s, 5), 10, X(s, 10), 2, "h", "horn"); b.line(X(s, 4), 10, X(s, 9), 2, "h", "horn"); eye(X(s, 3.5), 15); });
      for (let i = 1; i < pts.length; i += 2) b.set(Math.round(pts[i][0]), Math.round(pts[i][1]) - 5, "h", "spine");
      break;
    }
    case "treant": {
      b.rect(16, 18, 16, 28, "w", "trunk"); pal.w = ramp(28, .4, .32);
      b.ellipse(23.5, 12, 16, 10, "a", "leaves"); for (let i = 0; i < 7; i++) b.ellipse(r.int(10, 37), r.int(4, 18), 3, 3, "a", "leaves");
      pair((s) => { b.line(X(s, 8), 24, X(s, 18), 16, "w", "branch"); b.line(X(s, 8), 25, X(s, 18), 17, "w", "branch"); eye(X(s, 3.5), 25); });
      b.rect(20, 32, 8, 3, "k", "mouth");
      break;
    }
    case "watcher": {
      b.ellipse(23.5, 26, 15, 15, "a", "body");
      b.ellipse(23.5, 26, 9, 8, "k", "sclera"); pal.k = ["#b8c0c8", "#d0d8e0", "#e8eef4", "#ffffff"];
      b.ellipse(23.5, 26, 4.5, 4.5, "e", "iris"); b.ellipse(23.5, 26, 2, 3, "b2", "pupil"); glow.push([22, 24, "#ffffff"]);
      for (let i = 0; i < 5; i++) { const t = i / 4 - 0.5; const ex = 23.5 + t * 28, ey = 6 + Math.abs(t) * 8; b.line(23.5 + t * 12, 13, ex, ey, "b2", "stalk"); eye(ex, ey); }
      break;
    }
    default: { // spider
      b.ellipse(23.5, 30, 9, 8, "a", "abdomen"); b.ellipse(23.5, 19, 6, 5, "b2", "head");
      pair((s) => { for (let i = 0; i < 4; i++) { const y = 20 + i * 3; b.line(X(s, 5), y, X(s, 14 + i), y - 6 + i * 2, "b2", "leg"); b.line(X(s, 14 + i), y - 6 + i * 2, X(s, 19 + i), y + 8 + i * 2, "b2", "leg"); } });
      for (const [dx, dy] of [[2, 18], [4, 17], [1.5, 20], [4.5, 20]]) pair((s) => eye(X(s, dx), dy));
      b.set(23, 34, "e", "mark"); b.set(24, 34, "e", "mark"); b.set(23, 33, "e", "mark"); b.set(24, 35, "e", "mark");
    }
  }
  // random traits on top of the body plan, so two monsters of a kind rarely match
  const box = { x0: 48, y0: 48, x1: 0, y1: 0 };
  for (let y = 0; y < 48; y++) for (let x = 0; x < 48; x++) if (b.mat(x, y)) { box.x0 = Math.min(box.x0, x); box.x1 = Math.max(box.x1, x); box.y0 = Math.min(box.y0, y); box.y1 = Math.max(box.y1, y); }
  const traits = [];
  for (const t of ["horns", "plates", "crown", "scar", "spikes", "runes"]) if (r.chance(0.22)) traits.push(t);
  for (const t of traits.slice(0, 2)) {
    if (t === "horns" && kind !== "imp" && kind !== "wyrm") pair((sd) => b.poly([[X(sd, 4), box.y0 + 2], [X(sd, 8), box.y0 + 2], [X(sd, 9), Math.max(box.y0 - 6, 0)]], "h", "horn"));
    if (t === "plates") for (let i = 0; i < 4; i++) { const x = r.int(box.x0 + 3, box.x1 - 4), y = r.int(box.y0 + 8, box.y1 - 4); if (b.mat(x, y) && b.mat(x + 2, y + 2)) b.rect(x, y, 3, 3, "m", "plate"); }
    if (t === "crown" && kind !== "lich" && kind !== "slime") { b.rect(19, Math.max(box.y0 - 3, 0), 10, 3, "m", "crown"); for (let x = 19; x < 29; x += 3) b.set(x, Math.max(box.y0 - 4, 0), "m", "crown"); }
    if (t === "scar") b.line(box.x0 + 6, box.y0 + 6, box.x0 + 12, box.y0 + 14, "t", "scar", 2);
    if (t === "spikes") for (let x = box.x0 + 2; x < box.x1 - 1; x += 4) { let y = 0; while (y < 47 && !b.mat(x, y)) y++; if (y > 1) b.poly([[x - 1, y], [x + 1, y], [x, y - 3]], "h", "spike"); }
    if (t === "runes") for (let i = 0; i < 5; i++) { const x = r.int(box.x0 + 2, box.x1 - 2), y = r.int(box.y0 + 4, box.y1 - 2); if (b.mat(x, y)) { b.set(x, y, "e", "rune", 3); glow.push([x, y, pal.e[3]]); } }
  }
  const aura = hsl2hex(hue, 0.8, 0.6);
  const out = { src: toImage(b, pal, { glowPx: glow, halo: aura }), glow: aura, traits };
  cache.set(key, out);
  return out;
}

export { Buf, toImage, itemMats, baseOf, METALS, LEATHER, WOOD };
