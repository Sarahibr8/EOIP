# Final Team Leader Report — EOIP MVP

**Date:** 2026-10-09 · **Status: RUNNABLE — v3 (final MVP spec)** · **Repo:** `eoip/` (git, branch `main`)

## 0. v3 — final MVP spec (2026-10-09, afternoon)
- **Zones:** Zone A/B/C and six locations, one source (`data/zones.json`), used in every page, the data and both languages. A test checks that no old zone names remain.
- **Voice reports:**
  - Event, zone and location are extracted from the central lexicon `data/lexicon.json`.
  - Negation and ambiguity go to review; nothing is guessed.
  - Support request is distinguished from an incident report.
  - The reporter corrects before sending.
- **Camera from the phone:** live frames or an uploaded video, analysed on the server by the same YOLO detector as the laptop agent. Origins are `live_cv`, `video_file` and `replay_cv`.
- **Linking:** location-aware for emergencies; the reasons are shown.
- **Simulations:** crowd (receiving zone + share) and staffing (from / to / count, minimum-staff checks); both can be saved as options and approved or rejected.
- **Decision log:**
  - The operator name is required.
  - A full snapshot is kept with each decision (option, teams, simulation, priority).
  - The log survives reset and restart.
  - `--clear-decision-log` empties it only on request.
- **UI v3:** incident strips, filters and sort, the 3-zone map, simulation gauges, and a camera tab on the phone.
- **Tests:**
  - 105 unit tests.
  - Browser e2e 13/13 in AR and in EN.
  - Field 38/38, including a live camera fed by a fake device.
  - Mobile has no overflow.
- **Pending manual tests on a real phone:** microphone, camera and filming a screen.

## 0b. v2 — final changes (2026-10-09, morning)
The project was not restarted from scratch and the stack is unchanged (Flask + SQLite + vanilla JS).

**What changed:**
- **UI:** the single dashboard was replaced by a linked multi-page app:
  - Overview, Operations map, Incidents, Incident details, Decision support, Decision log, and the Field page.
  - New visual identity (see `design-system.md`).
  - AR/EN; laptop and mobile.
- **Correlation:** every linked report stores why it was linked (type, zone, time gap, open, independent or repeated source) and a rule score. Similar words never merge on their own.
- **Teams:** synthetic roster; nearest available team plus an ETA estimate; assign on approval, release on close; double dispatch blocked and re-planned.
- **Simulation:** an operator what-if (divert / move staff / meter) is computed on the server, with capacity and minimum-staff checks. It can be saved as an option and approved.
- **Bug fixed in review:** the fire plan's "why" text was stale ("single source" while 3 sources had confirmed). Plans now update in place as evidence arrives.

**Verified:**
- 66 unit/integration tests.
- Demo E2E 10/10 in AR and in EN.
- Phone page 27/27.
- Mobile 390 px: no page overflow on any page (one overflow on Decision support was found and fixed).

**Not verified here:** the real laptop camera, the phone microphone, and Google Fonts (blocked in the test environment, so the fallback font was used).

## 0a. Final Review (2026-10-08, afternoon)
No scope change and no restructuring. Everything was verified end to end, and 8 defects were fixed:

| # | Defect found in review | Severity | Fixed |
|---|---|---|---|
| 1 | Phone: a second report silently reused the previous report's location | High | ✅ |
| 2 | Decision log showed `{staff_moved}` placeholders in option titles | High | ✅ |
| 3 | Phone mic did nothing when the speech service didn't respond | Med | ✅ 5 s watchdog + message |
| 4 | Phone mic on plain HTTP failed without explanation | Med | ✅ disabled with a "needs HTTPS" hint |
| 5 | Mic messages didn't re-translate on language switch | Low | ✅ |
| 6 | Server down → error toast every 1.5 s | Med | ✅ one persistent notice + "Connection restored" |
| 7 | Old phone confirmation stayed visible during the next report | Low | ✅ |
| 8 | Startup didn't print the phone address | Low | ✅ `run.py` prints the dashboard and phone URLs |

**New verification:**
- Phone-page browser checks: 27/27 (AR/EN, review flow, mic fallbacks, HTTPS secure context).
- Demo E2E now also scans every screen for untranslated strings and verifies Reset.
- Camera robustness clips: walk → 0 alerts, crouch → 0, fall with flicker → 1.
- Fresh-clone run: tests OK, server up, demo 263 → 21 → 10 → 1.

## 1. Project overview
EOIP answers Challenge 3.6: the ops center can't tell what needs immediate intervention when hundreds of signals of four types arrive from separate parties during a live event. The MVP proves the full chain:

sources → many signals → filter / dedupe → correlation → incident → explained priority → recommendation (+ simulation) → human decision → log

## 2. Final concept
A decision-support layer *above* existing systems, shown as one ops-center screen. EOIP never acts on its own.

## 3. Final scenarios
See `scenario-proposal.md`.

| Scenario | Sources | Kind |
|---|---|---|
| S1 Fire · Zone A · Food Court | alarm system + radio | emergency |
| S2 Collapse · Plaza | live CV + Arabic voice | emergency |
| S3 Crowding + staff shortage · Zone C · Main Gate | sensors + roster + radio | operational, with simulation |
| S0 Background load | 263 signals | — |

**Changed vs the old plan:**
- Fire moved off the camera.
- Crowding and staff shortage are merged.

## 4. What was built
- Backend pipeline and APIs
- Intelligence: correlation, duplicates, priority, recommendations, simulation
- Voice report page (phone) with Arabic-first extraction
- YOLO camera agent
- Bilingual ops web app: 6 linked pages + the phone page (v2)
- Synthetic response-team roster with ETA, plus an operator what-if simulation (v2)
- Deterministic demo engine
- 66 unit/integration tests + a browser demo E2E in two languages (10 checks each) + 27 phone-page browser checks
- Documentation

## 5–12. Area summaries

| Area | What | Where |
|---|---|---|
| Architecture | Flask + SQLite, one process; pure-Python core; adapters post to `/api/ingest` | `architecture.md` |
| Database | 6 tables with CHECK constraints, indexes for duplicate check and incident lookup, append-only decision log | `schema.sql`, `data-contract.md` |
| Backend | Ingest, voice report/extract, state, incident detail, decisions, demo control; one IMMEDIATE transaction per signal | `api.py`, `core/pipeline.py`, `api-contract.md` |
| Frontend | Dashboard (funnel, queue, map, live stream, decision log, detail) + phone field page; vanilla JS, no build | `templates/`, `static/js/` |
| AI | Speech-to-text (browser) + Arabic-first rule-based extraction (14/14 golden) | `core/extract.py` |
| Computer vision | YOLO person detection (Ultralytics) + upright→lying state machine; posts `person_down` with confidence and snapshot | `cv/` |
| Voice | Mic → transcript → "what EOIP understood" (editable) → send → incident code shown | `field.js` |
| UX/UI | Control-room design system; every string in AR/EN JSON; RTL/LTR via logical CSS | `ux-spec.md`, `design-system.md` |

## 13. Usability testing
A structured **expert walkthrough** (not a user study): 13 tasks, 12 issues found and fixed across two passes, 1 left open (D-15). See `testing.md §4`.

## 14. Testing results
- **66/66 unit/integration tests pass (v2).**
- **Demo E2E passes in Arabic and English**, including the untranslated-string scan and Reset.
- **Phone page: 27/27 checks pass.**
- Camera: 4/4 synthetic clips give the expected alert count.
- The golden demo is reproducible: 263 → 21 → 10 → 1.

## 15–17. Mock / simulated / real

| Category | What |
|---|---|
| **Mock** | All system feeds, zones, volumes |
| **Simulated** | Radio channel (phone); impact model |
| **Real** | Pipeline, rules, decisions, browser STT, extraction, YOLO detection on live camera frames |

Full table in `limitations.md`.

## 18–19. Tools / skills used
- **Build stack:** Python 3.13, Flask, SQLite, OpenCV, Ultralytics YOLO, Playwright/Chromium (screenshots + E2E), git.
- **Skills:** `frontend-design` (design direction and critique).
- **Not available here:**
  - Django and package downloads (registry blocked) → Flask.
  - Web fonts and CDNs → system fonts and local icons.
  - A physical camera and microphone → synthetic clips, logic tests, and fallbacks.
  - Chromium couldn't open HTTPS on the sandbox's LAN IP (a sandbox network quirk) → HTTPS tested on localhost in the browser; the LAN-IP TLS handshake was verified with curl.

## 20–23. Technical decisions, trade-offs, problems → solutions
See `decisions.md` (D-01…D-15).

| Problem | Solution |
|---|---|
| Django unavailable | Flask with a portable core |
| No real data | Seeded synthetic script, labelled everywhere |
| Camera fire unrealistic | Alarm-system fire |
| Duplicates inflating confirmation | Evidence counted per source system |
| Operational pressure outranking a fire | Cap below P1 |
| Concurrent demo ticks | Cursor claimed in a transaction |
| UI issues found in the walkthrough | Fixed (banner icon, menu overlay, stale toasts, bidi, mobile overflow, stale phone location, log placeholders, offline toast spam, silent mic) |

## 24. Limitations
See `limitations.md`. Top 3:
1. Live CV and live mic are not yet validated on the demo hardware.
2. Priority weights are assumptions.
3. Flask, not Django.

## 25–26. Expo requirements and evaluation mapping
- **Requirements:** `expo-requirements-matrix.md`. R1–R13 are covered; R14 (upload) is pending.
- **Evaluation:** the official criteria and weights were **not in the provided material**, so no mapping to weights was made. Get them from the organizers and add them to the matrix.

## 27–28. Demo flow and fallbacks
See `demo-script.md`: a 4:50 script (5:00 max) with a fallback for camera, mic, phone network, internet, extraction and server.

## 29. Git status
Branch `main`, clean working tree; no secrets; `instance/` (SQLite) and CV snapshots are git-ignored.

## 30. Remaining work, by team member

| Owner | Task | When |
|---|---|---|
| **Team Leader (Sara)** | Approve D-01 (Flask vs Django port); get the evaluation criteria; confirm the demo date; review the scenario decision | Today |
| **Data Scientist / AI** | Run 10 live CV trials on the demo laptop (`testing.md §3`); extend the golden set with real team voice phrasing (≥30 phrases); tune the priority weights | Day 1–2 |
| **Backend** | Port to Django *only if* required (core unchanged); optional SSE push | Day 2–3 |
| **Frontend** | Test the phone mic on the actual demo phone over HTTPS; polish the empty and error states on the field page | Day 1–2 |
| **UX/UI** | Run the walkthrough with 2–3 classmates as operators; validate D-15; check fonts on the demo laptop | Day 2 |
| **All** | Rehearse the demo 3× with the fallbacks; record a backup video | Before the demo |

## 31. Final recommendations
1. **Freeze scope now.** No new scenarios; spend time on rehearsal and CV/mic reliability.
2. Keep Flask unless Django is explicitly graded. A port adds risk without adding value for the demo.
3. In the pitch, lead with the funnel number (263 → 1) and the P2→P1 escalation; they *are* Challenge 3.6.
4. Always say "synthetic data" and "camera replay" out loud when they are used. Honesty is part of feasibility.

## Summary table

| AREA | STATUS | WHAT WAS DONE | TOOLS / SKILLS USED | TEST RESULT | REMAINING RISK |
|---|---|---|---|---|---|
| Requirements | ✅ | Matrix R1–R14 from the official guide | PDF images, Project files | — | Evaluation weights unknown |
| Scenarios | ✅ | S0–S3 decided and documented | — | Golden demo test | Low |
| Database | ✅ | 6-table schema, constraints, seed | SQLite | Pipeline tests | Low |
| Backend / APIs | ✅ | 16 endpoints, transactional pipeline | Flask | 11 API tests | D-01 (framework) |
| Intelligence | ✅ | Dedupe, correlation, priority, playbooks, simulation | Python | 24 tests | Weights are assumptions |
| Voice | ✅ / ⚠ | Field page, STT, AR/EN extraction, mic fallbacks | Web Speech API, rules NLP | 14/14 golden; 27/27 phone checks | Real mic/speech service untested here |
| Computer vision | ✅ / ⚠ | Camera agent + replay fallback | YOLO (Ultralytics) | detector tested with a stand-in; real model: manual test | Real people / lighting untested |
| Frontend / UX | ✅ | Bilingual command center + phone page | Vanilla JS, frontend-design skill | E2E AR + EN pass; no untranslated strings | Real-user validation |
| Demo | ✅ | Script, fallbacks, checklist | Playwright screenshots | E2E pass | Rehearsal needed |
| Docs | ✅ | 12 documents | — | — | Keep in sync with changes |
