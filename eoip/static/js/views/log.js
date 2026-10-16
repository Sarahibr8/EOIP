// Log (UX design): reports + decisions in one timeline, grouped by day.
// Filters: period (daily / weekly / monthly) or one date, and status. Decisions are permanent
// (every event); reports belong to the current event (a new event clears them).
import { t, getLang, fmtTime } from "../i18n.js";
import { icon } from "../icons.js";
import { esc, zoneName, recTitle, withNames, code, errorText, isOpen, srcChips, escMatrix, escLabel } from "../ui.js";
import { api, lvl } from "../store.js";
import { outcome } from "./command.js";

const F = { period: "day", date: "", status: "all", month: "" };
const DAYS = { day: 1, week: 7, month: 30 };
const TZ = "Asia/Riyadh";

const dayKey = (d) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(d));
const fmtDay = (d) => {
  const ar = getLang() === "ar";
  const greg = new Intl.DateTimeFormat(ar ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: TZ }).format(new Date(d));
  const hijri = new Intl.DateTimeFormat(ar ? "ar-SA-u-ca-islamic-umalqura-nu-latn" : "en-GB-u-ca-islamic-umalqura", { day: "numeric", month: "long", year: "numeric", timeZone: TZ }).format(new Date(d));
  return `${greg} · ${hijri}`;
};
const shortDate = (d) => new Intl.DateTimeFormat(getLang() === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { day: "numeric", month: "short", timeZone: TZ }).format(new Date(d));
const pill = (p) => (p ? `<span class="pill sev-${p}"><span class="pdot"></span>${p} · ${t(`priority.${p}`)}</span>` : "—");
const srcBadge = (list) => (list && list.length ? `<div class="src-col">${srcChips(list)}</div>` : "—");
const monthKey = (d) => dayKey(d).slice(0, 7);
const fmtMonth = (key, opts = {}) => {
  const ar = getLang() === "ar", d = new Date(`${key}-15T12:00:00+03:00`);
  const greg = new Intl.DateTimeFormat(ar ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { month: "long", year: "numeric", timeZone: TZ }).format(d);
  if (opts.short) return greg;
  const h1 = new Intl.DateTimeFormat(ar ? "ar-SA-u-ca-islamic-umalqura-nu-latn" : "en-GB-u-ca-islamic-umalqura", { month: "long", timeZone: TZ });
  const first = new Date(`${key}-01T12:00:00+03:00`), last = new Date(new Date(first.getFullYear(), first.getMonth() + 1, 0, 12));
  const a = h1.format(first), b = h1.format(last);
  return `${greg} · ${a === b ? a : `${a} – ${b}`}`;
};
const lastMonths = (n) => { const out = [], now = new Date(); for (let k = 0; k < n; k++) { const d = new Date(now.getFullYear(), now.getMonth() - k, 15, 12); out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`); } return out; };

function records(state, signals, decisions, escalations) {
  const incById = Object.fromEntries(state.incidents.map((i) => [i.id, i]));
  const reports = signals.filter((s) => s.disposition === "correlated" || s.disposition === "needs_review").map((s) => {
    const inc = incById[s.incident_id];
    return { t: s.received_at, kind: "alert", id: inc?.id, code: s.incident_code || "—", title: inc ? t(`incident_label.${inc.label || inc.type}`) : t(`category.${s.category}`),
      zone: s.zone_id, src: [s.source_system], detail: `${t(`category.${s.category}`)}${s.raw_text ? ` · «${s.raw_text}»` : ""}`, by: null,
      sev: lvl(inc?.priority), done: inc ? !isOpen(inc) : false,
      st: !inc ? { cls: "open", key: "logx.st_open" } : inc.status === "open" ? { cls: "open", key: "logx.st_waiting" }
        : inc.status === "escalated" ? { cls: "escalated", key: "logx.st_escalated", p: { code: inc.escalation.code } }
        : inc.status === "dismissed" ? { cls: "dismissed", key: "logx.st_rejected" } : inc.status === "resolved" ? { cls: "resolved", key: "logx.st_done" }
          : { cls: "action_approved", key: "logx.st_approved" } };
  });
  const actions = decisions.map((d) => withNames(d.snapshot?.names, () => {
    const s = d.snapshot || {}, rec = s.recommendation;
    const inc = d.current_run ? incById[d.incident_id] : null;
    const closedByThis = d.action === "resolve" || d.action === "dismiss";
    return { t: d.created_at, kind: "action", id: inc?.id, code: s.incident_code || "—",
      title: s.incident_label ? t(`incident_label.${s.incident_label}`) : s.incident_type ? t(`incident_type.${s.incident_type}`) : "",
      zone: s.zone_id, src: inc?.sources?.length ? inc.sources : s.sources || [],
      detail: `${t(`decision_action.${d.action}`)}${rec ? ` · ${recTitle({ code: rec.code, params: rec.params || {} }, s.zone_id)}` : ""}${s.escalation ? ` · ${t("esc.log", { code: s.escalation })}` : ""}${d.note ? ` · ${d.note}` : ""}`,
      by: d.operator, sev: lvl(d.priority_at_decision), done: closedByThis || d.action === "approve" || (inc ? !isOpen(inc) : !d.current_run),
      st: outcome(d, null) };
  }));
  // escalations: the case ran past its response time and went to the managers (level rises L1 → L2 → L3)
  const escs = (escalations || []).map((e) => withNames(e.snapshot?.names, () => {
    const s = e.snapshot || {};
    const step = (escMatrix().step_s[e.priority] || 60) / 60;
    return { t: e.created_at, kind: "escalation", id: null, code: s.incident_code || "—",
      title: s.incident_label ? t(`incident_label.${s.incident_label}`) : s.incident_type ? t(`incident_type.${s.incident_type}`) : "",
      zone: s.zone_id, src: s.sources || [], detail: t("esc.log_detail", { min: step, label: escLabel(e.code) }),
      by: t("esc.by_system"), sev: lvl(e.priority), done: false,
      st: { cls: "escalated", key: "logx.st_escalated", p: { code: e.code } } };
  }));
  return [...reports, ...actions, ...escs].sort((a, b) => new Date(b.t) - new Date(a.t));
}

function range() {
  if (!F.date && F.period === "month") {
    const m = F.month || monthKey(Date.now());
    return { from: `${m}-01`, to: `${m}-31`, label: fmtMonth(m) };
  }
  if (F.date) return { from: F.date, to: F.date, label: t("logx.one_day", { d: fmtDay(`${F.date}T12:00:00+03:00`) }) };
  const to = dayKey(Date.now());
  const from = dayKey(Date.now() - (DAYS[F.period] - 1) * 864e5);
  return { from, to, label: t(`logx.range_${F.period}`) };
}

export const logView = {
  nav: "log",
  async render({ state }) {
    let data, sig;
    try { [data, sig] = await Promise.all([api("/api/decisions?limit=500"), api("/api/state?signals=1000")]); }
    catch (e) { return `<div class="banner warn">${esc(errorText(e))}</div>`; }
    const r = range();
    const allRecs = records(state, sig.signals, data.decisions, data.escalations);
    const inRange = allRecs.filter((x) => { const k = dayKey(x.t); return k >= r.from && k <= r.to; });
    const list = inRange.filter((x) => F.status === "all" || (F.status === "happened" ? x.kind === "alert"
      : F.status === "done" ? x.kind === "action" && x.done : (x.kind === "action" && !x.done) || x.kind === "escalation"));
    const ids = [...new Set(inRange.map((x) => x.code).filter((c) => c && c !== "—"))];
    const doneIds = ids.filter((c) => inRange.some((x) => x.code === c && x.done));

    let body = "", last = "";
    const showDate = F.period !== "day" || F.date;
    for (const x of list) {
      const k = dayKey(x.t);
      if (k !== last) { last = k; body += `<tr class="dayrow"><td colspan="9">${esc(fmtDay(x.t))}<span>${t("logx.rec_n", { n: list.filter((y) => dayKey(y.t) === k).length })}</span></td></tr>`; }
      const link = x.id ? `data-href="#/c/${x.id}" class="row-link"` : "";
      body += `<tr ${link}>
        <td class="tm">${showDate ? `<span class="ldt">${esc(shortDate(x.t))}</span>` : ""}<bdi>${fmtTime(x.t)}</bdi></td>
        <td><span class="kind ${x.kind}">${t(x.kind === "alert" ? "logx.k_alert" : x.kind === "escalation" ? "logx.k_escalation" : "logx.k_action")}</span></td>
        <td>${code(x.code)}<span class="sub">${esc(x.title)}</span></td>
        <td>${x.zone ? esc(zoneName(x.zone)) : "—"}</td>
        <td>${srcBadge(x.src)}</td>
        <td class="detail" dir="auto">${esc(x.detail)}</td>
        <td>${x.by ? esc(x.by) : "—"}</td>
        <td>${pill(x.sev)}</td>
        <td><span class="st ${x.st.cls}">${t(x.st.key, x.st.p || {})}</span></td></tr>`;
    }
    const monthBar = F.period === "month" && !F.date ? `<div class="monthbar" role="group" aria-label="${esc(t("logx.months"))}">${lastMonths(6).map((m) => {
      const n = allRecs.filter((x) => monthKey(x.t) === m).length;
      return `<button type="button" data-month="${m}" aria-pressed="${(F.month || monthKey(Date.now())) === m}"><b>${esc(fmtMonth(m, { short: true }))}</b><span>${t("logx.rec_n", { n })}</span></button>`;
    }).join("")}</div>` : "";
    const seg = (name, key, opts, cur) => `<div class="tool"><span>${name}</span><div class="segctl" role="group" aria-label="${esc(name)}">${opts.map(([v, n]) =>
      `<button type="button" data-${key}="${v}" aria-pressed="${cur === v}">${n}</button>`).join("")}</div></div>`;
    return `
      <section class="panel logtools">
        ${seg(t("logx.period"), "lp", [["day", t("logx.daily")], ["week", t("logx.weekly")], ["month", t("logx.monthly")]], F.date ? "" : F.period)}
        <div class="tool"><span>${t("logx.by_date")}</span><div class="datein"><input type="date" id="logDate" max="${dayKey(Date.now())}" value="${F.date}">
          ${F.date ? `<button class="btn btn-sm" type="button" id="clearDate">${t("logx.clear")}</button>` : ""}</div></div>
        ${seg(t("logx.status"), "ls", [["all", t("logx.s_all")], ["happened", t("logx.s_happened")], ["done", t("logx.s_done")], ["open", t("logx.s_open")]], F.status)}
        <span class="range-lbl">${esc(r.label)}</span>
      </section>
      ${monthBar}
      <div class="logsum">
        <div><b>${inRange.filter((x) => x.kind === "alert").length}</b><span>${t("logx.sum_alerts")}</span></div>
        <div><b>${inRange.filter((x) => x.kind === "action").length}</b><span>${t("logx.sum_actions")}</span></div>
        <div><b style="color:var(--ok)">${doneIds.length}</b><span>${t("logx.sum_done")}</span></div>
        <div><b style="color:var(--p2)">${ids.length - doneIds.length}</b><span>${t("logx.sum_open")}</span></div>
      </div>
      <section class="panel flush"><div class="ph"><h3>${t("logx.title")}</h3><span class="hint">${t("logx.hint", { n: list.length })}</span></div>
        ${list.length ? `<div class="table-wrap log-scroll"><table class="table log-table"><thead><tr><th>${t("logx.th_time")}</th><th>${t("logx.th_kind")}</th><th>${t("logx.th_case")}</th>
          <th>${t("logx.th_zone")}</th><th>${t("logx.th_src")}</th><th>${t("logx.th_detail")}</th><th>${t("logx.th_by")}</th><th>${t("logx.th_prio")}</th><th>${t("logx.th_status")}</th></tr></thead><tbody>${body}</tbody></table></div>`
          : `<div class="pb muted small">${t("logx.empty")}</div>`}</section>`;
  },
  after(root, { rerender }) {
    root.querySelectorAll("[data-lp]").forEach((b) => b.addEventListener("click", () => { F.period = b.dataset.lp; F.date = ""; rerender(true); }));
    root.querySelectorAll("[data-ls]").forEach((b) => b.addEventListener("click", () => { F.status = b.dataset.ls; rerender(true); }));
    root.querySelector("#logDate")?.addEventListener("change", (e) => { F.date = e.target.value; rerender(true); });
    root.querySelectorAll("[data-month]").forEach((b) => b.addEventListener("click", () => { F.month = b.dataset.month; rerender(true); }));
    root.querySelector("#clearDate")?.addEventListener("click", () => { F.date = ""; rerender(true); });
  },
};
