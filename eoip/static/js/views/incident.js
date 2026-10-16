import { t, fmtNum, fmtTime } from "../i18n.js";
import { icon, TYPE_ICON, SOURCE_ICON } from "../icons.js";
import { esc, pct, prioBadge, zoneName, locName, teamName, tr, isOpen, recTitle, placeHtml, originTag, code, incTitle, loading } from "../ui.js";
import { detail } from "../store.js";

export function incidentHeader(d) {
  return `<header class="inc-head ${d.priority}">
    <div class="meta">${prioBadge(d.priority)}<span class="tag ${d.status === "action_approved" ? "ok" : ""}">${t(`status.${d.status}`)}</span>
      ${code(d.code)}<span>${t(`kind.${d.kind}`)}</span><span>${t("incident.opened", { time: fmtTime(d.opened_at, false) })}</span></div>
    <h1>${icon(TYPE_ICON[d.type])}${esc(incTitle(d))}</h1>
    <div>${placeHtml(d.zone_id, d.location_id)}</div>
  </header>`;
}

const KEY_REASONS = ["independent_source", "duplicate_of", "no_open_match", "same_location"];

function links(d) {
  const nSrc = new Set(d.alerts.filter((a) => a.disposition === "correlated").map((a) => a.source_system)).size;
  return `<section class="panel">
    <h2 class="section-title">${t("incident.links")}<small>${t("incident.links_sub", { n: d.alerts.length, s: nSrc })}</small></h2>
    <div class="table-wrap"><table class="table links-table">
      <thead><tr><th>${t("incident.col_time")}</th><th>${t("incident.col_report")}</th><th>${t("incident.col_place")}</th>
        <th>${t("incident.col_link")}</th><th title="${esc(t("incident.score_hint"))}">${t("incident.col_score")}</th></tr></thead>
      <tbody>${d.alerts.map((a) => {
        const c = a.correlation;
        const chips = c ? c.reasons.map((r) => `<span class="${KEY_REASONS.includes(r.key) ? "key" : r.key === "different_location" ? "stop" : ""}">${esc(tr("corr", r))}</span>`).join("") : "—";
        const sameTime = !a.occurred_at || a.occurred_at.slice(0, 19) === a.received_at.slice(0, 19);
        return `<tr>
          <td class="muted"><div>${fmtTime(a.received_at)}</div>${sameTime ? "" : `<div class="small" title="${esc(t("incident.event_time"))}">${t("incident.event_at", { time: fmtTime(a.occurred_at) })}</div>`}</td>
          <td><div class="strong">${icon(SOURCE_ICON[a.source_system])} ${t(`source_system.${a.source_system}`)}</div>
            <div>${t(`category.${a.category}`)} ${originTag(a.origin)}
              <span class="muted small">${t("incident.confidence", { pct: pct(a.confidence) })}</span></div>
            ${a.raw_text ? `<span class="quote" dir="auto">${esc(a.raw_text)}</span>` : ""}
            ${a.payload?.snapshot ? `<img class="snap" src="${esc(a.payload.snapshot)}" alt="${esc(t("incident.snapshot"))}" loading="lazy">` : ""}</td>
          <td>${placeHtml(a.zone_id, a.location_id, a.location_detail && !a.location_id && a.source_system === "radio" ? a.location_detail : "")}</td>
          <td><div class="why-chips">${chips}</div></td>
          <td>${c && c.score != null ? `<span class="score">${c.score.toFixed(2)}</span>` : "—"}</td></tr>`;
      }).join("")}</tbody></table></div>
    <p class="calc-note">${t("incident.score_hint")}</p>
  </section>`;
}

function reasons(d) {
  const base = d.priority_reasons.find((r) => r.key === "type_base");
  const rest = d.priority_reasons.filter((r) => r.key !== "type_base");
  return `<section class="panel">
    <h2 class="section-title">${t("incident.why")}<small>${t("incident.confidence", { pct: pct(d.confidence) })}</small></h2>
    <ul class="reasons">
      ${rest.map((r) => `<li><span>${esc(tr("reason", r))}</span><span class="pts ${r.points > 0 ? "up" : r.points < 0 ? "down" : ""}">${r.points > 0 ? "+" : ""}${r.points || ""}</span></li>`).join("")}
      ${base ? `<li class="base"><span>${esc(tr("reason", base))}</span><span class="pts">${base.points}</span></li>` : ""}
    </ul>
    <div class="scale"><div class="track"><span class="needle" style="inset-inline-start:${d.priority_score}%"></span></div>
      <div class="ticks"><span>P4</span><span>P3 25</span><span>P2 50</span><span>P1 75</span><span>100</span></div>
      <div class="muted small" style="margin-top:4px">${t("incident.score", { score: d.priority_score })}</div></div>
  </section>`;
}

function timeline(d) {
  const ev = [{ at: d.opened_at, dot: "intel", html: t("timeline.opened") }];
  for (const a of d.alerts) if (a.disposition !== "duplicate")
    ev.push({ at: a.received_at, dot: "", html: `${t(`category.${a.category}`)}<small>${t(`source_system.${a.source_system}`)} · ${t(`origin.${a.origin}`)}</small>` });
  if (d.escalated_at) ev.push({ at: d.escalated_at, dot: d.priority === "P1" ? "p1" : "intel", html: t("timeline.escalated", { priority: `${d.priority} ${t(`priority.${d.priority}`)}` }) });
  for (const x of d.decisions) {
    const rec = d.recommendations.find((r) => r.id === x.recommendation_id);
    ev.push({ at: x.created_at, dot: "ok", html: `${t("timeline.decision", { action: t(`decision_action.${x.action}`), operator: esc(x.operator) })}${rec ? `<small>${esc(recTitle(rec, d.zone_id))}</small>` : ""}${x.note ? `<small>“${esc(x.note)}”</small>` : ""}` });
  }
  ev.sort((a, b) => new Date(a.at) - new Date(b.at));
  return `<section class="panel"><h2 class="section-title">${t("incident.timeline")}</h2>
    <ul class="timeline">${ev.map((e) => `<li><span class="tm">${fmtTime(e.at)}</span><span class="dt ${e.dot}"></span><span>${e.html}</span></li>`).join("")}</ul></section>`;
}

export function closedBanner(d) {
  if (d.status === "resolved" || d.status === "dismissed")
    return `<div class="banner closed">${t(`incident.status_banner_${d.status}`, { time: fmtTime(d.closed_at, false) })}</div>`;
  return "";
}

export const incidentView = {
  nav: "incidents",
  async render({ params }) {
    const id = Number(params[0]);
    if (!id) return `<div class="empty"><b>${t("incident.pick")}</b></div>`;
    const d = await detail(id);
    if (!d) return `<div class="empty"><b>${t("incident.not_found")}</b><a class="btn" href="#/incidents">${t("nav.incidents")}</a></div>`;
    const z = d.zone;
    return `${incidentHeader(d)}${closedBanner(d)}
      <div class="cols cols-2-1">
        <div>${links(d)}${reasons(d)}</div>
        <div>
          <section class="panel">
            ${isOpen(d) ? `<a class="btn btn-primary btn-wide" href="#/decide/${d.id}" style="margin-bottom:16px">${icon("decide")}${t("incident.go_decide")}</a>` : ""}
            <h2 class="section-title">${t("incident.place")}</h2>
            <dl class="kv">
              <dt>${t("place.zone")}</dt><dd><a href="#/map/${z.id}">${esc(zoneName(z.id))}</a></dd>
              <dt>${t("place.location")}</dt><dd>${d.location_id ? `<a href="#/map/${d.location_id}">${esc(locName(d.location_id))}</a>` : `<span class="muted">${t("place.no_location")}</span>`}</dd>
              <dt>${t("map.occupancy")}</dt><dd><b>${pct(z.load)}%</b> (${fmtNum(z.occupancy)} / ${fmtNum(z.capacity)})</dd>
              <dt>${t("map.staff")}</dt><dd>${z.staff_on_duty} / ${t("map.min_staff", { n: z.staff_required })}</dd>
            </dl>
          </section>
          <section class="panel"><h2 class="section-title">${t("incident.teams")}</h2>
            ${d.teams.length ? `<ul class="crew">${d.teams.map((tm) => `<li><span>${esc(teamName(tm.id))}<small>${t(`teamkind.${tm.kind}`)} · ${t("map.members", { n: tm.members })}</small></span><span class="tag ok">${fmtTime(tm.assigned_at, false)}</span></li>`).join("")}</ul>`
              : `<div class="muted small">${t("incident.no_teams")}</div>`}</section>
          ${timeline(d)}
        </div>
      </div>`;
  },
  loading,
};
