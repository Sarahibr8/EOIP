import { initI18n, t, getLang, setLang } from "./i18n.js";
import { icon, brandMark } from "./icons.js";
import "./theme.js";

const $ = (id) => document.getElementById(id);

function normalizeDigits(input) {
  input.value = [...input.value].map((char) => {
    const point = char.codePointAt(0);
    if (point >= 0x0660 && point <= 0x0669) return String(point - 0x0660);
    if (point >= 0x06f0 && point <= 0x06f9) return String(point - 0x06f0);
    return /[0-9]/.test(char) ? char : "";
  }).join("").slice(0, 24);
}

await initI18n();
document.querySelectorAll(".login-mark").forEach((el) => { el.innerHTML = brandMark(); });
document.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = icon(el.dataset.icon); });
const toggle = $("passwordToggle");
function labelPasswordToggle() {
  toggle.innerHTML = icon($("password").type === "password" ? "eye" : "eyeOff");
  toggle.title = t($("password").type === "password" ? "login.show_password" : "login.hide_password");
  toggle.setAttribute("aria-label", t($("password").type === "password" ? "login.show_password" : "login.hide_password"));
}
labelPasswordToggle();
toggle.addEventListener("click", () => {
  const field = $("password");
  field.type = field.type === "password" ? "text" : "password";
  labelPasswordToggle();
  field.focus();
});
$("employeeNumber").addEventListener("input", (event) => normalizeDigits(event.currentTarget));
$("loginLangBtn").innerHTML = `${icon("globe")}<span>${t("app.lang_switch")}</span>`;
$("loginLangBtn").addEventListener("click", () => {
  const lang = getLang() === "ar" ? "en" : "ar";
  setLang(lang);
  const url = new URL(location.href);
  url.searchParams.set("lang", lang);
  location.assign(url);
});
