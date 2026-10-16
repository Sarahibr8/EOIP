// Illustrative operations map (NOT the official Expo 2030 site plan): one band per zone with
// its occupancy and staff indicators, the zone's operational locations as pins, walkways, and
// decorative trees / pavilions. The band colour follows the occupancy level; a pin turns to the
// colour of the highest open priority at that location and shows the number of open incidents.
// Everything is drawn from /api/state + /api/layout; nothing here is real Expo data.
import { t, fmtNum } from "./i18n.js";
import { icon } from "./icons.js";
import { esc, pct, zoneName, locName, isOpen } from "./ui.js";
import { store } from "./store.js";

export const LOAD_LEVELS = [
  { max: 0.5, key: "l1", band: "#0e1d2e", fill: "#11302f", bar: "#4fc48d", label: "≤50%" },
  { max: 0.7, key: "l2", band: "#0e1d2e", fill: "#183634", bar: "#7bcf9a", label: "50–70%" },
  { max: 0.85, key: "l3", band: "#101e30", fill: "#2f3226", bar: "#cfa75a", label: "70–85%" },
  { max: 0.95, key: "l4", band: "#141d2f", fill: "#40301f", bar: "#f5b84a", label: "85–95%" },
  { max: 99, key: "l5", band: "#1a1a2b", fill: "#472329", bar: "#ff6b6b", label: "≥95%" },
];
export const loadLevel = (load) => LOAD_LEVELS.find((level) => (load || 0) < level.max) || LOAD_LEVELS.at(-1);
const RANK = { P1: 1, P2: 2, P3: 3, P4: 4 };
const worst = (list) => list.map((i) => i.priority).sort((a, b) => RANK[a] - RANK[b])[0];
const PIN_COLOR = { P1: "#e5484d", P2: "#e09a2a", P3: "#3f9bd6", P4: "#3f9bd6" };
const LOC_ICON = { "FOOD-COURT": "food", "EVENT-AREA": "event", "MAIN-WALKWAY": "route", "FIRST-AID": "aid",
  "MAIN-GATE": "gate", "WAITING-AREA": "team" };
// horizontal position of each demo location inside its band (0 = left edge, 1 = right edge)
const LOC_X = { "FOOD-COURT": 0.24, "EVENT-AREA": 0.74, "MAIN-WALKWAY": 0.5, "FIRST-AID": 0.81,
  "WAITING-AREA": 0.24, "MAIN-GATE": 0.8 };

const W = 1200, H = 660, X1 = W - 14, TOP = 8, GAP = 14;
let CARD_W = 190, X0 = CARD_W + 12;   // the compact map (command screen) uses a wider, larger-text card

// small deterministic random generator so the decoration does not move between renders
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
const hash = (str) => Array.from(str).reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
const textW = (s, fs) => Array.from(s).length * fs * 0.56;

function bandShape(i, y0, y1) {
  const ym = (y0 + y1) / 2;
  if (i % 3 === 1) {   // middle band: elongated hexagon, like a central plaza strip
    return `M${X0 + 70} ${y0 + 14} L${X1 - 70} ${y0 + 14} L${X1 - 16} ${ym} L${X1 - 70} ${y1 - 14} L${X0 + 70} ${y1 - 14} L${X0 + 16} ${ym} Z`;
  }
  return `M${X0 + 64} ${y0 + 14} L${X1 - 54} ${y0 + 14} Q${X1 - 18} ${y0 + 14} ${X1 - 18} ${y0 + 48} L${X1 - 22} ${y1 - 46}
    Q${X1 - 24} ${y1 - 14} ${X1 - 58} ${y1 - 14} L${X0 + 58} ${y1 - 14} Q${X0 + 22} ${y1 - 14} ${X0 + 18} ${y1 - 44}
    L${X0 + 26} ${y0 + 46} Q${X0 + 30} ${y0 + 14} ${X0 + 64} ${y0 + 14} Z`;
}

function tree(x, y, r, kind) {
  if (kind === "palm") {
    const fronds = [0, 60, 120, 180, 240, 300].map((a) => {
      const rad = a * Math.PI / 180;
      return `<path d="M${x} ${y - r} q${(Math.cos(rad) * r * 0.9).toFixed(1)} ${(Math.sin(rad) * r * 0.5 - r * 0.4).toFixed(1)} ${(Math.cos(rad) * r * 1.5).toFixed(1)} ${(Math.sin(rad) * r * 0.8).toFixed(1)}"/>`;
    }).join("");
    return `<g class="palm"><ellipse class="tree-shadow" cx="${x + 3}" cy="${y + 2}" rx="${r * 0.8}" ry="${r * 0.28}"/>
      <path class="trunk" d="M${x} ${y} L${x} ${y - r}"/>${fronds}</g>`;
  }
  return `<g class="tree"><ellipse class="tree-shadow" cx="${x + r * 0.4}" cy="${y + r * 0.75}" rx="${r}" ry="${r * 0.35}"/>
    <circle class="crown-d" cx="${x + r * 0.25}" cy="${y + r * 0.15}" r="${r}"/><circle class="crown" cx="${x}" cy="${y}" r="${r * 0.86}"/></g>`;
}

function pavilion(x, y, w, d, h, curved) {
  // simple isometric block: roof (top), front face and side face
  const dx = d * 0.9, dy = d * 0.45;
  const roof = curved
    ? `<path class="pv-roof" d="M${x} ${y - h} Q${x + w / 2} ${y - h - 22} ${x + w} ${y - h} L${x + w + dx} ${y - h - dy} Q${x + w / 2 + dx} ${y - h - dy - 22} ${x + dx} ${y - h - dy} Z"/>`
    : `<path class="pv-roof" d="M${x} ${y - h} L${x + w} ${y - h} L${x + w + dx} ${y - h - dy} L${x + dx} ${y - h - dy} Z"/>`;
  const windows = Array.from({ length: Math.max(1, Math.floor(w / 18)) }, (_, k) =>
    `<rect class="pv-win" x="${x + 6 + k * 18}" y="${y - h + 8}" width="9" height="${Math.max(6, h - 16)}" rx="1.5"/>`).join("");
  return `<g class="pavilion"><ellipse class="tree-shadow" cx="${x + w / 2 + dx / 2}" cy="${y + 3}" rx="${w / 2 + dx / 2 + 6}" ry="7"/>
    <path class="pv-side" d="M${x + w} ${y} L${x + w + dx} ${y - dy} L${x + w + dx} ${y - h - dy} L${x + w} ${y - h} Z"/>
    <rect class="pv-front" x="${x}" y="${y - h}" width="${w}" height="${h}"/>${windows}${roof}</g>`;
}

function zoneCard(z, y0, y1, selected, sim) {
  const load = sim?.load ?? z.load;
  const lv = loadLevel(load), p = pct(z.load), cy = (y0 + y1) / 2;
  const staffAfter = sim?.staff ?? z.staff_on_duty;
  const short = staffAfter < z.staff_required;
  const x = 14, r = x + CARD_W - 18;      // card content spans x..r (RTL text anchored at r)
  const loadText = sim && sim.load !== undefined && pct(sim.load) !== p
    ? `<tspan>${p}%</tspan><tspan class="arrow" dx="4">→</tspan><tspan class="after" dx="4">${pct(sim.load)}%</tspan>` : `${p}%`;
  const staffText = sim && sim.staff !== undefined && sim.staff !== z.staff_on_duty
    ? `<tspan direction="ltr">${z.staff_on_duty}→</tspan><tspan class="after" direction="ltr">${sim.staff}/${z.staff_required}</tspan>`
    : `<tspan direction="ltr">${z.staff_on_duty}/${z.staff_required}</tspan>`;
  return `<a class="zone-card ${selected ? "sel" : ""}" href="#/map/${esc(z.id)}" aria-label="${esc(zoneName(z.id))}: ${esc(t("map.zone_meta", { pct: p, on: z.staff_on_duty, req: z.staff_required }))}">
    <rect class="zc-hit" x="${x - 4}" y="${y0 + 6}" width="${CARD_W}" height="${y1 - y0 - 12}" rx="14"/>
    <rect class="zc-pill" x="${r - 120}" y="${cy - 76}" width="120" height="42" rx="9"/>
    <text class="zc-name" x="${r - 60}" y="${cy - 47}" text-anchor="middle">${esc(zoneName(z.id))}</text>
    <text class="zc-k" x="${r}" y="${cy - 8}" text-anchor="end">${esc(t("map.occupied"))}</text>
    <text class="zc-v ${sim?.load !== undefined ? "simv" : ""}" x="${x + 8}" y="${cy - 8}" text-anchor="start" direction="ltr">${loadText}</text>
    <rect class="zc-bar" x="${x + 8}" y="${cy + 6}" width="${r - x - 8}" height="10" rx="5"/>
    <rect x="${x + 8}" y="${cy + 6}" width="${((r - x - 8) * Math.min(1, load || 0)).toFixed(1)}" height="10" rx="5" fill="${lv.bar}"/>
    <text class="zc-k" x="${r}" y="${cy + 46}" text-anchor="end">${esc(t("map.staff_short"))}</text>
    <text class="zc-v ${short ? "short" : ""}" x="${x + 8}" y="${cy + 46}" text-anchor="start">${staffText}</text>
  </a>`;
}

/** Per-zone projected values for a simulation shown on the map: {zoneId: {load, staff}}. */
function simByZone(sim) {
  if (!sim) return {};
  const out = { [sim.source_zone]: { load: sim.source?.load_end } };
  if (sim.other_zone && sim.other) out[sim.other_zone] = { load: sim.other.load_end };
  const st = sim.staff || {};
  if (sim.action === "redeploy") {
    if (st.source) out[st.source.zone] = { ...(out[st.source.zone] || {}), staff: st.source.after };
    if (st.other) out[st.other.zone] = { ...(out[st.other.zone] || {}), staff: st.other.after };
  }
  return out;
}

function locPin(l, x, y, inc, opts) {
  const w = worst(inc), color = w ? PIN_COLOR[w] : "#2c4a6b";
  const label = locName(l.id), fs = opts.compact ? 23 : 19;
  const lw = textW(label, fs) + 34, lh = fs + 16;
  const ic = inc.length ? "incident" : (LOC_ICON[l.id] || "pin");
  const sel = opts.selected === l.id;
  const aria = `${label}${inc.length ? ` — ${t("map.loc_open", { n: inc.length })}` : ""}`;
  const chipW = opts.compact ? 58 : 50;
  const chipX = x + lw / 2 + 8 + chipW > X1 - 8 ? x - lw / 2 - 8 - chipW : x + lw / 2 + 8;   // keep the chip inside the map
  const team = opts.teams && opts.teamCount ? `<g class="team-chip ${opts.teamAssigned ? "assigned" : ""}" transform="translate(${chipX} ${y + 14})">
      <rect width="${chipW}" height="${lh - 4}" rx="${(lh - 4) / 2}"/>
      <svg x="8" y="${(lh - 4) / 2 - 8}" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icon("team").replace(/^<svg[^>]*>|<\/svg>$/g, "")}</svg>
      <text x="${opts.compact ? 42 : 36}" y="${(lh - 4) / 2 + 5}" text-anchor="middle">${fmtNum(opts.teamCount)}</text></g>` : "";
  return `<a class="loc ${w || "clear"} ${sel ? "sel" : ""}" href="#/map/${esc(l.id)}" aria-label="${esc(aria)}">
    ${w === "P1" ? `<circle class="halo" cx="${x}" cy="${y - 34}" r="30" fill="${color}"/>` : ""}
    <rect class="loc-hit" x="${x - Math.max(lw / 2, 26)}" y="${y - 60}" width="${Math.max(lw, 52)}" height="${72 + lh}" fill="transparent"/>
    <ellipse class="pin-shadow" cx="${x}" cy="${y + 2}" rx="11" ry="3.5"/>
    <path class="pin" fill="${color}" d="M${x} ${y} C${x - 6} ${y - 10} ${x - 21} ${y - 20} ${x - 21} ${y - 35} A21 21 0 1 1 ${x + 21} ${y - 35} C${x + 21} ${y - 20} ${x + 6} ${y - 10} ${x} ${y} Z"/>
    <svg class="pin-ic" x="${x - 11}" y="${y - 46}" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icon(ic).replace(/^<svg[^>]*>|<\/svg>$/g, "")}</svg>
    ${inc.length ? `<g class="pin-count"><circle cx="${x + 19}" cy="${y - 54}" r="12.5"/><text x="${x + 19}" y="${y - 49.5}" text-anchor="middle">${fmtNum(inc.length)}</text></g>` : ""}
    <rect class="lbl-bg" x="${x - lw / 2}" y="${y + 12}" width="${lw}" height="${lh}" rx="${lh / 2}"/>
    <text class="lbl" x="${x}" y="${y + 12 + lh / 2 + fs * 0.36}" text-anchor="middle">${esc(label)}</text>${team}
  </a>`;
}

/** The operations map. opts: { selected, teams, compact } */
export function sitePlan(state, opts = {}) {
  CARD_W = opts.compact ? 250 : 190; X0 = CARD_W + 12;
  const lay = store.layout;
  if (!lay) return `<div class="loading">${t("app.loading")}</div>`;
  const order = new Map(lay.zones.map((z, i) => [z.id, i]));
  const zones = [...(state.zones || [])].sort((a, b) => (order.get(a.id) ?? 99) - (order.get(b.id) ?? 99));
  const n = Math.max(1, zones.length);
  const bandH = (H - TOP * 2 - GAP * (n - 1)) / n;
  const open = (state.incidents || []).filter(isOpen);
  const selectedZone = opts.selected && store.locations[opts.selected] ? store.locations[opts.selected].zone_id : opts.selected;
  const simZ = simByZone(opts.sim);
  const bandY = {};

  // team positions (an assigned team is shown at its incident's location)
  const teamsAt = {};
  for (const tm of state.teams || []) {
    let at = tm.base_location;
    if (tm.status === "assigned" && tm.incident_id) {
      const inc = (state.incidents || []).find((i) => i.id === tm.incident_id);
      at = inc?.location_id || lay.locations.find((l) => l.zone_id === inc?.zone_id)?.id || at;
    }
    (teamsAt[at] ||= []).push(tm);
  }

  const pos = {};          // location id -> [x, y] (pin tip)
  const bands = [], cards = [], decor = [], pins = [], clips = [];
  zones.forEach((z, i) => {
    const y0 = TOP + i * (bandH + GAP), y1 = y0 + bandH;
    const zs = simZ[z.id];
    const lv = loadLevel(zs?.load ?? z.load), shape = bandShape(i, y0, y1);
    bandY[z.id] = (y0 + y1) / 2;
    const locs = lay.locations.filter((l) => l.zone_id === z.id);
    locs.forEach((l, k) => {
      const fx = LOC_X[l.id] ?? (locs.length === 1 ? 0.5 : 0.2 + (0.6 * k) / (locs.length - 1));
      pos[l.id] = [X0 + 40 + fx * (X1 - X0 - 80), y0 + bandH * 0.47];
    });
    bands.push(`<a class="band ${selectedZone === z.id ? "sel" : ""} ${zs ? "sim" : ""}" href="#/map/${esc(z.id)}" tabindex="-1" aria-hidden="true">
      <rect class="band-bg" x="6" y="${y0}" width="${W - 12}" height="${bandH}" rx="18" fill="${lv.band}"/>
      <path class="band-shape" d="${shape}" fill="${lv.fill}"/></a>`);
    clips.push(`<clipPath id="bandclip-${i}"><path d="${shape}"/></clipPath>`);
    cards.push(zoneCard(z, y0, y1, selectedZone === z.id, zs));

    // decoration: pavilions beside each location, then trees that avoid pins and labels
    const rnd = rng(hash(z.id));
    const items = [];
    const keepOut = locs.map((l) => pos[l.id]);
    locs.forEach((l, k) => {
      const [px, py] = pos[l.id];
      const side = k % 2 ? -1 : 1;
      items.push({ y: py - 30, svg: pavilion(px + side * 105 - (side < 0 ? 70 : 0), py - 26, 70, 34, 26 + rnd() * 10, rnd() > 0.6) });
      if (!opts.compact) items.push({ y: py + 46, svg: pavilion(px - side * 160 - (side > 0 ? 54 : 0), y1 - 26, 54, 26, 18, false) });
    });
    for (let k = 0; k < (opts.compact ? 26 : 42); k++) {
      const x = X0 + 30 + rnd() * (X1 - X0 - 60), y = y0 + 26 + rnd() * (bandH - 46);
      const clear = keepOut.every(([px, py]) => Math.abs(x - px) > 120 || Math.abs(y - py - 10) > 70);
      const notOnPavilion = keepOut.every(([px, py]) => Math.hypot(x - px, y - py) > 90);
      if (!clear || !notOnPavilion) continue;
      items.push({ y, svg: tree(+x.toFixed(1), +y.toFixed(1), +(7 + rnd() * 6).toFixed(1), i % 3 !== 0 && rnd() > 0.55 ? "palm" : "round") });
    }
    items.sort((a, b) => a.y - b.y);
    decor.push(`<g clip-path="url(#bandclip-${i})">${items.map((it) => it.svg).join("")}</g>`);

    locs.forEach((l) => {
      const [x, y] = pos[l.id];
      const inc = open.filter((it) => it.location_id === l.id);
      const tm = teamsAt[l.id] || [];
      pins.push(locPin(l, x, y, inc, { ...opts, teamCount: tm.length, teamAssigned: tm.some((m) => m.status === "assigned") }));
    });
  });

  const walks = (lay.walkways || []).filter(([a, b]) => pos[a] && pos[b]).map(([a, b]) => {
    const [x1, y1] = pos[a], [x2, y2] = pos[b];
    const my = (y1 + y2) / 2;
    const d = Math.abs(y1 - y2) < 4 ? `M${x1} ${y1 + 4} C${x1} ${y1 + 40} ${x2} ${y2 + 40} ${x2} ${y2 + 4}`
      : `M${x1} ${y1} C${x1} ${my} ${x2} ${my} ${x2} ${y2}`;
    return `<path class="walk-edge" d="${d}"/><path class="walk" d="${d}"/>`;
  }).join("");

  // simulation overlay: a moving gold flow between the two zones the option touches + a label
  let simLayer = "";
  if (opts.sim && bandY[opts.sim.source_zone] !== undefined) {
    const s = opts.sim, ys = bandY[s.source_zone];
    const fx = X1 - 70;
    if (s.other_zone && bandY[s.other_zone] !== undefined) {
      const yo = bandY[s.other_zone];
      const [ya, yb] = s.action === "redeploy" ? [yo, ys] : [ys, yo];   // people/staff move a -> b
      const bend = Math.sign(yb - ya) * 0;
      simLayer += `<path class="sim-flow" d="M${fx} ${ya + Math.sign(yb - ya) * 30} C${fx - 90} ${ya + (yb - ya) * .3 + bend} ${fx - 90} ${ya + (yb - ya) * .7} ${fx} ${yb - Math.sign(yb - ya) * 34}"/>
        <path d="M${fx - 9} ${yb - Math.sign(yb - ya) * 46} L${fx} ${yb - Math.sign(yb - ya) * 30} L${fx + 9} ${yb - Math.sign(yb - ya) * 46}" fill="none" stroke="var(--gold)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>`;
    }
    const label = esc(opts.simLabel || t("home.sim_mode"));
    const lw = textW(opts.simLabel || t("home.sim_mode"), 20) + 30;
    simLayer += `<g class="sim-tag" transform="translate(${(X0 + X1) / 2 - lw / 2} ${ys - bandH / 2 + 4})"><rect width="${lw}" height="34" rx="8"/><text x="${lw / 2}" y="23" text-anchor="middle">${label}</text></g>`;
  }

  return `<svg class="opsmap ${opts.compact ? "compact" : ""}" viewBox="0 0 ${W} ${H}" role="group" aria-label="${esc(t("map.plan_heading"))}" style="direction:ltr">
    <defs>${clips.join("")}<filter id="lblShadow" x="-20%" y="-40%" width="140%" height="190%"><feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#000" flood-opacity=".4"/></filter></defs>
    ${bands.join("")}<g class="walks" pointer-events="none">${walks}</g><g pointer-events="none">${decor.join("")}</g>
    ${cards.join("")}${pins.join("")}<g pointer-events="none">${simLayer}</g>
    <g class="north" transform="translate(${X1 - 44} ${TOP + 30})" aria-hidden="true"><circle r="17"/><path d="M0 -10 L6 7 L0 3 L-6 7 Z"/><text y="-21" text-anchor="middle">N</text></g>
  </svg>`;
}

/** Bottom legend bar (same order as the reference: note, markers, occupancy levels). */
export function legend() {
  const levels = LOAD_LEVELS.map((lv) => `<span class="lg-level"><i style="background:${lv.fill};border-color:${lv.bar}"></i><bdi>${lv.label}</bdi></span>`).join("");
  return `<div class="map-legend" role="note">
    <span class="lg-note">${icon("info")}<span>${t("map.legend_note")}</span></span>
    <span class="lg-item">${icon("pin")}<span>${t("map.legend_location")}</span></span>
    <span class="lg-item lg-incident"><i aria-hidden="true">!</i><span>${t("map.legend_incident")}</span></span>
    <span class="lg-levels"><span class="lg-caption">${t("map.legend_levels")}</span>${levels}</span>
  </div>`;
}
