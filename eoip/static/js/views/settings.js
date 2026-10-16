// Settings (UX design): account with the current shift, language, report sources and response parties.
import { t, getLang, setLang } from "../i18n.js";
import { icon } from "../icons.js";
import { esc, toast, errorText, escMatrix, iso } from "../ui.js";
import { getTheme, setTheme } from "../theme.js";
import { api, refresh, store } from "../store.js";

/** Shift from the Riyadh time of day: morning 08–16, evening 16–00, night 00–08. */
export function currentShift() {
  const h = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hour12: false, timeZone: "Asia/Riyadh" }).format(new Date())) % 24;
  if (h >= 8 && h < 16) return { key: "morning", hours: "08:00 – 16:00" };
  if (h >= 16) return { key: "evening", hours: "16:00 – 00:00" };
  return { key: "night", hours: "00:00 – 08:00" };
}

let toolsOpen = false;
function demoLine() {
  const d = store.state?.demo;
  if (!d) return "";
  return d.running ? t("demo.live_hint", { time: d.started_iso ? new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Riyadh" }).format(new Date(d.started_iso)) : "" })
    : d.cursor ? t("demo.progress", { done: d.cursor, total: d.total }) : t("demo.not_started");
}

/** Escalation matrix: who is notified when a waiting case passes its response time, by priority. */
function escPanel() {
  const m = escMatrix(), prios = ["P1", "P2", "P3"];
  const rows = m.levels.map((code, k) => `<tr><td><b>${iso(code)}</b></td><td>${t(`escalation.${code}`)}</td>
    ${prios.map((p) => `<td>${t("esc.after_min", { n: Math.round(((k + 1) * m.step_s[p]) / 60) })}</td>`).join("")}</tr>`).join("");
  return `<section class="panel flush"><div class="ph"><h3>${icon("incident")}${t("esc.set_title")}</h3><span class="hint">${t("esc.set_hint")}</span></div><div class="pb">
    <div class="table-wrap"><table class="esc-table"><thead><tr><th>${t("esc.th_level")}</th><th>${t("esc.th_role")}</th>
      ${prios.map((p) => `<th title="${esc(t(`priority.${p}`))}">${p}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
    <p class="calc-note">${t("esc.set_note")}</p></div></section>`;
}

const items = (key) => t(key).split("|").map((x) => `<li>${esc(x)}</li>`).join("");

export const settingsView = {
  nav: "settings",
  render() {
    const name = document.body.dataset.employeeName || "";
    const number = document.body.dataset.employeeNumber || "";
    const sh = currentShift();
    return `
      <div class="set2">
        <section class="panel flush"><div class="ph"><h3>${icon("person")}${t("settings.account")}</h3></div><div class="pb">
          <div class="profile"><div class="avatar">${esc(name.trim().charAt(0) || "؟")}</div><div><b>${esc(name)}</b><span>${t("settings.role")}</span></div></div>
          <dl class="kv">
            <dt>${t("app.employee_number")}</dt><dd><bdi>${esc(number)}</bdi></dd>
            <dt>${t("settings.shift")}</dt><dd>${t(`settings.shift_${sh.key}`)} · <bdi>${sh.hours}</bdi></dd>
            <dt>${t("settings.site")}</dt><dd>${t("settings.site_v")}</dd></dl>
          <button class="btn btn-sm set-logout" type="submit" form="logoutForm">${icon("logout")}${t("login.logout")}</button></div></section>
        <section class="panel flush"><div class="ph"><h3>${icon("globe")}${t("settings.language")}</h3></div><div class="pb">
          <div class="langsel"><button type="button" data-setlang="ar" aria-pressed="${getLang() === "ar"}">العربية</button><button type="button" data-setlang="en" aria-pressed="${getLang() === "en"}">English</button></div>
          <p class="calc-note">${t("settings.language_d")}</p></div></section>
        <section class="panel flush"><div class="ph"><h3>${icon("layers")}${t("settings.theme")}</h3></div><div class="pb">
          <div class="langsel theme-pick"><button type="button" data-settheme="dark" aria-pressed="${getTheme() === "dark"}">${t("settings.theme_dark")}</button><button type="button" data-settheme="light" aria-pressed="${getTheme() === "light"}">${t("settings.theme_light")}</button></div>
          <p class="calc-note">${t("settings.theme_d")}</p></div></section>
        ${escPanel()}
        <section class="panel flush"><div class="ph"><h3>${icon("team")}${t("settings.parties")}</h3></div><div class="pb">
          <div class="sources">${t("settings.parties_l").split("|").map((x) => `<span class="tag">${esc(x)}</span>`).join("")}</div>
          <p class="calc-note">${t("settings.parties_d")}</p></div></section>
        <section class="panel flush set-tools"><div class="ph"><h3>${icon("tools")}${t("demo.tools_title")}</h3><span class="hint">${t("demo.tools_set_hint")}</span></div><div class="pb">
          <details class="tools-box" ${toolsOpen ? "open" : ""}><summary>${t("demo.tools_show")}</summary>
            <p class="calc-note" id="setDemoStatus">${esc(demoLine())}</p>
            <div class="grp">${t("demo.grp_event")}</div>
            <div class="tools-row"><button class="btn" type="button" data-tool="new">${icon("reset")}<span>${t("demo.new_event")}</span></button>
              <button class="btn btn-quiet" type="button" data-tool="skip">${icon("skip")}<span>${t("demo.skip")}</span></button></div>
            <div class="grp">${t("demo.grp_fallback")}</div>
            <div class="tools-row"><button class="btn" type="button" data-tool="fire">${icon("radio")}<span>${t("demo.fire_report")}</span></button>
              <button class="btn" type="button" data-tool="med">${icon("radio")}<span>${t("demo.med_report")}</span></button>
              <button class="btn" type="button" data-tool="cv" title="${esc(t("demo.cv_replay_hint"))}">${icon("camera")}<span>${t("demo.cv_replay")}</span></button></div>
            <p class="calc-note">${t("demo.tools_note")}</p>
          </details></div></section>
        <section class="panel flush set-src"><div class="ph"><h3>${icon("radio")}${t("settings.sources")}</h3><span class="hint">${t("settings.sources_d")}</span></div><div class="pb">
          <div class="src-card"><div class="src-ic">${icon("radio")}</div><div><h4>${t("settings.src_radio")} <span class="st open">${t("settings.connected")}</span></h4>
            <p>${t("settings.src_radio_d")}</p><ul>${items("settings.src_radio_l")}</ul></div></div>
          <div class="src-card"><div class="src-ic cv">${icon("camera")}</div><div><h4>${t("settings.src_cv")} <span class="st open">${t("settings.connected")}</span></h4>
            <p>${t("settings.src_cv_d")}</p><ul>${items("settings.src_cv_l")}</ul></div></div>
        </div></section>
      </div>`;
  },
  after(root) {
    root.querySelectorAll("[data-setlang]").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.setlang)));
    root.querySelectorAll("[data-settheme]").forEach((b) => b.addEventListener("click", () => {
      setTheme(b.dataset.settheme);
      root.querySelectorAll("[data-settheme]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    }));
    root.querySelector(".tools-box")?.addEventListener("toggle", (e) => { toolsOpen = e.target.open; });
    root.querySelectorAll("[data-tool]").forEach((b) => b.addEventListener("click", async () => {
      const csrf = { method: "POST" };
      const calls = {
        new: async () => { await api("/api/demo/reset", csrf); await api("/api/demo/autostart", csrf); },
        skip: () => api("/api/demo/skip", csrf),
        fire: () => api("/api/voice/report", { method: "POST", body: { text: t("demo.fire_sample_text"), input_mode: "text" } }),
        med: () => api("/api/voice/report", { method: "POST", body: { text: t("demo.field_sample_text"), input_mode: "text" } }),
        cv: () => api("/api/demo/cv-replay", csrf),
      };
      b.disabled = true;
      try { await calls[b.dataset.tool](); toast(t(b.dataset.tool === "new" ? "demo.confirm_new" : "demo.tool_done")); await refresh(); }
      catch (e) { toast(errorText(e), "error"); }
      finally { b.disabled = false; }
    }));
  },
};
