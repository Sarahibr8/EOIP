# Architecture — EOIP MVP

## 1. Shape of the system

```
 SOURCES (separate parties)                        EOIP (one Flask process + SQLite)                       OPERATOR
 ───────────────────────────                       ──────────────────────────────────                      ────────
 Fire alarm / smoke detectors ─┐                  ┌──────────────────────────────────────────┐
 Crowd & queue sensors         │  POST /api/ingest│ normalize → classify → de-duplicate      │  GET /api/state (1.5 s poll)
 Staff roster / BMS / IT       ├─────────────────►│   → correlate → incident                  ├──────────────────► Ops app (6 pages)
 Service desk requests         │  (demo engine     │   → priority (explained)                  │                    (AR/EN, RTL/LTR)
 (all MOCK, data/demo_script)  │   replays these)  │   → recommendations (+ simulation)        │◄────────────────── approve / reject /
                               │                   │   → decisions log                         │  POST /decisions   resolve / dismiss
 Phone = supervisor radio ─────┤ POST /voice/report│                                           │
  (browser STT → text → AI     │                   │ eoip/core/*  (pure Python business logic) │
   extraction, AR-first)       │                   │ eoip/api.py  (thin HTTP layer)            │
 Laptop camera agent ──────────┘                   │ SQLite (eoip/schema.sql)                  │
  (YOLO person-down → alert)                     └──────────────────────────────────────────┘
```

**Principle:** EOIP is a layer *above* existing systems. Every source, real or mock, talks to it through the same `POST /api/ingest` contract, including our own camera agent and voice page. Plugging a real system in later means writing a small adapter that posts to this endpoint.

## 2. Components

| Component | File(s) | Role |
|---|---|---|
| Normalizer | `eoip/core/normalize.py` | Validates any source payload into one Alert shape and rejects bad data with explicit errors |
| Pipeline | `eoip/core/pipeline.py` | Classify → dedupe → correlate → update zone state → re-score → refresh recommendations, in one IMMEDIATE transaction |
| Priority engine | `eoip/core/priority.py` | Explainable score 0–100 → P1–P4; every point carries a reason |
| Recommender | `eoip/core/recommend.py` | Playbooks (emergency), ranked options (operational), routing (routine) |
| Simulator | `eoip/core/simulate.py` | 15-minute flow projection per option, plus side effects |
| Decisions | `eoip/core/decisions.py` | Human-in-the-loop state machine + audit log |
| Voice extraction | `eoip/core/extract.py` | Arabic-first text → category, zone, confidence, evidence |
| Demo engine | `eoip/demo.py` | Replays the synthetic event; cursor-based so it is exactly-once |
| Read models | `eoip/queries.py` | JSON for the ops app pages |
| Teams | `eoip/core/teams.py` | Synthetic roster: nearest available team (BFS hops), ETA, assign/release |
| Ops web app | `templates/app.html`, `static/js/app.js` (router), `store.js` (single state source), `views/*.js`, `siteplan.js` | Six linked pages (see §2b) |
| Field page | `templates/field.html`, `static/js/field.js` | Phone acting as radio |
| Camera agent | `cv/fall_detector.py`, `cv/fall_logic.py` | Separate process acting as an AI camera |

## 2b. Pages (v2)
All pages read the same store (`/api/state`, polled every 1.5 s) and the same incident detail endpoint.

| Route | Page | Purpose |
|---|---|---|
| `#/` | Overview | What EOIP is; triage funnel (received → attention → incidents → critical); what needs a decision; latest signals; compact site plan |
| `#/map[/ZONE]` | Operations map | Site plan: hatch density = occupancy, ring = highest open priority, pin = incident count, team dots; zone detail |
| `#/incidents` | Incidents | Filters (open/critical/awaiting/closed/all) plus the full signal stream |
| `#/incident/:id` | Incident details | Linked reports with *why linked* chips and rule score; priority reasons on a scale; zone now; teams; timeline |
| `#/decide[/:id]` | Decision support | Emergency playbook + team/ETA, or ranked options with before/after and checks, plus a what-if builder; approve/reject/dismiss/resolve |
| `#/log` | Decision log | Every decision, with the operator, note and priority at decision time |
| `/field` | Field reporting (phone) | Voice or text → extraction → send |

## 2c. v3 additions
- **Layout:** Zone A/B/C and six locations (`data/zones.json`). The map (`siteplan.js`) draws zones (hatch = occupancy), location nodes (colour = priority, number = open incidents), walkways and teams.
- **Voice extraction v2** (`core/extract.py` + `data/lexicon.json`):
  - Event, zone and location are extracted.
  - Place names are masked before event words, so «نقطة الإسعافات» is not read as a medical event.
  - Negation: a cue up to 1 token before a term negates it.
  - Fire + medical in one report → review.
  - Two zones → review.
  - Location without zone → the zone is filled in and marked `zone_source: location`.
  - Location in a different zone than stated → review.
  - Staff wording → `report_kind: support_request`.
- **Camera from the phone** (`eoip/camera.py` + `cv/analyzer.py`):
  - The detector the laptop agent uses is now a shared `FallAnalyzer`.
  - The server keeps one analyzer per live session (phone frames as JPEG, about 6 fps) and runs a fresh one per uploaded video.
  - Opening a camera never creates an alert; only the upright→lying state machine does.
- **Decision log:**
  - The authenticated employee identity comes from the server-side session; the browser cannot choose the author.
  - Every decision requires a reason and stores employee id, employee number, display name and timestamp.
  - Each decision carries a snapshot; the log is kept across resets (`run_id`) and restarts.
- **Teams:** ETA = 1 min + walking minutes on the location graph (`data/teams.json`).

## 3. AI vs rules (where intelligence lives and why)

| Step | Method | Why |
|---|---|---|
| Speech → text | **AI** (browser Web Speech API, `ar-SA` / `en-US`) | Real speech recognition; nothing to train or host for the MVP |
| Text → category / zone | **Rule-based NLP** (Arabic normalization + gazetteer + lexicon) | Offline, instant, explainable ("matched حريق + زون A + منطقة المطاعم"). Keywords live in `data/lexicon.json`; negation and ambiguity go to review. 19 extraction tests pass (8 spec phrases + vocabulary + negation). The `extract()` contract is the plug-in point for an LLM later |
| Camera → person down | **Deep learning**: pretrained YOLO (Ultralytics, COCO `person`) + posture state machine | A trained detector copes with moving cameras, lighting and people already in view; weights are downloaded once, then it runs offline |
| Normalization, de-dup, correlation | Rules | Must be deterministic and auditable |
| Priority | Rules (weighted, explained) | No labelled Expo data to train on; operators must see *why* |
| Recommendations | Rules / playbooks | Safety procedures must be pre-approved, not generated |
| Simulation | Arithmetic flow model | Transparent; numbers come from live zone state |
| Decision | **Human** | Always |

**Explicitly not used:** an LLM for summaries (the incident card already answers what, where, why and what to do), ML priority scoring (no data), or fire detection from the camera (unrealistic).

## 4. Key mechanisms

**De-duplication.** Same `source_system` + `category` + `zone` within 120 s → `duplicate`. The alert is attached to the root alert's incident and counted, but it adds no evidence. Stateful sensor readings are excluded because they are updates, not repeats.

**Correlation.** Each category maps to an incident family. A new alert joins an open incident of the same family and zone that was updated within 15 minutes; otherwise it opens a new incident. Crowd and staffing signals share one family on purpose, because the shortage causes the pressure.

**Correlation reasons (v2, `rules_v2`).** Every linked alert stores *why* it was linked: same family, same zone, gap since the last update, incident still open, and new vs. already-linked source. A rule score is shown with it. Words alone never link: a report must match the family **and** the zone. A different family in the same zone (for example a medical call in the fire zone) opens its own incident. A repeat after an incident was dismissed opens a new incident rather than attaching to the closed one.

**Teams and what-if (v2).** Plans pick the nearest *available* team of the right kind and show the ETA. Approving assigns the team, and closing the incident releases it. A double dispatch is blocked (`team_unavailable`) and re-planned. For operational incidents, the operator can compute any divert, redeploy or meter action on the live zone state, check capacity and minimum staff, and save it as an option to approve.

**Independence.** Evidence counts *source systems*, not alerts. A smoke detector and the fire panel are one system, so the confirmation in S1 comes from radio and the service desk, not from the panel repeating itself.

**Escalation.** Every new alert re-scores its incident. If the level rises, `escalated_at` is set and the app raises a persistent critical toast for a new P1, linking to its decision page.

**Exactly-once demo playback.** The engine reserves script entries by advancing the cursor inside a `BEGIN IMMEDIATE` transaction before ingesting them. Concurrent ticks therefore cannot double-ingest (covered by a test).

## 5. Technology choices

| Choice | Decision | Trade-off |
|---|---|---|
| Web framework | **Flask** (team default was Django) | Django could not be installed in the build environment; Flask was available, so the MVP could be run and tested. Business logic is framework-free, so a Django port only touches `api.py`/`web.py`/`db.py` (see decisions D-01) |
| Database | SQLite, raw SQL with CHECK constraints | Zero setup. The schema is explicit for the DB owner. Postgres later needs no model change |
| Real-time | 1.5 s polling | No WebSockets, Redis or Celery. Fine for one ops screen; SSE is the next step |
| Frontend | Vanilla JS modules, no build | Nothing to install, works offline, easy for any teammate to edit |
| i18n | JSON dictionaries + `dir` switch | Every visible string is translated; the backend returns keys, never sentences |
| Auth | SQLite employees, scrypt password hashes, opaque server-side sessions, HttpOnly/SameSite cookie and CSRF tokens | Local account provisioning only; no SSO, MFA, login throttling or self-service recovery |

## 6. Scaling path (not built)
1. Source adapters (fire panel via BACnet/Modbus gateway, CAD/radio over PTT-to-text, ticketing webhooks) posting to `/api/ingest`.
2. Postgres + SSE/WebSocket push; one ingestion worker per source.
3. Central directory / SSO, roles, MFA, login throttling and managed account recovery.
4. Rule tuning from the decision log: which recommendations were accepted or rejected, and false-alarm rates per source.
5. An LLM extractor behind the same `extract()` contract, evaluated on the golden set before replacing the rules.
6. Pose-based CV (MediaPipe / YOLO-pose) on real CCTV streams.
