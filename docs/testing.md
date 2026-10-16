# Testing — EOIP MVP

## Current safe verification
```bash
# Unit + integration (uses temporary SQLite databases; does not touch instance/eoip.sqlite3)
python -m unittest discover -s tests -t .
```

The legacy Playwright scripts below were written before employee authentication and include demo-reset actions. They are historical test records, not safe current commands; do not run them against a working database. Adapt them to a disposable database and the current login flow first.

## Historical v3 commands and results (2026-10-09)
The following command examples describe the older v3 suite and are retained as historical context only:
```bash

# 2. browser end-to-end (needs: pip install playwright && playwright install chromium)
python run.py --host 0.0.0.0 --reset &                 # HTTP :8000
python run.py --host 0.0.0.0 --https --port 8443 &     # HTTPS :8443
python tests/e2e_demo.py --lang ar
python tests/e2e_demo.py --lang en
python tests/e2e_field.py --lan-ip <laptop-ip> --https-port 8443

# 3. camera agent (needs ultralytics + weights in cv/models/; automated tests use a stand-in detector)
python cv/fall_detector.py --video <clip with a real person falling>.mp4 --no-window
```

## Current v4 authentication checks (2026-10-09)

| Check | Result | Evidence |
|---|---|---|
| Unit + integration (`python -m unittest discover -s tests -t .`) | ✅ 111 tests, 0 failures | Run against temporary SQLite files; includes auth, v3→v4 additive migration/log preservation, API identity, and existing pipeline/field/CV coverage. Werkzeug emitted file-handle `ResourceWarning`s. |
| Browser preview at desktop and 390 px | ✅ | Local isolated preview DB; invalid and valid login, employee identity, approve and decision log, Arabic/English directions, password toggle, logout and protected route, no horizontal overflow at 390 px. |
| Existing real `instance/eoip.sqlite3` | Not opened or migrated | No app run, reset or database command was directed at the project database during these checks. |

## 0. v3 results (final changes, run on 2026-10-09)

| Suite | Result | What it proves |
|---|---|---|
| Unit + integration (`python -m unittest discover -s tests -t .`) | ✅ **105 / 105** | All suites below plus the earlier ones (pipeline, API, CV logic + clips, v2) |
| `test_extract.py` | ✅ 19 | The **8 spec phrases** give event + zone + location; spec vocabulary (AR + EN, 45 phrases); unstated fields stay unknown; zone from location is marked; zone/location mismatch → review; two zones → review; negation («ما فيه حريق», "There is no fire", "false alarm"); fire + medical → review; support request vs incident; a place name is not an event word |
| `test_v3.py` | ✅ 28 | Zone A/B/C + six locations in state and layout; **no old zone names in data, dictionaries or JS**; location must belong to zone; same zone + different location = separate emergencies (reason `different_location`); unstated location still links (reason shown); crowding links by zone; field report stores text + zone + location + recording time + STT confidence; unknown zone → stored for review, not linked; "other location" text; negated report refused; staffing what-if (source, receiving zone, count, before/after vs minimum); crowd what-if shows both zones and capacities; numbers follow the current state; **approve, reject, resolve and dismiss each logged with operator, option, teams, simulation**; missing operator → nothing recorded; **log survives reset and a new app process on the same DB**; camera: fall video → `video_file` incident, walking video → nothing, live JPEG frames → `live_cv` incident, opening the camera (60 static frames) → no alert, replay labelled `replay_cv` |
| `test_v2.py` | ✅ 17 | v2 behaviours on the new layout, plus **v2 → v3 migration keeps old decisions** with names |
| `e2e_demo.py --lang ar` / `--lang en` | ✅ **13 / 13** each | Overview → live event → P1 toast → incident filters (priority, zone) and sort → incident details with *same location* reason → **decision without operator refused** → crowd simulation (2 zones) → staffing simulation (staff bars) → own option → reject (with reason) + approve → fire plan with team ETA → camera replay + field report = one P1 at Zone B / Main Walkway → decision log with operator + simulation result → map (3 zones, 6 locations) → no untranslated text → reset keeps the log |
| `e2e_field.py` | ✅ **38 / 38** | Phone page AR/EN: event/zone/location understood with sources; unknown zone sent for review; locations filtered by zone; "other" location; negation shown; mic fallbacks; HTTPS; **camera tab: fall video → incident, walking video → none; LIVE camera with Chromium's fake camera playing the fall clip → `live_cv` incident at Zone C / Waiting Area** |
| Mobile 390 px | ✅ | No horizontal overflow on any page (an overflow from the incident picker was found and fixed) |
| Restart check | ✅ | 9 decisions before → 9 after `run.py --reset` restart, same operator names |
| Laptop agent on a clip | ✅ | `cv/fall_detector.py --video …` still detects (now origin `video_file`) |

**Bugs found and fixed during testing:**
- Camera buttons on the phone page did not respond while the server loaded the camera libraries for the first time (seen once, then fixed and re-tested from a cold start).
- "Start" and "Stop camera" were both visible: the `hidden` attribute was overridden by the button style.
- Mixed Arabic/English sample texts in the synthetic data.
- Mobile overflow on Decision support.
- The incident strip broke in the narrow map side panel.

### Pending manual tests (cannot be done in this environment, NOT counted as passed)

| Test | How | Pass when |
|---|---|---|
| Real phone microphone (Arabic) | Phone on the same Wi-Fi → `https://<laptop-ip>:8000/field` → say «فيه حريق في زون A عند منطقة المطاعم» | Text appears; event Fire, Zone A, Food Court; sent; incident shown on the laptop |
| Real phone microphone (English) | Say "Someone is unconscious in Zone B at the Main Walkway" | Medical, Zone B, Main Walkway |
| Real phone camera, live | Camera tab → Zone B → Start; phone on a stand; empty scene 4 s; a person walks in, stands, lies down | "Possible fall" + incident code; laptop shows *Live camera* |
| Phone filming a screen | Same, pointing at a laptop playing a fall video | Detects in most attempts; if not, use video upload |
| Video upload from the phone | Record a 10–15 s clip (3 s empty first) → Analyse | Incident with origin *Video file analysed* |
| Laptop camera agent | `cv\fall_detector.py --zone ZONE-B --location MAIN-WALKWAY --server https://localhost:8000` | As before |

## 1. Results (earlier phases)

| Suite | Checks | Result | What it proves |
|---|---|---|---|
| `test_extract.py` | 8 tests (14 golden phrases) | ✅ | Arabic normalization and prefixes; AR + EN category/zone; unknown text → needs review |
| `test_pipeline.py` | 24 | ✅ | Validation, noise/routine, duplicates, correlation, P2→P1 escalation, zone state, priority caps/reasons, simulation, decisions, **golden demo (263 → 21 → 10 → 1)**, reproducibility, CV + voice corroboration |
| `test_api.py` | 11 | ✅ | HTTP codes, contract shape, exactly-once demo ticks, **AR/EN dictionaries identical**, every enum labelled in both languages |
| `test_cv.py` | 6 (5 logic + 4 clips) | ✅ | Fall → 1 alert; walking → 0; crouching → 0; fall under lighting flicker → 1; wide object without a person → 0; cooldown |
| `test_v2.py` | 17 | ✅ | Correlation reasons + score; different type in the same zone not merged; same words in another zone not linked; duplicate reason; repeat after dismiss → new incident; nearest team + ETA; no double dispatch (409 + re-plan); release on resolve; plan reasons follow evidence; what-if formulas, monotonicity, min-staff checks, validation; operator option saved and approvable; DB migration |
| `e2e_demo.py` (v2) | 10 checks × AR + EN | ✅ 10/10 both | Overview empty + synthetic label → live event → fire P1 + critical toast → incident details with link reasons/scores → decision support: ranked options, what-if recompute, own option saved, approve → fire plan with team ETA, teams assigned → camera replay + field report = one P1 → decision log → map (10 zones, zone select) → **no untranslated keys on any incident/decision page** → reset releases teams |
| Mobile layout (390 px, AR) | 6 pages | ✅ | No horizontal page overflow on Decision support, Incident, Map, Log, Incidents, Field (an overflow on Decision support was found and fixed); no JS errors |
| `e2e_field.py` | 27 checks | ✅ 27/27 | Phone page (see §2) |
| Manual: server killed mid-event | — | ✅ | One persistent "can't reach server" notice; "connection restored" on recovery; no toast spam |
| Manual: camera agent with no camera | — | ✅ | Exits with "use --replay" message (exit code 2); `--replay` CLI posts a labelled replay |

**Totals:**
- 66 unit/integration tests pass.
- Browser E2E (v2) passes 10/10 in both languages.
- 27/27 phone-page checks pass.

## 2. Voice / field report

| Check | Result |
|---|---|
| Arabic sample → send → "Linked to INC-xxxx (P2 · High)" shown, RTL | ✅ |
| English sample → linked incident, LTR | ✅ |
| Zone missing → send blocked + guidance → operator picks zone → sent, stored as `corrected_by_user` | ✅ |
| Text EOIP doesn't understand → nothing guessed → manual type + zone → accepted | ✅ |
| After sending, the next report never reuses the previous location (regression for a bug found today) | ✅ |
| Browser without Speech API → mic disabled + explanation (re-translates on language switch) | ✅ |
| Phone on plain HTTP over the LAN → mic disabled with "needs HTTPS" hint; typing works | ✅ |
| HTTPS (self-signed) → secure context, mic enabled, report sent | ✅ (via `https://localhost`; LAN-IP HTTPS handshake verified with curl) |
| Speech service doesn't respond → after 5 s "Voice input stopped (no-response)", typing still works | ✅ |
| No untranslated strings in AR or EN | ✅ |

**Not testable here:** actual speech recognition from a real microphone (no audio device, and the Google speech service is unreachable from this sandbox). That is why the no-response watchdog exists.

**On the demo phone:** use Chrome on Android over `https://<laptop-ip>:8000/field`, accept the certificate once, allow the microphone, and say one sentence.

## 3. Computer vision

> **Update (YOLO):** the synthetic stick-figure clips below were made for the earlier classical detector and gave the results shown. YOLO is trained on real people, so it does not detect those drawings. The automated tests now use a stand-in detector (`tests/helpers_cv.py`) to check the pipeline mechanics only.
>
> **Manual test still required for YOLO** (not run in the build environment: no internet for weights, no camera): 1) `pip install ultralytics`, `python cv/download_model.py`; 2) `python cv/fall_detector.py` and walk in, stand, lie down: expect ONE `person_down` alert; 3) walk only / crouch / sit: expect none; 4) repeat from the phone camera page.

| Clip (synthetic, `tests/make_cv_clips.py`) | Expected | Got |
|---|---|---|
| `synthetic_fall.avi`: block stands, falls, lies | 1 alert | 1 (conf 0.85) |
| `cv_fall_flicker.avi`: figure walks in, falls, lies 3 s, brightness flicker | 1 | 1 (conf 0.85) |
| `cv_walk.avi`: figure walks across, never falls | 0 | 0 |
| `cv_crouch.avi`: figure crouches, stands, leaves | 0 | 0 |

- **Labelling:** video input is sent as `replay_cv` and shown as **"Camera replay"**. Only the live camera is labelled **"Live camera"**.
- **Evidence:** the snapshot is saved and shown in the incident timeline.
- **Not tested here:** real people in front of a real laptop camera (no camera in this environment). Fill this on the demo laptop:

| Trial | Lighting / distance | Alert? | Notes |
|---|---|---|---|
| 1–10 | | | |

**Rule:** if fewer than 8/10 are detected, present with **Replay camera detection**, and say it is a replay.

## 4. Usability: structured expert walkthrough (not a user study)
Screens reviewed in AR and EN at 1600, 1100 and 390 px, plus the phone page. No real operators took part.

| # | Task | Observed issue | Sev. | Fix | Status |
|---|---|---|---|---|---|
| 1 | Spot the critical incident | — (funnel, queue top, map halo) | — | — | ✅ |
| 2 | Understand why it's P1 | Raw points could confuse | Low | Points muted; reason text leads | ✅ |
| 3 | Confirm an approval | Approval banner icon rendered huge | High | Sized banner icons | ✅ |
| 4 | Presenter uses a fallback | Demo menu covered the detail header | Med | Menu closes after each action | ✅ |
| 5 | Reload mid-event | Toast fired for P1s that already existed | Med | Existing P1s seeded silently | ✅ |
| 6 | Read the phone confirmation in Arabic | Code and priority out of order (bidi) | Med | Isolated with U+2068/2069 | ✅ |
| 7 | Narrow screens | Overflow at 390 px; cramped funnel at 1100 px | Med | Funnel on its own row ≤1280 px; mobile grid fixed | ✅ |
| 8 | Read the decision log | Option title showed `{staff_moved}` placeholders | **High** | Log now carries the option's parameters | ✅ |
| 9 | Second report on the phone | The previous report's location was pre-selected (silent wrong location) | **High** | Fresh analysis resets choices; cleared after send | ✅ |
| 10 | Start a new phone report | Old "Received" confirmation stayed visible | Low | Cleared when a new report starts | ✅ |
| 11 | Server goes down | Error toast repeated every 1.5 s | Med | One persistent notice + "Connection restored" | ✅ |
| 12 | Tap mic, service silent | Nothing happened | Med | 5 s watchdog with message | ✅ |
| 13 | Second P1 while handling the first | Detail doesn't switch (by design); toast + flash only | Low | Validate with real users (D-15) | Open |
