import { t, fmtNum, fmtTime } from "../i18n.js";
import { icon, SIGNAL_ICON } from "../icons.js";
import { esc, pct, zoneName, placeText, isOpen, strip, code, withNames } from "../ui.js";
import { sitePlan } from "../siteplan.js";

// funnel bar widths: log scale so 1 critical out of 263 signals is still visible
const width = (n, max) => (n <= 0 ? 0 : Math.max(8, Math.round((Math.log10(n + 1) / Math.log10(max + 1)) * 100)));

export const overview = {
  nav: "overview",
  render({ state }) {
    const c = state.counters;
    const idle = c.received === 0;
    const waiting = state.incidents.filter((i) => i.status === "open" && i.priority !== "P4");
    const priorityCounts = Object.fromEntries(["P1", "P2", "P3", "P4"].map((p) => [p, state.incidents.filter((i) => isOpen(i) && i.priority === p).length]));
    const top = waiting[0];
    const rest = waiting.slice(1, 6);
    const max = Math.max(1, c.received);
    const rows = [
      [c.received, t("overview.f_received")],
      [c.relevant + c.needs_review, t("overview.f_attention")],
      [c.incidents_open, t("overview.f_incidents")],
      [c.critical, t("overview.f_critical")],
    ];
    const funnel = `<div class="funnel" aria-label="${esc(t("overview.funnel_label"))}">
      ${rows.map(([n, label]) => `<div class="row"><b>${fmtNum(n)}</b>
        <div><div class="bar" style="width:${width(n, max)}%">${label}</div></div></div>`).join("")}
      <div class="notes">${t("overview.notes", { noise: fmtNum(c.noise), routine: fmtNum(c.routine), dup: fmtNum(c.duplicate) })}</div>
    </div>`;

    const needs = top ? `<div class="strips">${strip(top, { big: top.priority === "P1", decide: true })}${rest.map((i) => strip(i, { decide: true })).join("")}</div>`
      : `<div class="empty"><b>${t("overview.now_empty")}</b>${idle ? t("overview.now_empty_idle") : ""}</div>`;

    const signals = state.signals.slice(0, 10);
    const stream = signals.length ? `<ul class="stream">${signals.map((s) => `
      <li class="${s.disposition === "correlated" ? "" : "dim"}">
        <span class="time">${fmtTime(s.received_at)}</span><span class="stream-icon ${s.disposition}">${icon(SIGNAL_ICON[s.signal_type])}</span>
        <span class="what">${t(`category.${s.category}`)} · ${esc(s.zone_id ? placeText(s.zone_id, s.location_id) : t("place.unknown_zone"))}</span>
        <span class="disp ${s.disposition}">${s.disposition === "correlated" && s.incident_code ? code(s.incident_code) : t(`disposition.${s.disposition}`)}</span>
      </li>`).join("")}</ul>` : `<div class="empty">${t("overview.now_empty_idle")}</div>`;

    const zones = [...state.zones].sort((a, b) => a.id.localeCompare(b.id));
    const dec = state.decisions.slice(0, 4);
    const decisions = dec.length ? `<ul class="stream">${dec.map((d) => withNames(d.snapshot?.names, () => `
      <li><span class="time">${fmtTime(d.created_at, false)}</span><span class="stream-icon success">${icon("check")}</span>
        <span class="what">${t(`decision_action.${d.action}`)} · ${code(d.snapshot?.incident_code || "")} · ${esc(zoneName(d.snapshot?.zone_id))}</span>
        <span class="disp">${esc(d.operator)}</span></li>`)).join("")}</ul>` : `<div class="empty">${t("overview.decisions_empty")}</div>`;

    return `
      <section class="ov-hero">
        <div><h1>${t("overview.title")}</h1><p>${t("overview.intro")}</p></div>
        ${funnel}
      </section>
      <section class="priority-overview" aria-label="${t("overview.priority_title")}">
        <div class="priority-overview-head"><h2>${t("overview.priority_title")}</h2><span>${t("overview.priority_subtitle")}</span></div>
        <div class="priority-cards">${["P1", "P2", "P3", "P4"].map((p) => `<a href="#/incidents" class="priority-card ${p}" data-go="#/incidents">
          <span class="priority-card-head"><span class="priority-card-icon">${icon(({ P1: "incident", P2: "bell", P3: "overview", P4: "check" })[p])}</span><span class="prio ${p}">${p} · ${t(`priority.${p}`)}</span></span>
          <b>${fmtNum(priorityCounts[p])}</b><small>${t("overview.priority_open")}</small>
        </a>`).join("")}</div>
      </section>
      <div class="ov-grid">
        <div class="ov-primary">
          <section class="panel">
            <h2 class="section-title">${t("overview.now_title")}<a class="btn btn-quiet" href="#/incidents">${t("overview.all_incidents")}</a></h2>
            ${needs}
          </section>
          <section class="panel ov-map">
            <h2 class="section-title">${t("overview.plan_title")}<a class="btn btn-quiet" href="#/map">${t("overview.open_map")}</a></h2>
            <div class="opsmap-scroll">${sitePlan(state, { compact: true })}</div>
            <p class="ov-map-note">${t("map.legend_note")}</p>
          </section>
          <section class="panel">
            <h2 class="section-title">${t("overview.signals_title")}<small>${Object.entries(c.by_signal_type || {}).map(([k, n]) => `${t(`signal_type.${k}`)} ${fmtNum(n)}`).join(" · ")}</small></h2>
            ${stream}
          </section>
        </div>
        <aside class="ov-side">
          <section class="panel">
            <h2 class="section-title">${t("overview.zones_title")}</h2>
            <ul class="zone-bars">${zones.map((z) => `<li><span>${esc(zoneName(z.id))}</span>
              <div class="meter ${z.load >= 0.95 ? "hot" : z.load >= 0.85 ? "warm" : ""}"><i style="width:${Math.min(100, pct(z.load))}%"></i></div>
              <span class="num">${pct(z.load)}%</span></li>`).join("")}</ul>
          </section>
          <section class="panel">
            <h2 class="section-title">${t("overview.decisions_title")}<a class="btn btn-quiet" href="#/log">${t("nav.log")}</a></h2>
            ${decisions}
          </section>
        </aside>
      </div>`;
  },
};
