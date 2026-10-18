/*
 * Life RPG: the System panel (the sidebar page) and the life-rpg-card dashboard card.
 * Plain ES modules, served as they are by Home Assistant: no build step, no dependencies.
 *
 * How it fits together
 *   The integration sends the whole game view over one websocket subscription (life_rpg/subscribe, see
 *   websocket.py) every time it changes; the panel and cards redraw from that view. Buttons call life_rpg/action
 *   with an action name and its arguments (the list is in LifeRPGCoordinator.async_action), and the next view
 *   shows the result. Chats with the goddess and the merchant go through life_rpg/chat.
 *
 * This file, top to bottom
 *   framing and pixel-art helpers      used by the panel and the cards
 *   data layer                          one shared subscription per adventurer, and the action call
 *   helpers                             formatting, effect labels, event texts for toasts and the log
 *   art                                 portraits, item icons, monsters, medals, chests, bars and charts
 *   shared windows (V)                  the boxes both the panel and the cards show (status, quests, guardian...)
 *   the panel (LifeRpgPanel)            tabs, the Gallery, click and form handling
 *   the card (LifeRpgCard)              the dashboard card's views
 *
 * Other files: styles.js (all CSS), art.js (pixel art for the adventurer, gear and monsters),
 * cast.js (pixel art for the goddess, the merchant and the other people).
 */
import { adventurerArt, itemIconArt, monsterArt, RARITY_GLOW } from "./art.js?v=1.0.2";
import { luneArt, merchantArt, npcArt, trinketArt } from "./cast.js?v=1.0.2";
import { CARD_CSS, CSS, PANEL_CSS } from "./styles.js?v=1.0.2";

// The panel's element name carries the version, so a Home Assistant app that kept an older panel in memory
// loads this one as soon as Home Assistant hands it the new panel (see __init__.py).
const VERSION = "1.0.2";
const PANEL_TAG = `life-rpg-panel-${VERSION.replace(/\./g, "-")}`;

// Pixel art is the stand-in for every painting; a viewer can also prefer it on this device.
const PIXEL_KEY = "life_rpg_pixel";
const pixelPref = () => { try { return localStorage.getItem(PIXEL_KEY) === "1"; } catch (e) { return false; } };
let PIXEL = pixelPref();
const painted = (url) => (PIXEL ? null : url || null);
// Framing is a crop of a full-body painting, so choosing one never repaints anything. Each keeps this share of the
// painting's height, from the top (where the head is).
const FRAME_SHOW = { full: 1, three_quarter: 0.78, half: 0.58, bust: 0.42, closeup: 0.32 };
const PERSON_AR = 704 / 1024; // the shape of every painting of a person
/** A painting of a person cropped to a framing (full, three-quarter, half, bust, close-up). */
function framed(url, framing, cls = "", alt = "", ar = 0.75) {
  const f = FRAME_SHOW[framing] || 1, box = f >= 1 && ar === 0.75 ? PERSON_AR : ar;
  return `<span class="crop ${cls}" style="--ar:${box};--z:${(PERSON_AR / (box * f)).toFixed(3)}" role="img" aria-label="${String(alt).replace(/"/g, "&quot;")}"><img src="${url}" alt=""></span>`;
}
/** A pixel character cropped to head and shoulders, scaled by whole pixels. */
function bust(art, size, cls = "") {
  if (!art.headTop) return `<img class="pix ${cls}" src="${art.src}" width="${size}" height="${size}" alt="">`;
  const crop = 36, k = size / crop, top = Math.max(0, art.headTop - 8);
  return `<span class="bust ${cls}" role="img" style="width:${size}px;height:${size}px;background-image:url(${art.src});background-size:${64 * k}px ${84 * k}px;background-position:${-14 * k}px ${-top * k}px"></span>`;
}

if (!customElements.get(PANEL_TAG)) {
  // ---------------------------------------------------------------- data layer
  const subs = new Map(); // entry_id -> {listeners, last, unsub}
  // Subscribe to an adventurer's view; every caller shares one websocket subscription per adventurer.
  const subscribe = (hass, entryId, cb) => {
    let s = subs.get(entryId);
    if (!s) {
      s = { listeners: new Set(), last: null, unsub: null };
      subs.set(entryId, s);
      s.unsub = hass.connection.subscribeMessage((msg) => {
        s.last = msg;
        s.listeners.forEach((l) => l(msg, false));
      }, { type: "life_rpg/subscribe", entry_id: entryId });
    } else if (s.last) cb(s.last, true);
    s.listeners.add(cb);
    return () => {
      s.listeners.delete(cb);
      if (!s.listeners.size) {
        subs.delete(entryId);
        s.unsub.then((u) => u()).catch(() => {});
      }
    };
  };
  // Everyone the viewer may watch, and which adventurer is theirs.
  const players = (hass) => hass.callWS({ type: "life_rpg/players" });
  // Run a game action for this adventurer (see LifeRPGCoordinator.async_action); the new view follows.
  const act = (hass, entryId, action, extra = {}) =>
    hass.callWS({ type: "life_rpg/action", entry_id: entryId, action, ...extra });

  // ---------------------------------------------------------------- helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (n) => (n == null ? "–" : Number(n).toLocaleString());
  const pct = (a, b) => Math.max(0, Math.min(100, b ? (100 * a) / b : 0));
  const cap = (s) => String(s || "").charAt(0).toUpperCase() + String(s || "").slice(1);
  const plural = (n, w) => `${num(n)} ${w}${n === 1 ? "" : "s"}`;
  const RARITY = { common: "#9aa7b4", uncommon: "#4fd18b", rare: "#45b8ff", epic: "#b072ff", legendary: "#ffa640", mythic: "#ff4d6d" };
  const RANKC = { E: "#8b97a6", D: "#4fd18b", C: "#45b8ff", B: "#9b7bff", A: "#f5c451", S: "#ff5a5a" };
  // The colour of a rank's letter (each S+n rank past S gets its own hue).
  const rankColor = (rank) => {
    const m = /^S\+(\d+)$/.exec(rank || "");
    return m ? `hsl(${(0 + Number(m[1]) * 29) % 360} 90% 66%)` : RANKC[rank] || RANKC.E;
  };
  const TIERC = ["#3a4a63", "#c68642", "#c9d1da", "#f5c451", "#8fe3ff", "#e9fbff"];
  const SLOT_NAMES = { weapon: "Weapon", helm: "Helm", armor: "Armor", gloves: "Gloves", boots: "Boots", ring: "Ring" };
  const SLOT_ICON = { weapon: "mdi:sword", helm: "mdi:account-cowboy-hat", armor: "mdi:tshirt-crew", gloves: "mdi:hand-back-right", boots: "mdi:shoe-formal", ring: "mdi:ring" };
  const ATTR_ICON = { stamina: "mdi:run-fast", strength: "mdi:arm-flex", vitality: "mdi:heart-pulse", intelligence: "mdi:brain", wisdom: "mdi:meditation" };
  const JOB_ICON = { ranger: "mdi:bow-arrow", warrior: "mdi:sword", druid: "mdi:leaf", mage: "mdi:wizard-hat", monk: "mdi:meditation", paladin: "mdi:shield-cross", rogue: "mdi:incognito", bard: "mdi:music" };
  const JOB_FOCUS = { paladin: "Every quest", rogue: "Emergencies, hidden quests", bard: "Won choices" };
  const QUEST_UNIT = { steps: "", floors: "floors", sleep: "h", hydration: "mL", bedtime: "" };
  const QNAME = { steps: "Walk", floors: "Climb", sleep: "Rest", hydration: "Water", bedtime: "Lights-out" };
  const ELEMENT_C = { fire: "#ff7a3d", frost: "#8fe3ff", shadow: "#9b7bff", toxic: "#9be35a", storm: "#ffe066", earth: "#c99a5b", abyss: "#5b7bff", bone: "#e6dcc4", blood: "#ff4d6d", arcane: "#ff7ae0", tide: "#3de0d0", verdant: "#4fd18b" };
  // An effect key and value as words, for example xp:steps 5 -> "+5% Walk XP".
  const EFFECT_LABEL = (k, v) => {
    if (k.startsWith("xp:")) return `+${v}% ${k === "xp:all" ? "all" : QNAME[k.slice(3)] || k.slice(3)} XP`;
    if (k.startsWith("dmg:")) return `+${v}% ${QNAME[k.slice(4)] || k.slice(4)} damage`;
    return {
      boss: `+${v}% guardian damage`, luck: `+${v}% loot luck`, over: `Goal cap +${Math.round(v * 100)}%`,
      shield: `+${v} streak shield`, streak: `+${v} streak days`, perfect: `+${v}% perfect-day XP`, record: `+${v}% record XP`,
      emergency: `+${v}% emergency XP`, choice: `+${v}% choice rewards`, serenity: "Serenity", clear_mind: "Clear Mind", quest: `+${v}% quest XP`,
    }[k] || `${k} ${v}`;
  };
  const capName = (k) => (k === "over" ? "Goal cap" : EFFECT_LABEL(k, 1).replace(/^\+1%? /, "").replace(/^./, (c) => c.toUpperCase()));
  const capAmount = (k, x) => (k === "over" ? `+${Math.round(x * 100)}%` : ["shield", "streak"].includes(k) ? `+${x}` : `+${x}%`);
  const effectList = (eff) => Object.entries(eff || {}).filter(([, v]) => v).map(([k, v]) => EFFECT_LABEL(k, k === "over" ? v : Math.round(v * 10) / 10));
  let HOUR12; // from the adventurer's Clock setting (undefined until the first view: the browser decides)
  // Follow Home Assistant's 12- or 24-hour clock setting (sent in the view).
  const setClock = (v) => { if (v && v.clock) HOUR12 = v.clock === "12"; };
  const fmtTime = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", hour12: HOUR12 }); };
  const shortDate = (iso) => { const d = new Date(iso + "T12:00:00"); return isNaN(d) ? iso : d.toLocaleDateString([], { month: "short", day: "numeric" }); };

  // what each event says, in the System's voice
  function describe(e) {
    switch (e.type) {
      case "level_up": return ["Level up", `You have reached level ${e.level}.`, "gold"];
      case "rank_up": return ["Rank up", `You are now ${e.rank}-rank.`, "gold"];
      case "quest_complete": return ["Quest complete", `${e.name || QNAME[e.quest]} cleared. ${e.attribute ? cap(e.attribute) + " grows." : ""}`, "blue"];
      case "day_cleared": return ["Daily quest cleared", `Streak ${e.streak}. A chest has been delivered.`, "blue"];
      case "perfect_day": return ["Perfect day", `Every quest cleared. +${num(e.xp)} XP and a better chest.`, "gold"];
      case "streak_milestone": return ["Streak milestone", `${e.streak} days without falling.`, "gold"];
      case "personal_record": return ["Limit broken", `${QNAME[e.quest]}: ${num(e.value)} beats ${num(e.previous)}. +${num(e.xp)} XP.`, "gold"];
      case "attribute_up": return ["Attribute up", `${cap(e.attribute)} is now ${e.value}.`, "blue"];
      case "skill_up": return ["Skill proficiency up", `${e.skill} has reached ${e.grade}.`, "blue"];
      case "job_change": return ["Job change", `You are now a ${e.job}.`, "violet"];
      case "job_level": return ["Job level up", `${e.job} level ${e.level}${e.title ? `: ${e.title}` : ""}.`, "violet"];
      case "race_evolved": return ["Racial gift evolved", `${e.race}: ${e.gift}.`, "violet"];
      case "title_earned": return ["Title acquired", `“${e.title}”`, "gold"];
      case "badge_earned": return ["Badge earned", `${e.badge}: ${e.tier}.`, "blue"];
      case "hidden_quest": return ["Hidden quest cleared", `${e.quest}. +${num(e.xp)} XP.`, "violet"];
      case "emergency_quest": return ["Emergency quest", `${e.title}. ${e.minutes} minutes. ${e.excused ? "Working hours: failing costs nothing." : `Failing costs ${num(e.fine)} gold.`}`, "red"];
      case "emergency_cleared": return ["Emergency quest cleared", `+${num(e.xp)} XP and a chest.`, "gold"];
      case "emergency_failed": return ["Emergency quest failed", !e.excused ? `Time ran out. −${num(e.fine)} gold.`
        : e.why === "work" && e.would_be ? `Penalty: −${num(e.would_be)} gold… ERROR. ERROR. Working hours detected. Failing costs nothing.`
        : "Time ran out. No penalty this time.", "red"];
      case "emergency_declined": return ["Emergency declined", e.fine ? `The System accepts. −${num(e.fine)} gold.` : "Declined. No penalty.", "red"];
      case "reading_held": return ["Reading held back", `${e.name}: ${num(e.held)} ${e.unit} arrived faster than anyone could manage, so they weren't counted. If they were real, use "They were real" on the Quests tab.`, "red"];
      case "bounty_done": return ["Bounty done", `${e.bounty}: ${[e.xp ? `+${num(e.xp)} XP` : "", e.chest ? "a bounty chest" : ""].filter(Boolean).join(" and ") || "done"}.`, "gold"];
      case "bounty_claimed": return ["Chore done?", `${e.bounty} is waiting for a parent to approve it.`, "violet"];
      case "goddess_gift": return [`A gift from ${e.goddess || "the goddess"}`, `${e.gift[0].toUpperCase()}${e.gift.slice(1)}. ${e.desc}`, "violet"];
      case "penalty_quest": return ["Penalty quest", `Finish ${e.need} quests today to save your ${e.streak}-day streak.`, "red"];
      case "penalty_cleared": return ["Penalty survived", `Your streak lives on: ${e.streak} days.`, "gold"];
      case "streak_broken": return ["Streak lost", `The ${e.streak}-day streak has ended. Day one starts now.`, "red"];
      case "shield_earned": return ["Shield acquired", `You hold ${plural(e.shields, "streak shield")}.`, "blue"];
      case "shield_used": return ["Shield used", `Your ${e.streak}-day streak was protected.`, "blue"];
      case "guardian_appeared": return [e.cursed ? "A cursed floor" : e.elite ? "An elite floor" : "A new floor",
        `Floor ${e.floor}: ${e.guardian} awaits. ${num(e.hp)} HP. ${e.trait || ""}`, e.cursed ? "red" : "violet"];
      case "guardian_defeated": return ["Guardian defeated", `${e.guardian} falls on floor ${e.floor}. +${num(e.xp)} XP. Floor ${e.next_floor} is open.`, "gold"];
      case "chest_dropped": return ["Chest acquired", `${cap(e.chest)} chest${e.rank ? ", rank " + e.rank : ""}.`, "blue"];
      case "devotion_up": return ["Devotion deepens", `${e.tier}.${e.blessing ? ` Blessing: ${e.blessing}.` : ""}`, "violet"];
      case "choice_offered": return ["A choice appears", e.text || "", "violet"];
      case "choice_won": return ["Choice won", `+${num(e.xp)} XP.`, "gold"];
      case "bargain_struck": return ["Bargain struck", `${e.item} for ${num(e.price)} gold (was ${num(e.list)}).`, "gold"];
      case "market_restocked": return ["New stock at the market", `Marrow Fennick has unpacked ${e.what || "fresh wares"}.`, "gold"];
      case "choice_lost": return ["Choice lost", e.stake ? `The ${num(e.stake)} XP stake is gone.` : "The terms weren't met. Nothing was lost.", "red"];
      default: return [cap(String(e.type).replace(/_/g, " ")), "", "blue"];
    }
  }
  const BIG = new Set(["level_up", "rank_up", "race_evolved", "hidden_quest", "emergency_quest", "penalty_quest", "guardian_defeated",
    "guardian_appeared", "title_earned", "perfect_day", "job_change", "job_level", "choice_offered"]);

  // ---------------------------------------------------------------- art
  function rankEmblem(rank, size = 64) {
    const c = rankColor(rank), m = /^S\+(\d+)$/.exec(rank || ""), label = m ? "S" : rank, id = String(rank).replace(/\W/g, "_");
    return `<svg class="emblem" width="${size}" height="${size}" viewBox="0 0 100 100" role="img" aria-label="Rank ${esc(rank)}">
      <defs><radialGradient id="eg${id}" cx="50%" cy="40%" r="60%"><stop offset="0" stop-color="${c}" stop-opacity=".45"/><stop offset="1" stop-color="#040815" stop-opacity=".9"/></radialGradient></defs>
      <polygon points="50,4 93,27 93,73 50,96 7,73 7,27" fill="url(#eg${id})" stroke="${c}" stroke-width="3"/>
      <polygon points="50,14 84,32 84,68 50,86 16,68 16,32" fill="none" stroke="${c}" stroke-opacity=".35" stroke-width="1.5"/>
      <text x="50" y="${m ? 58 : 66}" text-anchor="middle" font-size="46" font-weight="700" fill="${c}" style="filter:drop-shadow(0 0 6px ${c})">${esc(label)}</text>
      ${m ? `<text x="50" y="82" text-anchor="middle" font-size="18" font-weight="700" fill="#fff">+${m[1]}</text>` : ""}</svg>`;
  }

  // the adventurer: the painted portrait when ComfyUI has made one, else the pixel-art paper doll
  function portrait(v, equipped, scale = 3) {
    const a = { ...(v.art || {}), portrait: painted((v.art || {}).portrait) };
    const badge = a.portrait_pending && !PIXEL ? `<span class="paint-badge">${a.portrait ? "Painting your new look…" : "Painting…"}</span>` : "";
    if (a.portrait) {
      return `<div class="stage painted-stage frame-${esc(a.frame || "none")}" style="--aura:${rankColor(v.rank)};width:${64 * scale}px">
        ${framed(esc(a.portrait), (v.portrait_prefs || {}).framing || "full", "painted", `Painted portrait of your ${v.race.name} adventurer`)}${badge}</div>`;
    }
    const art = adventurerArt(v.race.id, `${v.seed}:${v.look || 0}`, equipped || {}, v.appearance || null);
    return `<div class="stage" style="--aura:${rankColor(v.rank)};--glow:${art.glow || "transparent"};width:${64 * scale}px">
      <img class="doll" src="${art.src}" width="${64 * scale}" height="${84 * scale}" alt="${esc(v.race.name)} adventurer">${badge}</div>`;
  }

  // a potion, charm or cosmetic: its painting when there is one, else the pixel icon
  const trinketIcon = (cid, art) => painted(art)
    ? `<span class="cicon"><img class="paint" src="${esc(art)}" width="48" height="48" alt=""></span>`
    : `<span class="cicon"><img class="pix" src="${trinketArt(cid)}" width="48" height="48" alt=""></span>`;
  /** A gear icon with its rarity glow (or the empty slot's outline). */
  function itemIcon(item, scale = 2, slotIfEmpty = null) {
    const size = 24 * scale + 8;
    if (!item) {
      return `<span class="icon empty" style="width:${size}px;height:${size}px" title="${esc(SLOT_NAMES[slotIfEmpty])} slot: empty"><ha-icon icon="${SLOT_ICON[slotIfEmpty]}"></ha-icon></span>`;
    }
    const img = painted(item.art) ? `<img class="paint" src="${esc(item.art)}" width="${24 * scale + 4}" height="${24 * scale + 4}" alt="${esc(item.name)}">`
      : `<img src="${itemIconArt(item)}" width="${24 * scale}" height="${24 * scale}" alt="${esc(item.name)}">`;
    return `<span class="icon r-${item.rarity}" style="--rc:${RARITY[item.rarity]};width:${size}px;height:${size}px">${img}
      ${item.enh ? `<b class="enh">+${item.enh}</b>` : ""}</span>`;
  }

  /** A labyrinth guardian: its painting, or pixel art from its kind, element and seed. */
  function monster(kind, element, seed, scale = 4, cls = "", pic = null) {
    const art = painted(pic);
    if (art) return `<img class="mon paint ${cls}" src="${esc(art)}" width="${48 * scale}" height="${48 * scale}" style="--mg:${ELEMENT_C[element] || "#9b7bff"}" alt="${esc(cap(element))} ${esc(kind)}">`;
    const m = monsterArt(kind, element, seed);
    return `<img class="mon ${cls}" src="${m.src}" width="${48 * scale}" height="${48 * scale}" style="--mg:${m.glow}" alt="${esc(cap(element))} ${esc(kind)}">`;
  }

  /** A badge medal at its tier. */
  function medal(b, size = 58) {
    const c = TIERC[Math.min(b.tier, 5)];
    const stars = b.tier > 5 ? b.tier - 5 : 0;
    return `<div class="medal ${b.tier ? "" : "locked"}" style="--c:${c}">
      <svg width="${size}" height="${size}" viewBox="0 0 60 60" aria-hidden="true"><polygon points="30,3 54,16 54,44 30,57 6,44 6,16" fill="${c}" fill-opacity="${b.tier ? 0.22 : 0.06}" stroke="${c}" stroke-width="2.5"/></svg>
      <ha-icon icon="${b.icon}"></ha-icon>${stars ? `<i class="stars">★${stars}</i>` : ""}</div>`;
  }


  const CHEST_C = { daily: "#45b8ff", perfect: "#f5c451", level: "#4fd18b", record: "#ffa640", emergency: "#ff3d57", hidden: "#b072ff", blessed: "#e2a8e0", rank: "#ff5a5a", guardian: "#7b5cff", choice: "#3de0d0", wager: "#ff7ae0" };
  /** A chest of one kind (a special one glows red). */
  function chestArt(kind, special) {
    const c = special ? "#ff3d57" : CHEST_C[kind] || "#45b8ff";
    return `<svg class="chest" width="64" height="56" viewBox="0 0 32 28" shape-rendering="crispEdges" aria-hidden="true">
      <g class="lid"><rect x="4" y="4" width="24" height="2" fill="${c}"/><rect x="3" y="6" width="26" height="6" fill="${c}" fill-opacity=".45"/><rect x="3" y="6" width="26" height="1" fill="#fff" fill-opacity=".35"/></g>
      <rect x="3" y="12" width="26" height="13" fill="${c}" fill-opacity=".25"/><rect x="3" y="12" width="26" height="1" fill="${c}"/>
      <rect x="3" y="24" width="26" height="1" fill="${c}"/><rect x="3" y="12" width="1" height="13" fill="${c}"/><rect x="28" y="12" width="1" height="13" fill="${c}"/>
      <rect x="9" y="6" width="2" height="19" fill="${c}" fill-opacity=".7"/><rect x="21" y="6" width="2" height="19" fill="${c}" fill-opacity=".7"/>
      <rect x="14" y="10" width="4" height="5" fill="${c}"/><rect x="15" y="12" width="2" height="2" fill="#040815"/></svg>`;
  }

  /** A progress bar with an accessible label. */
  function bar(value, max, cls = "", label = "") {
    return `<div class="bar ${cls}" role="progressbar" aria-valuenow="${Math.round(pct(value, max))}" aria-valuemin="0" aria-valuemax="100" ${label ? `aria-label="${esc(label)}"` : ""}><i style="width:${pct(value, max)}%"></i></div>`;
  }

  /** XP per day as bars, coloured perfect, cleared or missed. */
  function historyChart(hist) {
    if (!hist?.length) return '<p class="muted">No history yet.</p>';
    const max = Math.max(...hist.map((h) => h.xp), 1), w = 300, h = 80, bw = w / hist.length;
    return `<svg class="hist" viewBox="0 0 ${w} ${h + 14}" preserveAspectRatio="none" role="img" aria-label="XP over the last ${hist.length} days">
      ${hist.map((d, i) => { const bh = Math.max(2, (d.xp / max) * h); return `<rect x="${i * bw + 1}" y="${h - bh}" width="${bw - 2}" height="${bh}" rx="1.5" fill="${d.p ? "#f5c451" : d.c ? "#45b8ff" : "#2a3b57"}"><title>${esc(d.d)}: ${num(d.xp)} XP${d.p ? ", perfect" : d.c ? ", cleared" : ""}</title></rect>`; }).join("")}
    </svg><div class="legend"><span><i style="background:#f5c451"></i>Perfect</span><span><i style="background:#45b8ff"></i>Cleared</span><span><i style="background:#2a3b57"></i>Missed</span></div>`;
  }

  /** One line about the painter: painting, queued, or ComfyUI offline. */
  function studioLine(v) {
    const st = v.art && v.art.studio;
    if (!st || st.state === "off" || st.state === "idle") return "";
    if (st.state === "offline") return `<p class="small studio warn-t" title="${esc(st.error || "")}">ComfyUI is offline. Paintings will resume.</p>`;
    return `<p class="small studio muted">Painting${st.queue > 1 ? ` · ${st.queue} in the queue` : ""}</p>`;
  }
  const today = (v) => v.now.slice(0, 10);
  const loreFor = (v, kind, ref) => { const l = (v.lore || {})[kind]; return l && l.ref === ref ? l.text : null; };

  // Hand logging: water goes in the adventurer's unit (a glass is 250 mL or 8 fl oz).
  const waterUnit = (v) => ((v.quests || {}).hydration || {}).unit || "mL";
  const GLASS = (v) => (waterUnit(v) === "fl oz" ? 8 : 250);
  const unitOf = (k, q) => (k === "steps" ? "" : q.unit || QUEST_UNIT[k] || "");
  /** The quick-log buttons for a quest: [amount, label] pairs. */
  function logSteps(q, v) {
    if (q === "floors") return [[1, "+1 flight"], [3, "+3"], [-1, "Undo 1"]];
    if (q !== "hydration") return [];
    const u = waterUnit(v), g = GLASS(v);
    return [[g, "+1 glass"], [g * 2, `+${g * 2} ${u}`], [-g, `Undo ${g}`]];
  }
  /** The row of quick-log buttons, plus how much was logged by hand today. */
  function logRow(q, v) {
    const steps = logSteps(q, v);
    if (!steps.length) return "";
    const today = (v.manual_log || {})[q] || 0;
    return `<div class="logrow">${steps.map(([n, label]) => `<button class="btn small" data-log="${q}" data-amount="${n}" ${n < 0 && today <= 0 ? "disabled" : ""}>${esc(label)}</button>`).join("")}
      ${today ? `<span class="small muted">${num(today)} ${q === "hydration" ? esc(waterUnit(v)) : "flights"} logged today</span>` : ""}</div>`;
  }
  // a quest whose sensor has said nothing today (Samsung Health doesn't share water or floors, some phones no sleep start)
  const QUIET_HINT = { hydration: "water", floors: "floors", sleep: "sleep", bedtime: "when you fell asleep" };
  function quiet(k, q, v) {
    if (q.value != null || !QUIET_HINT[k] || Number(v.now.slice(11, 13)) < 12) return "";
    const logged = (v.manual || []).includes(k === "bedtime" ? "sleep" : k);
    if (logged) return "";
    return `<p class="small muted quiet">No ${QUIET_HINT[k]} from your phone today. If your health app doesn't share it (Samsung Health keeps water and floors to itself), tick ${k === "bedtime" || k === "sleep" ? "Rest and Lights out" : k === "floors" ? "Climb" : "Drink water"} under Configure → Quests and goals → Log in Home Assistant and log it here.</p>`;
  }
  // sensor sanity: what the guard held back, and a way to set the real count (or record) by hand
  const FIXABLE = ["steps", "floors", "hydration"];
  function fixRow(k, q, v, open) {
    const u = unitOf(k, q) || "steps";
    const held = q.held ? `<div class="held small"><span>${num(q.held)} ${esc(u)} held back: the sensor jumped faster than anyone could manage, so they weren't counted.</span>
      ${q.fixable ? `<button class="btn small" data-act="accept_held" data-quest="${k}">They were real</button>` : `<span class="muted">If they were real, turn on corrections for this quest under Configure → Quests and goals.</span>`}</div>` : "";
    if (!q.fixable) return held;
    if (!open) return `${held}<button class="fixlink small" data-fix="${k}">Wrong count?</button>`;
    return `${held}<form class="fixform" data-fix-form="${k}">
      <label class="small">Today's real count <input name="today" type="number" min="0" step="any" inputmode="decimal" placeholder="${q.value ?? ""}"></label>
      <label class="small">Best ever <input name="record" type="number" min="0" step="any" inputmode="decimal" placeholder="${q.record ?? ""}"></label>
      <div class="row tight"><button class="btn small gold">Save</button><button type="button" class="btn small ghost" data-fix="">Cancel</button></div>
      <p class="small muted">Counting the same steps twice (say, the phone and a watch app both writing to Health Connect)? Set today's real count here; later readings carry on from it.</p></form>`;
  }

  // Whole days left until a date (when this week's guardian leaves).
  const daysLeft = (iso) => Math.max(0, Math.ceil((new Date(iso + "T23:59:59") - Date.now()) / 86400000));

  // ---------------------------------------------------------------- shared windows (panel and cards)
  const V = {
    // The main window: name, level, rank, job, title, streak and meters.
    status(v, name, can) {
      const q = v.quests, job = v.job;
      // HP is last night's rest, MP today's water; both top out at 100% (the quests themselves can go past it)
      const hp = q.sleep ? [Math.min(q.sleep.pct, 100), "HP", "Rest"] : null, mp = q.hydration ? [Math.min(q.hydration.pct, 100), "MP", "Water"] : null;
      const meter = ([p, k, label], cls) => `<div class="row small"><b class="mk">${k}</b><div class="bar ${cls}" style="flex:1" role="progressbar" aria-label="${label}" aria-valuenow="${p}" aria-valuemin="0" aria-valuemax="100"><i style="width:${Math.min(p, 100)}%"></i></div><span class="pv">${p}%</span></div>`;
      return `<section class="win hero">
        <div class="wt">Status</div>
        ${v.daily_title ? `<p class="episode">${esc(v.daily_title)}</p>` : ""}
        <div class="status">
          <div class="portrait-col">${portrait(v, v.gear.equipped)}
            ${studioLine(v)}
            ${can ? `<div class="row center-row tight"><button class="btn ghost small" data-act="restyle" title="New hair, colours and features">Change look</button>
</div>` : ""}</div>
          <div class="stack">
            <div class="row between"><div><div class="name">${esc(name)}</div><div class="muted">${esc(v.title ? "“" + v.title.name + "”" : "No title")}</div></div>${rankEmblem(v.rank, 60)}</div>
            <div class="lvl"><b>${v.level}</b><span>Level</span></div>
            <div>${bar(v.level_xp, v.level_span, "thick", "Experience")}<div class="row between small muted"><span>EXP ${num(v.level_xp)} / ${num(v.level_span)}</span><span>${v.progress}%</span></div></div>
            ${hp ? meter(hp, "red") : ""}${mp ? meter(mp, "") : ""}
            ${hp || mp ? `<p class="small muted meters-note">${[hp ? "HP is last night's rest" : "", mp ? "MP is today's water: it starts empty each morning and fills as you drink" : ""].filter(Boolean).join(". ")}.</p>` : ""}
            <dl class="kv">
              <dt>Job</dt><dd>${job ? `${esc(job.title)} <span class="muted">· ${esc(job.name)} Lv ${job.level}</span>` : v.level >= v.job_unlock_level ? '<span class="gold-t">Choose a job in the Class tab</span>' : `Villager <span class="muted">(jobs at Lv ${v.job_unlock_level})</span>`}</dd>
              <dt>Race</dt><dd>${esc(v.race.name)} · ${esc(v.race.gift.name)}</dd>
              <dt>Rank</dt><dd>${esc(v.rank)}-rank${v.next_rank_level ? ` <span class="muted">(next at Lv ${v.next_rank_level})</span>` : ""}</dd>
              <dt>Streak</dt><dd>${plural(v.streak, "day")} · ${plural(v.shields, "shield")} · ×${v.multiplier} XP</dd>
              <dt>Gear score</dt><dd>${num(v.gear.score)}</dd>
            </dl>
          </div>
        </div>
      </section>`;
    },
    // Attribute points and how far each is from the next point.
    attributes(v) {
      return `<section class="win">
        <div class="wt">Attributes</div>
        <div class="attrs">${Object.entries(v.attrs).map(([k, a]) => `<div class="attr" title="${num(a.next_point_xp)} XP to the next point"><ha-icon icon="${ATTR_ICON[k]}"></ha-icon><span>${esc(a.short)}</span><b>${a.points}</b></div>`).join("")}</div>
        <div class="wt" style="margin-top:18px">Skills</div>
        <div class="skills">${Object.values(v.skills).map((s) => `<div class="skill"><div class="row between"><b>${esc(s.name)}</b><span class="grade">${esc(s.grade)}</span></div>${bar(s.progress, 100, "violet", s.name)}</div>`).join("")}</div>
        <div class="wt" style="margin-top:18px">Active bonuses</div>
        ${(() => { const caps = v.bonus_caps || {}, capped = caps.capped || [], held = new Set(capped.map((c) => c.effect));
          const chips = Object.entries(v.effects || {}).filter(([, x]) => x).map(([k, x]) =>
            `<span class="chip ${held.has(k) ? "gold" : ""}">${esc(EFFECT_LABEL(k, k === "over" ? x : Math.round(x * 10) / 10))}${held.has(k) ? " (max)" : ""}</span>`).join("");
          return `<div class="chips">${chips || '<span class="muted">None yet. Equip gear, pick a job and earn titles.</span>'}</div>
          ${capped.length ? `<p class="small capnote">${capped.map((c) => `${esc(capName(c.effect))} is held at its ${esc(c.max)} limit (your bonuses add up to ${esc(capAmount(c.effect, c.total))})`).join(". ")}.</p>` : ""}
          ${(v.bonus_sources || []).length ? `<details class="sources"><summary class="small">Where they come from, and the limits</summary>
            ${v.bonus_sources.map((b) => `<div class="src"><span class="small">${esc(b.name)}</span><span class="small muted">${esc(effectList(b.effects).join(", "))}</span></div>`).join("")}
            <p class="small muted"><b>Limits:</b> ${(caps.limits || []).map((l) => `${esc(l.name)} ${esc(l.max)}`).join(", ")}. Potions and tonics count on top of these limits.</p></details>` : ""}`; })()}
      </section>`;
    },
    // The Today box: XP so far and how the day is going.
    today(v) {
      const lab = v.labyrinth;
      return `<section class="win">
        <div class="wt">Today</div>
        <div class="row between today">
          <div><div class="count">${num(v.xp_today)}</div><div class="muted small center-text">XP today</div></div>
          <div><div class="count">${v.done}/${Object.keys(v.quests).length}</div><div class="muted small center-text">Quests</div></div>
          <div><div class="count">${lab.defeated ? "✓" : lab.pct + "%"}</div><div class="muted small center-text">Floor ${lab.floor} guardian</div></div>
        </div>
        <blockquote style="margin-top:14px">${esc((Number(v.now.slice(11, 13)) < 12 && loreFor(v, "morning", today(v))) || v.goddess.line)}<div class="small muted" style="font-style:normal;margin-top:6px">${esc(v.goddess.name)}, ${esc(v.goddess.title)}</div></blockquote>
      </section>`;
    },
    // The daily choice and its Accept and Decline buttons.
    choice(v, can) {
      const c = v.choice;
      if (!c) return "";
      const result = { won: ["gold", "Choice won", `+${num(c.reward_xp)} XP was yours.`], lost: ["red", "Choice lost", "The terms weren't met this time."],
        declined: ["", "Choice declined", "You walked on. Another offer comes tomorrow."], expired: ["", "Choice expired", "No answer before the deadline."],
        done: ["", "Trade complete", "The trade ran its course."],
        accepted: ["violet", "Choice accepted", c.kind === "trade" ? "The trade is in effect for the rest of today."
          : "The terms are set. It resolves when they're met, or at midnight."] }[c.status];
      if (c.status !== "offered" && !result) return "";
      const tone = c.status === "offered" ? "violet" : result[0];
      return `<section class="win ${tone} choice">
        <div class="wt">${c.status === "offered" ? "A choice appears" : result[1]}</div>
        <div class="npc">${painted(c.art) ? (c.voice_index === 1 ? framed(esc(c.art), "closeup", "npc-face", v.goddess.name, 1) : `<img src="${esc(c.art)}" alt="">`) : bust(npcArt(c.voice_index ?? 0), 72, "npc-bust")}<div>
          <p class="voice">${esc(c.voice)}</p>${loreFor(v, "choice", today(v)) ? `<p class="speech">“${esc(loreFor(v, "choice", today(v)))}”</p>` : ""}</div></div>
        <p class="offer">${esc(c.text)}</p>
        ${c.status === "offered"
          ? can ? `<div class="row center-row"><button class="btn gold" data-act="answer_choice" data-accept="1">${esc(c.accept || "Accept")}</button><button class="btn ghost" data-act="answer_choice" data-accept="0">Not today</button></div>
              <p class="small muted center-text">Answer before ${esc(c.deadline)}. Reward: ${num(c.reward_xp)} XP${c.chest ? ` and a ${esc(c.chest.name)}` : ""}.</p>
              ${c.chest ? `<p class="small muted center-text odds">The ${esc(c.chest.name)} holds one item: ${Object.entries(c.chest.odds).map(([r, p]) => `<span class="r-${r}">${r} ${p}%</span>`).join(", ")}.</p>` : ""}` : `<p class="small muted center-text">Waiting for an answer.</p>`
          : `<p class="small center-text">${esc(result[2])}</p>`}
      </section>`;
    },
    // Each quest's progress, with quick logging and corrections where they're allowed.
    quests(v, can, fix = null) {
      const qs = Object.entries(v.quests), e = v.emergency, p = v.penalty;
      return `${e && e.status === "active" ? `<section class="win red"><div class="wt">Emergency quest</div>
          <p class="center-text big-line">${esc(e.title)}</p>
          ${loreFor(v, "emergency", today(v)) ? `<p class="center-text speech">${esc(loreFor(v, "emergency", today(v)))}</p>` : ""}
          ${bar(e.progress, e.target, "red thick")}
          <div class="row between small"><span>${num(Math.round(e.progress))} / ${num(e.target)}</span><span>Time left <b data-end="${esc(e.end)}">--:--</b></span></div>
          ${e.excused ? `<p class="small center-text glitch">Reward: XP and an emergency chest. Failing penalty: −${num(e.fine)} gold… <span>ERR0R. ERROR. Working hours detected.</span> Failing costs nothing.</p>`
            : `<p class="small muted center-text">Reward: XP and an emergency chest. Failing costs <b>${num(e.fine)}</b> gold${e.decline_fine ? `; declining costs ${num(e.decline_fine)}` : ""}.</p>`}
          ${can ? `<div class="center-text"><button class="btn ghost" data-act="decline_emergency">${!e.excused && e.decline_fine ? `Decline (−${num(e.decline_fine)} gold)` : "Decline"}</button></div>` : ""}</section>` : ""}
        ${p && !p.met ? `<section class="win red"><div class="wt">Penalty quest</div>
          <p class="center-text big-line">Survive the penalty zone</p>
          <p class="center-text">Finish <b>${p.need}</b> quests today to restore your <b>${p.streak}-day</b> streak.</p>
          ${bar(v.done, p.need, "red thick")}<p class="center-text small">${v.done} / ${p.need}</p></section>` : ""}
        ${p && p.met ? `<section class="win gold"><div class="wt">Penalty survived</div><p class="center-text">Your ${p.streak}-day streak is safe. It continues at midnight.</p></section>` : ""}
        <section class="win">
          <div class="wt">Daily quest</div>
          <p class="center-text muted small">Clear ${v.needed} of ${qs.length} quests to secure the day.</p>
          ${qs.map(([k, q]) => `<div class="q ${q.done ? "done" : ""}">
            <div class="check">${q.done ? "✓" : ""}</div>
            <div>${esc(q.name)} <span class="muted small">· ${esc(q.attr)}</span>${q.streak > 1 ? ` <span class="chip">${q.streak}d</span>` : ""}</div>
            <div class="val">[${q.value == null ? "–" : esc(typeof q.value === "number" ? num(q.value) : q.value)}/${esc(typeof q.goal === "number" ? num(q.goal) : q.goal)}${unitOf(k, q) ? " " + esc(unitOf(k, q)) : ""}]</div>
            ${bar(q.pct, 100, q.done ? "gold" : "", q.name)}
            ${can && (v.manual || []).includes(k) ? logRow(k, v) : ""}
            ${can && FIXABLE.includes(k) ? fixRow(k, q, v, fix === k) : ""}
            ${quiet(k, q, v)}
          </div>`).join("")}
          ${can && (v.manual || []).includes("sleep") ? `<form class="sleeplog" data-sleep>
            <b class="small">Log last night's sleep</b>
            <label class="small">Fell asleep <input type="time" name="bedtime" data-keep="bed" required></label>
            <label class="small">Woke up <input type="time" name="wake" data-keep="wake" aria-describedby="wake-note"></label>
            <button class="btn small">Log sleep</button><p class="small muted" id="wake-note">Leave "Woke up" empty to log only Lights out (when your sleep app counts the rest).</p></form>` : ""}
          <div class="row between" style="margin-top:12px"><span>${v.cleared ? '<b class="gold-t">Day secured</b>' : `${Math.max(v.needed - v.done, 0)} more to secure the day`}</span><span class="muted">${num(v.xp_today)} XP · ×${v.multiplier}</span></div>
          <p class="warn">Losing your streak without a shield opens a penalty quest.</p>
        </section>`;
    },
    // the bounty board: a parent's chores (kids mode) and today's small side quests
    bounties(v, can, parent) {
      const list = v.bounties || [], manage = !!(v.kids_mode && parent && can);
      const chores = list.filter((b) => b.source === "chore"), daily = list.filter((b) => b.source === "daily");
      if (!list.length && !manage) return "";
      const reward = (b) => [b.xp ? `${num(b.xp)} XP` : "", b.gold ? `${num(b.gold)} gold` : "", b.chest ? "a bounty chest" : ""].filter(Boolean).join(", ");
      const btn = (b, act, label, cls = "gold") => `<button class="btn small ${cls}" data-bounty="${b.id}" data-bact="${act}">${label}</button>`;
      const row = (b) => `<div class="bounty ${b.state}"><div><b>${esc(b.title)}</b>
          <div class="small muted">${esc(reward(b))}${b.source === "chore" && b.repeat !== "once" ? `, ${esc(b.repeat)}` : ""}</div></div>
        <div class="row tight">${b.state === "open" && can ? btn(b, "claim", "Done")
          : b.state === "claimed" ? (manage ? `${btn(b, "approve", "Approve")}${btn(b, "reject", "Not yet", "ghost")}` : '<span class="small gold-t">Waiting for a parent</span>')
          : b.state === "done" ? '<span class="small muted">Done for now</span>' : ""}
          ${manage && b.source === "chore" ? btn(b, "remove", "Remove", "ghost") : ""}</div></div>`;
      const form = manage ? `<form class="choreform" data-chore>
          <label class="small wide">New chore <input name="title" maxlength="80" required placeholder="Feed the dog" autocomplete="off"></label>
          <label class="small">XP <input name="xp" type="number" min="0" max="300" value="50"></label>
          <label class="small">Gold <input name="gold" type="number" min="0" max="300" value="20"></label>
          <label class="small">Repeats <select name="repeat"><option value="once">Once</option><option value="daily">Every day</option><option value="weekly">Every week</option></select></label>
          <label class="small check"><input name="chest" type="checkbox"> Bounty chest</label>
          <button class="btn small gold">Post chore</button></form>` : "";
      return `<section class="win gold"><div class="wt">Bounty board</div>
        ${chores.length || manage ? `<h4 class="bh">Chores</h4>${chores.map(row).join("") || '<p class="small muted">No chores posted yet.</p>'}
          ${v.kids_mode && !manage ? '<p class="small muted">Tap Done when a chore is finished; a parent approves it and the reward arrives.</p>' : ""}${form}` : ""}
        ${daily.length ? `<h4 class="bh">Today's side quests</h4>${daily.map(row).join("")}
          <p class="small muted">Small extras, on your honour. New ones arrive each morning.</p>` : ""}
      </section>`;
    },
    // This week's labyrinth guardian, its HP and the floor's trait.
    guardian(v) {
      const g = v.labyrinth, tone = g.cursed ? "red" : g.elite ? "gold" : "violet";
      const left = daysLeft(g.ends);
      return `<section class="win ${tone}">
        <div class="wt">Labyrinth · floor ${g.floor}</div>
        <div class="guardian">
          <div class="lair ${g.defeated ? "felled" : ""}" style="--ec:${ELEMENT_C[g.element] || "#9b7bff"}">${monster(g.kind, g.element, g.seed, painted(g.art) ? 5 : 4, "", g.art)}${g.defeated ? '<span class="felled-tag">Defeated</span>' : ""}</div>
          <div class="stack">
            <div><div class="name">${esc(g.name)}</div>
              <div class="chips" style="margin-top:6px"><span class="chip el" style="--ec:${ELEMENT_C[g.element]}">${esc(cap(g.element))}</span><span class="chip">${esc(cap(g.kind))}</span>
              ${g.elite ? '<span class="chip gold">Elite</span>' : ""}${g.cursed ? '<span class="chip red">Cursed</span>' : ""}</div></div>
            <div>${bar(g.hp - g.damage, g.hp, `${tone} thick`, "Guardian HP")}<div class="row between small"><span>${num(g.hp - g.damage)} / ${num(g.hp)} HP</span><span>${g.pct}%</span></div></div>
            ${loreFor(v, "guardian", g.floor) ? `<p class="speech small">${esc(loreFor(v, "guardian", g.floor))}</p>` : ""}
            <div class="trait"><b>${esc(g.trait.name)}</b><div class="small">${esc(g.trait.desc)}</div></div>
            <p class="small">${g.defeated ? `Defeated. +${num(g.reward)} XP and a guardian chest were yours. Floor ${g.floor + 1} opens on Monday.`
              : `Every quest XP you earn hits the guardian. ${left ? `${plural(left, "day")} left this week.` : "Last day."} Reward: ${num(g.reward)} XP and a rank-${esc(g.rank)} chest.`}</p>
          </div>
        </div>
      </section>`;
    },
  };


  // ---------------------------------------------------------------- the panel
  // the Gallery: every painting in one place, each with its own Repaint (only when paintings are on)
  const eta = (sec) => sec < 90 ? "a minute" : sec < 5400 ? `${Math.round(sec / 60)} minutes` : `${Math.round(sec / 3600)} hours`;
  const galleryOn = (v) => !!(v.art && v.art.style === "painted" && v.art.studio && v.art.studio.state !== "off");
  /** One painting in the Gallery, with Repaint (or a note while it's waiting to be painted). */
  function galleryTile(url, label, can, studio, opts = {}) {
    const busy = url && (studio.repainting || []).some((k) => url.includes(k));
    const pic = !url ? `<div class="gwait">${esc(opts.wait || "Not painted yet")}</div>`
      : opts.framing ? framed(esc(url), opts.framing, "", label) : `<img src="${esc(url)}" alt="${esc(label)}" loading="lazy">`;
    return `<figure class="gtile ${opts.square ? "square" : ""} ${opts.base ? "base" : ""}">${pic}
      <figcaption><span class="gname" title="${esc(label)}">${esc(label)}</span>${busy ? '<span class="small gold-t">Repainting…</span>'
        : url && can ? `<button class="btn ghost small" data-repaint="${esc(url)}" aria-label="Repaint ${esc(label)}">Repaint</button>` : ""}
        ${opts.note ? `<span class="gnote">${esc(opts.note)}</span>` : ""}</figcaption></figure>`;
  }
  // How you, the goddess and the merchant are painted. Each choice says what it changes: framing only crops (nothing is
  // repainted); outfit, accessory, what you hold and the backdrop are edits of the base painting (the face stays); race,
  // age, build, hair and eyes are who they are, so they paint a new base painting and everything after it.
  const TIER = { framing: "view", weapon: "edit", outfit: "edit", accessory: "edit", backdrop: "edit" };
  const PREF_LABELS = { race: "Race", age: "Age", build: "Build", framing: "Framing", hair: "Hair colour", fur: "Fur colour",
    hairstyle: "Hairstyle", eyes: "Eye colour", weapon: "In hand", outfit: "Outfit", accessory: "Accessory", backdrop: "Backdrop" };
  const PREF_NAMES = { kid: "Kid", teen: "Teen", young_adult: "Young adult", adult: "Adult", elderly: "Elderly",
    full: "Full body", three_quarter: "Three-quarter", half: "Waist up", bust: "Head and shoulders", closeup: "Close-up (face)",
    equipped: "Equipped weapon", none: "Nothing", human: "Human", elf: "Elf", half_elf: "Half-elf", dwarf: "Dwarf",
    beastkin: "Beastkin", dragonkin: "Dragonkin", celestial: "Celestial", gnome: "Gnome", halfling: "Halfling", goblin: "Goblin",
    petite: "Petite", slender: "Slender", average: "Average", athletic: "Athletic", sturdy: "Sturdy", wiry: "Wiry", slight: "Slight",
    stout: "Stout", broad: "Broad-shouldered", heavyset: "Heavyset", lanky: "Tall and lanky", muscular: "Muscular", stocky: "Stocky",
    ribbons: "Long, with ribbon bows", long: "Long and loose", braid: "Braid", updo: "Updo", twintails: "Twin tails", bob: "Bob",
    short: "Short", crown_braid: "Crown braid", spiky: "Spiky", ponytail: "Ponytail", swept: "Swept aside",
    moonlit: "Moonlit (indigo and lilac)", starlight: "Starlight gown", dawn: "Dawn gown", priestess: "Priestess robes",
    cosy: "Cosy cardigan", armoured: "Moon armour", huntress: "Huntress", winter: "Winter", festival: "Festival",
    scholar: "Scholar's robes", traveller: "Travelling cloak", ballgown: "Silver ballgown", modern: "Modern (hoodie)",
    ethereal: "Ethereal veils", muttonchops: "White mutton-chops", ginger: "Ginger beard", grey: "Long grey beard",
    bald: "Bald, clean-shaven", moustache: "Curly moustache", wild: "Wild white hair", stubble: "Stubble",
    monocle: "Brass monocle", spectacles: "Spectacles", goggles: "Tinker's goggles", eyepatch: "Eyepatch", pipe: "Long pipe",
    hat: "Feathered hat", scales: "Merchant's scales", waistcoat: "Patched waistcoat", coat: "Travelling coat",
    apron: "Work apron", finery: "Fine coat", cloak: "Hooded cloak", sailor: "Sailor's coat", desert: "Desert robes",
    noble: "Noble's doublet", tinker: "Tinker's harness", shrine: "Her shrine (grows with devotion)", mood: "Match each mood",
    night_sky: "Night sky", garden: "Temple garden", lake: "Moonlit lake", library: "Star library", forest: "Birch forest",
    plain: "Plain grey", wagon: "Lantern-lit wagon", market: "Market stall", tavern: "Tavern table", caravan: "Caravan tent",
    shop: "Cramped shop", harbour: "Harbour stall" };
  const PREFS = {
    portrait: { action: "set_portrait_prefs", them: "you",
      fields: (v) => ["age", v.race.id === "beastkin" ? "fur" : "hair", "hairstyle", "eyes", "build", "weapon", "framing"],
      defaults: { framing: "full", weapon: "equipped" }, blank: { age: "Not set" }, unset: "As rolled",
      choices: (v) => v.portrait_choices, prefs: (v) => v.portrait_prefs },
    goddess: { action: "set_goddess_prefs", them: "her",
      fields: () => ["race", "age", "build", "hair", "hairstyle", "eyes", "outfit", "backdrop", "framing"],
      defaults: { race: "human", age: "young_adult", hair: "chestnut-brown", hairstyle: "ribbons", eyes: "violet", outfit: "moonlit",
        backdrop: "shrine", framing: "three_quarter" }, blank: {}, unset: "Not set",
      choices: (v) => v.goddess.choices, prefs: (v) => v.goddess.prefs },
    merchant: { action: "set_merchant_prefs", them: "him",
      fields: () => ["race", "age", "build", "hair", "outfit", "accessory", "backdrop", "framing"],
      defaults: { race: "gnome", build: "wiry", outfit: "waistcoat", accessory: "monocle", backdrop: "wagon", framing: "bust" },
      blank: {}, unset: "Not set", choices: (v) => (v.market || {}).choices, prefs: (v) => (v.market || {}).prefs },
  };
  /** The appearance form for you, the goddess or the merchant, grouped by what a change costs:
   * shown differently (a crop), edited from the base painting, or a new base painting. */
  function prefsForm(kind, v) {
    const cfg = PREFS[kind], c = cfg.choices(v) || {}, p = cfg.prefs(v) || {}, edit = !!(v.art && v.art.edit);
    const nice = (o) => PREF_NAMES[o] || (/^[A-Z]/.test(o) ? o : o.charAt(0).toUpperCase() + o.slice(1).replace(/_/g, " "));
    const field = (k) => `<label class="small">${(kind === "merchant" && k === "hair") ? "Hair and beard" : PREF_LABELS[k]}<select name="${k}">
      <option value="">${esc(cfg.blank[k] || (cfg.defaults[k] ? nice(cfg.defaults[k]) : cfg.unset))}</option>
      ${c[k].filter((o) => o !== cfg.defaults[k]).map((o) => `<option value="${esc(o)}" ${p[k] === o ? "selected" : ""}>${esc(nice(o))}</option>`).join("")}</select></label>`;
    const keys = cfg.fields(v).filter((k) => c[k]);
    const group = (tier, title, note) => { const ks = keys.filter((k) => (TIER[k] || "base") === tier);
      return ks.length ? `<fieldset class="tier t-${tier}"><legend class="small">${title}</legend><p class="small muted">${note}</p><div class="tierf">${ks.map(field).join("")}</div></fieldset>` : ""; };
    return `<form class="prefs tiers" data-prefs="${kind}">
        ${group("view", "Shown differently", "Crops the full-body painting. Nothing is repainted.")}
        ${group("edit", edit ? "Edited from the base painting" : "Repainted", edit ? `The base stays, so ${cfg.them === "you" ? "your" : cfg.them === "her" ? "her" : "his"} face stays. Every picture is edited again.` : "Every picture is painted again.")}
        ${group("base", edit ? "A new base painting" : "Repainted", edit ? `Who ${cfg.them === "you" ? "you are" : cfg.them === "her" ? "she is" : "he is"}: a new base painting, then every picture is edited from it.` : `Who ${cfg.them === "you" ? "you are" : cfg.them === "her" ? "she is" : "he is"}: every picture is painted again.`)}
        <div class="prefs-go"><button class="btn gold small">Save</button></div></form>`;
  }
  const TABS = [["status", "Status"], ["quests", "Quests"], ["labyrinth", "Labyrinth"], ["inventory", "Inventory"], ["market", "Market"], ["class", "Class"], ["records", "Records"], ["goddess", "Goddess"], ["log", "Log"]];

  /** The sidebar panel. Home Assistant sets `hass`, `narrow` and `panel`; everything else is drawn from
   * the subscribed view. */
  class LifeRpgPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this.tab = "status";
      this.state = null;
      this.sel = null; // selected item id
      this.reveal = null; // last opened item
      this.toasts = [];
      this.allTitles = false;
      this.haggleId = null; // stock item being haggled over
      this.luneMood = null; // mood of Lune's last reply
      this.busy = null; // "lune" | "merchant" while waiting for a reply
      this.pending = null; // the line just sent, shown until the reply arrives
    }
    set hass(hass) {
      const first = !this._hass;
      this._hass = hass;
      if (first) this.load();
      else this.menu();
    }
    set narrow(v) { this._narrow = v; this.menu(); }
    set panel(v) {}
    // Pass hass to the sidebar menu button (it shows only on narrow screens).
    menu() {
      const mb = this.shadowRoot.querySelector("ha-menu-button");
      if (mb) { mb.hass = this._hass; mb.narrow = this._narrow; }
    }
    connectedCallback() {
      this.tick = setInterval(() => this.countdown(), 1000);
      if (this._hass && this.entryId && !this.unsub) this.watch(this.entryId);
    }
    disconnectedCallback() {
      clearInterval(this.tick);
      this.unsub?.();
      this.unsub = null;
    }
    // Find the viewer's own adventurer (or let them pick one to watch).
    async load() {
      try {
        this.party = await players(this._hass);
      } catch (e) {
        this.party = { players: [], error: e.message };
      }
      const mine = this.party.players.find((p) => p.mine) || (this.party.is_admin && this.party.players[0]);
      if (mine) this.watch(mine.entry_id);
      else this.render();
    }
    // Switch to an adventurer's view; new events become toasts.
    watch(entryId) {
      this.unsub?.();
      if (entryId !== this.entryId) { this.state = null; this.sel = null; this.reveal = null; }
      this.entryId = entryId;
      this.unsub = subscribe(this._hass, entryId, (msg, replay) => {
        const wasLoaded = !!this.state;
        this.state = msg;
        setClock(msg.view);
        if (wasLoaded && !replay) msg.view.events.forEach((e) => this.toast(e));
        this.render();
      });
      this.render();
    }
    // Show an event as a toast (big ones stay longer).
    toast(e, override = {}) {
      const [title, msg, tone] = describe(e);
      const t = { id: Math.random(), title, msg: e.gold ? `${msg} +${num(e.gold)} gold.` : msg, tone, big: BIG.has(e.type), ...override };
      this.toasts = [...this.toasts.slice(-3), t];
      this.renderToasts();
      setTimeout(() => { this.toasts = this.toasts.filter((x) => x !== t); this.renderToasts(); }, t.big ? 7000 : 4500);
    }
    renderToasts() {
      const box = this.shadowRoot.querySelector(".toasts");
      if (!box) return;
      box.innerHTML = this.toasts.map((t) => `<div class="toast win ${["red", "gold", "violet"].includes(t.tone) ? t.tone : ""} ${t.big ? "big" : ""}" role="status">
        <div class="wt">${esc(t.title)}</div><div class="msg">${esc(t.msg)}</div></div>`).join("");
    }
    // Tick every running timer (emergency quests) once a second without redrawing the page.
    countdown() {
      this.shadowRoot.querySelectorAll("[data-end]").forEach((el) => {
        const left = Math.max(0, new Date(el.dataset.end) - Date.now());
        el.textContent = `${String(Math.floor(left / 60000)).padStart(2, "0")}:${String(Math.floor((left % 60000) / 1000)).padStart(2, "0")}`;
      });
    }
    // Run an action; failures show as a red toast. Returns the action's result.
    async action(action, extra = {}) {
      try {
        const res = await act(this._hass, this.entryId, action, extra);
        return res?.result;
      } catch (e) {
        this.toast({ type: "error" }, { title: "Action failed", msg: e.message, tone: "red" });
        return undefined;
      }
    }

    // Redraw the page, keeping scroll position, focus and anything typed into inputs marked data-keep.
    render() {
      const root = this.shadowRoot;
      if (!root.querySelector("style")) {
        root.innerHTML = `<style>${CSS}${PANEL_CSS}</style><div class="page"></div><div class="toasts" aria-live="polite"></div>`;
        root.addEventListener("click", (ev) => this.onClick(ev));
        root.addEventListener("submit", (ev) => { ev.preventDefault(); this.onSubmit(ev.target); });
      }
      const y = this.scrollTop;
      const focus = root.activeElement && root.activeElement.dataset.keep;
      const kept = {};
      root.querySelectorAll("[data-keep]").forEach((el) => { kept[el.dataset.keep] = el.value; });
      root.querySelector(".page").innerHTML = this.page();
      root.querySelectorAll("[data-keep]").forEach((el) => { if (kept[el.dataset.keep]) el.value = kept[el.dataset.keep]; });
      if (focus) root.querySelector(`[data-keep="${focus}"]`)?.focus();
      root.querySelectorAll(".chatlog").forEach((el) => { el.scrollTop = el.scrollHeight; });
      this.menu();
      this.renderToasts();
      this.countdown();
      this.scrollTop = y;
    }

    // The whole page: header, tabs and the open tab.
    page() {
      if (!this.party) return `<div class="center"><div class="win"><div class="wt">System</div>Connecting…</div></div>`;
      if (!this.state) {
        const list = this.party.players;
        return `<div class="center"><div class="win" style="max-width:460px"><div class="wt">System</div>
          ${list.length ? `<p>You haven't been linked to an adventurer yet. Pick one to watch, or ask an admin to link your user in the Life RPG settings.</p>
            <div class="chips">${list.map((p) => `<button class="btn" data-watch="${esc(p.entry_id)}">${esc(p.name)} · Lv ${p.level ?? "?"}</button>`).join("")}</div>`
          : `<p>No adventurers have awakened yet. Add the Life RPG integration in Settings → Devices &amp; services to create one.</p>`}
          ${this.party.error ? `<p class="muted small">${esc(this.party.error)}</p>` : ""}</div></div>`;
      }
      const v = this.state.view;
      if (!this[`tab_${this.tab}`] || (this.tab === "gallery" && !galleryOn(v))) this.tab = "status";
      const alert = (v.emergency && v.emergency.status === "active") || (v.penalty && !v.penalty.met) || (v.choice && v.choice.status === "offered");
      const chests = v.gear.chests.length;
      const jobAlert = !v.job && v.level >= v.job_unlock_level;
      return `
        <header>
          <ha-menu-button></ha-menu-button>
          <div class="brand"><ha-icon icon="mdi:sword-cross"></ha-icon><span>System</span></div>
          ${v.art && v.art.style === "painted" ? `<button class="art-toggle" data-pixel title="Switch between paintings and pixel art on this device">${PIXEL ? "Pixel art" : "Paintings"}</button>` : ""}
          <button class="gold-chip" data-tab="market" title="Gold. Spend it at the Market."><ha-icon icon="mdi:cash-multiple"></ha-icon>${num(v.gold)}</button>
          ${this.party.players.length > 1 ? `<div class="party">${this.party.players.map((p) => `<button class="pchip ${p.entry_id === this.entryId ? "on" : ""}" data-watch="${esc(p.entry_id)}" title="${esc(p.job || "")}">${esc(p.name)} <small>${esc(p.rank || "")} · ${p.level ?? ""}</small></button>`).join("")}</div>` : ""}
        </header>
        <nav role="tablist">${TABS.concat(galleryOn(v) ? [["gallery", "Gallery"]] : []).map(([id, label]) => `<button role="tab" aria-selected="${this.tab === id}" class="${this.tab === id ? "on" : ""}" data-tab="${id}">${label}${id === "quests" && alert ? ' <i class="dot red"></i>' : ""}${id === "inventory" && chests ? ` <i class="dot">${chests}</i>` : ""}${id === "class" && jobAlert ? ' <i class="dot red"></i>' : ""}${id === "labyrinth" && v.labyrinth.defeated ? ' <i class="dot ok">✓</i>' : ""}</button>`).join("")}</nav>
        ${this.state.version && this.state.version !== VERSION ? `<div class="update-note" role="status">Life RPG has been updated. This screen is still the old version.
          <button class="btn small gold" data-reload>Reload</button></div>` : ""}
        ${this.state.can_act ? "" : `<p class="muted small center-text">Watching ${esc(this.state.name)}. Only they can open chests or change gear.</p>`}
        <main class="tab-${this.tab}">${this[`tab_${this.tab}`](v)}</main>`;
    }

    // ---- STATUS
    tab_status(v) {
      const can = this.state.can_act;
      return `<div class="grid cols st">
        <div class="grid">${V.status(v, this.state.name, can)}${V.today(v)}</div>
        <div class="grid">${V.choice(v, can)}${V.attributes(v)}</div>
      </div>`;
    }

    // ---- QUESTS
    tab_quests(v) {
      const can = this.state.can_act;
      return `<div class="grid cols">
        ${V.choice(v, can)}
        ${V.quests(v, can, this.fixQuest)}
        ${V.bounties(v, can, !!this.state.parent)}
        ${v.hidden.length ? `<section class="win violet">
          <div class="wt">Hidden quests</div>
          <p class="center-text"><span class="count">${v.hidden.length}</span><span class="muted"> found</span></p>
          <p class="center-text muted small">Latest: ${esc(v.hidden[0].name)}, ${esc(shortDate(v.hidden[0].date))}. The rest are in Records.</p>
        </section>` : ""}
      </div>`;
    }

    // ---- LABYRINTH
    tab_labyrinth(v) {
      const g = v.labyrinth, nextElite = Math.ceil((g.floor + (g.elite ? 1 : 0)) / 10) * 10 || 10;
      const kinds = Object.entries(v.bestiary_kinds || {});
      return `<div class="grid cols">
        ${V.guardian(v)}
        <section class="win">
          <div class="wt">Depth</div>
          <div class="depth">
            <div><div class="count">${g.deepest}</div><div class="small muted">Deepest floor</div></div>
            <div><div class="count">${num(v.bestiary_total)}</div><div class="small muted">Guardians defeated</div></div>
            <div><div class="count">${nextElite}</div><div class="small muted">Next elite floor</div></div>
          </div>
          <p class="small muted center-text">One floor opens each Monday. Its guardian's HP is set by your recent pace, so it always asks a little more of you. Lose a week and the next guardian is weaker.</p>
          <div class="wt" style="margin-top:14px">Creatures</div>
          <div class="kinds">${kinds.map(([k, n]) => `<div class="kind ${n ? "" : "unseen"}">${monster(k, n ? (v.bestiary.find((b) => b.kind === k) || {}).element || "shadow" : "shadow", n ? (v.bestiary.find((b) => b.kind === k) || {}).seed || k : `silhouette:${k}`, 1)}<b>${n || "?"}</b><span>${n ? esc(cap(k)) : "Unknown"}</span></div>`).join("")}</div>
        </section>
        <section class="win violet span2">
          <div class="wt">Bestiary</div>
          ${v.bestiary.length ? `<div class="bestiary">${v.bestiary.map((b) => `<div class="beast ${b.elite ? "elite" : ""} ${b.cursed ? "cursed" : ""}">${monster(b.kind, b.element, b.seed, 2, "", b.art)}<div>${esc(b.name)}</div><div class="muted">Floor ${b.floor} · ${esc(shortDate(b.date))}</div></div>`).join("")}</div>`
            : '<p class="muted center-text">Empty for now. Defeat this week\'s guardian to record your first entry.</p>'}
        </section>
      </div>`;
    }

    // ---- INVENTORY
    tab_inventory(v) {
      const gear = v.gear, eq = gear.equipped;
      const items = gear.inventory.slice().sort((a, b) => b.equipped - a.equipped || b.power - a.power);
      const sel = items.find((i) => i.id === this.sel);
      const can = this.state.can_act;
      const slotCol = (slots) => `<div class="slots">${slots.map((s) => `<button class="slotbtn" data-sel="${eq[s] ? eq[s].id : ""}" title="${esc(eq[s] ? eq[s].name : SLOT_NAMES[s])}">${itemIcon(eq[s], 2, s)}</button>`).join("")}</div>`;
      const r = this.reveal && (items.find((i) => i.id === this.reveal.id) || this.reveal);
      return `<div class="grid cols">
        ${r ? `<section class="win gold reveal"><div class="wt">Item acquired</div>${chestArt(this.revealKind || "daily", this.revealRed)}
          <div class="burst">${["epic", "legendary", "mythic"].includes(r.rarity) ? `<div class="rays" style="--rc:${RARITY[r.rarity]}"></div>` : ""}${itemIcon(r, 4)}
          <h3 style="color:${RARITY[r.rarity]};margin:10px 0 2px">${esc(r.name)}</h3><div class="rarity" style="color:${RARITY[r.rarity]}">${esc(r.rarity)} ${esc(r.base || SLOT_NAMES[r.slot])}</div>
          <div class="chips" style="justify-content:center;margin-top:8px">${effectList(r.effects).map((t) => `<span class="chip gold">${esc(t)}</span>`).join("")}</div></div>
          <button class="btn" style="margin-top:12px" data-dismiss>Continue</button></section>` : ""}
        <section class="win">
          <div class="wt">Equipment</div>
          <div class="doll">${slotCol(["helm", "armor", "gloves"])}${portrait(v, eq)}${slotCol(["weapon", "ring", "boots"])}</div>
          <div class="row between small" style="margin-top:8px"><span>Gear score <b>${num(gear.score)}</b></span><span><ha-icon icon="mdi:diamond-stone" style="--mdc-icon-size:16px"></ha-icon> ${num(gear.shards)} shards</span></div>
        </section>
        <section class="win gold">
          <div class="wt">Chests</div>
          ${gear.chests.length ? `<div class="chests">${gear.chests.slice(0, 12).map((c) => `<button class="chestbtn" ${can ? `data-open="${c.id}"` : "disabled"} title="Open ${esc(c.kind)} chest">${chestArt(c.kind, c.red)}<span>${esc(c.kind)}${c.rank ? " " + esc(c.rank) : ""}</span></button>`).join("")}${gear.chests.length > 12 ? `<span class="muted">+${gear.chests.length - 12} more</span>` : ""}</div>
            ${can ? `<div class="row" style="margin-top:12px"><button class="btn gold" data-open="${gear.chests[0].id}">Open chest</button>${gear.chests.length > 1 ? `<button class="btn" data-act="open_all">Open all ${gear.chests.length}</button>` : ""}</div>` : ""}`
          : '<p class="muted center-text">No chests waiting. Clear today\'s quests to earn one.</p>'}
        </section>
        ${sel ? `<section class="win detail" style="border-color:${RARITY[sel.rarity]}">
          <div class="row">${itemIcon(sel, 3)}<div><h3 style="color:${RARITY[sel.rarity]}">${esc(sel.name)}${sel.enh ? ` +${sel.enh}` : ""}</h3><div class="rarity" style="color:${RARITY[sel.rarity]}">${esc(sel.rarity)} ${esc(sel.base || SLOT_NAMES[sel.slot])}</div><div class="small muted">${esc(SLOT_NAMES[sel.slot])} · item level ${sel.lvl} · power ${sel.power}</div></div></div>
          <div class="chips" style="margin:10px 0">${effectList(sel.effects).map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</div>
          ${sel.lore ? `<p class="speech small">${esc(sel.lore)}</p>` : ""}
          ${can ? `<div class="row wrap">${sel.equipped ? `<button class="btn" data-act="unequip" data-slot="${sel.slot}">Unequip</button>` : `<button class="btn gold" data-act="equip" data-item="${sel.id}">Equip</button>`}
            <button class="btn" data-act="enhance" data-item="${sel.id}" ${sel.enhance_cost == null || sel.enhance_cost > gear.shards ? "disabled" : ""}>${sel.enhance_cost == null ? "Fully enhanced" : `Enhance (${sel.enhance_cost} shards)`}</button>
            ${sel.equipped ? "" : `<button class="btn" data-act="sell" data-item="${sel.id}">Sell for ${num(sel.sell)} gold</button>
              <button class="btn ghost" data-act="salvage" data-item="${sel.id}">Salvage for ${sel.salvage} shards</button>`}</div>` : ""}
        </section>` : ""}
        <section class="win">
          <div class="wt">Inventory</div>
          ${items.length ? `<div class="inv">${items.map((i) => `<button data-sel="${i.id}" class="${i.equipped ? "eq" : ""}" title="${esc(i.name)}" aria-pressed="${i.id === this.sel}">${itemIcon(i, 2)}</button>`).join("")}</div>` : '<p class="muted center-text">Your inventory is empty. Open a chest.</p>'}
          <p class="small muted">${items.length}/40 slots. When full, the weakest spare item is salvaged automatically.</p>
        </section>
      </div>`;
    }

    // ---- MARKET
    tab_market(v) {
      const m = v.market, can = this.state.can_act, llm = v.art && v.art.llm;
      if (!m) return '<div class="win"><div class="wt">Market</div><p class="center-text muted">The merchant arrives at dawn.</p></div>';
      const delivery = `${this.entryId}:${m.date}:${m.delivery}`;
      if (can && !m.seen && this.seenDelivery !== delivery) { // goods are painted once someone has looked at them
        this.seenDelivery = delivery;
        setTimeout(() => this.action("market_seen"), 0);
      }
      const target = m.stock.find((e) => e.id === this.haggleId && !e.sold);
      const MOOD = { generous: "in a generous mood", fair: "his usual shrewd self", stubborn: "feeling stubborn today", offended: "still offended",
        annoyed: "getting annoyed with you", angry: "red in the face and glaring", furious: "furious, and his prices show it" };
      const label = (e) => e.kind === "gear" ? e.item.name : e.name;
      const card = (e) => {
        const art = e.kind === "gear" ? itemIcon(e.item, 3) : trinketIcon(e.cid, e.art);
        const sub = e.kind === "gear" ? `<span style="color:${RARITY[e.item.rarity]}">${esc(cap(e.item.rarity))} ${esc(e.item.base || SLOT_NAMES[e.item.slot])}</span>${e.featured ? ' <span class="chip gold">Featured</span>' : ""}`
          : e.kind === "consumable" ? "Consumable" : "Cosmetic";
        const desc = e.kind === "gear" ? effectList(e.item.effects).join(" · ") + (e.upgrade > 0 ? ` · <span class="gold-t">+${e.upgrade} gear score</span>` : "")
          : esc(e.desc || "Changes how your adventurer is painted.");
        return `<div class="ware ${e.sold ? "sold" : ""} ${e.id === this.haggleId ? "on" : ""}">
          ${art}<div class="ware-body"><b>${esc(label(e))}</b><div class="small">${sub}</div><div class="small muted">${desc}</div>
          <div class="price">${e.price < e.list ? `<s>${num(e.list)}</s> ` : ""}<b>${num(e.price)}</b> gold${e.deal ? ' <span class="chip gold">Deal</span>' : ""}${e.why ? ` <span class="chip" title="${esc({ final: "Six rounds of haggling: this is his last word on it.", refused: "You insulted him twice over this one. He'll haggle on it again after his next delivery.", parting: "You walked away and he called you back with this price." }[e.why] || "")}">${{ final: "His last word", refused: "Won't haggle: insulted", parting: "Parting offer" }[e.why] || "Final"}</span>` : ""}</div>
          ${e.sold ? '<span class="chip">Sold</span>' : can ? `<div class="row tight"><button class="btn gold small" data-act="buy" data-stock="${e.id}" ${v.gold < e.price ? "disabled" : ""}>Buy</button>
            ${!e.deal && !e.closed ? `<button class="btn small" data-haggle="${e.id}">Haggle</button>` : ""}</div>` : ""}</div></div>`;
      };
      const chat = (m.chat || []).slice(-8);
      return `<div class="grid cols market">
        <section class="win gold merchant">
          <div class="wt">${esc(m.merchant)}</div>
          <div class="merchant-head">${(() => { const face = m.face || m.mood, pic = painted((m.art || {})[face]) ? m.art[face] : (m.art || {})[m.mood];
            return painted(pic) ? framed(esc(pic), (m.prefs || {}).framing || "bust", "npc-portrait", `${m.merchant}, ${face}`, 1)
              : bust(merchantArt(face), 120, "npc-portrait"); })()}
            <div><p>“${esc(m.delivery > 1 ? "Just unpacked, friend. Have a look." : "Fresh stock, friend. Have a look.")}” He's ${MOOD[m.face || m.mood] || "here"}.</p>
              <p class="small muted">On the cart: ${esc(m.theme_text || "his usual wares")}. ${m.next_delivery ? `Next delivery around ${esc(m.next_delivery)}.` : "Next delivery at midnight."}</p>
              <p class="small muted">You have <b class="gold-t">${num(v.gold)} gold</b>.${m.rapport >= 2 ? " He's taken a liking to you." : m.rapport <= -2 ? " He's wary of you after past haggling." : ""}${m.haggle_bonus ? ` Bard's silver tongue: haggle ${m.haggle_bonus}% further.` : ""}</p></div></div>
          ${m.temper === "fed_up" ? `<p class="fed-up">He's had enough of your haggling. He'll bargain again once he's calmed down (an hour or two) or his next delivery arrives. Prices haven't changed.</p>`
            : m.temper === "fuming" ? '<p class="small warn-t">He\'s irritated. Another lowball and he\'ll stop haggling with you for a while.</p>'
            : m.temper === "impatient" ? '<p class="small muted">He\'s getting a little impatient. Fair offers calm him down.</p>' : ""}
          ${target && m.temper !== "fed_up" ? `<div class="haggle">
            <div class="row between wrap"><b>Haggling: ${esc(label(target))}</b><span>His price <b class="gold-t">${num(target.price)}</b> gold${target.price !== target.list ? ` <span class="muted">(list ${num(target.list)})</span>` : ""}</span></div>
            <div class="row between small muted wrap"><span>${target.offer ? `Your last offer: ${num(target.offer)} gold` : "Make him an offer."}</span><span>${target.deal ? "Deal agreed: press Buy" : target.closed ? "His final word" : `${target.rounds_left} round${target.rounds_left === 1 ? "" : "s"} left`}</span></div>
            ${llm ? `<div class="chatlog">${chat.map((c) => `<p class="${c.role === "user" ? "me" : "them"}">${esc(c.text)}</p>`).join("")}
                ${this.pending && this.pending.who === "merchant" ? `<p class="me">${esc(this.pending.text)}</p><p class="them typing">${esc(m.merchant)} is thinking…</p>` : ""}</div>
              <form data-chat="merchant" class="row"><input data-keep="merchant" name="text" maxlength="300" autocomplete="off" placeholder="Make your pitch, e.g. ${num(Math.round(target.price * 0.85))} gold and not a coin more" aria-label="Message to the merchant">
                <button class="btn gold" ${this.busy ? "disabled" : ""}>Say</button></form>`
              : `<form data-offer="${target.id}" class="row"><input data-keep="offer" name="offer" type="number" min="1" placeholder="Your offer in gold" aria-label="Your offer">
                <button class="btn gold">Offer</button></form>`}
            ${!target.deal && !target.closed ? `<div class="row tight wrap">${[0.8, 0.88, 0.95].map((f) => Math.round(target.price * f)).filter((n, i, a) => n > (target.offer || 0) && a.indexOf(n) === i)
                .map((n) => `<button class="btn ghost small" data-quick="${n}">Offer ${num(n)}</button>`).join("")}
              <button class="btn ghost small" data-walk="${target.id}" ${target.rounds ? "" : "disabled"} title="Turn to leave. He might call you back with a better price.">Walk away</button>
              <button class="btn ghost small" data-haggle="">Done</button></div>` : `<div class="row tight wrap"><button class="btn ghost small" data-haggle="">Done</button></div>`}
            <p class="small muted">He enjoys a haggle: meet him partway and raise your offer a little each round. Lowballs annoy him and insults put that price up. Walk away mid-haggle and he may call you back.</p></div>`
          : `<p class="small muted center-text">Pick Haggle on anything to bargain.${llm ? " Talk to him like a person: any price you name is your offer, and \"never mind\" walks away." : ""}</p>`}
        </section>
        <section class="win span2">
          <div class="wt">${m.delivery > 1 ? "Fresh stock" : "Today's stock"}</div>
          <div class="wares">${m.stock.map(card).join("")}</div>
        </section>
        <section class="win violet">
          <div class="wt">Your bag</div>
          ${v.bag.length ? v.bag.map((b) => `<div class="bagrow">${trinketIcon(b.id, b.art)}<div><b>${esc(b.name)}</b> <span class="muted">×${b.count}</span><div class="small muted">${esc(b.desc)}</div></div>
              ${can ? `<button class="btn small" data-act="use" data-cons="${esc(b.id)}">Use</button>` : ""}</div>`).join("") : '<p class="muted center-text">Empty. Potions and charms from the market land here.</p>'}
          ${v.buffs.length ? `<div class="chips" style="margin-top:10px">${v.buffs.map((b) => `<span class="chip gold">${esc(b.name)}: ${esc(effectList(b.effects).join(", "))}</span>`).join("")}</div>` : ""}
          <p class="small muted">${v.elixirs_left} elixir${v.elixirs_left === 1 ? "" : "s"} or oils left this week.${v.charms && v.charms.luck ? " A lucky charm is waiting on your next chest." : ""}</p>
        </section>
        <section class="win">
          <div class="wt">Wardrobe</div>
          ${Object.keys(v.cosmetics.catalog).length ? ["background", "pose", "dye", "frame"].map((cat) => {
            const owned = Object.entries(v.cosmetics.catalog).filter(([, c]) => c.category === cat);
            if (!owned.length) return "";
            const active = v.cosmetics.active[cat];
            return `<div class="cosrow"><b>${cap(cat === "background" ? "backdrop" : cat)}</b><div class="chips">
              <button class="chip ${!active ? "on" : ""}" ${can ? `data-act="set_cosmetic" data-cat="${cat}" data-cos=""` : "disabled"}>None</button>
              ${owned.map(([id, c]) => `<button class="chip ${active === id ? "on" : ""}" ${can ? `data-act="set_cosmetic" data-cat="${cat}" data-cos="${esc(id)}"` : "disabled"}>${esc(c.name.split(": ")[1] || c.name)}</button>`).join("")}</div></div>`;
          }).join("") : '<p class="muted center-text">Backdrops, poses, dyes and frames from the market show up here.</p>'}
          <p class="small muted">Backdrops, poses and dyes repaint your portrait; frames go around it.</p>
        </section>
      </div>`;
    }

    // ---- CLASS
    tab_class(v) {
      const can = this.state.can_act, unlocked = v.level >= v.job_unlock_level, rec = v.recommended_job;
      const recName = rec ? (v.jobs.find((j) => j.id === rec) || {}).name : null;
      return `<div class="grid cols">
        <section class="win ${unlocked ? (v.job ? "gold" : "violet") : ""} span2">
          <div class="wt">Class</div>
          ${unlocked
            ? `<p class="center-text">${v.job ? `You are a <b>${esc(v.job.title)}</b>, ${esc(v.job.name)} level ${v.job.level}.` : "You can choose a job."}
                ${recName ? ` Your last four weeks point to <b>${esc(recName)}</b>.` : ""}</p>
               <p class="center-text small muted">Your active job earns job XP from quest XP gained while you hold it (its focus counts double), starting from the moment you take it. Switch jobs and the old one keeps every level and XP it earned, but only the active job's passive and skills count. Passives grow every job level; skills unlock at job levels 3, 8, 15, 25 and 40.</p>`
            : `<p class="center-text">Jobs unlock at level ${v.job_unlock_level}. You are level ${v.level}.${recName ? ` So far your habits point to <b>${esc(recName)}</b>.` : ""}</p>`}
        </section>
        <section class="win span2">
          <div class="wt">Jobs</div>
          <div class="jobs">${v.jobs.map((j) => `<div class="job ${j.active ? "active" : ""} ${j.id === rec && !j.active ? "rec" : ""}">
            <div class="head"><span class="jicon"><ha-icon icon="${JOB_ICON[j.id] || "mdi:account"}"></ha-icon></span>
              <div style="flex:1;min-width:0"><b>${esc(j.name)}</b> <span class="muted small">Lv ${j.level}</span><div class="small ${j.active ? "gold-t" : "muted"}">${esc(j.title)}</div></div>
              ${j.active ? '<span class="chip gold">Current</span>' : j.id === rec ? '<span class="chip">Suggested</span>' : ""}</div>
            <div class="small">${esc(j.desc)}</div>
            <div>${bar(j.progress, 100, j.active ? "gold" : "", `${j.name} job level`)}<div class="row between small muted"><span>Focus: ${esc(JOB_FOCUS[j.id] || j.quests.map((q) => QNAME[q] || q).join(", "))}</span><span>${j.progress}%</span></div></div>
            ${effectList(j.effects).length ? `<div class="chips">${effectList(j.effects).map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</div>` : ""}
            <ul>${j.skills.map((s) => `<li class="${s.unlocked ? "" : "off"}"><span>Lv ${s.at}</span><div><b>${esc(s.name)}</b> ${esc(s.desc)}</div></li>`).join("")}</ul>
            ${can && unlocked && !j.active ? `<button class="btn ${j.id === rec ? "gold" : ""}" data-act="set_job" data-job="${esc(j.id)}">Become a ${esc(j.name)}</button>` : ""}
          </div>`).join("")}</div>
        </section>
        <section class="win violet">
          <div class="wt">Skill proficiency</div>
          <p class="center-text small muted">Skills grow by doing, a little every day, and never stop. Each grade adds a small XP bonus to its quest.</p>
          <div class="skills">${Object.values(v.skills).map((s) => `<div class="skill"><div class="row between"><b>${esc(s.name)}</b><span class="grade">${esc(s.grade)}</span></div>
            <div class="small muted">${esc(s.desc)}</div>${bar(s.progress, 100, "violet", s.name)}
            <div class="row between small muted"><span>${num(s.proficiency)} / ${num(s.next)}</span><span>+${s.bonus}% XP</span></div></div>`).join("")}</div>
        </section>
      </div>`;
    }

    // ---- GALLERY
    tab_gallery(v) {
      const real = (u) => u || null; // paintings even while this device shows pixel art
      const can = this.state.can_act, st = v.art.studio || {}, cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
      const edit = !!v.art.edit, sq = { square: true };
      const section = (title, tiles, extra = "") => tiles.length ? `<section class="win"><div class="wt">${esc(title)}</div>${extra}<div class="gallery">${tiles.join("")}</div></section>` : "";
      const base = (url, whose, them, extra = {}) => edit ? [galleryTile(real(url) ? url : null, "Base painting", can, st,
        { ...extra, base: true, wait: "Base painting not ready yet", note: `${whose} face and look. Every other picture of ${them} is an edit of it, so repainting it repaints them all.` })] : [];
      const seen = new Set(), items = [];
      const addItem = (url, label) => { if (url && !seen.has(url) && real(url)) { seen.add(url); items.push(galleryTile(url, label, can, st, sq)); } };
      Object.values(v.gear.equipped).forEach((i) => i && addItem(i.art, i.name));
      v.gear.inventory.forEach((i) => addItem(i.art, i.name));
      ((v.market || {}).stock || []).forEach((e) => addItem(e.kind === "gear" ? e.item.art : e.art, e.kind === "gear" ? e.item.name : e.name));
      (v.bag || []).forEach((b) => addItem(b.art, b.name));
      const mb = (st.bytes || 0) / 1048576;
      return `<div class="grid">
        <section class="win gold"><div class="wt">Gallery</div>
          <p class="center-text small muted">${num(st.done || 0)} paintings, ${mb >= 1024 ? (mb / 1024).toFixed(1) + " GB" : Math.round(mb) + " MB"}${st.queue ? `, ${num(st.queue)} waiting${st.avg_s ? ` (about ${eta(st.queue * st.avg_s)} at ${Math.round(st.avg_s)} seconds each)` : ""}` : ""}. Don't like one? Repaint it: ComfyUI paints a new version, and the old one stays until the new one is ready (then it's deleted).</p></section>
        <section class="win"><div class="wt">You</div><div class="you-row">
          <div class="gallery pair">${[...base(v.art.portrait_base, "Your", "you"), galleryTile(real(v.art.portrait) ? v.art.portrait : null, "Your portrait", can, st, { framing: (v.portrait_prefs || {}).framing || "full" })].join("")}</div>
          ${can ? prefsForm("portrait", v) : ""}</div></section>
        ${(() => { // the goddess: her base (or today's mood) and her choices, then every mood
          const g = v.goddess, art = g.art || {}, mood = g.mood || "serene";
          const fr = { framing: (g.prefs || {}).framing || "three_quarter" };
          const lead = edit ? base(g.base_art, "Her", "her") : [galleryTile(real(art[mood]) ? art[mood] : null, `${cap(mood)} (today)`, can, st, fr)];
          const rest = Object.entries(art).filter(([m]) => edit || m !== mood).map(([m, u]) => galleryTile(real(u) ? u : null, cap(m), can, st, fr));
          return `<section class="win"><div class="wt">${esc(g.name)}</div><div class="you-row">
            <div class="gallery pair">${lead.join("")}</div>${can ? prefsForm("goddess", v) : ""}</div>
            <div class="gallery" style="margin-top:12px">${rest.join("")}</div></section>`; })()}
        ${v.market ? (() => { // Marrow Fennick, the same way
          const m = v.market, art = m.art || {}, face = m.face || m.mood || "fair";
          const fr = { framing: (m.prefs || {}).framing || "bust" };
          const lead = edit ? base(m.base_art, "His", "him") : [galleryTile(real(art[face]) ? art[face] : null, `${cap(face)} (now)`, can, st, fr)];
          const rest = Object.entries(art).filter(([f]) => edit || f !== face).map(([f, u]) => galleryTile(real(u) ? u : null, cap(f), can, st, fr));
          return `<section class="win"><div class="wt">${esc(m.merchant)}</div><div class="you-row">
            <div class="gallery pair">${lead.join("")}</div>${can ? prefsForm("merchant", v) : ""}</div>
            <div class="gallery" style="margin-top:12px">${rest.join("")}</div></section>`; })() : ""}
        ${v.choice ? section("Today's visitor", [galleryTile(real(v.choice.art) ? v.choice.art : null, "Visitor", can, st, sq)]) : ""}
        ${section("Labyrinth", [galleryTile(real(v.labyrinth.art) ? v.labyrinth.art : null, v.labyrinth.name, can, st, sq),
          ...v.bestiary.slice(0, 12).filter((b) => real(b.art)).map((b) => galleryTile(b.art, b.name, can, st, sq))])}
        ${section("Gear, potions and cosmetics", items)}
      </div>`;
    }

    // ---- RECORDS
    tab_records(v) {
      const can = this.state.can_act;
      // titles and hidden quests are surprises: only what you've earned is shown, nothing about the rest
      const titles = v.titles.slice().sort((a, b) => b.equipped - a.equipped || String(b.date || "").localeCompare(String(a.date || "")));
      const shown = this.allTitles ? titles : titles.slice(0, 8);
      return `<div class="grid cols">
        ${titles.length ? `<section class="win gold">
          <div class="wt">Titles</div>
          <p class="center-text small muted">${titles.length === 1 ? "One title" : `${titles.length} titles`} earned. Equip one for its bonus.</p>
          <div class="titles">${shown.map((t) => `<div class="title earned ${t.equipped ? "eqd" : ""}">
            <div><b>“${esc(t.name)}”</b><div class="small muted">${esc(t.how)}</div><div class="small gold-t">${[t.date ? "Earned " + shortDate(t.date) : "", effectList(t.effects).join(", ")].filter(Boolean).map(esc).join(" · ")}</div></div>
            <div>${can ? (t.equipped ? `<button class="btn ghost" data-act="set_title" data-title="">Unequip</button>` : `<button class="btn gold" data-act="set_title" data-title="${esc(t.id)}">Equip</button>`) : ""}</div></div>`).join("")}</div>
          ${titles.length > 8 ? `<div class="center-text" style="margin-top:10px"><button class="btn ghost" data-toggle-titles>${this.allTitles ? "Show fewer" : `Show all ${titles.length}`}</button></div>` : ""}
        </section>` : ""}
        <section class="win">
          <div class="wt">Badges</div>
          <p class="center-text small muted">Bronze to Diamond, then a star each time the total doubles.</p>
          <div class="badges">${v.badges.map((b) => `<div class="badge">${medal(b)}<div><b>${esc(b.name)}</b><div class="small muted">${b.tier_name ? esc(b.tier_name) : "Locked"} · ${num(b.value)} / ${num(b.next)}</div></div>${bar(b.value - (b.prev || 0), b.next - (b.prev || 0), b.tier ? "gold" : "")}</div>`).join("")}</div>
        </section>
        ${v.hidden.length ? `<section class="win violet">
          <div class="wt">Hidden quests</div>
          <p class="center-text small muted">${v.hidden.length === 1 ? "One found" : `${v.hidden.length} found`}.</p>
          <div class="hidden">${v.hidden.map((h) => `<div class="hq found"><b>${esc(h.name)}</b><div>${esc(h.desc)}</div><div class="small muted">Found ${esc(shortDate(h.date))}</div></div>`).join("")}</div>
        </section>` : ""}
      </div>`;
    }

    // ---- GODDESS
    tab_goddess(v) {
      const d = v.devotion, r = v.race, tree = r.tree, g = r.gift;
      const base = String(d.tier).replace(/ \+\d+$/, "");
      const tierIdx = Math.max(0, ["Stranger", "Believer", "Devotee", "Apostle", "Saint", "Hand of the Goddess"].indexOf(base));
      const node = (t, on, off, lvl) => `<div class="node ${on ? "on" : ""} ${off ? "off" : ""}"><b>${esc(t.name)}</b>${lvl ? ` <span class="small muted">Lv ${lvl}</span>` : ""}<div class="small muted">${esc(t.desc)}</div><div class="chips" style="margin-top:6px">${effectList(t.effects).map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</div></div>`;
      const branches = Object.entries(tree.branches);
      return `<div class="grid cols">
        <section class="win violet">
          <div class="wt">${esc(v.goddess.name)}, ${esc(v.goddess.title)}</div>
          <div class="goddess painted">${(() => { const art = v.goddess.art || {}, mood = this.luneMood || v.goddess.mood || "serene";
              const src = painted(art[mood] || art[v.goddess.mood]);
              return src ? framed(esc(src), (v.goddess.prefs || {}).framing || "three_quarter", "lune", v.goddess.name)
                : `<img class="lune pix" src="${luneArt(mood, v.goddess.tier ?? tierIdx).src}" width="192" height="252" alt="${esc(v.goddess.name)}, ${esc(mood)}">`; })()}
            <div class="stack"><blockquote>${esc((Number(v.now.slice(11, 13)) < 12 && loreFor(v, "morning", today(v))) || v.goddess.line)}</blockquote>
              <div><b>${esc(d.tier)}</b> <span class="muted">· ${plural(d.faith, "day")} of faith · believers: 1</span></div>
              <div>${bar(d.faith, d.next_at, "violet")}<div class="small muted">${num(d.next_at - d.faith)} cleared days until ${esc(d.next_tier)}</div></div>
            </div></div>
          ${v.goddess.name === "Lune" && this.state.can_act ? '<p class="small muted center-text">You can give her another name (your voice assistant\'s, say) under Settings → Devices & services → Life RPG → Configure → Goddess.</p>' : ""}
          <div style="margin-top:14px">${d.blessings.map((b) => `<div class="blessing ${b.unlocked ? "" : "off"}"><ha-icon icon="${b.unlocked ? "mdi:star-four-points" : "mdi:lock-outline"}"></ha-icon><div><b>${esc(b.name)}</b> <span class="small muted">· ${esc(b.tier)} (${b.at} days)</span><div class="small">${esc(b.desc)}</div></div></div>`).join("")}</div>
        </section>
        <section class="win violet">
          <div class="wt">Speak with ${esc(v.goddess.name)}</div>
          ${v.art && v.art.llm ? `<div class="chatlog tall">${v.lune_chat.slice(-10).map((c) => `<p class="${c.role === "user" ? "me" : "them"}">${esc(c.text)}</p>`).join("")
              || '<p class="them">You came to my shrine? Ha! Of course you did. Tell me about your day, my believer.</p>'}
              ${this.pending && this.pending.who === "lune" ? `<p class="me">${esc(this.pending.text)}</p><p class="them typing">${esc(v.goddess.name)} is listening…</p>` : ""}</div>
            ${this.state.can_act ? `<form data-chat="lune" class="row"><input data-keep="lune" name="text" maxlength="400" autocomplete="off" placeholder="Say something to ${esc(v.goddess.name)}" aria-label="Message to ${esc(v.goddess.name)}">
              <button class="btn gold" ${this.busy ? "disabled" : ""}>Send</button></form>` : ""}`
            : `<p class="muted center-text">${esc(v.goddess.name)} can talk back once an AI Task entity is set in Configure → Goddess, art and AI.</p>`}
        </section>
        <section class="win">
          <div class="wt">${esc(r.name)} racial gift</div>
          <p class="center-text small muted">${esc(r.lore)} ${r.next_evolution ? `Next evolution at level ${r.next_evolution}${g.branch ? "" : ", along the path you train most"}.` : "Fully evolved."}</p>
          <div class="tree">
            <div class="node root ${g.tier === 1 ? "on" : ""}"><b>${esc(tree.gift.name)}</b><div class="small muted">${esc(tree.gift.desc)}</div></div>
            ${branches.map(([b]) => `<div class="small muted center-text">${esc(cap(b))} path</div>`).join("")}
            ${[0, 1].map((i) => branches.map(([b, tiers]) => node(tiers[i], g.branch === b && g.tier === i + 2, (g.branch && g.branch !== b) || g.tier < i + 2, i === 0 ? 10 : 30)).join("")).join("")}
          </div>
        </section>
      </div>`;
    }

    // ---- LOG
    tab_log(v) {
      return `<div class="grid cols">
        <section class="win"><div class="wt">Last 30 days</div>${historyChart(v.history)}
          ${(v.lore.chronicle || []).length ? `<div class="wt" style="margin-top:18px">Chronicle</div>${v.lore.chronicle.slice().reverse().map((c) => `<div class="chron"><b>${esc(c.week)}</b><p>${esc(c.text)}</p></div>`).join("")}` : ""}</section>
        <section class="win"><div class="wt">System log</div>
          <ul class="log">${v.log.map((e) => { const [t, m] = describe(e); return `<li><time>${esc(fmtTime(e.t))}</time><b>${esc(t)}</b><span class="small">${esc(m)}</span></li>`; }).join("") || '<li class="muted">Nothing yet.</li>'}</ul></section>
      </div>`;
    }

    // Every button in the panel, by its data- attributes.
    async onClick(ev) {
      const el = ev.target.closest("button,[data-dismiss]");
      if (!el) return;
      const d = el.dataset;
      if ("reload" in d) { location.reload(); return; }
      if (d.tab) { this.tab = d.tab; this.reveal = null; this.render(); return; }
      if (d.watch) { this.watch(d.watch); return; }
      if (d.sel !== undefined) { this.sel = d.sel ? Number(d.sel) : null; this.render(); return; }
      if ("dismiss" in d) { this.reveal = null; this.render(); return; }
      if ("pixel" in d) {
        PIXEL = !PIXEL;
        try { localStorage.setItem(PIXEL_KEY, PIXEL ? "1" : "0"); } catch (e) { /* private mode: this session only */ }
        this.render();
        return;
      }
      if (d.repaint) {
        el.disabled = true;
        if (await this.action("repaint_art", { url: d.repaint })) this.toast({ type: "repaint" }, { title: "Repainting", msg: "A new version is on its way. The old one stays until it's ready.", tone: "violet" });
        this.render();
        return;
      }
      if (d.bounty) {
        el.disabled = true;
        const id = Number(d.bounty), act = { claim: ["claim_bounty", {}], approve: ["approve_bounty", { ok: true }], reject: ["approve_bounty", { ok: false }], remove: ["remove_bounty", {}] }[d.bact];
        if (act) await this.action(act[0], { bounty_id: id, ...act[1] });
        this.render();
        return;
      }
      if (d.fix !== undefined) { this.fixQuest = d.fix || null; this.render(); return; }
      if ("toggleTitles" in d) { this.allTitles = !this.allTitles; this.render(); return; }
      if (d.log) {
        el.disabled = true;
        const total = await this.action("log", { quest: d.log, amount: Number(d.amount) });
        if (total != null) this.toast({ type: "log" }, { title: "Logged", msg: `${num(total)} ${d.log === "hydration" ? `${waterUnit(this.state.view)} of water` : "flights"} logged today.`, tone: "blue" });
        this.render();
        return;
      }
      if (d.haggle !== undefined) { this.haggleId = d.haggle ? Number(d.haggle) : null; this.render(); return; }
      if (d.walk) {
        el.disabled = true;
        const v = this.state.view;
        if (v.art && v.art.llm) this.chat("merchant", "Never mind, I'll leave it.");
        else this.haggleResult(await this.action("walk_away", { stock_id: Number(d.walk) }));
        return;
      }
      if (d.quick) {
        const v = this.state.view;
        if (v.art && v.art.llm) this.chat("merchant", `I'll pay ${num(Number(d.quick))} gold.`);
        else this.offer(this.haggleId, Number(d.quick));
        return;
      }
      if (d.open) {
        el.disabled = true;
        const chest = this.state.view.gear.chests.find((c) => c.id === Number(d.open));
        this.revealKind = chest?.kind; this.revealRed = chest?.red;
        const item = await this.action("open_chest", { chest_id: Number(d.open) });
        if (item) { this.reveal = item; this.sel = item.id; }
        this.render();
        return;
      }
      if (d.act) {
        const extra = {};
        if (d.item) extra.item_id = Number(d.item);
        if (d.slot) extra.slot = d.slot;
        if (d.job) extra.job = d.job;
        if (d.accept !== undefined) extra.accept = d.accept === "1";
        if (d.act === "set_title") extra.title = d.title || null;
        if (d.stock) extra.stock_id = Number(d.stock);
        if (d.cons) extra.consumable = d.cons;
        if (d.quest) extra.quest = d.quest;
        if (d.cat) { extra.category = d.cat; extra.cosmetic = d.cos || null; }
        el.disabled = true;
        const res = await this.action(d.act, extra);
        if (d.act === "salvage" || d.act === "sell") this.sel = null;
        if (d.act === "sell" && res) this.toast({ type: "sale" }, { title: "Sold", msg: `+${num(res)} gold.`, tone: "gold" });
        if (d.act === "use" && res) this.toast({ type: "use" }, { title: "Used", msg: res, tone: "violet" });
        if (d.act === "buy" && res) { this.haggleId = null; this.toast({ type: "buy" }, { title: "Purchased", msg: "It's yours. Gear goes to your inventory, potions to your bag.", tone: "gold" }); }
        if (d.act === "open_all" && Array.isArray(res) && res.length) {
          const best = res.slice().sort((a, b) => b.power - a.power)[0];
          this.reveal = best; this.revealKind = "daily"; this.revealRed = false; this.sel = best.id;
          this.toast({ type: "chests" }, { title: `${res.length} chests opened`, msg: `Best find: ${best.name}.`, tone: "gold" });
        }
        this.render();
      }
    }
  }

  // Every form in the panel (appearance, corrections, chats, haggling, bounties).
  LifeRpgPanel.prototype.onSubmit = async function (form) {
    if ("chore" in form.dataset) {
      const f = (n) => form.querySelector(`[name="${n}"]`);
      const res = await this.action("add_bounty", { title: f("title").value.trim(), xp: Number(f("xp").value || 0), gold: Number(f("gold").value || 0),
        chest: f("chest").checked, repeat: f("repeat").value });
      if (res) this.toast({ type: "chore" }, { title: "Chore posted", msg: res.title, tone: "gold" });
      this.render();
      return;
    }
    if (form.dataset.prefs) {
      const kind = form.dataset.prefs, v = this.state.view, cfg = PREFS[kind], old = cfg.prefs(v) || {}, prefs = {};
      form.querySelectorAll("select").forEach((sel) => { prefs[sel.name] = sel.value || null; });
      const changed = Object.keys(prefs).filter((k) => (prefs[k] || null) !== (old[k] || null)).map((k) => TIER[k] || "base");
      const who = { portrait: "you", goddess: v.goddess.name, merchant: (v.market || {}).merchant || "Marrow Fennick" }[kind];
      if (await this.action(cfg.action, { prefs })) {
        const msg = !changed.length ? "Nothing changed."
          : changed.every((t) => t === "view") ? "New framing. Nothing needs repainting."
          : changed.includes("base") && v.art.edit ? `A new base painting of ${who} is on its way, then everything is edited from it. The current pictures stay until then.`
          : `New paintings of ${who} are on their way. The current ones stay until they're ready.`;
        this.toast({ type: "repaint" }, { title: "Saved", msg, tone: "violet" });
      }
      this.render();
      return;
    }
    if (form.dataset.fixForm) {
      const val = (n) => { const x = form.querySelector(`[name="${n}"]`).value.trim(); return x === "" ? null : Number(x); };
      const today = val("today"), record = val("record");
      if (today == null && record == null) return;
      const res = await this.action("correct", { quest: form.dataset.fixForm, ...(today != null ? { today } : {}), ...(record != null ? { record } : {}) });
      if (res) {
        this.fixQuest = null;
        this.toast({ type: "fix" }, { title: "Count corrected", msg: [res.today != null ? `Today: ${num(res.today)}.` : "", res.record != null ? `Record: ${num(res.record)}.` : ""].join(" "), tone: "blue" });
      }
      this.render();
      return;
    }
    if ("sleep" in form.dataset) {
      const bed = form.querySelector('[name="bedtime"]').value, wake = form.querySelector('[name="wake"]').value;
      if (!bed) return;
      const res = await this.action("log_sleep", { bedtime: bed, ...(wake ? { wake } : {}) });
      if (res != null) this.toast({ type: "log" }, wake ? { title: "Sleep logged", msg: `${res} hours of rest counted for today.`, tone: "blue" }
        : { title: "Lights out logged", msg: `You fell asleep at ${res}. Rest is left to your sleep sensor.`, tone: "blue" });
      this.render();
      return;
    }
    const input = form.querySelector("input");
    const value = (input && input.value || "").trim();
    if (!value) return;
    input.value = "";
    if (form.dataset.chat) await this.chat(form.dataset.chat, value);
    else if (form.dataset.offer) await this.offer(Number(form.dataset.offer), Number(value));
  };
  LifeRpgPanel.prototype.chat = async function (who, text) {
    if (this.busy) return;
    this.busy = who; this.pending = { who, text };
    this.render();
    try {
      const res = await this._hass.callWS({ type: "life_rpg/chat", entry_id: this.entryId, who, text,
        ...(who === "merchant" && this.haggleId ? { stock_id: this.haggleId } : {}) });
      if (who === "lune") this.luneMood = res.mood;
      if (who === "merchant" && ["accepted", "called_back"].includes(res.result)) this.toast({ type: "deal" }, { title: "Deal", msg: `${num(res.price)} gold. Press Buy to take it home.`, tone: "gold" });
    } catch (e) {
      this.toast({ type: "error" }, { title: who === "lune" ? `${this.state.view.goddess.name} is silent` : "The merchant is busy", msg: e.message, tone: "red" });
    } finally {
      this.busy = null; this.pending = null;
      this.render();
    }
  };
  LifeRpgPanel.prototype.offer = async function (stockId, gold) {
    this.haggleResult(await this.action("haggle", { stock_id: stockId, offer: Math.round(gold) }));
  };
  LifeRpgPanel.prototype.haggleResult = function (res) {
    if (res) {
      const p = num(res.price);
      const words = { accepted: `Deal at ${p} gold! Press Buy to take it home.`, countered: `He comes down to ${p} gold.`,
        holding: `Too low. He barely moves: ${p} gold.`, final: `His final word: ${p} gold.`, insulted: `Insulted! For that, it's ${p} gold now.`,
        refused: `He won't haggle over that one any more today. ${p} gold.`, closed: "Nothing more to haggle on that one.",
        fed_up: "He's fed up and won't haggle with you until he's calmed down. Prices haven't changed.",
        called_back: `“Wait! Come back!” His last offer: ${p} gold.`, walked: "You walk away. He lets you go." }[res.result] || "";
      const tone = ["accepted", "called_back"].includes(res.result) ? "gold" : ["insulted", "refused", "fed_up"].includes(res.result) ? "red" : "violet";
      this.toast({ type: "haggle" }, { title: "Marrow Fennick", msg: words, tone });
      if (res.result === "walked") this.haggleId = null;
    }
    this.render();
  };


  // ---------------------------------------------------------------- the card
  const CARD_VIEWS = ["compact", "status", "quests", "labyrinth"];
  /** The dashboard card. Views: compact, status, quests, labyrinth (set with `view:`). */
  class LifeRpgCard extends HTMLElement {
    static getStubConfig() { return { view: "compact" }; }
    // The card's YAML: view and, in a household with several adventurers, adventurer.
    setConfig(config) {
      if (config.view && !CARD_VIEWS.includes(config.view)) throw new Error("view must be compact, status, quests or labyrinth");
      this.config = { view: "compact", ...config };
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      if (this.last) this.draw(this.last);
    }
    getCardSize() { return { compact: 4, status: 7, quests: 6, labyrinth: 5 }[this.config.view] || 4; }
    getGridOptions() { return { columns: 12, min_columns: 6 }; }
    set hass(hass) {
      this._hass = hass;
      if (!this.started) { this.started = true; this.start(); }
    }
    connectedCallback() { if (this._hass && !this.unsub && this.started) this.start(); }
    disconnectedCallback() { this.unsub?.(); this.unsub = null; clearInterval(this.tick); }
    // Pick the adventurer (the configured one, else the viewer's own) and subscribe.
    async start() {
      try {
        const party = await players(this._hass);
        const want = (this.config.adventurer || "").toLowerCase();
        const p = party.players.find((x) => (want ? x.name.toLowerCase() === want : x.mine)) || party.players[0];
        if (!p) { this.draw(null, "No adventurers yet. Add the Life RPG integration."); return; }
        this.entryId = p.entry_id;
        this.unsub = subscribe(this._hass, p.entry_id, (msg) => this.draw(msg));
      } catch (e) { this.draw(null, e.message); }
    }
    // Draw the chosen view; quick-log buttons work from the card without opening the panel.
    draw(msg, error) {
      const root = this.shadowRoot;
      if (!root.querySelector("style")) {
        root.innerHTML = `<style>${CSS}${CARD_CSS}</style><ha-card><div class="body"></div></ha-card>`;
        root.querySelector("ha-card").addEventListener("click", async (ev) => {
          const log = ev.target.closest("[data-log]");
          if (log) { // quick log from the card; don't open the panel
            log.disabled = true;
            try { await act(this._hass, this.entryId, "log", { quest: log.dataset.log, amount: Number(log.dataset.amount) }); }
            catch (e) { log.title = e.message; }
            log.disabled = false;
            return;
          }
          history.pushState(null, "", "/life-rpg");
          window.dispatchEvent(new CustomEvent("location-changed"));
        });
      }
      const body = root.querySelector(".body");
      if (!msg) { body.innerHTML = `<div class="win"><div class="wt">System</div>${esc(error || "Connecting…")}</div>`; return; }
      this.last = msg;
      const v = msg.view, view = this.config.view;
      setClock(v);
      if (view === "status") body.innerHTML = `<div class="grid">${V.status(v, msg.name, false)}${V.choice(v, false)}</div>`;
      else if (view === "quests") body.innerHTML = `<div class="grid">${V.choice(v, false)}${V.quests(v, false)}</div>`;
      else if (view === "labyrinth") body.innerHTML = V.guardian(v);
      else body.innerHTML = this.compact(msg);
      if (msg.version && msg.version !== VERSION) body.insertAdjacentHTML("beforeend", '<p class="small muted center-text">Life RPG was updated: reload this page.</p>');
      clearInterval(this.tick);
      const end = body.querySelector("[data-end]");
      if (end) {
        const tick = () => { const left = Math.max(0, new Date(end.dataset.end) - Date.now()); end.textContent = `${String(Math.floor(left / 60000)).padStart(2, "0")}:${String(Math.floor((left % 60000) / 1000)).padStart(2, "0")}`; };
        tick();
        this.tick = setInterval(tick, 1000);
      }
    }
    // The compact view: portrait, level, quest bars, streak, floor and any alerts.
    compact(msg) {
      const v = msg.view, e = v.emergency, p = v.penalty, g = v.labyrinth, c = v.choice;
      return `<div class="win ${(e && e.status === "active") || (p && !p.met) ? "red" : ""}">
        <div class="row" style="align-items:stretch">${portrait(v, v.gear.equipped, 2)}
          <div style="flex:1;min-width:0" class="stack">
            <div class="row between"><b class="name" style="font-size:18px">${esc(msg.name)}</b><span class="lv">Lv <b>${v.level}</b> <span class="rk" style="color:${rankColor(v.rank)}">${esc(v.rank)}</span></span></div>
            <div class="small muted ell">${esc(v.job ? v.job.title : "Villager")}${v.title ? " · “" + esc(v.title.name) + "”" : ""}</div>
            ${bar(v.level_xp, v.level_span, "", "Experience")}
            <div class="mini">${Object.values(v.quests).map((q) => `<div class="${q.done ? "done" : ""}"><span>${esc(q.name)}</span>${bar(q.pct, 100, q.done ? "gold" : "")}</div>`).join("")}</div>
          </div></div>
        <div class="row between small wrap" style="margin-top:10px">
          <span><ha-icon icon="mdi:fire" style="--mdc-icon-size:16px;color:var(--gold)"></ha-icon> ${v.streak}d${v.shields ? ` · <ha-icon icon="mdi:shield-half-full" style="--mdc-icon-size:15px"></ha-icon>${v.shields}` : ""}</span>
          <span><ha-icon icon="mdi:stairs-down" style="--mdc-icon-size:16px"></ha-icon> Floor ${g.floor} ${g.defeated ? "cleared" : g.pct + "%"}</span>
          ${v.gear.chests.length ? `<span class="chip gold">${plural(v.gear.chests.length, "chest")}</span>` : ""}
          ${msg.can_act && (v.manual || []).includes("hydration") ? `<button class="btn small" data-log="hydration" data-amount="${GLASS(v)}" title="Log a glass of water">+ Water</button>` : ""}
          ${msg.can_act && (v.manual || []).includes("floors") ? '<button class="btn small" data-log="floors" data-amount="1" title="Log a flight of stairs">+ Stairs</button>' : ""}
        </div>
        ${c && c.status === "offered" ? `<div class="alert violet-a">A choice is waiting: ${esc(c.text)}</div>` : ""}
        ${e && e.status === "active" ? `<div class="alert">Emergency quest: ${esc(e.title)} · <b data-end="${esc(e.end)}">--:--</b></div>` : ""}
        ${p && !p.met ? `<div class="alert">Penalty quest: finish ${p.need} quests to save your ${p.streak}-day streak.</div>` : ""}
      </div>`;
    }
  }

  customElements.define(PANEL_TAG, LifeRpgPanel);
  if (!customElements.get("life-rpg-card")) customElements.define("life-rpg-card", LifeRpgCard);
  window.customCards = window.customCards || [];
  window.customCards.push({ type: "life-rpg-card", name: "Life RPG", description: "Adventurer status, daily quests or this week's labyrinth floor.", preview: false });
}
