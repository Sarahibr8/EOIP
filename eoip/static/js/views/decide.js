import { t, fmtNum, fmtTime } from "../i18n.js";
import { icon } from "../icons.js";
import { esc, pct, zoneName, locName, teamName, tr, isOpen, recTitle, recDesc, toast, errorText, incTitle, placeText, code } from "../ui.js";
import { api, detail, refresh } from "../store.js";
import { incidentHeader, closedBanner } from "./incident.js";

const notes = {};
const ui = { incident: null, tab: "options" };
const crowd = { target: null, share: 40, result: null, error: null };
const staff = { from: null, to: null, n: 2, result: null, error: null };
let busy = false;

/* ---------- visual before/after ---------- */
function gauge(zoneId, now, base, withO, cap, occEnd) {
  const max = Math.max(1.25, now, base, withO) * 1.04;
  const pos = (x) => `${Math.min(100, (x / max) * 100)}%`;
  return `<div class="gauge">
    <div class="head"><b>${esc(zoneName(zoneId))}</b>
      <span>${t("sim.line", { now: pct(now), base: pct(base), with: pct(withO) })}</span></div>
    <div class="track" role="img" aria-label="${esc(t("sim.aria", { zone: zoneName(zoneId), now: pct(now), base: pct(base), with: pct(withO) }))}">
      <span class="fill now" style="width:${pos(now)}"></span>
      <span class="fill base" style="width:${pos(base)}"></span>
      <span class="fill with ${withO > 1 ? "over" : ""}" style="width:${pos(withO)}"></span>
      <span class="cap" style="inset-inline-start:${pos(1)}"></span><span class="capl" style="inset-inline-start:${pos(1)}">${t("sim.capacity", { n: fmtNum(cap) })}</span>
    </div>
    <div class="keys"><span><i class="now"></i>${t("sim.k_now")}</span><span><i class="base"></i>${t("sim.k_base")}</span>
      <span><i class="with"></i>${t("sim.k_with", { n: fmtNum(occEnd) })}</span></div>
  </div>`;
}

function staffBars(st) {
  if (!st) return "";
  const rows = [st.source, st.other].filter(Boolean);
  const max = Math.max(...rows.flatMap((r) => [r.before, r.after, r.required])) * 1.15 || 1;
  const pos = (x) => `${Math.min(100, (x / max) * 100)}%`;
  return `<div class="staffbars"><div class="subhead">${t("sim.staff_title")}</div>${rows.map((r) => `
    <div class="staffbar"><span>${esc(zoneName(r.zone))}</span>
      <div class="track" role="img" aria-label="${esc(t("sim.staff_line", { before: r.before, after: r.after, min: r.required }))}">
        <i class="before" style="width:${pos(r.before)}"></i><i class="after ${r.after < r.required ? "low" : ""}" style="width:${pos(r.after)}"></i>
        <span class="min" style="inset-inline-start:${pos(r.required)}"></span></div>
      <span class="small">${t("sim.staff_line", { before: r.before, after: r.after, min: r.required })}</span></div>`).join("")}
    <div class="keys small muted">${t("sim.staff_keys")}</div></div>`;
}

function baTable(sim) {
  const row = (zone, b, w) => {
    const n = (x) => `<bdi dir="ltr">${x > 0 ? "+" : ""}${x}</bdi>`;
    return `<tr><td>${esc(zoneName(zone))}</td><td>${fmtNum(b.occupancy_now)} / ${fmtNum(b.capacity)}</td>
      <td>${fmtNum(b.occupancy_end)}<span class="arr"></span><b>${fmtNum(w.occupancy_end)}</b></td>
      <td>${b.wait_end_min}<span class="arr"></span><b>${w.wait_end_min}</b></td>
      <td>${n(b.net_per_min)}<span class="arr"></span><b>${n(w.net_per_min)}</b></td></tr>`;
  };
  let rows = row(sim.source_zone, sim.baseline, sim.source);
  if (sim.other && sim.other_before) rows += row(sim.other_zone, sim.other_before, sim.other);
  return `<details class="ba-details"><summary>${t("sim.details")}</summary><div class="table-wrap"><table class="ba">
    <thead><tr><th>${t("sim.zone")}</th><th>${t("sim.occ_now")}</th><th>${t("sim.occ_end", { min: sim.horizon_min })}</th>
    <th>${t("sim.wait")}</th><th>${t("sim.net")}</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
}

function simViz(sim) {
  const b = sim.baseline, s = sim.source;
  let out = `<div class="gauges">${gauge(sim.source_zone, b.load_now, b.load_end, s.load_end, s.capacity, s.occupancy_end)}`;
  if (sim.other && sim.other_before && sim.action === "divert") {
    const ob = sim.other_before, o = sim.other;
    out += gauge(sim.other_zone, ob.load_now, ob.load_end, o.load_end, o.capacity, o.occupancy_end);
  }
  out += "</div>";
  if (sim.action === "redeploy") out += staffBars(sim.staff);
  return out + baTable(sim);
}

function checksList(sim) {
  if (!sim.checks?.length) return "";
  return `<ul class="checks">${sim.checks.map((c) => `<li><span class="tag ${c.status}">${t(`check_status.${c.status}`)}</span><span>${esc(tr("check", c))}</span></li>`).join("")}</ul>`;
}
function tradeOffs(sim) {
  const s = sim.side_effects || [];
  return s.length ? `<ul class="checks">${s.map((x) => `<li><span class="tag warn">!</span><span>${esc(tr("side_effect", x))}</span></li>`).join("")}</ul>`
    : `<div class="muted small">${t("decide.none_tradeoff")}</div>`;
}

/* ---------- emergency / routine ---------- */
function crewList(params) {
  const crew = params.teams || [];
  if (!crew.length) return "";
  return `<div><h3 class="subhead">${t("decide.crew")}</h3>
    <ul class="crew">${crew.map((c) => c.team_id
      ? `<li><span>${esc(teamName(c.team_id))}<small>${t(`teamkind.${c.kind}`)} · ${t("decide.from", { place: locName(c.from_location) })}</small></span><span class="eta">${t("decide.eta", { min: c.eta_min })}</span></li>`
      : `<li><span>${t("decide.no_team", { kind: t(`teamkind.${c.kind}`) })}</span><span class="tag fail">—</span></li>`).join("")}</ul>
    <p class="calc-note">${t("decide.crew_note")}</p></div>`;
}
function whyList(params) {
  const w = params.why || [];
  return w.length ? `<div><h3 class="subhead">${t("decide.why")}</h3>
    <ul class="checks">${w.map((x) => `<li><span class="tag intel">i</span><span>${esc(tr("why", x))}</span></li>`).join("")}</ul></div>` : "";
}
const noteBox = (d) => `<div class="field" style="margin-top:14px"><label for="note">${t("decide.note_label")}</label>
  <textarea id="note" class="note-input" data-note="${d.id}" rows="2" placeholder="${t("decide.note_placeholder")}">${esc(notes[d.id] || "")}</textarea></div>
  <p class="form-error" id="formError" role="alert"></p>`;
const statusLabel = (r) => (r.status !== "proposed" ? `<span class="rec-status ${r.status}">${t(`decide.${r.status}`)}</span>` : "");
const recommendationIcon = (r) => ({ "FIRE-01": "flame", "MED-01": "medical", route_team: "team" }[r.code] || "decide");

function emergency(d) {
  const r = d.recommendations[0];
  if (!r) return "";
  const open = d.status === "open" && r.status === "proposed";
  const place = placeText(d.zone_id, d.location_id);
  return `<section class="panel">
    <div class="option-head"><h2><span class="option-title-icon ${d.priority === "P1" ? "critical" : ""}">${icon(recommendationIcon(r))}</span>${esc(t("decide.playbook", { code: r.code }))}</h2>${statusLabel(r)}</div>
    <p class="option-desc" style="margin:4px 0 12px">${esc(recTitle(r, d.zone_id))}</p>
    <ol class="steps">${r.params.steps.map((s) => `<li>${esc(tr("step", { key: s, params: { zone: r.params.zone, adjacent: r.params.adjacent, place } }))}</li>`).join("")}</ol>
    <p class="calc-note">${t("decide.no_simulation")}</p>
    ${open ? `<div class="actions" style="margin-top:14px"><button class="btn btn-danger" data-act="approve" data-rec="${r.id}">${icon("check")}${t("decide.approve")}</button>
      <button class="btn btn-quiet" data-act="dismiss">${icon("x")}${t("decide.reject")}</button></div>${noteBox(d)}` : ""}
  </section>`;
}

function routine(d) {
  const r = d.recommendations[0];
  if (!r) return "";
  const open = d.status === "open" && r.status === "proposed";
  return `<section class="panel">
    <div class="option-head"><h2><span class="option-title-icon">${icon(recommendationIcon(r))}</span>${esc(recTitle(r, d.zone_id))}</h2>${statusLabel(r)}</div>
    <p class="option-desc" style="margin:10px 0">${t("option.route_team_desc")}</p>
    ${open ? `<div class="actions"><button class="btn btn-primary" data-act="approve" data-rec="${r.id}">${icon("check")}${t("decide.approve")}</button>
      <button class="btn btn-quiet" data-act="dismiss">${icon("x")}${t("decide.reject")}</button></div>${noteBox(d)}` : ""}
  </section>`;
}

/* ---------- operational ---------- */
function optionBlock(d, r, top) {
  const open = d.status === "open" && r.status === "proposed";
  const label = statusLabel(r) || `<span class="tag ${top ? "intel" : ""}">${r.params.custom ? t("decide.custom") : top ? t("decide.recommended") : t("decide.option_rank", { rank: r.rank })}</span>`;
  return `<div class="option ${top && open ? "recommended" : ""} ${["superseded", "rejected"].includes(r.status) ? "dim" : ""}">
    <div class="option-head"><h3><span class="option-title-icon">${icon(recommendationIcon(r))}</span>${esc(recTitle(r, d.zone_id))}</h3>${label}</div>
    <p class="option-desc">${esc(recDesc(r, d.zone_id))}</p>
    <div><div class="subhead">${t("decide.ba_title", { min: r.simulation.horizon_min || 15 })}</div>${simViz(r.simulation)}</div>
    <div class="cols cols-1-1"><div><div class="subhead">${t("decide.checks")}</div>${checksList(r.simulation)}</div>
      <div><div class="subhead">${t("decide.trade_offs")}</div>${tradeOffs(r.simulation)}</div></div>
    ${open ? `<div class="actions"><button class="btn ${top ? "btn-primary" : ""}" data-act="approve" data-rec="${r.id}">${icon("check")}${t("decide.approve")}</button>
      <button class="btn btn-quiet" data-act="reject" data-rec="${r.id}">${icon("x")}${t("decide.reject")}</button></div>` : ""}
  </div>`;
}

const zoneOpt = (z, cur, info) => `<option value="${z.id}" ${cur === z.id ? "selected" : ""}>${esc(zoneName(z.id))} (${info})</option>`;

function crowdTab(d, state) {
  const others = state.zones.filter((z) => z.id !== d.zone_id);
  if (!others.some((z) => z.id === crowd.target)) crowd.target = [...others].sort((a, b) => a.load - b.load)[0]?.id;
  return `<p class="calc-note" style="margin:0 0 12px">${t("sim.crowd_intro", { zone: zoneName(d.zone_id) })}</p>
    <div class="sim-form">
      <div class="field"><label for="crTarget">${t("sim.receiving")}</label>
        <select id="crTarget">${others.map((z) => zoneOpt(z, crowd.target, `${pct(z.load)}%`)).join("")}</select></div>
      <div class="field"><label for="crShare">${t("sim.share")}</label>
        <div class="range-row"><input id="crShare" type="range" min="5" max="80" step="5" value="${crowd.share}"><output id="crShareOut">${crowd.share}%</output></div></div>
    </div>
    <div id="crResult">${resultBlock(crowd)}</div>`;
}

function staffTab(d, state) {
  const zones = state.zones;
  staff.to = staff.to || d.zone_id;
  const donors = zones.filter((z) => z.id !== staff.to && z.staff_on_duty > 0);
  if (!donors.some((z) => z.id === staff.from)) {
    staff.from = [...donors].sort((a, b) => (b.staff_on_duty - b.staff_required) - (a.staff_on_duty - a.staff_required))[0]?.id;
  }
  const donor = zones.find((z) => z.id === staff.from);
  const max = donor ? Math.max(1, donor.staff_on_duty) : 1;
  staff.n = Math.min(Math.max(1, staff.n), max);
  return `<p class="calc-note" style="margin:0 0 12px">${t("sim.staff_intro")}</p>
    <div class="sim-form">
      <div class="field"><label for="stFrom">${t("sim.source_zone")}</label>
        <select id="stFrom">${donors.map((z) => zoneOpt(z, staff.from, t("sim.staff_info", { on: z.staff_on_duty, min: z.staff_required }))).join("")}</select></div>
      <div class="field"><label for="stTo">${t("sim.receiving")}</label>
        <select id="stTo">${zones.map((z) => zoneOpt(z, staff.to, t("sim.staff_info", { on: z.staff_on_duty, min: z.staff_required }))).join("")}</select></div>
      <div class="field"><label for="stN">${t("sim.staff_n")}</label>
        <div class="range-row"><input id="stN" type="range" min="1" max="${max}" step="1" value="${staff.n}"><output id="stNOut">${staff.n}</output></div></div>
    </div>
    <div id="stResult">${resultBlock(staff)}</div>`;
}

function resultBlock(s) {
  if (s.error) return `<div class="banner warn">${esc(s.error)}</div>`;
  if (!s.result) return `<div class="loading">${t("sim.computing")}</div>`;
  return `<div class="subhead">${t("decide.ba_title", { min: s.result.horizon_min })}</div>${simViz(s.result)}
    <div style="margin-top:12px"><div class="subhead">${t("decide.checks")}</div>${checksList(s.result)}</div>
    <p class="calc-note">${t("sim.calc_note", { rate: 16, min: s.result.horizon_min })}</p>`;
}

function operational(d, state) {
  const recs = d.recommendations;
  const topId = recs.find((r) => r.status === "proposed" && !r.params.custom)?.id;
  const open = d.status === "open";
  const tabs = ["options", "crowd", "staff"];
  const tabBody = ui.tab === "crowd" ? crowdTab(d, state) : ui.tab === "staff" ? staffTab(d, state)
    : recs.length ? recs.map((r) => optionBlock(d, r, r.id === topId || r.status === "approved")).join("")
      : `<div class="empty"><b>${t("decide.no_options")}</b>${t("decide.no_options_hint")}</div>`;
  const add = (ui.tab !== "options" && open) ? `<div class="actions" style="margin-top:14px">
      <button class="btn btn-primary" id="simAdd" ${(ui.tab === "crowd" ? crowd : staff).result ? "" : "disabled"}>${t("sim.add_option")}</button>
      <span class="muted small">${t("sim.add_hint")}</span></div>` : "";
  return `<section class="panel">
    <div class="tabs" role="tablist">${tabs.map((k) => `<button type="button" role="tab" data-tab="${k}" aria-selected="${ui.tab === k}">${t(`decide.tab_${k}`)}</button>`).join("")}</div>
    ${tabBody}${add}
    ${open && ui.tab === "options" && recs.some((r) => r.status === "proposed") ? noteBox(d) : ""}
  </section>`;
}

const crowdBody = () => ({ action: "divert", target_zone: crowd.target, share_pct: crowd.share });
const staffBody = () => ({ action: "redeploy", target_zone: staff.from, to_zone: staff.to, staff: staff.n });

async function compute(which, rerender) {
  const s = which === "crowd" ? crowd : staff;
  try {
    s.result = await api(`/api/incidents/${ui.incident}/simulate`, { method: "POST", body: which === "crowd" ? crowdBody() : staffBody() });
    s.error = null;
  } catch (e) { s.result = null; s.error = errorText(e); }
  rerender(true);
}

export const decideView = {
  nav: "decide",
  async render({ state, params }) {
    const open = state.incidents.filter(isOpen);
    const id = Number(params[0]) || open.find((i) => i.status === "open")?.id || open[0]?.id;
    const head = `<div class="page-head"><div><h1>${t("decide.title")}</h1><p>${t("decide.subtitle")}</p></div></div>`;
    if (!id) return `${head}<div class="panel"><div class="empty"><b>${t("decide.none")}</b>${t("overview.now_empty_idle")}</div></div>`;
    const d = await detail(id);
    if (!d) return `${head}<div class="panel"><div class="empty"><b>${t("incident.not_found")}</b></div></div>`;
    if (ui.incident !== d.id) {
      Object.assign(ui, { incident: d.id, tab: "options" });
      Object.assign(crowd, { target: null, result: null, error: null });
      Object.assign(staff, { from: null, to: null, result: null, error: null });
    }
    const pickList = [...open, ...(open.some((i) => i.id === id) ? [] : state.incidents.filter((i) => i.id === id))];
    const picker = `<div class="field" style="max-width:640px;margin-bottom:16px"><label for="incPick">${t("decide.pick")}</label>
      <select id="incPick">${pickList.map((i) => `<option value="${i.id}" ${i.id === id ? "selected" : ""}>${i.priority} · ${esc(incTitle(i))} · ${esc(placeText(i.zone_id, i.location_id))} · ${i.code}</option>`).join("")}</select></div>`;
    const employeeName = document.body.dataset.employeeName || "";
    const employeeNumber = document.body.dataset.employeeNumber || "";
    const operator = `<div class="operator" id="operatorBar">
      <span class="operator-icon">${icon("person")}</span><span class="operator-copy"><b>${t("decide.operator_label")}</b>
      <strong>${esc(employeeName)}</strong><small>${t("decide.operator_number_label")}: <bdi>${esc(employeeNumber)}</bdi> · ${t("decide.operator_note")}</small></span></div>`;
    const toolbar = `<div class="decision-toolbar">${picker}${operator}</div>`;

    const approvedDec = [...d.decisions].reverse().find((x) => x.action === "approve");
    const banner = d.status === "action_approved" ? `<div class="banner ok"><span>${icon("check")} ${esc(t("decide.approved_by", { operator: approvedDec?.operator || "", time: fmtTime(approvedDec?.created_at, false) }))}</span></div>
      ${noteBox(d)}<div class="actions"><button class="btn" data-act="resolve">${t("decide.resolve")}</button></div>` : closedBanner(d);

    let main, side = "";
    const crewPanel = (r) => (r ? `<section class="panel" style="display:grid;gap:18px">${crewList(r.params)}${whyList(r.params)}</section>` : "");
    if (d.kind === "emergency") { main = emergency(d); side = crewPanel(d.recommendations[0]); }
    else if (d.kind === "operational") {
      main = operational(d, state);
      const z = state.zones.find((x) => x.id === d.zone_id);
      side = `<section class="panel"><h2 class="section-title">${t("decide.zone_state")}<small>${esc(zoneName(d.zone_id))}</small></h2>
        <dl class="kv"><dt>${t("map.occupancy")}</dt><dd><b>${pct(z.load)}%</b> (${fmtNum(z.occupancy)} / ${fmtNum(z.capacity)})</dd>
        <dt>${t("map.staff")}</dt><dd>${z.staff_on_duty} / ${t("map.min_staff", { n: z.staff_required })}</dd>
        <dt>${t("map.flow")}</dt><dd>${fmtNum(z.inflow_per_min)} / ${fmtNum(z.kind === "gate" ? z.staff_on_duty * 16 : z.outflow_per_min)}</dd></dl></section>`;
    } else { main = routine(d); side = crewPanel(d.recommendations[0]); }

    return `${head}${toolbar}${incidentHeader(d)}${banner}
      <div class="cols cols-2-1"><div>${main}</div><div>${side}
        <section class="panel"><div class="human">${icon("person")}<span>${t("decide.human_note")}</span></div>
          <a class="btn btn-quiet" href="#/incident/${d.id}" style="margin-top:8px">${t("nav.incident")}: ${code(d.code)}</a></section></div></div>`;
  },
  after(root, { params, go, rerender }) {
    root.querySelector("#incPick")?.addEventListener("change", (e) => go(`#/decide/${e.target.value}`));
    root.querySelectorAll(".note-input").forEach((n) => n.addEventListener("input", () => { notes[n.dataset.note] = n.value; }));
    root.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
      ui.tab = b.dataset.tab; rerender(true);
      if (ui.tab === "crowd" && !crowd.result) compute("crowd", rerender);
      if (ui.tab === "staff" && !staff.result) compute("staff", rerender);
    }));
    let timer;
    const later = (which) => { clearTimeout(timer); timer = setTimeout(() => compute(which, rerender), 120); };
    const range = (sel, obj, key, which, suffix = "") => {
      const el = root.querySelector(sel); if (!el) return;
      el.addEventListener("input", () => { obj[key] = Number(el.value); root.querySelector(`${sel}Out`).textContent = `${el.value}${suffix}`; });
      el.addEventListener("change", () => later(which));
    };
    root.querySelector("#crTarget")?.addEventListener("change", (e) => { crowd.target = e.target.value; later("crowd"); });
    range("#crShare", crowd, "share", "crowd", "%");
    root.querySelector("#stFrom")?.addEventListener("change", (e) => { staff.from = e.target.value; staff.result = null; rerender(true); later("staff"); });
    root.querySelector("#stTo")?.addEventListener("change", (e) => { staff.to = e.target.value; staff.result = null; rerender(true); later("staff"); });
    range("#stN", staff, "n", "staff");
    if (ui.tab === "crowd" && !crowd.result && !crowd.error) later("crowd");
    if (ui.tab === "staff" && !staff.result && !staff.error) later("staff");

    root.querySelector("#simAdd")?.addEventListener("click", async () => {
      try {
        await api(`/api/incidents/${ui.incident}/options`, { method: "POST", body: ui.tab === "crowd" ? crowdBody() : staffBody() });
        toast(t("sim.added")); ui.tab = "options"; crowd.result = null; staff.result = null;
        await detail(ui.incident, true); rerender(true);
      } catch (e) { toast(errorText(e), "error"); }
    });

    root.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
      if (busy) return;
      const id = Number(root.querySelector("#incPick")?.value || params[0]);
      const act = b.dataset.act, note = (notes[id] || "").trim();
      const operatorName = document.body.dataset.employeeName || "";
      const fe = root.querySelector("#formError");
      busy = true; b.disabled = true;
      try {
        await api(`/api/incidents/${id}/decisions`, { method: "POST",
          body: { action: act, recommendation_id: b.dataset.rec ? Number(b.dataset.rec) : null, note } });
        notes[id] = ""; toast(t("decide.done", { action: t(`decision_action.${act}`), operator: operatorName }));
        await refresh().catch(() => {});
      } catch (e) { toast(errorText(e), "error"); }
      finally { busy = false; await detail(id, true); rerender(true); }
    }));
  },
};
