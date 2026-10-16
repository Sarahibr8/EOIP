// Single source of truth for every page: /api/state polled every 1.5 s.
// Pages subscribe; incident details are fetched on demand and cached per poll.
const POLL_MS = 1500;
const subs = new Set();
const S = { state: null, zones: {}, locations: {}, teams: {}, layout: null, offline: false, details: {} };

export const store = S;

export async function api(path, opts = {}) {
  const method = opts.method || "GET";
  const headers = new Headers(opts.headers || {});
  if (opts.body && !(opts.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase())) {
    headers.set("X-CSRF-Token", document.querySelector('meta[name="csrf-token"]')?.content || "");
  }
  let res;
  try {
    res = await fetch(path, { method, headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
  } catch (cause) {
    // only a failed fetch (server down / connection refused) is a network problem
    throw Object.assign(new Error("network"), { code: "network", network: true, cause });
  }
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : {}; } catch { json = null; }
  if (res.status === 401) {
    location.assign("/login");
    throw Object.assign(new Error("unauthorized"), { code: "unauthorized", status: 401 });
  }
  if (json === null) {
    throw Object.assign(new Error(`unexpected response (${res.status})`), { code: "unexpected_response", status: res.status });
  }
  if (!res.ok) throw Object.assign(new Error(json.error || res.status), { code: json.error || String(res.status), status: res.status, data: json });
  return json;
}

export function subscribe(fn) { subs.add(fn); return () => subs.delete(fn); }
// A bug in one subscriber must not stop the others, and must not be mistaken for a lost connection.
function emit() {
  subs.forEach((fn) => {
    try { fn(S); } catch (e) { console.error("[EOIP] UI update failed", e); onError(e); }
  });
}

// Three levels on screen: critical (P1), medium (P2), normal (P3). P4 is shown as P3.
export const lvl = (p) => (p === "P4" ? "P3" : p);
function levels(st) {
  (st.incidents || []).forEach((i) => { i.priority = lvl(i.priority); });
  (st.decisions || []).forEach((d) => { d.priority_at_decision = lvl(d.priority_at_decision); });
  return st;
}

function ingestState(st) {
  S.state = levels(st);
  S.zones = Object.fromEntries(st.zones.map((z) => [z.id, z]));
  S.locations = Object.fromEntries((st.locations || []).map((l) => [l.id, l]));
  S.teams = Object.fromEntries((st.teams || []).map((t) => [t.id, t]));
}

export async function refresh() {
  ingestState(await api("/api/state"));
  S.details = {};
  emit();
}

export async function detail(id, force = false) {
  if (!force && S.details[id]) return S.details[id];
  try { const d = await api(`/api/incidents/${id}`); if (d) { d.priority = lvl(d.priority); (d.decisions || []).forEach((x) => { x.priority_at_decision = lvl(x.priority_at_decision); }); } S.details[id] = d; }
  catch (e) { if (e.code === "not_found") S.details[id] = null; else throw e; }
  return S.details[id];
}

let onOffline = () => {}, onOnline = () => {}, onError = () => {};
export function onConnection(off, on, err) { onOffline = off; onOnline = on; if (err) onError = err; }

async function loop() {
  try {
    if (!S.layout) S.layout = await api("/api/layout").catch(() => null);   // retry if the first load failed
    if (S.state?.demo?.running) await api("/api/demo/tick", { method: "POST" });
    ingestState(await api("/api/state"));
    S.details = {};
    if (S.offline) { S.offline = false; onOnline(); }
    emit();
  } catch (e) {
    if (e.network) { if (!S.offline) { S.offline = true; onOffline(); } }
    else if (e.code !== "unauthorized") { console.error("[EOIP] state refresh failed", e); onError(e); }
  } finally {
    setTimeout(loop, POLL_MS);
  }
}
export async function start() {
  try { S.layout = await api("/api/layout"); } catch { S.layout = null; }
  loop();
}
