// Field reporting on the phone: (1) voice/text report = the supervisor's radio,
// (2) camera = live camera frames from the phone/laptop, analysed by the EOIP server.
// Speech-to-text = the browser's Web Speech API (where available). Extraction of event /
// zone / location is rule-based on the server (data/lexicon.json), never guessed here.
import { initI18n, t, getLang, setLang, onLangChange, fmtTime } from "./i18n.js";
import { icon, brandMark } from "./icons.js";

const $ = (id) => document.getElementById(id);
const iso = (x) => `⁨${x}⁩`;
const REPORT_CATEGORIES = ["smoke_report", "medical_report", "crowd_report", "staff_shortage_report"];
const EVENT_CAT = { fire: "smoke_report", medical: "medical_report", crowding: "crowd_report", staff_shortage: "staff_shortage_report" };
const SAMPLES = [
  "فيه حريق في زون A عند منطقة المطاعم",
  "شخص مغمى عليه في زون B عند الممر الرئيسي، نحتاج إسعاف بسرعة",
  "ازدحام شديد في زون C عند البوابة الرئيسية",
  "نحتاج منظمين إضافيين في زون A عند منطقة الفعاليات",
  "Someone is unconscious in Zone B at the Main Walkway",
];

let zones = [], locations = [];
let extraction = null, recordedAt = null, sttConfidence = null;
let inputMode = "text", recognizing = false, rec = null;
let micNote = null;

async function api(path, body, raw = false) {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const opts = body === undefined ? {} : raw ? { method: "POST", body }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  if (opts.method) opts.headers = { ...(opts.headers || {}), "X-CSRF-Token": csrf };
  const res = await fetch(path, opts);
  const json = await res.json().catch(() => ({}));
  if (res.status === 401) location.assign("/login");
  if (!res.ok) throw Object.assign(new Error(json.error || res.status), { code: json.error, data: json });
  return json;
}
const nm = (x) => (getLang() === "ar" ? x.name_ar : x.name_en);
const errText = (e) => (e instanceof TypeError ? t("errors.network") : (t(`errors.${e.code}`) !== `errors.${e.code}` ? t(`errors.${e.code}`) : t("errors.generic", { code: e.code })));

function setMicNote(key, params = {}) { micNote = key ? { key, params } : null; $("micNote").textContent = key ? t(key, params) : ""; }
function setResult(msg, cls) { $("result").textContent = msg; $("result").className = `f-result ${cls || ""}`; }

/* ---------- selects ---------- */
function zoneOptions(sel, cur, unknownKey) {
  sel.innerHTML = `<option value="">${t(unknownKey)}</option>` + zones.map((z) => `<option value="${z.id}">${nm(z)}</option>`).join("");
  sel.value = cur || "";
}
function locOptions(sel, zone, cur, withOther = true, placeholderKey = "field.location_unknown") {
  const list = locations.filter((l) => !zone || l.zone_id === zone);
  sel.innerHTML = `<option value="">${t(placeholderKey)}</option>` +
    list.map((l) => `<option value="${l.id}">${nm(l)}${zone ? "" : ` (${nm(zones.find((z) => z.id === l.zone_id) || {})})`}</option>`).join("") +
    (withOther ? `<option value="other">${t("field.location_other_opt")}</option>` : "");
  sel.value = list.some((l) => l.id === cur) || cur === "other" ? cur : "";
}
function fillReport(values) {
  const cat = values ? values.cat : $("catSel").value;
  const zone = values ? values.zone : $("zoneSel").value;
  const loc = values ? values.loc : $("locSel").value;
  $("catSel").innerHTML = `<option value="">${t("field.choose")}</option>` +
    REPORT_CATEGORIES.map((c) => `<option value="${c}">${t(`category.${c}`)}</option>`).join("");
  $("catSel").value = cat || "";
  zoneOptions($("zoneSel"), zone, "field.zone_unknown");
  locOptions($("locSel"), zone, loc);
  toggleOther();
}
function toggleOther() {
  const other = $("locSel").value === "other";
  $("locOther").hidden = !other; $("locOtherLbl").hidden = !other;
}

/* ---------- static text ---------- */
function ensureCameraScaffold() {
  const panel = $("panelCam");
  if (!$('camGuideTitle')) {
    const intro = panel.querySelector('[data-i18n="field.cam_intro"]');
    const guide = document.createElement("section");
    guide.className = "cam-guide";
    guide.setAttribute("aria-labelledby", "camGuideTitle");
    guide.innerHTML = `<div class="cam-guide-copy"><span class="cam-eyebrow" id="camKicker"></span>
      <h1 id="camGuideTitle"></h1><p id="camIntro"></p></div>
      <ol class="cam-steps" id="camSteps"><li><span class="cam-step-num">01</span><span id="camStepZone"></span></li>
      <li><span class="cam-step-num">02</span><span id="camStepEmpty"></span></li>
      <li><span class="cam-step-num">03</span><span id="camStepClip"></span></li></ol>`;
    if (intro) intro.replaceWith(guide); else panel.prepend(guide);
  }
  const frame = panel.querySelector(".cam-frame");
  if (frame) {
    frame.id = "camFrame";
    if (!$('camPlaceholder')) {
      const placeholder = document.createElement("div");
      placeholder.className = "cam-placeholder"; placeholder.id = "camPlaceholder";
      placeholder.setAttribute("aria-live", "polite");
      frame.insertBefore(placeholder, $("camBadge") || null);
    }
  }
  if (!$('camDisclosureTitle')) {
    const oldNote = panel.querySelector('[data-i18n="field.cam_honest"]');
    const note = document.createElement("aside");
    note.className = "cam-disclosure";
    note.innerHTML = `<strong id="camDisclosureTitle"></strong><p id="camHonest"></p>`;
    if (oldNote) oldNote.replaceWith(note); else panel.append(note);
  }
}

function renderStatic() {
  $("brandMark").innerHTML = brandMark();
  $("langBtn").innerHTML = `${icon("globe")}<span>${t("app.lang_switch")}</span>`;
  $("tabVoice").innerHTML = `${icon("mic")}<span>${t("field.tab_voice")}</span>`;
  $("tabCam").innerHTML = `${icon("camera")}<span>${t("field.tab_camera")}</span>`;
  $("micIcon").innerHTML = icon("mic");
  $("micLabel").textContent = recognizing ? t("field.mic_listening") : t("field.mic_tap");
  $("sendBtn").innerHTML = `${icon("send")}<span>${t("field.send")}</span>`;
  $("samples").innerHTML = SAMPLES.map((s, i) => `<button class="btn" type="button" data-i="${i}" dir="auto">${s}</button>`).join("");
  $("locOther").placeholder = t("field.location_other_ph");
  fillReport();
  if (extraction) showExtraction(false);
  if (micNote) $("micNote").textContent = t(micNote.key, micNote.params);
  // camera
  $("camStart").innerHTML = `${icon("camera")}<span>${t("field.cam_start")}</span>`;
  $("camStop").textContent = t("field.cam_stop");
  $("camAnalyze").textContent = t("field.cam_analyze");
  $("camKicker").textContent = t("field.cam_kicker");
  $("camGuideTitle").textContent = t("field.cam_title");
  $("camIntro").textContent = t("field.cam_intro");
  $("camStepZone").textContent = t("field.cam_step_zone");
  $("camStepEmpty").textContent = t("field.cam_step_empty");
  $("camStepClip").textContent = t("field.cam_step_clip");
  $("camPlaceholder").innerHTML = `<span class="cam-placeholder-icon">${icon("camera")}</span><strong>${t("field.cam_preview_title")}</strong><small>${t("field.cam_preview_note")}</small>`;
  $("camSteps").setAttribute("aria-label", t("field.cam_steps"));
  $("camDisclosureTitle").textContent = t("field.cam_disclosure_title");
  $("camHonest").textContent = t("field.cam_honest");
  const cz = $("camZone").value, cl = $("camLoc").value;
  zoneOptions($("camZone"), cz, "field.choose");
  locOptions($("camLoc"), cz, cl, false, "field.cam_choose_location");
  refreshCamControls(false);
  setCamState(cam.state);
  renderCamStatus();
}

/* ---------- voice report ---------- */
const SRC = { stated: ["said", "field.src_said"], location: ["derived", "field.src_from_location"], user: ["", "field.src_user"] };
function srcNote(el, kind) {
  const [cls, key] = SRC[kind] || ["", "field.src_not_said"];
  el.className = `src ${cls}`; el.textContent = t(key);
}
function updateSendState() {
  const hasText = !!$("transcript").value.trim(), hasCat = !!$("catSel").value;
  $("sendBtn").disabled = !(hasText && hasCat);
  let note = "";
  if (extraction && !hasCat) note = t("field.need_type");
  else if (extraction && !$("zoneSel").value) note = t("field.zone_unknown_note");
  $("reviewNote").textContent = note;
}
function showExtraction(fresh = true) {
  $("understood").hidden = false;
  const e = extraction;
  if (fresh) fillReport({ cat: e.category || (e.candidates?.length ? "" : ""), zone: e.zone_id, loc: e.location_id });
  srcNote($("catSrc"), e.category ? "stated" : null);
  srcNote($("zoneSrc"), e.zone_source);
  srcNote($("locSrc"), e.location_id ? "stated" : null);
  $("reviewReasons").innerHTML = (e.review_reasons || []).map((r) => `<li>${t(`field.reason_${r}`, { events: (e.candidates || []).map((c) => t(`field.event_${c}`)).join(" / ") })}</li>`).join("")
    + (e.report_kind === "support_request" ? `<li>${t("field.support_request")}</li>` : "");
  const parts = [t("field.confidence", { pct: Math.round(e.confidence * 100) })];
  if (sttConfidence != null && sttConfidence > 0) parts.push(t("field.stt_confidence", { pct: Math.round(sttConfidence * 100) }));
  $("conf").textContent = parts.join(" · ");
  updateSendState();
}
async function analyze() {
  const text = $("transcript").value.trim();
  if (!text) return;
  setResult("");
  try { extraction = await api("/api/voice/extract", { text }); showExtraction(); }
  catch (e) { setResult(errText(e), "err"); }
}
async function send() {
  const text = $("transcript").value.trim();
  if (!text) return;
  $("sendBtn").disabled = true;
  try {
    const loc = $("locSel").value;
    const r = await api("/api/voice/report", {
      text, category: $("catSel").value || null, zone_id: $("zoneSel").value || "", location_id: loc,
      location_other: loc === "other" ? $("locOther").value.trim() : null, input_mode: inputMode,
      recorded_at: recordedAt, stt_confidence: sttConfidence,
    });
    if (r.incident) setResult(t("field.sent", { code: iso(r.incident.code), priority: iso(`${r.incident.priority} · ${t(`priority.${r.incident.priority}`)}`) }), "ok");
    else if (r.disposition === "needs_review") setResult(t("field.sent_review"), "warn");
    else setResult(t("field.sent_routed"), "ok");
    $("transcript").value = ""; extraction = null; inputMode = "text"; recordedAt = null; sttConfidence = null;
    fillReport({ cat: "", zone: "", loc: "" }); $("locOther").value = "";
    $("understood").hidden = true;
  } catch (e) {
    if (e.code === "needs_review" && e.data?.extraction) { extraction = e.data.extraction; showExtraction(); setResult(t("field.need_type"), "err"); }
    else setResult(errText(e), "err");
  } finally { updateSendState(); }
}
function setupSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { $("micBtn").disabled = true; setMicNote("field.mic_unavailable"); return; }
  if (!window.isSecureContext) { $("micBtn").disabled = true; setMicNote("field.mic_insecure"); return; }
  $("micBtn").addEventListener("click", () => {
    if (recognizing) { rec?.stop(); return; }
    rec = new SR();
    rec.lang = $("speechLang").value; rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 1;
    let finalText = "", started = false, conf = [];
    const current = rec;
    const watchdog = setTimeout(() => {
      if (!started) { try { current.abort(); } catch { /* ignore */ } setMicNote("field.mic_error", { code: "no-response" }); }
    }, 5000);
    rec.onstart = () => { started = true; clearTimeout(watchdog); recognizing = true; recordedAt = new Date().toISOString();
      $("micBtn").setAttribute("aria-pressed", "true"); $("micLabel").textContent = t("field.mic_listening"); setMicNote(null); };
    rec.onresult = (ev) => {
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i];
        if (r.isFinal) { finalText += r[0].transcript; if (typeof r[0].confidence === "number") conf.push(r[0].confidence); }
        else interim += r[0].transcript;
      }
      $("transcript").value = (finalText + interim).trim();
    };
    rec.onerror = (ev) => { clearTimeout(watchdog); setMicNote("field.mic_error", { code: ev.error }); };
    rec.onend = () => {
      recognizing = false; $("micBtn").setAttribute("aria-pressed", "false"); $("micLabel").textContent = t("field.mic_tap");
      if ($("transcript").value.trim()) {
        inputMode = "voice"; sttConfidence = conf.length ? conf.reduce((a, b) => a + b, 0) / conf.length : null; analyze();
      }
    };
    try { rec.start(); } catch (e) { clearTimeout(watchdog); setMicNote("field.mic_error", { code: e.name }); }
  });
}

/* ---------- camera (live only) ---------- */
// Live camera frames go to the server analyser. One report per fall: the server state machine
// is disarmed after an alert and re-arms only when the person is seen upright again; the page
// also keeps the first alert card on screen while the state stays "alerted".
const cam = { stream: null, sid: null, running: false, fileBusy: false, status: null, frames: 0, warmup: 24, alerts: [], state: "idle" };
function renderCamStatus() {
  const s = cam.status;
  $("camStatus").innerHTML = s ? t(`field.cam_s_${s.key}`, s.params || {}) : "";
  $("camStatus").dataset.kind = s ? s.key : "";
}
const escHtml = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function camStatus(key, params = {}) {
  const safe = Object.fromEntries(Object.entries(params).map(([k, v]) => [k, escHtml(v)]));   // status uses innerHTML
  cam.status = { key, params: safe }; renderCamStatus();
}
function setCamState(state) {
  cam.state = state;
  $("camFrame").dataset.state = state;
  const badge = $("camBadge");
  badge.hidden = state === "idle";
  badge.textContent = state === "idle" ? "" : t(`field.cam_badge_${state}`);
}
function camPlace() {
  return { zone_id: $("camZone").value || null, location_id: $("camLoc").value || null };
}
function refreshCamControls(showStatus = false) {
  const place = camPlace();
  const complete = !!(place.zone_id && place.location_id);
  $("camStart").disabled = !complete || cam.running || cam.fileBusy;
  $("camAnalyze").disabled = !complete || !$("camFile").files.length || cam.fileBusy;
  $("camZone").disabled = cam.running || cam.fileBusy; $("camLoc").disabled = cam.running || cam.fileBusy;
  if (showStatus && !cam.running) camStatus(!place.zone_id ? "need_zone" : !place.location_id ? "need_location" : "live_ready");
}
function camResult(alert, origin = "live_cv") {
  // Same as a radio report: a short confirmation here; the case itself goes straight to the dashboard.
  if (!alert || typeof alert !== "object") return;
  const inc = alert.incident;
  const box = $("camResult");
  box.textContent = inc
    ? t("field.sent", { code: iso(inc.code), priority: iso(`${inc.priority} · ${t(`priority.${inc.priority}`)}`) })
    : t("field.sent_routed");
  box.className = "f-result ok";
}
const CAM_ERR = { NotAllowedError: "denied", SecurityError: "denied", PermissionDeniedError: "denied",
  NotFoundError: "no_camera", DevicesNotFoundError: "no_camera", OverconstrainedError: "no_camera",
  NotReadableError: "busy", TrackStartError: "busy", AbortError: "busy" };
async function startLive() {
  if (cam.running) return;
  const place = camPlace();
  if (!place.zone_id) { camStatus("need_zone"); return; }
  if (!place.location_id) { camStatus("need_location"); return; }
  if (!window.isSecureContext) { camStatus("insecure"); return; }
  if (!navigator.mediaDevices?.getUserMedia) { camStatus("unsupported"); return; }
  $("camStart").disabled = true;
  camStatus("opening");
  try {
    cam.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
  } catch (e) { camStatus(CAM_ERR[e?.name] || "denied", { code: e?.name || "?" }); refreshCamControls(false); return; }
  const v = $("camVideo"); v.srcObject = cam.stream; await v.play().catch(() => {});
  $("camFrame").classList.add("is-live");
  try {
    const s = await api("/api/cv/sessions", place);
    Object.assign(cam, { sid: s.session_id, warmup: s.warmup_frames, frames: 0, running: true, alerts: [] });
  } catch (e) { stopLive(); camStatus("server_error", { msg: errText(e) }); return; }
  $("camStart").hidden = true; $("camStop").hidden = false;
  setCamState("learning");
  $("camResult").replaceChildren(); $("camResult").className = "f-result cam-result";
  refreshCamControls(false);
  frameLoop();
}
async function frameLoop() {
  const v = $("camVideo"), c = $("camCanvas");
  const sid = cam.sid;
  while (cam.running && cam.sid === sid) {
    const t0 = performance.now();
    if (v.videoWidth) {
      c.width = 320; c.height = Math.round(320 * v.videoHeight / v.videoWidth);
      c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
      const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.6));
      try {
        const res = await fetch(`/api/cv/sessions/${sid}/frame`, { method: "POST", body: blob,
          headers: { "Content-Type": "image/jpeg", "X-Frame-Time": String(Math.round(performance.now())),
            "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "" } });
        if (res.status === 401) { location.assign("/login"); return; }
        const r = await res.json();
        if (!cam.running || cam.sid !== sid) break;
        if (!res.ok) { camStatus("server_error", { msg: errText({ code: r.error }) }); if (r.error === "session_not_found") { stopLive(); break; } }
        else {
          cam.frames = r.frames;
          if (r.state === "learning") { setCamState("learning"); camStatus("learning", { n: r.frames, total: r.warmup }); }
          else {
            setCamState(r.state === "alerted" ? "alerted" : r.state === "lying" || r.state === "transition" ? "checking" : "watching");
            camStatus(`state_${r.state}`);
          }
          if (r.alert) { cam.alerts.push(r.alert); camResult(r.alert); }
        }
      } catch { camStatus("server_error", { msg: t("errors.network") }); }
    }
    const wait = Math.max(0, 170 - (performance.now() - t0));   // about 5-6 frames per second
    await new Promise((res) => setTimeout(res, wait));
  }
}
function stopLive() {
  const wasRunning = cam.running || cam.stream;
  cam.running = false;
  cam.stream?.getTracks().forEach((tr) => tr.stop()); cam.stream = null;
  $("camVideo").srcObject = null; $("camFrame").classList.remove("is-live");
  if (cam.sid) { fetch(`/api/cv/sessions/${cam.sid}`, { method: "DELETE",
    headers: { "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "" } }).catch(() => {}); cam.sid = null; }
  $("camStart").hidden = false; $("camStop").hidden = true;
  setCamState("idle");
  refreshCamControls(false);
  if (wasRunning && cam.frames) camStatus("stopped", { n: cam.frames, alerts: cam.alerts.length });
}
async function analyzeFile() {
  const file = $("camFile").files[0];
  const place = camPlace();
  if (!place.zone_id) { camStatus("need_zone"); return; }
  if (!place.location_id) { camStatus("need_location"); return; }
  if (!file) return;
  const body = new FormData();
  body.append("video", file); body.append("zone_id", place.zone_id); body.append("location_id", place.location_id);
  cam.fileBusy = true;
  $("camResult").replaceChildren(); $("camResult").className = "f-result cam-result";
  refreshCamControls(false);
  camStatus("uploading", { name: file.name });
  try {
    const result = await api("/api/cv/video", body, true);
    camStatus("file_done", { s: result.duration_s, frames: result.frames, n: result.events?.length || 0 });
    if (Array.isArray(result.alerts) && result.alerts.length) camResult(result.alerts[0], "video_file");
    else {
      $("camResult").className = "f-result warn";
      $("camResult").textContent = t("field.cam_no_fall");
    }
  } catch (error) {
    camStatus("server_error", { msg: errText(error) });
  } finally {
    cam.fileBusy = false;
    refreshCamControls(false);
  }
}
function setTab(which) {
  $("tabVoice").setAttribute("aria-selected", which === "voice"); $("tabCam").setAttribute("aria-selected", which === "cam");
  $("panelVoice").hidden = which !== "voice"; $("panelCam").hidden = which !== "cam";
  if (which !== "cam") stopLive();
}

(async function main() {
  await initI18n();
  // Bind the navigation before rendering so a stale cached template cannot make the tabs inert.
  $("tabVoice").addEventListener("click", () => setTab("voice"));
  $("tabCam").addEventListener("click", () => setTab("cam"));
  $("speechLang").value = getLang() === "en" ? "en-US" : "ar-SA";
  try {
    zones = (await api("/api/zones")).zones.sort((a, b) => a.id.localeCompare(b.id));
    locations = (await api("/api/layout")).locations;
  } catch { setResult(t("errors.network"), "err"); }
  ensureCameraScaffold();
  renderStatic();
  setupSpeech();
  setCamState("idle");
  refreshCamControls(true);
  onLangChange(renderStatic);
  $("langBtn").addEventListener("click", () => setLang(getLang() === "ar" ? "en" : "ar"));
  $("analyzeBtn").addEventListener("click", analyze);
  $("sendBtn").addEventListener("click", send);
  $("transcript").addEventListener("input", () => { inputMode = "text"; sttConfidence = null; setResult(""); updateSendState(); });
  $("catSel").addEventListener("change", () => { srcNote($("catSrc"), "user"); updateSendState(); });
  $("zoneSel").addEventListener("change", () => {
    srcNote($("zoneSrc"), "user"); locOptions($("locSel"), $("zoneSel").value, $("locSel").value); toggleOther(); updateSendState();
  });
  $("locSel").addEventListener("change", () => {
    const l = locations.find((x) => x.id === $("locSel").value);
    if (l && !$("zoneSel").value) { $("zoneSel").value = l.zone_id; srcNote($("zoneSrc"), "location"); locOptions($("locSel"), l.zone_id, l.id); }
    srcNote($("locSrc"), "user"); toggleOther(); updateSendState();
  });
  $("samples").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-i]"); if (!b) return;
    $("transcript").value = SAMPLES[b.dataset.i]; inputMode = "text"; recordedAt = null; sttConfidence = null; analyze();
  });
  $("camZone").addEventListener("change", () => {
    locOptions($("camLoc"), $("camZone").value, $("camLoc").value, false, "field.cam_choose_location"); refreshCamControls(true);
  });
  $("camLoc").addEventListener("change", () => refreshCamControls(true));
  $("camFile").addEventListener("change", () => refreshCamControls(false));
  $("camAnalyze").addEventListener("click", analyzeFile);
  $("camStart").addEventListener("click", startLive);
  $("camStop").addEventListener("click", stopLive);
  window.addEventListener("pagehide", stopLive);
  // checked last, after every control is bound: the first call may load the YOLO model on the server and can be slow
  api("/api/cv/status").then((st) => { if (!st.available) camStatus("cv_unavailable"); }).catch(() => { /* shown on use */ });
})();

export { EVENT_CAT };
