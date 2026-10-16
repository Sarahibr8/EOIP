// Dark (default) or light appearance, chosen in Settings and remembered on this browser.
const KEY = "eoip_theme";
export function getTheme() {
  try { return localStorage.getItem(KEY) === "light" ? "light" : "dark"; } catch { return "dark"; }
}
export function applyTheme(theme = getTheme()) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#f2f5f8" : "#0b1522");
}
export function setTheme(theme) {
  try { localStorage.setItem(KEY, theme); } catch { /* storage may be blocked */ }
  applyTheme(theme);
}
applyTheme();
