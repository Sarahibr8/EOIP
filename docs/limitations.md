# Known Limitations — EOIP MVP

## Real / Mock / Simulated / AI / Rule-based

| Part | What it is |
|---|---|
| Fire panel, smoke detectors, crowd/queue sensors, roster, BMS, IT, access control, service desk | **Mock**: scripted synthetic signals (`data/demo_script.json`) |
| Zones (A/B/C), six locations, capacities, staffing, map | **Mock**: illustrative demo names and figures, not the Expo site plan |
| Signal volume (263) | **Mock**: chosen to demonstrate triage; not an official figure |
| Phone as radio | **Simulated** radio channel; speech recognition is **real (AI)** via the browser |
| Report understanding | **Rule-based NLP**, real, runs on any text |
| Camera person-down | **Deep learning**: pretrained YOLO (COCO `person`, not fine-tuned on falls) + a posture rule (standing → lying ≥ 1 s). Sources: the laptop camera agent or the phone camera (`live_cv`), an uploaded video (`video_file`), or a **replay** with no analysis (`replay_cv`). Accuracy on real people is **not measured** |
| Correlation, duplicates, priority, recommendations | **Rule-based**, real code |
| Impact simulation | **Simulated**: a simple arithmetic flow model, not a crowd-dynamics model |
| Response teams, team positions, ETA | **Mock**: synthetic roster (`data/teams.json`); ETA = 1 min + 2.5 min per zone hop on the illustrative layout, not real routing or GPS |
| Correlation link score | **Rule score** (0–1), not a trained model |
| What-if results | **Computed** live by the same flow model, from current (synthetic) zone state |
| Decisions and log | **Real**, stored in SQLite |

## Technical limitations
1. **Django → Flask** (decision D-01). Port before handing over to a Django-based team, if required.
2. **Speech recognition:**
   - Needs a browser with the Web Speech API (Chrome/Edge; Android Chrome is best) and usually internet.
   - The phone mic needs HTTPS (`run.py --https`, self-signed certificate warning). On plain HTTP the page disables the mic and says why.
   - If the speech service doesn't answer within 5 s, the page says so and the operator types instead.
3. **Live CV not validated on people** in this environment (no camera). Expect sensitivity to camera angle, lighting, occlusion and multiple people (the largest person in view is tracked). No background learning is needed.
4. **CV snapshots** are stored in `static/snapshots/`, with no face blurring. Demo only; never on real visitors.
5. **Extraction:**
   - The lexicon covers the three illustrative zones A/B/C and six demo locations.
   - Negation handling covers short cues near the event term; longer or unusual phrasing can still need review.
   - One zone per report.
6. **Priority weights and thresholds** are expert assumptions, not tuned on data.
7. **Correlation** uses the same zone only (no adjacency or geo radius). One incident per family and zone within a 15-minute window. Free text never links reports on its own: it is first mapped to a category and a zone.
8. **Local MVP authentication:** employee accounts are provisioned on the host, with scrypt password hashes and eight-hour server-side sessions. There is no SSO, MFA, login throttling, role model, managed password recovery, or account-management UI; account changes require host-side administration. Multiple authenticated users can use the same local app, but there is no multi-screen push sync beyond polling.
9. **Simulation:**
   - Gates are modelled as queues served by staff.
   - Halls and plaza use fixed outflow.
   - What-if and ranked options cover crowd pressure only.
   - Emergencies get a fixed playbook and the nearest free team; nothing is simulated.
10. **Fonts:** the UI uses local/system font stacks (Segoe UI / Tahoma on Windows); it does not need Google Fonts to render.
11. **Teams:** one team serves one incident at a time; no shifts, no partial crews, no team status from the field (the operator resolves to release).
12. **Map:** an illustrative schematic of three zones and six locations, not a GIS map or the official site plan.
13. **Not tested on the real hardware here:** the laptop camera, the phone microphone and the projector resolution. Browser tests ran in headless Chromium at 1440 px and 390 px.

## Not built (by design)
Drones, real radio/PTT integration, GIS maps, centralized SSO, MFA, managed password recovery, mobile app, LLM summaries, ML priority model, notifications to field teams.

## v3 limitations (2026-10-09)
1. **Not tested on a real phone in this environment:**
   - Phone microphone + browser speech recognition.
   - Phone camera (live).
   - Filming a screen with the phone.

   The browser tests used Chromium's fake microphone and a fake camera fed from the synthetic clip. These are **pending manual tests** (see `testing.md`).
2. **Filming a screen with a phone:** YOLO must still recognise a person on the screen, so keep the person large and fully in frame, and the phone on a stand.
3. **The detector:**
   - Needs about 3–4 s of empty, still scene first.
   - Assumes one person.
   - Can miss partial views or low light.
   - Has no measured accuracy.
4. **Operator identity:** employee accounts are local MVP records, not synchronized to an official directory. The host administrator must provision and deactivate accounts; there is no self-service recovery or login throttling.
5. **Zone from location:** when a report names a location but no zone, the zone is filled in from the layout (each location belongs to one zone). It is labelled "from the location" for review.
6. **Extraction:** rules plus a central lexicon. Unusual phrasing, spelling or speech-recognition errors can be missed; the reporter reviews before sending. Negation covers short cues just before the event word.
7. **Location-level state:** occupancy and staffing are per zone, not per location.
8. **Live camera session state** is kept in server memory. A server restart ends sessions; the phone shows "session ended".
9. **Fonts:** local/system font stacks are used so login and operations pages render without a network connection.
