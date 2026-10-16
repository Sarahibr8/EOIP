// Map page (UX design): the map on one side, «محاكاة قرار» on the other, and under them the
// selected zone's details next to the map layers.
import { t, fmtNum } from "../i18n.js";
import { icon, TYPE_ICON } from "../icons.js";
import { esc, pct, zoneName, locName, isOpen, incTitle, recTitle, recDesc, tr, code, toast, errorText } from "../ui.js";
import { fmtTime } from "../i18n.js";
import { opsMap, mapLegend, loadColor } from "../opsmap.js";
import { store, detail, api, refresh } from "../store.js";

const layers = { heat: true, pins: true, cams: true, teams: true };
const sim = { inc: null, rec: null };
let expanded = false;
const GATE_RATE = 16;

const simulable = (state) => state.incidents.filter((i) => i.status === "open" && i.kind === "operational");
const worst = (s) => { const st = (s.checks || []).map((c) => c.status); return st.includes("fail") ? "fail" : st.includes("warn") ? "warn" : "ok"; };

function simCard(state, d) {
  const cases = simulable(state);
  if (!cases.length) {
    return `<section class="panel flush sim-card"><div class="ph"><h3>${t("mapx.sim_title")}</h3></div>
      <div class="pb"><div class="queue-empty">${icon("check")}${t("mapx.sim_none")}</div></div></section>`;
  }
  const recs = d ? d.recommendations.filter((r) => r.simulation) : [];
  const active = recs.find((r) => r.id === sim.rec);
  const opts = recs.map((r, k) => {
    const s = r.simulation, on = r.id === sim.rec;
    const load = s.action !== "redeploy" || d.zone?.kind === "gate"
      ? `<span>${t("mapx.load")} <b><bdi>${pct(s.baseline.load_end)}% → ${pct(s.source.load_end)}%</bdi></b></span>` : "";
    const staff = s.action === "redeploy" && s.staff?.source
      ? `<span>${t("home.staff_after")} <b><bdi>${s.staff.source.before} → ${s.staff.source.after}/${s.staff.source.required}</bdi></b></span>` : "";
    return `<div class="gopt" data-active="${on}">
      <div class="go-t"><b>${k + 1}. ${esc(recTitle(r, d.zone_id))}</b>${k === 0 && r.status === "proposed" ? `<span class="rec2">${t("home.recommended")}</span>` : ""}</div>
      <p>${esc(recDesc(r, d.zone_id))}</p>
      <div class="go-m">${load}${staff}<span class="tag ${worst(s)}">${t(`check_status.${worst(s)}`)}</span></div>
      <button class="go-btn" type="button" data-simrec="${r.id}">${on ? t("mapx.stop") : t("mapx.simulate")}</button>
      ${on && r.status === "proposed" && d.status === "open" ? `<button class="btn btn-primary btn-sm go-approve" type="button" data-approve="${r.id}">${icon("check")}<span>${t("mapx.approve")}</span></button>` : ""}</div>`;
  }).join("");
  let result = `<p class="calc-note">${t("mapx.sim_hint")}</p>`;
  if (active) {
    const s = active.simulation;
    const rows = [[s.source_zone, s.baseline, s.source]];
    if (s.other_zone && s.other_before && s.other) rows.push([s.other_zone, s.other_before, s.other]);
    const bars = (s.action !== "redeploy" || d.zone?.kind === "gate" ? rows : []).map(([z, b, a]) => `<div class="mr-row"><span>${esc(zoneName(z))}</span>
      <div class="dual" style="--c:${loadColor(a.load_end)}"><i class="before" style="width:${Math.min(100, pct(b.load_end))}%"></i><i class="after" style="width:${Math.min(100, pct(a.load_end))}%"></i></div>
      <bdi>${pct(b.load_end)}→${pct(a.load_end)}%</bdi></div>`).join("");
    const st = s.staff || {};
    const staffRows = s.action === "redeploy" ? [st.source, st.other].filter(Boolean).map((x) => `<div class="mr-row"><span>${esc(zoneName(x.zone))}</span>
      <span class="${x.after >= x.required ? "ok" : "bad"}">${t("home.staff_after")}</span><bdi>${x.before}→${x.after}/${x.required}</bdi></div>`).join("") : "";
    const w = worst(s);
    const notes = (w === "ok" ? (s.side_effects || []).map((x) => tr("side_effect", x)) : (s.checks || []).filter((c) => c.status !== "ok").map((c) => tr("check", c)));
    result = `<div class="map-res"><div class="label">${t("home.sim_res", { min: s.horizon_min })}</div>${bars}${staffRows}
      <div class="verdict ${w}">${icon(w === "ok" ? "check" : "info")}<div><b>${t(`home.v_${w}`)}</b>${notes.length ? `<ul>${notes.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}</div></div>
      <div class="go-actions">${active.status === "proposed" && d.status === "open"
        ? `<button class="btn btn-primary btn-sm" type="button" data-approve="${active.id}">${icon("check")}<span>${t("mapx.approve")}</span></button>
           <span class="calc-note">${t("mapx.approve_note")}</span>` : ""}</div></div>`;
  }
  return `<section class="panel flush sim-card"><div class="ph"><h3>${t("mapx.sim_title")}</h3></div>
    <div class="pb">
      <label class="fld"><span>${t("mapx.case")}</span><select id="simCase">${cases.map((i) => `<option value="${i.id}" ${i.id === sim.inc ? "selected" : ""}>${i.priority} · ${esc(i.code)} · ${esc(incTitle(i))} · ${esc(zoneName(i.zone_id))}</option>`).join("")}</select></label>
      <div class="gbox"><h5>${t("mapx.alts")}</h5><span class="hint">${t("mapx.alts_hint")}</span>
        ${recs.length ? opts : `<div class="muted small">${t("decide.no_options")}</div>`}</div>
      ${result}
    </div></section>`;
}

function zoneCard(state, selId) {
  const zones = state.zones || [];
  const loc = store.locations[selId];
  const zoneId = loc ? loc.zone_id : zones.find((z) => z.id === selId) ? selId : zones[0]?.id;
  const z = zones.find((x) => x.id === zoneId);
  if (!z) return `<section class="panel flush"><div class="ph"><h3>${t("mapx.details")}</h3></div><div class="pb muted small">${t("map.pick")}</div></section>`;
  const open = state.incidents.filter((i) => isOpen(i) && i.zone_id === z.id);
  const locs = (state.locations || []).filter((l) => l.zone_id === z.id);
  const outRate = z.kind === "gate" ? z.staff_on_duty * GATE_RATE : z.outflow_per_min;
  return `<section class="panel flush zone-card"><div class="ph"><h3>${t("mapx.details")}</h3><span class="spacer"></span>
      <div class="zsel">${zones.map((x) => `<a href="#/map/${x.id}" aria-current="${x.id === z.id}">${esc(zoneName(x.id))}</a>`).join("")}</div></div>
    <div class="pb">
      <div class="zc-h"><b>${esc(zoneName(z.id))}</b>${loc ? `<span>· ${esc(locName(selId))}</span>` : ""}</div>
      <div class="meter" style="--c:${loadColor(z.load)}"><i style="width:${Math.min(100, pct(z.load))}%;background:${loadColor(z.load)}"></i></div>
      <dl class="kv zc-kv">
        <dt>${t("mapx.density")}</dt><dd><bdi>${pct(z.load)}%</bdi></dd>
        <dt>${t("mapx.visitors")}</dt><dd><bdi>${fmtNum(z.occupancy)} / ${fmtNum(z.capacity)}</bdi></dd>
        <dt>${t("map.staff")}</dt><dd class="${z.staff_on_duty < z.staff_required ? "short" : ""}"><bdi>${z.staff_on_duty} / ${z.staff_required}</bdi></dd>
        <dt>${t("map.flow")}</dt><dd><bdi>${fmtNum(z.inflow_per_min)} / ${fmtNum(outRate)}</bdi></dd>
        <dt>${t("map.locations")}</dt><dd>${locs.map((l) => `<a href="#/map/${l.id}" aria-current="${l.id === selId}">${esc(locName(l.id))}</a>`).join(" · ")}</dd>
        <dt>${t("mapx.open")}</dt><dd>${fmtNum(open.length)}</dd>
      </dl>
      ${loc ? locBox(state, selId) : ""}
      ${open.length && !loc ? `<ul class="zc-inc">${open.map((i) => `<li class="sev-${i.priority}"><a href="#/c/${i.id}">${icon(TYPE_ICON[i.type] || "incident")}<span>${esc(incTitle(i))}</span>${code(i.code)}</a></li>`).join("")}</ul>` : ""}
      <p class="calc-note">${t("mapx.details_hint")}</p>
    </div></section>`;
}

/** Details of one operational location (clicked in the zone card or on the map). */
function locBox(state, locId) {
  const here = state.incidents.filter((i) => i.location_id === locId);
  const open = here.filter((i) => isOpen(i));
  const sigs = (state.signals || []).filter((s) => s.location_id === locId).slice(0, 4);
  return `<div class="loc-box"><h4>${icon("pin")}${esc(locName(locId))}<span class="muted small">· ${esc(zoneName(store.locations[locId]?.zone_id))}</span></h4>
    <dl class="kv"><dt>${t("mapx.loc_open")}</dt><dd>${open.length}</dd><dt>${t("mapx.loc_total")}</dt><dd>${here.length}</dd></dl>
    ${open.length ? `<ul class="zc-inc">${open.map((i) => `<li class="sev-${i.priority}"><a href="#/c/${i.id}">${icon(TYPE_ICON[i.type] || "incident")}<span>${esc(incTitle(i))} · ${t(`status.${i.status}`)}</span>${code(i.code)}</a></li>`).join("")}</ul>`
      : `<p class="calc-note">${t("mapx.loc_calm")}</p>`}
    ${sigs.length ? `<div class="label sub">${t("mapx.loc_recent")}</div><ul class="loc-sig">${sigs.map((s) => `<li><bdi>${fmtTime(s.received_at)}</bdi><span>${esc(t(`category.${s.category}`))}${s.raw_text ? ` · «${esc(s.raw_text)}»` : ""}</span></li>`).join("")}</ul>` : ""}
  </div>`;
}

function layersCard() {
  const row = (k) => `<label class="switch-row"><span>${t(`mapx.l_${k}`)}</span>
    <input type="checkbox" class="switch" data-layer="${k}" ${layers[k] ? "checked" : ""}></label>`;
  return `<section class="panel flush layers-card"><div class="ph"><h3>${t("mapx.layers")}</h3></div>
    <div class="pb">${row("heat")}${row("pins")}${row("cams")}${row("teams")}</div></section>`;
}

export const mapView = {
  nav: "map",
  async render({ state, params }) {
    const cases = simulable(state);
    if (!cases.some((i) => i.id === sim.inc)) { sim.inc = cases[0]?.id || null; sim.rec = null; }
    const d = sim.inc ? await detail(sim.inc).catch(() => null) : null;
    const active = d?.recommendations.find((r) => r.id === sim.rec && r.simulation);
    if (!active) sim.rec = null;
    const selId = params[0] || (d?.zone_id) || state.zones[0]?.id;
    return `
      <div class="map2">
        ${simCard(state, d)}
        <section class="panel flush map-card ${expanded ? "is-expanded" : ""}">
          <div class="ph"><h3>${t("mapx.title")}</h3><span class="mode-chip ${active ? "sim" : ""}"><i></i>${active ? t("home.sim_mode") : t("home.live")}</span><span class="spacer"></span>
            <button class="icon-btn" type="button" id="mapExpand" aria-pressed="${expanded}" title="${esc(t(expanded ? "map.collapse" : "map.expand"))}" aria-label="${esc(t(expanded ? "map.collapse" : "map.expand"))}">${icon(expanded ? "x" : "expand")}</button></div>
          ${opsMap(state, { selected: selId, teams: layers.teams, heat: layers.heat, pins: layers.pins, cams: layers.cams, sim: active?.simulation, simLabel: active ? recTitle(active, d.zone_id) : "" })}
          ${mapLegend()}
        </section>
        <div class="map2-bottom">${zoneCard(state, selId)}${layersCard()}</div>
      </div>`;
  },
  after(root, { rerender }) {
    root.querySelector("#mapExpand")?.addEventListener("click", () => { expanded = !expanded; rerender(true); });
    root.querySelector("#simCase")?.addEventListener("change", (e) => { sim.inc = Number(e.target.value); sim.rec = null; rerender(true); });
    root.querySelectorAll("[data-simrec]").forEach((b) => b.addEventListener("click", () => {
      const id = Number(b.dataset.simrec); sim.rec = sim.rec === id ? null : id; rerender(true);
    }));
    root.querySelectorAll("[data-approve]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        await api(`/api/incidents/${sim.inc}/decisions`, { method: "POST", body: { action: "approve", recommendation_id: Number(b.dataset.approve), note: "" } });
        toast(t("home.moved_approved", { operator: document.body.dataset.employeeName || "" }));
        sim.rec = null; sim.inc = null; await refresh();
      } catch (e) { toast(errorText(e), "error"); b.disabled = false; }
      rerender(true);
    }));
    root.querySelectorAll("[data-layer]").forEach((c) => c.addEventListener("change", () => { layers[c.dataset.layer] = c.checked; rerender(true); }));
    if (!mapView.escBound) {
      mapView.escBound = true;
      document.addEventListener("keydown", (e) => { if (e.key === "Escape" && expanded) { expanded = false; rerender(true); } });
    }
  },
};
