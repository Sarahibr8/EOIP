// Alerts page (UX design): every report case as a card. «عرض التفاصيل» opens the details under
// the card itself (no page change): the raw reports from camera / radio, why the priority, and
// what was decided.
import { t, fmtTime, fmtNum } from "../i18n.js";
import { icon, TYPE_ICON } from "../icons.js";
import { esc, zoneName, placeText, isOpen, code, incTitle, tr, recTitle, srcKind, srcChips, teamName, escTag } from "../ui.js";
import { detail } from "../store.js";

const f = { tab: "all", zone: "", type: "", sort: "priority" };
const openCards = new Set();
const RANK = { P1: 1, P2: 2, P3: 3, P4: 3 };
const KIND_RANK = { emergency: 1, operational: 2, routine: 3 };
// Only cases still waiting for a decision are listed here; approved / rejected / solved cases are in the log.
const TABS = {
  all: () => true,
  P1: (i) => i.priority === "P1",
  P2: (i) => i.priority === "P2",
  P3: (i) => i.priority === "P3" || i.priority === "P4",
};
const SORT = {
  priority: (a, b) => (isOpen(b) - isOpen(a)) || RANK[a.priority] - RANK[b.priority]
    || (KIND_RANK[a.kind] ?? 3) - (KIND_RANK[b.kind] ?? 3) || b.priority_score - a.priority_score,
  newest: (a, b) => new Date(b.updated_at) - new Date(a.updated_at),
  zone: (a, b) => a.zone_id.localeCompare(b.zone_id) || RANK[a.priority] - RANK[b.priority],
};
const opt = (v, label, cur) => `<option value="${v}" ${cur === v ? "selected" : ""}>${esc(label)}</option>`;
const pill = (p) => `<span class="pill sev-${p}"><span class="pdot"></span>${p} · ${t(`priority.${p}`)}</span>`;

function details(d) {
  if (!d) return `<div class="ac-detail"><div class="muted small">${t("app.loading")}</div></div>`;
  const reports = d.alerts.filter((a) => a.disposition !== "duplicate");
  const dup = d.alerts.length - reports.length;
  const reasons = (d.priority_reasons || []).filter((r) => r.key !== "type_base" && r.points > 0).sort((a, b) => b.points - a.points);
  const rec = d.recommendations?.[0];
  const decided = [...(d.decisions || [])].reverse();
  const teams = (d.teams || []).map((x) => x.id).filter(Boolean);
  return `<div class="ac-detail">
    <div class="ac-facts">
      <div><span>${t("alerts.f_place")}</span><b>${esc(placeText(d.zone_id, d.location_id))}</b></div>
      <div><span>${t("alerts.f_opened")}</span><b><bdi>${fmtTime(d.opened_at)}</bdi></b></div>
      <div><span>${t("alerts.f_kind")}</span><b>${t(`kind.${d.kind}`)}</b></div>
      <div><span>${t("alerts.f_reports")}</span><b>${t("alerts.n_reports", { n: reports.length })}${dup ? ` · ${t("alerts.n_dup", { n: dup })}` : ""}</b></div>
    </div>
    <div class="ac-cols">
      <div class="ac-sec"><h4>${t("alerts.reports")}</h4>
        <ol class="ac-tl">${reports.map((a) => `<li><span class="tm"><bdi>${fmtTime(a.received_at)}</bdi></span>
          <span class="tsrc ${srcKind(a.source_system)}">${icon(srcKind(a.source_system))}<b>${t(`source_system.${a.source_system}`)}</b></span>
          <span class="tx">${t(`category.${a.category}`)}${a.raw_text ? ` · <q dir="auto">${esc(a.raw_text)}</q>` : ""}</span></li>`).join("")}</ol></div>
      <div class="ac-sec"><h4>${t("alerts.why")}</h4>
        ${reasons.length ? `<ul class="ac-why">${reasons.map((r) => `<li><b>+${r.points}</b><span>${esc(tr("reason", r))}</span></li>`).join("")}</ul>` : `<div class="muted small">—</div>`}
        <h4>${t("alerts.action")}</h4>
        ${decided.length ? `<ul class="ac-dec">${decided.map((x) => `<li><span class="tm"><bdi>${fmtTime(x.created_at, false)}</bdi></span><b>${t(`decision_action.${x.action}`)}</b>
            <span>${esc(x.operator || "")}${x.note ? ` · ${esc(x.note)}` : ""}</span></li>`).join("")}</ul>`
          : `<div class="ac-rec">${rec ? `${t("alerts.suggested")}: <b>${esc(recTitle(rec, d.zone_id))}</b>` : t("alerts.no_action")}</div>`}
        ${teams.length ? `<div class="ac-teams">${icon("team")}${teams.map((x) => esc(teamName(x))).join(" · ")}</div>` : ""}
      </div>
    </div>
    <div class="ac-foot">${isOpen(d) ? `<a class="btn btn-primary btn-sm" href="#/c/${d.id}">${icon("decide")}<span>${t(d.status === "open" ? "alerts.go_decide" : "alerts.go_case")}</span></a>` : ""}
      <a class="btn btn-quiet btn-sm" href="#/incident/${d.id}">${t("alerts.full")}</a></div>
  </div>`;
}

function card(i, d) {
  const isOpenCard = openCards.has(i.id);
  return `<article class="acard sev-${i.priority} ${isOpen(i) ? "" : "closed"}" id="ac-${i.id}">
    <div class="ac-row">
      <div class="ac-main">
        <div class="ac-meta">${pill(i.priority)}${escTag(i)}${code(i.code)}<span class="ac-src">${srcChips(i.sources || [])}</span></div>
        <h3>${icon(TYPE_ICON[i.type] || "incident")}${esc(incTitle(i))}</h3>
        <div class="ac-loc">${esc(placeText(i.zone_id, i.location_id))} · ${t("alerts.first", { time: fmtTime(i.opened_at, false) })} · ${t("alerts.n_reports", { n: i.alert_count || 0 })}</div>
      </div>
      <div class="ac-side">
        <span class="ac-st">${t("alerts.status")}: <b class="st ${i.status}">${t(`status.${i.status}`)}</b></span>
        <button class="btn btn-sm ac-more" type="button" data-more="${i.id}" aria-expanded="${isOpenCard}">
          <span>${t(isOpenCard ? "alerts.hide" : "alerts.show")}</span>${icon("chevronDown", "chev")}</button>
      </div>
    </div>
    ${isOpenCard ? details(d) : ""}
  </article>`;
}

export const incidentsView = {
  nav: "incidents",
  async render({ state }) {
    const types = [...new Set(state.incidents.map((i) => i.label || i.type))];
    if (!TABS[f.tab]) f.tab = "all";
    const base = state.incidents.filter((i) => i.status === "open" && (!f.zone || i.zone_id === f.zone) && (!f.type || (i.label || i.type) === f.type));
    const list = base.filter(TABS[f.tab]).sort(SORT[f.sort]);
    const n = (k) => base.filter(TABS[k]).length;
    const ds = {};
    await Promise.all(list.filter((i) => openCards.has(i.id)).map(async (i) => { ds[i.id] = await detail(i.id).catch(() => null); }));
    const tab = (k, label) => `<button type="button" data-tab="${k}" aria-pressed="${f.tab === k}">${label}<span class="n">${fmtNum(n(k))}</span></button>`;
    return `
      <section class="panel filterbar" role="search">
        <div class="fb-group"><span class="fb-l">${t("alerts.f_level")}</span>
          <div class="segctl" role="group" aria-label="${esc(t("alerts.filter"))}">
            ${tab("all", t("alerts.t_all"))}${tab("P1", `${t("priority.P1")} · P1`)}${tab("P2", `${t("priority.P2")} · P2`)}${tab("P3", `${t("priority.P3")} · P3`)}
          </div></div>
        <label class="fb-group"><span class="fb-l">${t("incidents.f_zone")}</span><select id="fZone">${opt("", t("incidents.any"), f.zone)}${state.zones.map((z) => opt(z.id, zoneName(z.id), f.zone)).join("")}</select></label>
        <label class="fb-group"><span class="fb-l">${t("incidents.f_type")}</span><select id="fType">${opt("", t("incidents.any"), f.type)}${types.map((x) => opt(x, t(`incident_label.${x}`), f.type)).join("")}</select></label>
        <label class="fb-group"><span class="fb-l">${t("incidents.sort")}</span><select id="fSort">${Object.keys(SORT).map((k) => opt(k, t(`incidents.sort_${k}`), f.sort)).join("")}</select></label>
        <button class="btn btn-quiet btn-sm fb-clear" id="fClear" type="button" title="${esc(t("incidents.clear"))}" ${f.zone || f.type || f.tab !== "all" || f.sort !== "priority" ? "" : "disabled"}>${icon("reset")}<span>${t("incidents.clear")}</span></button>
      </section>
      <div class="alerts-links"><p class="alerts-count">${t("alerts.count", { n: fmtNum(state.counters.received), c: fmtNum(base.length), shown: fmtNum(list.length) })}</p></div>
      ${list.length ? `<div class="acards">${list.map((i) => card(i, ds[i.id])).join("")}</div>`
        : base.length ? `<div class="empty"><b>${t("incidents.empty")}</b>${t("incidents.empty_hint")}</div>`
          : `<div class="empty"><b>${t(state.incidents.length ? "alerts.all_decided" : "incidents.none_yet")}</b>${state.incidents.length ? t("alerts.all_decided_hint") : ""}</div>`}`;
  },
  after(root, { rerender }) {
    const set = (k, v) => { f[k] = v; rerender(true); };
    root.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => set("tab", b.dataset.tab)));
    root.querySelector("#fZone")?.addEventListener("change", (e) => set("zone", e.target.value));
    root.querySelector("#fType")?.addEventListener("change", (e) => set("type", e.target.value));
    root.querySelector("#fSort")?.addEventListener("change", (e) => set("sort", e.target.value));
    root.querySelector("#fClear")?.addEventListener("click", () => { Object.assign(f, { tab: "all", zone: "", type: "", sort: "priority" }); rerender(true); });
    root.querySelectorAll("[data-more]").forEach((b) => b.addEventListener("click", () => {
      const id = Number(b.dataset.more);
      if (openCards.has(id)) openCards.delete(id); else openCards.add(id);
      rerender(true);
    }));
  },
};

export { incTitle };
