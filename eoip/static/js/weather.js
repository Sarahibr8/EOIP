// Live Riyadh weather for the top bar (Open-Meteo, no key). Needs internet in the browser;
// without it the chip simply stays hidden — nothing on the screen depends on it.
const URL = "https://api.open-meteo.com/v1/forecast?latitude=24.71&longitude=46.68"
  + "&current=temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code,is_day&timezone=Asia%2FRiyadh";
const EVERY_MS = 15 * 60 * 1000;

let current = null, loadedAt = 0, inflight = null;

/** WMO weather code -> label key + icon */
function kind(code, day) {
  if (code === 0) return { key: day ? "clear_day" : "clear_night", icon: day ? "sun" : "moon" };
  if (code <= 3) return { key: "partly", icon: day ? "sun" : "moon" };
  if (code === 45 || code === 48) return { key: "fog", icon: "cloud" };
  if (code >= 51 && code <= 67) return { key: "rain", icon: "drop" };
  if (code >= 80 && code <= 82) return { key: "rain", icon: "drop" };
  if (code >= 95) return { key: "storm", icon: "cloud" };
  return { key: "cloudy", icon: "cloud" };
}

export async function loadWeather(onChange) {
  if (inflight || (current && Date.now() - loadedAt < EVERY_MS)) return current;
  inflight = (async () => {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 6000);
      const res = await fetch(URL, { signal: ctrl.signal });
      clearTimeout(timer);
      if (!res.ok) throw new Error(String(res.status));
      const c = (await res.json()).current;
      current = { temp: Math.round(c.temperature_2m), feels: Math.round(c.apparent_temperature), hum: Math.round(c.relative_humidity_2m),
        wind: Math.round(c.wind_speed_10m), ...kind(c.weather_code, c.is_day === 1) };
      loadedAt = Date.now();
      onChange?.(current);
    } catch { /* offline or blocked: keep the chip hidden */ loadedAt = Date.now() - EVERY_MS + 60000; }
    finally { inflight = null; }
  })();
  return current;
}

export const weatherNow = () => current;
