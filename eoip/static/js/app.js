// EOIP operations app: hash router + shell. All pages share one store (/api/state).
import { initI18n, t, getLang, setLang, onLangChange, fmtTime, fmtNum } from "./i18n.js";
import { icon, brandMark } from "./icons.js";
import { store, api, subscribe, start, refresh, onConnection } from "./store.js";
import { toast, errorText, placeText, isOpen, incTitle, loading, esc } from "./ui.js";
import { commandView, tickCountdowns } from "./views/command.js";
import { mapView } from "./views/map.js";
import { incidentsView } from "./views/incidents.js";
import { incidentView } from "./views/incident.js";
import { decideView } from "./views/decide.js";
import { logView } from "./views/log.js";
import { settingsView } from "./views/settings.js";
import { loadWeather, weatherNow } from "./weather.js";
import { currentShift } from "./views/settings.js";
import "./theme.js";

const $ = (id) => document.getElementById(id);
const ROUTES = { "": commandView, c: commandView, map: mapView, incidents: incidentsView, incident: incidentView, decide: decideView, log: logView, settings: settingsView };
const NAV_ICON = { overview: "home", c: "home", map: "map", incidents: "bell", incident: "bell", decide: "decide", log: "clock", settings: "gear", field: "phone" };

let lastBar = "", lastHtml = "", lastRoute = "", rendering = false, pending = false, pointerDown = false;
const knownP1 = new Set();
let seeded = false;

function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const name = parts[0] || "";
  return { name, view: ROUTES[name] || commandView, params: parts.slice(1) };
}
const go = (hash) => { if (location.hash === hash) render(true); else location.hash = hash; };

async function render(force = false) {
  if (!store.state) { $("page").innerHTML = loading(); return; }
  const page = $("page");
  const ae = document.activeElement;
  const typing = ae && page.contains(ae) && (ae.tagName === "TEXTAREA" || (ae.tagName === "INPUT" && ae.type !== "range" && ae.type !== "checkbox"));
  if (!force && (typing || pointerDown)) return;
  if (rendering) { pending = true; return; }
  rendering = true;
  try {
    const r = route();
    page.dataset.route = r.name || "overview";
    const key = location.hash + getLang();
    const ctx = { state: store.state, params: r.params, go, rerender: (f) => render(f) };
    const html = await r.view.render(ctx);
    if (force || html !== lastHtml || key !== lastRoute) {
      const sameRoute = key === lastRoute;
      const y = window.scrollY;
      page.innerHTML = html;
      lastHtml = html;
      r.view.after?.(page, ctx);
      if (sameRoute) window.scrollTo(0, y); else { window.scrollTo(0, 0); page.focus({ preventScroll: true }); }
      lastRoute = key;
    }
    renderNav(r.view.nav);
    renderBar();
  } catch (e) {
    console.error("[EOIP] page render failed", e);
    page.innerHTML = `<div class="empty"><b>${esc(errorText(e))}</b></div>`;
  } finally {
    rendering = false;
    if (pending) { pending = false; render(); }
  }
}

function renderNav(active) {
  const s = store.state;
  const openN = s ? s.incidents.filter((i) => i.status === "open").length : 0;   // waiting for a decision
  const crit = s ? s.incidents.filter((i) => i.status === "open" && i.priority === "P1").length : 0;
  const waiting = s ? s.counters.awaiting_decision : 0;
  document.querySelectorAll("[data-nav]").forEach((a) => {
    const k = a.dataset.nav;
    const count = k === "incidents" && openN ? `<span class="count ${crit ? "hot" : ""}">${openN}</span>`
      : k === "decide" && waiting ? `<span class="count hot">${waiting}</span>` : "<span></span>";
    a.innerHTML = `${icon(NAV_ICON[k])}<span class="lbl">${t(`nav.${k}`)}</span>${count}`;
    if (k === active) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}

/* Page title shown in the top bar (the UX design has no breadcrumbs or page headings). */
const PAGE_KEY = { "": "home", c: "home", map: "map", incidents: "alerts", incident: "alerts", decide: "decide", log: "log", settings: "settings" };
const pageKey = () => PAGE_KEY[route().name] || "home";

const TZ = "Asia/Riyadh";
function fmtDateParts(d) {
  const ar = getLang() === "ar";
  const day = new Intl.DateTimeFormat(ar ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { weekday: "long", timeZone: TZ }).format(d);
  const hijri = new Intl.DateTimeFormat(ar ? "ar-SA-u-ca-islamic-umalqura-nu-latn" : "en-GB-u-ca-islamic-umalqura", { day: "numeric", month: "long", year: "numeric", timeZone: TZ }).format(d);
  const greg = new Intl.DateTimeFormat(ar ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: TZ }).format(d);
  return { day, line: `${hijri.replace(/\s*هـ$/, "")}${ar ? " هـ" : ""} · ${greg}` };
}
const clockText = () => new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: TZ }).format(new Date());

function renderBar() {
  const s = store.state; if (!s) return;
  const d = s.demo;
  const operatorName = document.body.dataset.employeeName || "";
  const employeeNumber = document.body.dataset.employeeNumber || "";
  const sh = currentShift();
  const k = pageKey();
  const dt = fmtDateParts(new Date());
  const menuOpen = !!document.querySelector(".tb-user[open]");
  const barHtml = `
    <div class="tb-title"><div class="tb-h"><h1>${t(`pages.${k}`)}</h1><span class="tag mock" title="${esc(t("app.synthetic_hint"))}">${icon("info")}${t("app.synthetic")}</span></div>
      <p>${t(`pages.${k}_s`)}</p></div>
    <div class="tb-end">
      <div class="tb-info">${weatherChip()}
        <span class="tb-date"><b>${esc(dt.day)}</b><small>${esc(dt.line)}</small></span>
        <span class="tb-clock" id="clock" dir="ltr">${clockText()}</span></div>
      <button class="tb-lang" type="button" id="tbLang" aria-label="${esc(t("app.lang_switch"))}"><span>${getLang() === "ar" ? "EN" : "ع"}</span>${icon("globe")}</button>
      <details class="tb-user">
        <summary aria-label="${esc(operatorName)}"><span class="tb-who"><b>${esc(operatorName)}</b><small>${t("settings.role")}</small></span>${icon("chevronDown", "tb-chev")}</summary>
        <div class="tb-menu"><div class="tb-menu-who"><b>${esc(operatorName)}</b><small>${t("settings.role")}</small></div>
          <dl class="tb-menu-kv"><dt>${t("app.employee_number")}</dt><dd><bdi>${esc(employeeNumber)}</bdi></dd>
            <dt>${t("settings.shift")}</dt><dd>${t(`settings.shift_${sh.key}`)} · <bdi>${sh.hours}</bdi></dd></dl>
          <button type="submit" form="logoutForm" class="tb-menu-btn">${icon("logout")}<span>${t("login.logout")}</span></button></div>
      </details>
    </div>`;
  if (barHtml.replace(/<span class="tb-clock"[^>]*>[^<]*<\/span>/, "") !== lastBar) {   // rebuild only when something changed (keeps the user menu open)
    $("eventbar").innerHTML = barHtml; lastBar = barHtml.replace(/<span class="tb-clock"[^>]*>[^<]*<\/span>/, "");
    if (menuOpen) document.querySelector(".tb-user")?.setAttribute("open", "");
  }
  $("demoStatus").textContent = d.running ? t("demo.live_hint", { time: fmtTime(store.state.demo.started_iso || new Date().toISOString(), false) })
    : d.cursor ? t("demo.progress", { done: d.cursor, total: d.total }) : t("demo.not_started");
}

function weatherChip() {
  const w = weatherNow();
  if (!w) return "";
  return `<span class="tb-wx" title="${esc(t("weather.detail", w))}">${icon(w.icon)}<span class="temp">${w.temp}°</span>
    <span class="wd"><b>${t(`weather.${w.key}`)} · ${t("weather.city")}</b></span></span>`;
}

/* The event starts by itself the first time a dashboard opens after a reset (never restarts). */
let autostartTried = false;
async function autostart() {
  const d = store.state?.demo;
  if (!d || autostartTried || d.running || d.cursor > 0) return;
  autostartTried = true;
  try { await api("/api/demo/autostart", { method: "POST" }); await refresh(); }
  catch (e) { autostartTried = false; console.error("[EOIP] autostart failed", e); }
}

/* A case that ran past its response time leaves the queue: tell the officer where it went. */
const knownEsc = new Set(); let escSeeded = false;
function watchEscalated() {
  const list = store.state.incidents.filter((i) => i.status === "escalated");
  const key = (i) => `${i.id}@${i.opened_at}`;
  if (!escSeeded) { list.forEach((i) => knownEsc.add(key(i))); escSeeded = true; return; }
  for (const i of list) {
    if (knownEsc.has(key(i))) continue;
    knownEsc.add(key(i));
    toast(t("esc.toast", { title: incTitle(i), place: placeText(i.zone_id, i.location_id), code: i.escalation.code,
      role: t(`escalation.${i.escalation.code}`) }), "error");
  }
}

function watchCritical() {
  const s = store.state;
  const p1 = s.incidents.filter((i) => isOpen(i) && i.priority === "P1");
  // key = id + opening time: a reset reuses incident numbers, a new incident must still alert
  const key = (i) => `${i.id}@${i.opened_at}`;
  if (!seeded) { p1.forEach((i) => knownP1.add(key(i))); seeded = true; return; }
  for (const i of p1) {
    if (knownP1.has(key(i))) continue;
    knownP1.add(key(i));
    if (i.status !== "open") continue;          // already being handled: no alarm
    const el = toast(t("app.critical_toast", { title: incTitle(i), place: placeText(i.zone_id, i.location_id) }), "critical", true);
    el.addEventListener("click", () => { el.remove(); criticalToasts.delete(i.id); go(`#/c/${i.id}`); });
    criticalToasts.set(i.id, el);
  }
  // A critical alert stays until the operator acts: it closes when a decision is taken, the incident
  // drops below P1 or closes, or the operator opens that incident.
  const r = route();
  for (const [id, el] of criticalToasts) {
    const inc = s.incidents.find((x) => x.id === id);
    const viewing = (["decide", "incident", "c"].includes(r.name) && Number(r.params[0]) === id)
      || (r.view === commandView && !r.params[0]);   // the command screen already shows the alert bar
    if (!inc || inc.status !== "open" || inc.priority !== "P1" || viewing) { el.remove(); criticalToasts.delete(id); }
  }
}
const criticalToasts = new Map();

function staticChrome() {
  $("markIcon").innerHTML = brandMark();
  if (!store.state) $("page").innerHTML = loading();
  $("railNote").innerHTML = `<b>${t("app.proto")}</b>${t("app.proto_d")}`;
  $("demoBtn").innerHTML = `${icon("tools")}<span>${t("nav.demo")}</span>`;
  $("demoBtn").setAttribute("aria-label", t("nav.demo"));
  $("demoTitle").innerHTML = `<span>${t("demo.tools_title")}</span><small>${t("demo.tools_hint")}</small>`;
  $("demoGrpEvent").textContent = t("demo.grp_event");
  $("demoGrpFallback").textContent = t("demo.grp_fallback");
  $("demoReset").innerHTML = `${icon("reset")}<span>${t("demo.new_event")}</span>`;
  $("demoSkip").innerHTML = `${icon("skip")}<span>${t("demo.skip")}</span>`;
  $("demoFire").innerHTML = `${icon("radio")}<span>${t("demo.fire_report")}</span>`;
  $("demoField").innerHTML = `${icon("radio")}<span>${t("demo.med_report")}</span>`;
  $("demoCv").innerHTML = `${icon("camera")}<span>${t("demo.cv_replay")}</span>`;
  $("demoCv").title = t("demo.cv_replay_hint");
}

/* Presenter tools stay hidden during the demo: Shift + D shows or hides them (remembered on this browser). */
function setTools(on) {
  document.body.classList.toggle("tools-on", on);
  try { localStorage.setItem("eoip_tools", on ? "1" : "0"); } catch { /* storage may be blocked */ }
}

function bind() {
  window.addEventListener("hashchange", () => render(true));
  document.addEventListener("pointerdown", () => { pointerDown = true; });
  document.addEventListener("pointerup", () => { pointerDown = false; });
  $("page").addEventListener("click", (e) => {
    const g = e.target.closest("[data-go]");
    if (g) { e.preventDefault(); go(g.dataset.go); return; }
    const row = e.target.closest("[data-href]");
    if (row && !e.target.closest("a,button,select,input,textarea")) go(row.dataset.href);
  });
  const switchLanguage = () => setLang(getLang() === "ar" ? "en" : "ar");
  $("eventbar").addEventListener("click", (e) => { if (e.target.closest("#tbLang")) switchLanguage(); });
  onLangChange(() => { lastBar = ""; staticChrome(); renderBar(); render(true); });
  document.addEventListener("click", (e) => { const m = document.querySelector(".tb-user[open]"); if (m && !m.contains(e.target)) m.removeAttribute("open"); });

  const pop = $("demoPop");
  const close = () => { pop.classList.remove("open"); $("demoBtn").setAttribute("aria-expanded", "false"); };
  $("demoBtn").addEventListener("click", (e) => {
    e.stopPropagation();
    const open = !pop.classList.contains("open");
    pop.classList.toggle("open", open); $("demoBtn").setAttribute("aria-expanded", open);
  });
  document.addEventListener("click", (e) => { if (!e.target.closest("#demoPop") && !e.target.closest("#demoBtn")) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  const call = async (path, body, after) => {
    close();
    try { await api(path, { method: "POST", body }); if (after) await after(); await refresh(); }
    catch (ex) { toast(errorText(ex), "error"); }
  };
  const resetView = () => { knownP1.clear(); seeded = false; };
  $("demoReset").addEventListener("click", () => call("/api/demo/reset", null, async () => {
    resetView(); autostartTried = true; toast(t("demo.confirm_new"));
    await api("/api/demo/autostart", { method: "POST" }); go("#/");
  }));
  $("demoSkip").addEventListener("click", () => call("/api/demo/skip"));
  $("demoCv").addEventListener("click", () => call("/api/demo/cv-replay"));
  // fallback field reports = the same text a supervisor would say; they go through the same extraction
  $("demoFire").addEventListener("click", () => call("/api/voice/report", { text: t("demo.fire_sample_text"), input_mode: "text" }));
  $("demoField").addEventListener("click", () => call("/api/voice/report", { text: t("demo.field_sample_text"), input_mode: "text" }));
  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
    if (!typing && e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey && e.code === "KeyD") {
      e.preventDefault(); setTools(!document.body.classList.contains("tools-on"));
      if (!document.body.classList.contains("tools-on")) close();
    }
  });
}

(async function main() {
  await initI18n();
  staticChrome();
  bind();
  let offlineToast = null;
  let lastError = "";
  onConnection(() => { offlineToast = toast(t("errors.network"), "error", true); },
    () => { offlineToast?.remove(); toast(t("app.reconnected")); },
    (e) => { const msg = errorText(e); if (msg !== lastError) { lastError = msg; toast(msg, "error"); setTimeout(() => { lastError = ""; }, 15000); } });
  try { if (localStorage.getItem("eoip_tools") === "1") document.body.classList.add("tools-on"); } catch { /* ignore */ }
  subscribe(() => { renderBar(); watchCritical(); watchEscalated(); render(); autostart(); loadWeather(() => { lastBar = ""; renderBar(); }); });
  setInterval(() => {
    const c = $("clock"); if (c) c.textContent = clockText();
    tickCountdowns($("page"));
  }, 1000);
  start();
})();
