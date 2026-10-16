// Command screen (home): everything the duty officer needs on one screen.
//   critical alert bar (with time left to act) · KPIs · decision panel · decision queue · live map
// Data and logic come from /api/state and /api/incidents/<id> — nothing here is hard-coded.
import { t, fmtNum, fmtTime, fmtAge } from "../i18n.js";
import { icon, TYPE_ICON } from "../icons.js";
import { esc, pct, zoneName, teamName, tr, isOpen, recTitle, recDesc, toast, errorText, incTitle, placeText, code, srcKind, srcChips, escInfo, escLabel, escTag } from "../ui.js";
import { api, detail, refresh } from "../store.js";
import { opsMap, mapLegend } from "../opsmap.js";

// Response target for life-safety incidents, counted from the moment the incident became critical
// (or was opened). A target, not a prediction — the label says so.
export const RESPONSE_TARGET_MIN = 3;
const GATE_RATE = 16;              // visitors per staff member per minute (same as core/simulate.py)

const ui = { sel: null, picked: false, preview: null, routineOpen: false, busy: false, proc: null };
const notes = {};

// The dashboard shows only what still waits for a decision. As soon as the officer approves or
// rejects, the case leaves the queue and the alerts list and is found in the log (and under
// «حالة المعالجة» while the approved response is under way).
const waiting = (i) => i.status === "open";        // an escalated case (status «escalated») has left the officer
const handled = (i) => i.status === "resolved" || i.status === "dismissed";
const needsDecision = (i) => waiting(i) && (i.priority === "P1" || i.priority === "P2");
// one list for every case waiting for a decision: critical first, then medium, then normal
const RANK = { P1: 1, P2: 2, P3: 3, P4: 3 };
const byUrgency = (a, b) => (RANK[a.priority] || 4) - (RANK[b.priority] || 4) || b.priority_score - a.priority_score
  || new Date(b.updated_at) - new Date(a.updated_at);

/* ---------- time windows ---------- */
export function emergencyDeadline(i) {
  const from = i.escalated_at || i.opened_at;
  return from ? new Date(from).getTime() + RESPONSE_TARGET_MIN * 60000 : null;
}
function minutesToCapacity(z) {
  if (!z) return null;
  const proc = z.kind === "gate" ? Math.max(1, z.staff_on_duty * GATE_RATE) : Math.max(1, z.outflow_per_min);
  const net = z.inflow_per_min - proc;
  return net > 0 && z.occupancy < z.capacity ? (z.capacity - z.occupancy) / net : null;
}
/** {deadline, cls, label, text} for the window box of an incident. */
function windowInfo(i, state) {
  if (i.status === "action_approved") return { cls: "done", label: t("home.window_handled"), text: "✓" };
  if (i.status !== "open") return null;
  // response time by priority (escalation matrix): when it runs out the case is late and escalated L1 → L2 → L3
  const e = escInfo(i);
  return { deadline: e.deadline, label: t("home.window"), lateLabel: escLabel(e.code || "L1"),
    title: t("esc.note", { min: Math.round(e.step / 60000) }) };
}
const mmss = (ms) => {
  const s = Math.round(Math.abs(ms) / 1000);
  return `${ms < 0 ? "+" : ""}${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};
/** Fill every countdown on the page (called after each render and once a second). */
export function tickCountdowns(root = document) {
  const now = Date.now();
  root.querySelectorAll("[data-deadline]").forEach((el) => {
    const left = Number(el.dataset.deadline) - now;
    // past the target: say so in a word instead of a growing number
    el.textContent = left < 0 ? (el.dataset.lateText || mmss(left)) : mmss(left);
    const box = el.closest(".window, .ab-m");
    if (box) {
      box.classList.toggle("late", left < 0);
      const lbl = box.querySelector("[data-late-label]");
      if (lbl) lbl.textContent = left < 0 ? lbl.dataset.lateLabel : lbl.dataset.label;
    }
  });
}

/* ---------- small pieces ---------- */
const sevClass = (p) => `sev-${p || "P4"}`;
const pill = (p) => `<span class="pill"><span class="pdot"></span>${p} · ${t(`priority.${p}`)}</span>`;
const srcCount = (n) => (n === 1 ? t("home.source_1") : t("home.sources_n", { n }));
const ago = (iso) => (iso ? fmtAge(iso) : "");

function greeting() {
  const name = (document.body.dataset.employeeName || "").split(" ")[0];
  const h = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hour12: false, timeZone: "Asia/Riyadh" }).format(new Date()));
  return t(h < 12 ? "home.greet_morning" : "home.greet_evening", { name });
}

function alertBars(list) {
  return list.map((i) => {
    const e = escInfo(i), dl = e.deadline;
    return `<div class="alertbar" role="alert"><span class="ab-icon">${icon(TYPE_ICON[i.type] || "incident")}</span>
      <span class="ab-t"><b>${t("home.ab_title")} · ${esc(incTitle(i))}</b><span>${esc(placeText(i.zone_id, i.location_id))} · ${code(i.code)} · ${srcCount(i.source_count)}</span></span>
      <span class="ab-m" title="${esc(t("esc.note", { min: Math.round(e.step / 60000) }))}"><span class="cd" ${dl ? `data-deadline="${dl}" data-late-text="${esc(t("home.late"))}"` : ""}>--:--</span>
        <small data-label="${esc(t("home.ab_window"))}" data-late-label="${esc(escLabel(e.code || "L1"))}">${t("home.ab_window")}</small></span>
      <button class="ab-btn" type="button" data-sel="${i.id}">${t("home.ab_btn")}</button></div>`;
  }).join("");
}

function kpis(state) {
  const c = state.counters, open = state.incidents.filter(isOpen);
  const crit = open.filter((i) => i.status === "open" && i.priority === "P1").length;
  const mid = open.filter((i) => i.status === "open" && i.priority === "P2").length;
  const normal = open.filter((i) => i.status === "open" && (i.priority === "P3" || i.priority === "P4")).length;
  const inProgress = state.incidents.filter((i) => i.status === "action_approved").length;
  const closed = state.incidents.filter(handled).length;
  const card = (cls, ic, label, kc, v, sub) => `<div class="kcard ${cls}"><div class="kc-top"><span class="kc-ic">${icon(ic)}</span><span class="kc-l">${label}</span>${kc ? `<span class="kc-code">${kc}</span>` : ""}</div>
      <div class="kc-v">${v}</div><div class="kc-s">${sub}</div></div>`;
  return `<div class="kcards">
    ${card("total", "layers", t("home.k_total"), "", fmtNum(c.received), t("home.k_total_s", { n: fmtNum(state.incidents.length), out: fmtNum(c.noise + c.duplicate) }))}
    ${card("crit", "incident", t("priority.P1"), "P1", fmtNum(crit), t("home.k_crit_s"))}
    ${card("warn", "bell", t("priority.P2"), "P2", fmtNum(mid), t("home.k_ops_s"))}
    ${card("low", "info", t("priority.P3"), "P3", fmtNum(normal), t("home.k_routine_s"))}
    <div class="kcard proc"><div class="kc-top"><span class="kc-l">${t("home.k_proc_short")}</span></div>
      <div class="pair">
        <button type="button" data-proc="prog" aria-expanded="${ui.proc === "prog"}"><span class="pn"><b style="color:var(--p2)">${fmtNum(inProgress)}</b>${icon("chevronDown", "pgo")}</span><span>${t("home.in_prog")}</span></button>
        <button type="button" data-proc="done" aria-expanded="${ui.proc === "done"}"><span class="pn"><b style="color:var(--ok)">${fmtNum(closed)}</b>${icon("chevronDown", "pgo")}</span><span>${t("home.done")}</span></button>
      </div></div>
  </div>${ui.proc ? drill(state, ui.proc) : ""}`;
}

/** List under the KPIs: incidents in progress (approved, not closed) or handled (closed). */
function drill(state, which) {
  const list = state.incidents.filter((i) => (which === "prog" ? i.status === "action_approved" : handled(i)));
  const lastDecision = (id) => state.decisions.find((d) => d.incident_id === id);   // newest first
  const rows = list.map((i) => {
    const d = lastDecision(i.id), rec = d?.snapshot?.recommendation;
    const what = rec ? recTitle({ code: rec.code, params: rec.params || {} }, i.zone_id) : d ? t(`decision_action.${d.action}`) : t(`status.${i.status}`);
    const line = [code(i.code), esc(placeText(i.zone_id, i.location_id)), esc(what), d ? esc(d.operator) : "", d ? fmtTime(d.created_at, false) : ""].filter(Boolean).join(" · ");
    return `<li class="${sevClass(i.priority)}">${pill(i.priority)}<div class="t"><b>${esc(incTitle(i))}</b><span>${line}</span></div>
      ${which === "prog" ? `<button class="btn btn-sm" type="button" data-sel="${i.id}">${t("home.open")}</button>` : (() => { const o = d ? outcome(d, i) : { cls: "resolved", key: "logx.st_done" }; return `<span class="st ${o.cls}">${t(o.key)}</span>`; })()}</li>`;
  }).join("");
  return `<section class="panel flush drill"><div class="ph"><h3>${t(which === "prog" ? "home.dr_prog" : "home.dr_done")} (${fmtNum(list.length)})</h3><span class="spacer"></span>
      <button class="btn btn-sm btn-quiet" type="button" data-proc="${which}">${t("home.close")}</button></div>
    ${list.length ? `<ul>${rows}</ul>` : `<div class="pb muted small">${t("home.dr_empty")}</div>`}</section>`;
}

function queueItem(i, selId) {
  return `<li class="qi ${sevClass(i.priority)}" role="option" tabindex="0" data-sel="${i.id}" aria-selected="${i.id === selId}">
    <span class="bar"></span>
    <div class="t"><b>${icon(TYPE_ICON[i.type] || "incident")}${esc(incTitle(i))}</b>
      <span>${esc(placeText(i.zone_id, i.location_id))} · ${srcCount(i.source_count)} · ${t(`status.${i.status}`)}</span></div>
    <div class="m">${pill(i.priority)}${escTag(i) || `<span>${ago(i.updated_at)}</span>`}</div></li>`;
}

function queuePanel(state, selId) {
  const all = state.incidents.filter(waiting).sort(byUrgency);
  const list = all.length ? `<ul class="queue" role="listbox" aria-label="${esc(t("home.q_title"))}">${all.map((i) => queueItem(i, selId)).join("")}</ul>`
    : `<div class="queue-empty">${icon("check")}${t("home.q_empty")}</div>`;
  return `<section class="panel flush">
    <div class="ph"><h3>${t("home.q_title")}</h3><span class="spacer"></span><a class="btn btn-quiet btn-sm all-btn" href="#/incidents"><span>${t("home.all")}</span>${icon("chevron", "fwd")}</a></div>
    ${list}</section>`;
}

/* ---------- decision panel ---------- */
function whyLine(d) {
  const r = (d.priority_reasons || []).filter((x) => x.key !== "type_base" && x.points > 0).sort((a, b) => b.points - a.points).slice(0, 3);
  if (!r.length) return "";
  return `<div class="why-line" title="${esc(t("home.why"))}">${r.map((x) => `<span><b>+${x.points}</b>${esc(tr("reason", x))}</span>`).join("")}</div>`;
}
function sourceChips(d) {
  const srcs = d.alerts.filter((a) => a.disposition === "correlated").map((a) => a.source_system);
  return `<div class="sources"><span class="label">${t("home.sources")}</span>${srcChips(srcs, true)}</div>`;
}

function timeline(d) {
  const main = d.alerts.filter((a) => a.disposition !== "duplicate");
  const dup = d.alerts.length - main.length;
  const nSrc = new Set(main.map((a) => a.source_system)).size;
  const items = main.map((a) => ({ at: a.received_at, html: `<li class="${["live_cv", "voice"].includes(a.origin) ? "live" : ""}">
      <span class="tm">${fmtTime(a.received_at)}</span>
      <span class="tsrc ${srcKind(a.source_system)}" title="${esc(t(`source_system.${a.source_system}`))}">${icon(srcKind(a.source_system))}<b>${t(`source_system.${a.source_system}`)}</b></span>
      <span class="tx" title="${esc(a.raw_text || "")}">${t(`category.${a.category}`)}${a.raw_text ? ` · <q dir="auto">${esc(a.raw_text)}</q>` : ""}</span></li>` }));
  for (const x of d.decisions) {
    items.push({ at: x.created_at, html: `<li class="act"><span class="tm">${fmtTime(x.created_at)}</span>
      <span class="tsrc act">${icon("check")}<b>${t(`decision_action.${x.action}`)}</b></span><span class="tx">${esc(x.operator)}${x.note ? ` · ${esc(x.note)}` : ""}</span></li>` });
  }
  items.sort((a, b) => new Date(a.at) - new Date(b.at));
  return `<div class="sec-title">${t("home.tl_title")}<span class="hint">${t("home.tl_hint", { n: main.length, s: nSrc, dup: dup ? t("home.tl_dup", { n: dup }) : "" })}</span>
      <a href="#/incident/${d.id}">${code(d.code)} ↗</a></div>
    <ol class="tl">${items.map((x) => x.html).join("")}</ol>`;
}

const noteBox = (d) => `<div class="dp-note"><label class="sr-only" for="dpNote">${t("home.note_ph")}</label>
  <textarea id="dpNote" class="note-input" data-note="${d.id}" rows="1" placeholder="${esc(t("home.note_ph"))}">${esc(notes[d.id] || "")}</textarea></div>`;
const humanNote = () => `<span class="note">${icon("person")}${t("home.human")}</span>`;

function approvedBanner(d) {
  const dec = [...d.decisions].reverse().find((x) => x.action === "approve");
  return `<div class="close-box"><span class="cb-ic">${icon("check")}</span>
    <div class="cb-t"><b>${esc(t("home.approved_by", { operator: dec?.operator || "", time: fmtTime(dec?.created_at, false) }))}</b><span>${t("home.close_hint")}</span></div>
    <button class="btn btn-close" type="button" data-act="resolve">${icon("check")}<span>${t("home.resolve")}</span></button></div>`;
}

function worstCheck(sim) {
  const st = (sim.checks || []).map((c) => c.status);
  return st.includes("fail") ? "fail" : st.includes("warn") ? "warn" : "ok";
}

/** The option the panel shows: the one being previewed, else the approved one, else the best proposed one. */
function selectedRec(d) {
  const recs = d.recommendations;
  return recs.find((r) => r.id === ui.preview?.recId) || recs.find((r) => r.status === "approved")
    || recs.find((r) => r.status === "proposed") || recs[0] || null;
}

function crewLine(d, r) {
  return (r.params.teams || []).map((c) => c.team_id
    ? `<span>${icon("team")}${esc(teamName(c.team_id))} · <b>${t("home.eta", { min: c.eta_min })}</b></span>`
    : `<span class="none">${t("home.no_team", { kind: t(`teamkind.${c.kind}`) })}</span>`).join("");
}

function optionRow(d, r, top, sel) {
  const sim = r.simulation;
  const shown = sel?.id === r.id;
  const open = d.status === "open" && r.status === "proposed";
  let meta = "";
  if (sim) {
    const w = worstCheck(sim);
    const staffMove = sim.action === "redeploy" && sim.staff?.source;
    const loadMatters = !staffMove || d.zone?.kind === "gate";
    meta = `${loadMatters ? `<span>${t("home.load_after", { min: sim.horizon_min })} <span class="sc">${pct(sim.baseline.load_end)}% → ${pct(sim.source.load_end)}%</span></span>` : ""}
      ${staffMove ? `<span>${t("home.staff_after")} <span class="sc">${sim.staff.source.before} → ${sim.staff.source.after}/${sim.staff.source.required}</span></span>` : ""}
      <span class="tag ${w}">${t(`check_status.${w}`)}</span>`;
  } else if (r.rec_type === "playbook") {
    meta = `<span>${t("home.n_steps", { n: r.params.steps.length })}</span>${crewLine(d, r)}`;
  } else {
    meta = `<span>${esc(recDesc(r, d.zone_id))}</span>`;
  }
  const label = sim ? (ui.preview?.recId === r.id ? t("home.showing") : t("home.simulate")) : (shown ? t("home.showing") : t("home.view_opt"));
  return `<div class="opt ${["superseded", "rejected"].includes(r.status) ? "dim" : ""}" data-active="${shown}">
    <div><div class="ot"><span class="on">${r.rank}.</span> ${esc(recTitle(r, d.zone_id))}</div>
      <div class="om">${top && open ? `<span class="rec2">${t("home.recommended")}</span>` : ""}${r.status !== "proposed" ? `<span class="tag ${r.status === "approved" ? "ok" : ""}">${t(`decide.${r.status}`)}</span>` : ""}${meta}</div></div>
    ${open || shown ? `<button class="simbtn" type="button" data-sim="${r.id}">${label}</button>` : ""}</div>`;
}

/** Projected effect of the previewed option (operational cases). */
function simPanel(d, r) {
  const sim = r.simulation, H = sim.horizon_min;
  const rows = [[sim.source_zone, sim.baseline, sim.source]];
  if (sim.other_zone && sim.other_before && sim.other) rows.push([sim.other_zone, sim.other_before, sim.other]);
  const color = (x) => (x >= 1 ? "var(--p1)" : x >= 0.85 ? "var(--p2)" : "var(--ok)");
  const w = (x) => `${Math.min(100, pct(x))}%`;
  const staffMove = sim.action === "redeploy";
  const loadRows = (!staffMove || d.zone?.kind === "gate") ? rows : [];
  const bars = loadRows.map(([z, b, a]) => {
    const before = b.load_end, after = a.load_end, delta = pct(after) - pct(before);
    return `<div class="sim-row"><span class="sz">${esc(zoneName(z))}</span>
      <div class="dual" style="--c:${color(after)}" role="img" aria-label="${esc(`${zoneName(z)}: ${pct(before)}% → ${pct(after)}%`)}"><i class="before" style="width:${w(before)}"></i><i class="after" style="width:${w(after)}"></i></div>
      <span class="delta" style="color:${delta < 0 ? "var(--ok)" : delta > 0 ? "var(--p2)" : "var(--muted)"}">${pct(before)}→${pct(after)}%</span></div>`;
  }).join("");
  const st = sim.staff || {};
  const staffRows = staffMove ? [st.source, st.other].filter(Boolean).map((s) => {
    const max = Math.max(s.before, s.after, s.required) * 1.15 || 1;
    const sw = (x) => `${Math.min(100, (x / max) * 100)}%`;
    const okAfter = s.after >= s.required;
    return `<div class="sim-row"><span class="sz">${esc(zoneName(s.zone))}</span>
      <div class="dual" style="--c:${okAfter ? "var(--ok)" : "var(--p1)"}" role="img" aria-label="${esc(t("home.staff_line", { zone: zoneName(s.zone), before: s.before, after: s.after, min: s.required }))}">
        <i class="before" style="width:${sw(s.before)}"></i><i class="after" style="width:${sw(s.after)}"></i><span class="capmark" style="inset-inline-start:${sw(s.required)}"></span></div>
      <span class="delta" style="color:${okAfter ? "var(--ok)" : "var(--p1)"}">${s.before}→${s.after}/${s.required}</span></div>`;
  }).join("") : "";
  const bad = (sim.checks || []).filter((c) => c.status === "fail" || c.status === "warn");
  const vcls = worstCheck(sim);
  const side = (sim.side_effects || []).filter((x) => x.key !== "longer_walk" || vcls === "ok");
  const verdictItems = vcls === "ok" ? side.map((x) => `<li>${esc(tr("side_effect", x))}</li>`).join("")
    : bad.map((c) => `<li>${esc(tr("check", c))}</li>`).join("");
  return `<div class="sim"><div class="label">${t("home.sim_res", { min: H })} · <span class="muted">${t("home.no_action")} ↔ ${t("home.with_option")}</span></div>
    <div class="sim-rows">${bars}${staffRows ? `<div class="label sub">${t("home.staff_title")}</div>${staffRows}` : ""}</div>
    <div class="verdict ${vcls}">${icon(vcls === "ok" ? "check" : "info")}<div><b>${t(`home.v_${vcls}`)}</b>${verdictItems ? `<ul>${verdictItems}</ul>` : ""}</div></div></div>`;
}

/** What the selected option means on the ground (life-safety plans and routine routing). */
function planDetail(d, r) {
  if (r.rec_type === "playbook") {
    const place = placeText(d.zone_id, d.location_id);
    const crew = crewLine(d, r);
    return `<div class="sec-title">${t("home.steps")}<span class="hint">${esc(recTitle(r, d.zone_id))}</span></div>
      <ol class="steps">${r.params.steps.map((s) => `<li>${esc(tr("step", { key: s, params: { zone: r.params.zone, adjacent: r.params.adjacent, place } }))}</li>`).join("")}</ol>
      ${crew ? `<div class="crew-line">${crew}</div>` : ""}`;
  }
  return `<p class="option-desc">${esc(recDesc(r, d.zone_id))}</p>`;
}

/** The three decision buttons: approve the shown option, close the report, cancel the preview. */
function actionsRow(d, r) {
  if (d.status !== "open") return "";
  const canApprove = r && r.status === "proposed";
  return `<div class="dp-bar"><div class="dp-actions">
      <button class="btn ${d.priority === "P1" ? "btn-danger" : "btn-primary"}" type="button" data-act="approve" ${canApprove ? `data-rec="${r.id}"` : "disabled"}>${icon("check")}${t("home.approve_decision")}</button>
      <button class="btn btn-quiet" type="button" data-act="dismiss">${t("home.close_report")}</button>
      ${d.kind === "emergency" ? "" : `<button class="btn btn-quiet" type="button" data-endsim="1" ${ui.preview ? "" : "disabled"}>${t("home.cancel_sim")}</button>`}${humanNote()}</div>${noteBox(d)}</div>`;
}

/** Critical (life-safety) case: no list of options — the pre-approved plan is shown and approved directly. */
function emergencyBody(d, recs) {
  const plan = recs.find((r) => r.status === "approved") || recs.find((r) => r.status === "proposed" && !r.params.custom) || recs[0];
  return `<div class="optbox"><div class="optbox-h"><h5>${t("esc.plan_title")}</h5><span class="hint">${t("esc.plan_hint")}</span></div>
      <div class="opts">${optionRow(d, plan, false, plan).replace(/<button class="simbtn"[^]*?<\/button>/, "")}</div></div>
    ${planDetail(d, plan)}
    ${actionsRow(d, plan)}
    ${d.status === "action_approved" ? approvedBanner(d) : ""}`;
}

function decisionBody(d) {
  const recs = [...d.recommendations].sort((a, b) => (a.rank || 99) - (b.rank || 99));
  if (!recs.length) return `<div class="muted small">${t("decide.no_options")}</div>`;
  if (d.kind === "emergency") return emergencyBody(d, recs);
  const sel = selectedRec(d);
  const topId = recs.find((r) => r.status === "proposed" && !r.params.custom)?.id;
  const H = recs.find((r) => r.simulation)?.simulation?.horizon_min || 15;
  const operational = d.kind === "operational";
  const previewSim = recs.find((r) => r.id === ui.preview?.recId && r.simulation);
  return `<div class="optbox"><div class="optbox-h"><h5>${t("home.opts_title")}</h5><span class="hint">${operational ? t("home.opts_hint", { min: H }) : t("home.opts_hint_plan")}</span>
      ${operational ? `<a href="#/decide/${d.id}">${t("home.custom")}</a>` : ""}</div>
    <div class="opts">${recs.map((r) => optionRow(d, r, r.id === topId, sel)).join("")}</div></div>
    ${previewSim ? simPanel(d, previewSim) : sel && !sel.simulation ? planDetail(d, sel) : ""}
    ${actionsRow(d, sel)}
    ${d.status === "action_approved" ? approvedBanner(d) : ""}`;
}

/** Four fact boxes under the case title. Derived from the case type, its reports and the live zone state. */
function facts(d, state) {
  const z = d.zone || state.zones.find((x) => x.id === d.zone_id) || {};
  const place = placeText(d.zone_id, d.location_id);
  const label = d.label || d.type;
  const out = z.kind === "gate" ? (z.staff_on_duty || 0) * GATE_RATE : z.outflow_per_min;
  const p = { place, zone: zoneName(d.zone_id), pct: pct(z.load), inflow: fmtNum(z.inflow_per_min || 0), out: fmtNum(out || 0),
    on: z.staff_on_duty, req: z.staff_required };
  const key = ["fire", "medical", "crowding", "staff_shortage", "crowding_staff"].includes(label) ? label : "other";
  const cat = d.alerts?.find((a) => a.disposition === "correlated")?.category;
  if (key === "other") p.cause = cat ? t(`category.${cat}`) : incTitle(d);
  const box = (k) => `<div class="fact"><span>${t(`facts.${k}`)}</span><b>${esc(t(`facts.${k}_${key}`, p))}</b></div>`;
  return `<div class="facts">${box("injuries")}${box("cause")}${box("parties")}${box("party")}</div>`;
}

function decisionPanel(d, state) {
  const win = windowInfo(d, state);
  const hint = t(`home.ds_${d.kind === "emergency" ? "emergency" : d.kind === "operational" ? "operational" : "routine"}`);
  const winBox = win ? `<div class="window ${win.cls || ""}" ${win.title ? `title="${esc(win.title)}"` : ""}>
      <span class="cd" ${win.deadline ? `data-deadline="${Math.round(win.deadline)}" data-late-text="${esc(win.lateText || t("home.late"))}"` : ""}>${win.text || "--:--"}</span>
      <span data-label="${esc(win.label)}" data-late-label="${esc(win.lateLabel || t("home.window_late"))}">${esc(win.label)}</span></div>` : "";
  const body = decisionBody(d);
  const closed = !isOpen(d) ? `<div class="banner closed">${t(`incident.status_banner_${d.status}`, { time: fmtTime(d.status === "escalated" ? d.escalation?.at : d.closed_at, false) })}</div>` : "";
  return `<section class="panel flush ${sevClass(d.priority)}" id="decision">
    <div class="ph"><h3>${t("home.ds_title")}</h3><span class="hint">${hint}</span></div>
    <div class="pb">
      <div class="case-head"><div class="ttl"><div class="meta">${pill(d.priority)}${code(d.code)}<span class="st ${d.status}">${t(`status.${d.status}`)}</span></div>
        <h4>${icon(TYPE_ICON[d.type] || "incident")}${esc(incTitle(d))}</h4>
        <div class="loc">${esc(placeText(d.zone_id, d.location_id))} · ${t("incident.opened", { time: fmtTime(d.opened_at, false) })}</div></div>${winBox}</div>
      ${facts(d, state)}
      ${whyLine(d)}${sourceChips(d)}
      ${closed}${body}
      ${timeline(d)}
    </div></section>`;
}

function mapPanel(state, sel, simRec) {
  const label = simRec ? recTitle(simRec, sel?.zone_id) : "";
  return `<section class="panel flush home-map">
    <div class="ph"><h3>${t("home.map_title")}</h3><span class="live-chip ${simRec ? "sim" : ""}">${simRec ? t("home.sim_mode") : t("home.live")}</span>
      <span class="spacer"></span><a class="icon-btn" href="#/map" title="${esc(t("home.open_map"))}" aria-label="${esc(t("home.open_map"))}">${icon("expand")}</a></div>
    <div class="map-fill">${opsMap(state, { teams: true, selected: sel?.id, sim: simRec?.simulation, simLabel: label })}</div>
    ${mapLegend()}
  </section>`;
}

/** Status label from the newest decision of a case: solved, rejected by the officer, or approved and under way. */
export function outcome(d, inc) {
  if (d.action === "dismiss" || inc?.status === "dismissed") return { cls: "dismissed", key: "logx.st_rejected" };
  if (d.action === "resolve" || inc?.status === "resolved") return { cls: "resolved", key: "logx.st_done" };
  if (d.action === "approve" || inc?.status === "action_approved") return { cls: "action_approved", key: "logx.st_approved" };
  return { cls: "open", key: "logx.st_option_rejected" };
}

/** Latest reports that were handled: the newest decision per case (current event). */
function handledPanel(state) {
  const seen = new Set(), rows = [];
  for (const d of state.decisions) {
    if (seen.has(d.incident_id)) continue;
    seen.add(d.incident_id);
    const inc = state.incidents.find((i) => i.id === d.incident_id);
    const s = d.snapshot || {};
    // a solved case shows the plan that was approved before it was closed
    const rec = s.recommendation || state.decisions.find((x) => x.incident_id === d.incident_id && x.action === "approve")?.snapshot?.recommendation;
    const title = inc ? incTitle(inc) : s.incident_label ? t(`incident_label.${s.incident_label}`) : "";
    const what = (d.action === "approve" || d.action === "resolve") && rec ? recTitle({ code: rec.code, params: rec.params || {} }, s.zone_id) : t(`decision_action.${d.action}`);
    const st = outcome(d, inc);
    rows.push(`<tr ${inc ? `data-sel="${inc.id}" class="row-link"` : ""}>
      <td class="tm"><bdi>${fmtTime(d.created_at)}</bdi></td>
      <td><b>${esc(title)}</b><span class="sub">${code(s.incident_code || inc?.code || "")} · ${esc(zoneName(s.zone_id || inc?.zone_id))}</span></td>
      <td><div class="src-col">${srcChips(inc?.sources?.length ? inc.sources : s.sources || [])}</div></td>
      <td dir="auto">${esc(what)}${d.note ? `<span class="sub">${esc(d.note)}</span>` : ""}</td>
      <td>${esc(d.operator || "")}</td>
      <td><span class="st ${st.cls}">${t(st.key)}</span></td></tr>`);
    if (rows.length >= 6) break;
  }
  return `<section class="panel flush handled" style="margin-top:16px">
    <div class="ph"><h3>${t("home.handled_title")}</h3><span class="hint">${t("home.handled_hint")}</span><span class="spacer"></span>
      <a class="btn btn-sm" href="#/log">${t("home.view_log")}</a></div>
    ${rows.length ? `<div class="table-wrap"><table class="table handled-table"><thead><tr><th>${t("logx.th_time")}</th><th>${t("home.th_case")}</th><th>${t("logx.th_src")}</th>
      <th>${t("home.th_decision")}</th><th>${t("logx.th_by")}</th><th>${t("logx.th_status")}</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>`
      : `<div class="pb muted small">${t("home.handled_empty")}</div>`}
  </section>`;
}

function pickSelected(state, params) {
  const byId = (id) => state.incidents.find((i) => i.id === id);
  const fromRoute = Number(params[0]);
  if (fromRoute && byId(fromRoute)) { ui.sel = fromRoute; ui.picked = true; }
  if (!fromRoute) ui.picked = ui.picked && !!ui.sel;
  const cur = ui.sel && byId(ui.sel);
  // until the officer picks an incident, the panel follows the most important one (a new P1 comes first)
  if (cur && ui.picked && (waiting(cur) || fromRoute === cur.id)) return cur;
  const needs = state.incidents.filter(needsDecision).sort(byUrgency);
  const first = needs.find((i) => i.status === "open") || needs[0] || state.incidents.filter(waiting).sort(byUrgency)[0] || state.incidents.find(isOpen);
  ui.sel = first?.id || null;
  return first || null;
}

export const commandView = {
  nav: "overview",
  async render({ state, params }) {
    const sel = pickSelected(state, params);
    if (ui.preview && ui.preview.incId !== sel?.id) ui.preview = null;
    const d = sel ? await detail(sel.id) : null;
    const prevRec = d && ui.preview ? d.recommendations.find((r) => r.id === ui.preview.recId) : null;
    if (ui.preview && !prevRec) ui.preview = null;
    const simRec = prevRec?.simulation ? prevRec : null;
    const crit = state.incidents.filter((i) => i.priority === "P1" && i.status === "open" && i.kind === "emergency");
    const decision = d ? decisionPanel(d, state) : `<section class="panel"><div class="empty"><b>${t("home.q_empty")}</b>${t("home.pick")}</div></section>`;
    return `
      <div class="greet"><div><h1>${esc(greeting())}</h1><p class="tagline">${t("home.tagline")}</p></div></div>
      ${alertBars(crit)}
      ${kpis(state)}
      <div class="ops-grid">
        ${decision}
        <div class="stack">${queuePanel(state, sel?.id)}${mapPanel(state, sel, simRec)}</div>
      </div>
      ${handledPanel(state)}`;
  },
  after(root, { go, rerender }) {
    tickCountdowns(root);
    if (ui.focus) {        // after «افتح الحالة»: scroll to the decision panel (the router scrolls to top first)
      ui.focus = false;
      setTimeout(() => { const p = document.getElementById("decision"); if (!p) return;
        p.scrollIntoView({ behavior: "smooth", block: "start" }); p.classList.add("flash"); setTimeout(() => p.classList.remove("flash"), 1600); }, 80);
    }
    root.querySelectorAll("[data-sel]").forEach((el) => {
      const pick = () => {
        ui.preview = null; ui.sel = Number(el.dataset.sel); ui.picked = true;
        ui.focus = el.classList.contains("ab-btn") || el.closest(".drill") !== null;
        if (location.hash === `#/c/${el.dataset.sel}`) rerender(true); else go(`#/c/${el.dataset.sel}`);
      };
      el.addEventListener("click", pick);
      if (el.tagName === "LI") el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
    });
    root.querySelectorAll("[data-proc]").forEach((b) => b.addEventListener("click", () => { ui.proc = ui.proc === b.dataset.proc ? null : b.dataset.proc; rerender(true); }));
    root.querySelectorAll("[data-sim]").forEach((b) => b.addEventListener("click", () => {
      const id = Number(b.dataset.sim);
      ui.preview = ui.preview?.recId === id ? null : { incId: ui.sel, recId: id };
      rerender(true);
    }));
    root.querySelectorAll("[data-endsim]").forEach((b) => b.addEventListener("click", () => { ui.preview = null; rerender(true); }));
    root.querySelectorAll(".note-input").forEach((n) => n.addEventListener("input", () => { notes[n.dataset.note] = n.value; }));
    root.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
      if (ui.busy || !ui.sel) return;
      const id = ui.sel, act = b.dataset.act;
      ui.busy = true; b.disabled = true;
      try {
        await api(`/api/incidents/${id}/decisions`, { method: "POST",
          body: { action: act, recommendation_id: b.dataset.rec ? Number(b.dataset.rec) : null, note: (notes[id] || "").trim() } });
        notes[id] = ""; ui.preview = null;
        await refresh().catch(() => {});      // the decided case leaves the list and the counters at once
        toast(t(act === "approve" ? "home.moved_approved" : act === "dismiss" ? "home.moved_rejected" : "decide.done",
          { action: t(`decision_action.${act}`), operator: document.body.dataset.employeeName || "" }));
        if (act !== "reject") { ui.picked = false; ui.sel = null; }
      } catch (e) { toast(errorText(e), "error"); }
      finally {
        ui.busy = false; await detail(id, true);
        if (act !== "reject" && location.hash !== "#/" && location.hash !== "") go("#/"); else rerender(true);
      }
    }));
  },
};
