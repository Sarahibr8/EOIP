// Shared formatting + label helpers. Every visible string goes through t().
import { t, getLang, fmtNum, fmtAge, fmtTime } from "./i18n.js";
import { icon, TYPE_ICON, SOURCE_ICON } from "./icons.js";
import { store } from "./store.js";

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const pct = (x) => Math.round((x || 0) * 100);
export const OPEN = ["open", "action_approved"];
export const isOpen = (i) => OPEN.includes(i.status);
export const iso = (x) => `⁨${x}⁩`;          // keep Latin codes in order inside Arabic text
export const code = (x) => `<bdi class="code">${esc(x)}</bdi>`;

// names: live layout first, then names carried by a decision snapshot (earlier runs)
let extraNames = {};
export function withNames(names, fn) { const prev = extraNames; extraNames = names || {}; try { return fn(); } finally { extraNames = prev; } }
const nm = (obj) => (getLang() === "ar" ? obj.name_ar ?? obj.ar : obj.name_en ?? obj.en);

export function zoneName(id) {
  if (!id) return t("place.unknown_zone");
  const z = store.zones[id] || extraNames[id];
  return z ? nm(z) : id;
}
export function locName(id) {
  if (!id) return "";
  const l = store.locations[id] || extraNames[id];
  return l ? nm(l) : id;
}
export function teamName(id) {
  const tm = store.teams[id] || extraNames[id];
  return tm ? nm(tm) : (id || "—");
}
/** "Zone A · Food Court" as text */
export function placeText(zone, loc, detail) {
  const parts = [zoneName(zone)];
  if (loc) parts.push(locName(loc)); else if (detail) parts.push(detail);
  return parts.join(" · ");
}
/** place chip: zone + location (or "location not stated") */
export function placeHtml(zone, loc, detail) {
  if (!zone) return `<span class="place unknown">${t("place.unknown_zone")}</span>`;
  const where = loc ? `<b>${esc(locName(loc))}</b>` : detail ? `<span>${esc(detail)}</span>` : `<span class="muted">${t("place.no_location")}</span>`;
  return `<span class="place"><b>${esc(zoneName(zone))}</b><span class="sep"></span>${where}</span>`;
}

export const listJoin = (arr) => arr.join(getLang() === "ar" ? "، " : ", ");
export const incTitle = (i) => t(`incident_label.${i.label || i.type}`);

export function prioBadge(p) { return `<span class="prio ${p}">${p} · ${t(`priority.${p}`)}</span>`; }
export function originTag(o) { return `<span class="tag ${o}">${t(`origin.${o}`)}</span>`; }

// translate {key, params} with zone/location/team/type/percentage conversion
export function tr(prefix, item) {
  const p = { ...(item.params || {}) };
  for (const k of ["zone", "from_zone", "to_zone"]) if (k in p) p[k] = zoneName(p[k]);
  for (const k of ["location", "from_location", "this_location"]) if (k in p) p[k] = p[k] ? locName(p[k]) : t("place.no_location");
  if (p.team && (store.teams[p.team] || extraNames[p.team])) p.team = teamName(p.team);
  if (p.kind) p.kind = t(`teamkind.${p.kind}`);
  if (p.type) p.type = t(`incident_type.${p.type}`);
  if (p.load !== undefined) p.pct = pct(p.load);
  if (p.confidence !== undefined) p.pct = pct(p.confidence);
  if (p.before !== undefined) p.before = pct(p.before);
  if (p.after !== undefined) p.after = pct(p.after);
  if (p.people !== undefined) p.people = fmtNum(p.people);
  if (p.code) p.code = iso(p.code);
  if (p.source) p.source = t(`source_system.${p.source}`);
  if (Array.isArray(p.adjacent)) p.adjacent = listJoin(p.adjacent.map(zoneName));
  return t(`${prefix}.${item.key}`, p);
}

function recParams(rec, incZone) {
  const p = { ...rec.params, zone: zoneName(rec.params.zone || incZone) };
  for (const k of ["from_zone", "to_zone"]) if (p[k]) p[k] = zoneName(p[k]);
  if (!p.to_zone) p.to_zone = p.zone;   // decisions logged before v3 did not record the receiving zone
  return p;
}
export function recTitle(rec, incZone) {
  const p = recParams(rec, incZone);
  if (/^(FIRE|MED)-\d+$/.test(rec.code)) return t(`option.${rec.code}`);
  if (rec.code === "route_team") return t("option.route_team", { team: t(`team.${p.team}`) });
  return t(`option.${rec.code}`, p);
}
export function recDesc(rec, incZone) { return t(`option.${rec.code}_desc`, recParams(rec, incZone)); }

/** One incident strip — the signature element. */
export function strip(i, opts = {}) {
  const r = i.top_reasons?.[0];
  const closed = !isOpen(i);
  const srcs = (i.sources || []).map((s) => icon(SOURCE_ICON[s])).join("");
  return `<a class="strip ${closed ? "closed" : i.priority} ${opts.big ? "big" : ""}" href="#/incident/${i.id}">
    <span class="pb"><span class="priority-icon">${icon(TYPE_ICON[i.type])}</span><b>${i.priority}</b><small>${t(`priority.${i.priority}`)}</small></span>
    <span class="body">
      <span class="t"><h3>${icon(TYPE_ICON[i.type])}${esc(incTitle(i))}</h3>${placeHtml(i.zone_id, i.location_id)}</span>
      <span class="why">${code(i.code)} · ${r ? esc(tr("reason", r)) : t(`kind.${i.kind}`)}</span>
    </span>
    <span class="side">
      <span class="src" title="${esc(listJoin((i.sources || []).map((s) => t(`source_system.${s}`))))}">${srcs}</span>
      ${opts.decide && i.status === "open" ? "" : `<span class="tag ${i.status === "action_approved" ? "ok" : ""}">${t(`status.${i.status}`)}</span>`}
      <span class="age">${fmtAge(i.updated_at)}</span>
      ${opts.decide && i.status === "open" ? `<span class="btn ${i.priority === "P1" ? "btn-danger" : "btn-primary"}" data-go="#/decide/${i.id}">${t("overview.open_decision")}</span>` : ""}
    </span>
  </a>`;
}

let toastBox;
export function toast(msg, kind = "", sticky = false) {
  toastBox = toastBox || document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  const critical = kind.includes("critical");
  el.setAttribute("role", critical ? "button" : kind.includes("error") ? "alert" : "status");
  if (critical) {
    el.tabIndex = 0;
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); el.click(); }
    });
  }
  const symbol = critical ? "incident" : kind.includes("error") ? "x" : "check";
  el.innerHTML = `<span class="toast-icon">${icon(symbol)}</span><span class="toast-copy">${esc(msg)}</span>`;
  toastBox.appendChild(el);
  if (!sticky) setTimeout(() => el.remove(), 4500);
  return el;
}

export function errorText(e) {
  if (e?.network) return t("errors.network");
  if (!e?.code) return t("errors.ui", { detail: String(e?.message || e) });   // a bug in the page, not the server
  const k = `errors.${e.code}`;
  const msg = t(k);
  return msg === k ? t("errors.generic", { code: e.code }) : msg;
}

export function emptyState(title, body = "") {
  return `<div class="empty"><b>${esc(title)}</b>${body ? esc(body) : ""}</div>`;
}
export const loading = () => `<div class="loading">${t("app.loading")}</div>`;
export const timeAt = (isoStr, sec = true) => (isoStr ? fmtTime(isoStr, sec) : "—");

/* Every report reaches the centre over one of two channels: a camera or the radio. */
// Four kinds of source, as in the team video: camera, radio (field staff), automatic systems, service requests.
const SRC_KIND = { cctv_ai: "camera", radio: "radio" };
export const srcKind = (s) => SRC_KIND[s] || "system";
export function srcChip(kind, n) {
  return `<span class="src-chip ${kind}">${icon(kind)}${t(`src2.${kind}`)}${n > 1 ? ` <bdi>× ${n}</bdi>` : ""}</span>`;
}
/** Source chips for a list of source systems (or alerts), grouped into camera / radio. */
export function srcChips(list, count = false) {
  const n = {};
  (list || []).forEach((s) => { const k = srcKind(s); n[k] = (n[k] || 0) + 1; });
  return ["camera", "radio"].filter((k) => n[k]).map((k) => srcChip(k, count ? n[k] : 1)).join("");
}

/* ---------- escalation matrix (server rule: core/escalation.py) ----------
   A case still waiting for a decision after one response time goes to L1, after two to L2, after three to L3. */
const ESC_FALLBACK = { step_s: { P1: 60, P2: 180, P3: 300, P4: 300 }, levels: ["L1", "L2", "L3"] };
export function escMatrix() { return store.state?.escalation || ESC_FALLBACK; }
export function escInfo(i, now = Date.now()) {
  const m = escMatrix();
  const step = (m.step_s[i.priority] || m.step_s.P3) * 1000;
  const from = new Date(i.escalated_at || i.opened_at).getTime();
  const level = Number.isFinite(from) ? Math.max(0, Math.min(m.levels.length, Math.floor((now - from) / step))) : 0;
  return { step, from, deadline: from + step, level, code: level ? m.levels[level - 1] : null };
}
/** "escalated to L1 · shift manager" for the level reached (or the first one, before it is reached). */
export function escLabel(code) { return t("esc.escalated", { code: iso(code), role: t(`escalation.${code}`) }); }
/** Small red tag on a list item when a waiting case is already late. */
export function escTag(i) {
  if (i.status !== "open") return "";
  const e = escInfo(i);
  return e.level ? `<span class="esc-tag" title="${esc(escLabel(e.code))}">${icon("incident")}${t("esc.tag", { code: iso(e.code) })}</span>` : "";
}
