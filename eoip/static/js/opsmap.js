// Operations map in the team's UX design: a drawn site terrain, organic zone shapes coloured by
// live occupancy, location markers, incident pins (colour = priority), cameras and the simulation
// overlay (projected occupancy + a moving flow between the two zones an option touches).
// Illustrative layout — NOT the official Expo 2030 site plan. Every number comes from /api/state.
import { t } from "./i18n.js";
import { icon } from "./icons.js";
import { esc, pct, zoneName, locName, teamName, isOpen, incTitle } from "./ui.js";

// zone shapes (1000 × 780 canvas), from the UX design
const ZPOLY = {
  "ZONE-A": [[120, 271], [139, 217], [194, 181], [278, 172], [352, 163], [417, 176], [500, 208], [532, 262], [519, 316], [463, 380], [407, 425], [333, 443], [259, 425], [185, 389], [130, 343]],
  "ZONE-B": [[667, 217], [704, 163], [787, 145], [861, 172], [917, 208], [963, 262], [954, 325], [917, 371], [852, 380], [769, 371], [704, 344], [667, 298]],
  "ZONE-C": [[593, 506], [648, 452], [722, 434], [815, 443], [889, 461], [944, 506], [954, 579], [935, 633], [870, 669], [796, 678], [713, 669], [639, 633], [583, 579]],
};
const CARD = { "ZONE-A": [318, 222], "ZONE-B": [850, 205], "ZONE-C": [768, 500] };
const CENTER = { "ZONE-A": [330, 330], "ZONE-B": [815, 290], "ZONE-C": [770, 590] };
const LOC = {
  "FOOD-COURT": [232, 345], "EVENT-AREA": [440, 312],
  "MAIN-WALKWAY": [730, 305], "FIRST-AID": [885, 310],
  "WAITING-AREA": [668, 612], "MAIN-GATE": [862, 622],
};
const LOC_ICON = { "FOOD-COURT": "food", "EVENT-AREA": "event", "MAIN-WALKWAY": "route", "FIRST-AID": "aid", "MAIN-GATE": "gate", "WAITING-AREA": "team" };
const CAMS = [[150, 300], [455, 230], [300, 410], [690, 340], [930, 270], [640, 560], [910, 560], [800, 650]];
const SEV = { P1: "#e5383b", P2: "#f2a33a", P3: "#2e9be0", P4: "#2e9be0" };
const PIN_ICON = { fire: "flame", medical: "medical", crowd_pressure: "crowd" };

export const loadColor = (load) => (load >= 0.85 ? "#ff6b6b" : load >= 0.65 ? "#f5b84a" : "#4ade80");
const P = (x, y) => `left:${(x / 10).toFixed(2)}%;top:${(y / 7.8).toFixed(2)}%`;

function smooth(pts) {   // closed Catmull-Rom → cubic Bézier
  const n = pts.length, Q = (i) => pts[(i + n) % n];
  let d = `M${Q(0)[0]} ${Q(0)[1]}`;
  for (let i = 0; i < n; i++) {
    const p0 = Q(i - 1), p1 = Q(i), p2 = Q(i + 1), p3 = Q(i + 2);
    d += ` C${(p1[0] + (p2[0] - p0[0]) / 6).toFixed(1)} ${(p1[1] + (p2[1] - p0[1]) / 6).toFixed(1)}, ${(p2[0] - (p3[0] - p1[0]) / 6).toFixed(1)} ${(p2[1] - (p3[1] - p1[1]) / 6).toFixed(1)}, ${p2[0]} ${p2[1]}`;
  }
  return `${d}Z`;
}

/* ---------- terrain: drawn once per page load (deterministic) ---------- */
let terrainUrl = null;
function terrain() {
  if (terrainUrl !== null) return terrainUrl;
  try {
    const W = 1000, H = 780, S = 2, cv = document.createElement("canvas");
    cv.width = W * S; cv.height = H * S;
    const x = cv.getContext("2d"); x.scale(S, S);
    let seed = 20261010;
    const R = () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let q = Math.imul(seed ^ seed >>> 15, 1 | seed); q = q + Math.imul(q ^ q >>> 7, 61 | q) ^ q; return ((q ^ q >>> 14) >>> 0) / 4294967296; };
    const pick = (a) => a[Math.floor(R() * a.length)];
    x.fillStyle = "#2f3a3a"; x.fillRect(0, 0, W, H);
    for (let i = 0; i < 420; i++) { x.globalAlpha = 0.5; x.fillStyle = pick(["#36433e", "#2a3533", "#3d4743", "#323d3a", "#454e49"]); x.beginPath(); x.ellipse(R() * W, R() * H, 20 + R() * 50, 14 + R() * 36, R() * 3, 0, 7); x.fill(); }
    x.globalAlpha = 1;
    for (let gy = 8; gy < H; gy += 50) for (let gx = 8; gx < W; gx += 56) {       // city blocks
      if (R() < 0.22) continue;
      const bw = 44 + R() * 6, bh = 38 + R() * 6;
      x.fillStyle = "rgba(120,128,130,.3)"; x.fillRect(gx, gy, bw, bh);
      const parts = 1 + Math.floor(R() * 4);
      for (let k = 0; k < parts; k++) {
        const w = 10 + R() * (bw * 0.55), h = 10 + R() * (bh * 0.55), px = gx + 2 + R() * (bw - w - 4), py = gy + 2 + R() * (bh - h - 4);
        x.fillStyle = "rgba(0,0,0,.38)"; x.fillRect(px + 2.5, py + 2.5, w, h);
        x.fillStyle = pick(["#6c7479", "#7d8180", "#5a6368", "#8a877f", "#99968b", "#525b60", "#a2a29b"]); x.fillRect(px, py, w, h);
        x.fillStyle = "rgba(255,255,255,.08)"; x.fillRect(px, py, w, 2);
      }
    }
    for (let i = 0; i < 3000; i++) {                                               // trees
      const tx = R() * W, ty = R() * H, r = 3 + R() * 6.5;
      x.fillStyle = pick(["#2a5230", "#316036", "#21422b", "#3d6e3e", "#264a31"]); x.beginPath(); x.arc(tx, ty, r, 0, 7); x.fill();
      x.fillStyle = "rgba(170,210,120,.18)"; x.beginPath(); x.arc(tx - r * 0.3, ty - r * 0.3, r * 0.5, 0, 7); x.fill();
    }
    const road = (fn, w, center) => {
      x.lineCap = "round"; x.lineJoin = "round";
      x.strokeStyle = "#232a2e"; x.lineWidth = w + 4; x.beginPath(); fn(); x.stroke();
      x.strokeStyle = "#7c8488"; x.lineWidth = w; x.beginPath(); fn(); x.stroke();
      if (center) { x.setLineDash([7, 8]); x.strokeStyle = "rgba(235,230,210,.55)"; x.lineWidth = 1; x.beginPath(); fn(); x.stroke(); x.setLineDash([]); }
    };
    for (let gx = 0; gx <= W; gx += 112) road(() => { x.moveTo(gx + R() * 6, 0); x.bezierCurveTo(gx + 20, H * 0.3, gx - 20, H * 0.7, gx + R() * 6, H); }, 4, false);
    for (let gy = 0; gy <= H; gy += 104) road(() => { x.moveTo(0, gy); x.bezierCurveTo(W * 0.3, gy + 16, W * 0.7, gy - 16, W, gy + R() * 6); }, 4, false);
    road(() => { x.moveTo(30, 40); x.bezierCurveTo(300, 10, 700, 20, 980, 50); }, 11, true);
    road(() => { x.moveTo(20, 740); x.bezierCurveTo(300, 770, 700, 760, 985, 730); }, 11, true);
    road(() => { x.moveTo(40, 30); x.bezierCurveTo(10, 300, 20, 500, 40, 760); }, 10, true);
    road(() => { x.moveTo(975, 30); x.bezierCurveTo(995, 300, 990, 500, 975, 760); }, 10, true);
    const px = 585, py = 402;
    road(() => { x.ellipse(px, py, 100, 100, 0, 0, 7); }, 14, true);
    road(() => { x.moveTo(px, py - 100); x.bezierCurveTo(630, 280, 670, 200, 677, 120); }, 12, true);
    road(() => { x.moveTo(px - 80, py - 60); x.bezierCurveTo(470, 300, 360, 200, 233, 120); }, 10, true);
    road(() => { x.moveTo(px - 80, py + 60); x.bezierCurveTo(450, 540, 320, 620, 274, 700); }, 12, true);
    road(() => { x.moveTo(px + 90, py + 45); x.bezierCurveTo(720, 520, 560, 600, 889, 700); }, 10, true);
    road(() => { x.moveTo(px + 100, py); x.bezierCurveTo(700, 400, 800, 410, 975, 400); }, 10, true);
    road(() => { x.moveTo(40, 470); x.bezierCurveTo(200, 500, 380, 470, px - 100, py + 20); }, 9, true);
    x.fillStyle = "#a9a59a"; x.beginPath(); x.arc(px, py, 70, 0, 7); x.fill();               // central plaza + fountain
    x.strokeStyle = "rgba(90,80,70,.45)"; x.lineWidth = 1;
    for (let a = 0; a < 48; a++) { x.beginPath(); x.moveTo(px + Math.cos(a / 48 * 6.283) * 36, py + Math.sin(a / 48 * 6.283) * 36); x.lineTo(px + Math.cos(a / 48 * 6.283) * 70, py + Math.sin(a / 48 * 6.283) * 70); x.stroke(); }
    const g = x.createRadialGradient(px, py, 4, px, py, 34); g.addColorStop(0, "#cfeaf6"); g.addColorStop(0.5, "#6fb2d4"); g.addColorStop(1, "#2d6e92");
    x.fillStyle = g; x.beginPath(); x.arc(px, py, 34, 0, 7); x.fill();
    x.strokeStyle = "#e9e5da"; x.lineWidth = 3; x.beginPath(); x.arc(px, py, 35, 0, 7); x.stroke();
    x.fillStyle = "rgba(6,12,22,.30)"; x.fillRect(0, 0, W, H);                                 // grade towards navy for contrast
    const v = x.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.85); v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, "rgba(4,8,16,.5)");
    x.fillStyle = v; x.fillRect(0, 0, W, H);
    terrainUrl = cv.toDataURL("image/jpeg", 0.86);
  } catch { terrainUrl = ""; }
  return terrainUrl;
}

/** projected values per zone for a simulation: {zoneId: {load, staff}} */
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

/** The map. opts: { selected (zone/location/incident id), sim, simLabel, teams, fill,
 *  heat (colour zones by load, default on), pins (report pins, default on), cams (default on) } */
export function opsMap(state, opts = {}) {
  const heat = opts.heat !== false, showPins = opts.pins !== false, showCams = opts.cams !== false;
  const zones = state.zones || [];
  const open = (state.incidents || []).filter(isOpen);
  const simZ = simByZone(opts.sim);
  const selZone = ZPOLY[opts.selected] ? opts.selected : null;

  const zpaths = zones.filter((z) => ZPOLY[z.id]).map((z) => {
    const s = simZ[z.id], load = s?.load ?? z.load, c = heat || s ? loadColor(load) : "#8aa0b8", d = smooth(ZPOLY[z.id]);
    return `<a href="#/map/${z.id}" aria-label="${esc(zoneName(z.id))}"><path class="zone ${selZone === z.id ? "sel" : ""} ${s ? "sim" : ""}" d="${d}" fill="${c}" fill-opacity="${heat || s ? ".34" : ".12"}" stroke="${c}" stroke-width="${selZone === z.id || s ? 4 : 2.5}" ${s ? 'stroke-dasharray="12 7"' : ""}/></a>
      <path d="${d}" fill="url(#zgrid)" pointer-events="none"/>`;
  }).join("");

  const cards = zones.filter((z) => CARD[z.id]).map((z) => {
    const s = simZ[z.id], load = s?.load ?? z.load, c = heat || s ? loadColor(load) : "#8aa0b8";
    const loadTxt = s?.load !== undefined && pct(s.load) !== pct(z.load) ? `<bdi>${pct(z.load)}% → <b class="after">${pct(s.load)}%</b></bdi>` : `<bdi>${pct(z.load)}%</bdi>`;
    const staffAfter = s?.staff ?? z.staff_on_duty;
    const staffTxt = s?.staff !== undefined && s.staff !== z.staff_on_duty ? `<bdi>${z.staff_on_duty} → <b class="after">${s.staff}/${z.staff_required}</b></bdi>` : `<bdi>${z.staff_on_duty}/${z.staff_required}</bdi>`;
    return `<a class="zcard ${selZone === z.id ? "sel" : ""}" href="#/map/${z.id}" style="${P(...CARD[z.id])};--c:${c}">
      <b>${esc(zoneName(z.id))}</b>
      <span><i class="zd"></i>${t("map.occupied")} ${loadTxt}</span>
      <span class="${staffAfter < z.staff_required ? "short" : ""}">${icon("team")}${t("map.staff_short")} ${staffTxt}</span></a>`;
  }).join("");

  const locs = (state.locations || []).filter((l) => LOC[l.id]).map((l) => `<a class="locmark ${opts.selected === l.id ? "sel" : ""}" href="#/map/${l.id}" style="${P(LOC[l.id][0], LOC[l.id][1] + 26)}">${icon(LOC_ICON[l.id] || "pin")}<span>${esc(locName(l.id))}</span></a>`).join("");

  // incident pins sit on their location (spread out when several share one)
  const byLoc = {};
  const pins = !showPins ? "" : open.map((i) => {
    const at = LOC[i.location_id] || CENTER[i.zone_id];
    if (!at) return "";
    const k = i.location_id || i.zone_id, n = (byLoc[k] = (byLoc[k] || 0) + 1) - 1;
    const x = at[0] + (n ? (n % 2 ? 1 : -1) * Math.ceil(n / 2) * 34 : 0), y = at[1] - 8;
    const crit = i.priority === "P1" && i.status === "open";
    return `<a class="pin ${crit ? "crit" : ""} ${String(opts.selected) === String(i.id) ? "sel" : ""}" href="#/c/${i.id}" style="${P(x, y)};--c:${SEV[i.priority] || SEV.P3}" title="${esc(`${i.priority} · ${incTitle(i)}`)}" aria-label="${esc(`${i.priority} · ${incTitle(i)}`)}">
      <span class="h">${icon(PIN_ICON[i.type] || "incident")}</span></a>`;
  }).join("");

  const teams = opts.teams ? (state.teams || []).filter((tm) => tm.status === "assigned" && tm.incident_id).map((tm, k) => {
    const inc = open.find((i) => i.id === tm.incident_id);
    const at = inc && (LOC[inc.location_id] || CENTER[inc.zone_id]);
    return at ? `<span class="mtag" style="${P(at[0] + 70, at[1] - 40 + k * 26)}">${icon("team")}${esc(teamName(tm.id))}</span>` : "";
  }).join("") : "";

  const cams = !showCams ? "" : CAMS.map(([cx, cy]) => `<span class="cam" style="${P(cx, cy)}">${icon("camera")}</span>`).join("")
    + `<span class="camtag" style="${P(612, 360)}">${icon("camera")}CAM-B-03</span>`;

  let flow = "", simTag = "";
  if (opts.sim && CENTER[opts.sim.source_zone]) {
    const s = opts.sim;
    const src = CENTER[s.source_zone];
    if (s.other_zone && CENTER[s.other_zone]) {
      const oth = CENTER[s.other_zone];
      const [a, b] = s.action === "redeploy" ? [oth, src] : [src, oth];   // people / staff move a -> b
      const mx = (a[0] + b[0]) / 2 + (b[1] - a[1]) * 0.18, my = (a[1] + b[1]) / 2 - (b[0] - a[0]) * 0.18;
      flow = `<path class="flow" d="M${a[0]} ${a[1]} Q${mx.toFixed(0)} ${my.toFixed(0)} ${b[0]} ${b[1]}" fill="none" stroke="#d4a64a" stroke-width="6" stroke-dasharray="14 9" stroke-linecap="round" marker-end="url(#ao)"/>`;
      simTag = `<span class="simtag" style="${P(mx, my)}">${esc(opts.simLabel || "")}</span>`;
    } else {
      simTag = `<span class="simtag" style="${P(src[0], src[1] + 40)}">${esc(opts.simLabel || "")}</span>`;
    }
  }

  return `<div class="omap ${opts.fill ? "fill" : ""}" dir="ltr"><img class="terrain" src="${terrain()}" alt="" draggable="false">
    <svg class="ov" viewBox="0 0 1000 780" preserveAspectRatio="none" role="group" aria-label="${esc(t("map.plan_heading"))}">
      <defs><pattern id="zgrid" width="26" height="22" patternUnits="userSpaceOnUse" patternTransform="rotate(-8)"><path d="M0 0H26M0 0V22" stroke="rgba(255,255,255,.18)" stroke-width="1" fill="none"/></pattern>
        <marker id="ao" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="3.6" markerHeight="3.6" orient="auto"><path d="M0 0 10 5 0 10z" fill="#d4a64a"/></marker></defs>
      ${zpaths}${flow}</svg>
    <div class="lay" dir="${document.documentElement.dir || "rtl"}">${cams}${locs}${cards}${teams}${pins}${simTag}
      <span class="compass" style="${P(958, 56)}">N</span>${opts.sim ? `<span class="mode">${t("home.sim_mode")}</span>` : ""}</div></div>`;
}

/** Legend under the map. */
export function mapLegend() {
  return `<div class="legend">
    <span><i style="background:#4ade80"></i>${t("map.lg_ok")}</span><span><i style="background:#f5b84a"></i>${t("map.lg_high")}</span><span><i style="background:#ff6b6b"></i>${t("map.lg_crowd")}</span>
    <span><i class="dot" style="background:#e5383b"></i>${t("map.lg_p1")}</span><span><i class="dot" style="background:#f2a33a"></i>${t("map.lg_p2")}</span><span><i class="dot" style="background:#2e9be0"></i>${t("map.lg_p3")}</span>
    <span>${icon("camera")}${t("map.lg_cam")}</span><span class="lg-note">${t("map.legend_note")}</span></div>`;
}
