// Minimal i18n: JSON dictionaries, {param} interpolation, RTL/LTR switching,
// Riyadh-time formatting. Every visible string goes through t().
const STORE_KEY = "eoip.lang";
const dicts = {};
let lang = "ar";
const listeners = [];

function readSaved() {
  try { return localStorage.getItem(STORE_KEY); } catch { return null; }
}
function save(l) {
  try { localStorage.setItem(STORE_KEY, l); } catch { /* storage unavailable: keep in memory */ }
}

export async function initI18n() {
  const fromUrl = new URLSearchParams(location.search).get("lang");
  lang = ["ar", "en"].includes(fromUrl) ? fromUrl : (readSaved() || "ar");
  const [ar, en] = await Promise.all(
    ["ar", "en"].map((l) => fetch(`/static/i18n/${l}.json`).then((r) => r.json())));
  dicts.ar = ar; dicts.en = en;
  applyDocument();
  return lang;
}

export const getLang = () => lang;

export function setLang(l) {
  lang = l; save(l); applyDocument();
  listeners.forEach((fn) => fn(l));
}
export const onLangChange = (fn) => listeners.push(fn);

function applyDocument() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
}

function lookup(d, key) {
  return key.split(".").reduce((o, k) => (o && o[k] !== undefined ? o[k] : undefined), d);
}

export function t(key, params = {}) {
  let s = lookup(dicts[lang], key);
  if (s === undefined) s = lookup(dicts.en, key);
  if (s === undefined) return key;
  return String(s).replace(/\{(\w+)\}/g, (_, k) => (params[k] !== undefined ? params[k] : `{${k}}`));
}

export function has(key) { return lookup(dicts[lang], key) !== undefined; }

const locale = () => (lang === "ar" ? "ar-SA-u-nu-latn-ca-gregory" : "en-GB");

export function fmtTime(iso, withSeconds = true) {
  if (!iso) return "";
  return new Intl.DateTimeFormat(locale(), {
    hour: "2-digit", minute: "2-digit", second: withSeconds ? "2-digit" : undefined,
    hour12: false, timeZone: "Asia/Riyadh",
  }).format(new Date(iso));
}

export function fmtNum(n) {
  return new Intl.NumberFormat(locale()).format(n);
}

export function fmtAge(iso) {
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 10) return t("time.now");
  if (s < 60) return t("time.sec", { n: s });
  if (s < 3600) return t("time.min", { n: Math.round(s / 60) });
  return t("time.hr", { n: Math.round(s / 3600) });
}
