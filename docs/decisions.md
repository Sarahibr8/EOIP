# Decision Log — EOIP MVP (2026-10-08)

Format: decision · reason · trade-off · owner to confirm.

| ID | Decision | Reason | Trade-off | Confirm |
|---|---|---|---|---|
| D-01 | **Flask + SQLite instead of Django + SQLite** | Django could not be installed in the build environment (package registry blocked); Flask was available, so the MVP could be run and tested end to end today | The team knows Django. Mitigation: business logic (`eoip/core`) is framework-free; a Django port only rewrites `api.py`, `web.py` and `db.py` (≈1 day). Models map 1:1 from `schema.sql` | **Team Leader** |
| D-02 | Fire is detected through the fire-alarm system + radio, not the camera | Venues detect fire through panels and detectors; laptop-camera fire detection is unreliable | Less "AI" in S1, more realism | Done |
| D-03 | Camera = person-down only, **YOLO deep-learning person detector** + posture rule (replaces the earlier classical OpenCV MOG2 detector) | A trained detector does not need an empty background and handles lighting / moving camera better; matches the project description | Needs `ultralytics` (PyTorch) and the weights file; slower on CPU; pretrained on COCO, **not** fine-tuned on falls; fall = posture rule on the person box | Team (CV) |
| D-04 | Crowding + staff shortage = one operational incident | The shortage causes the pressure; it shows correlation across different alert types | — | Done |
| D-05 | Rules for correlation, priority, recommendations; AI only for speech and vision | No labelled data; operators need explanations; safety playbooks must be pre-approved | Weights are expert guesses, to be tuned with real data | Team (AI) |
| D-06 | Voice extraction is rule-based Arabic NLP, not an LLM | Offline, instant, traceable evidence; 14/14 golden cases | Less flexible with unusual phrasing; `extract()` is the seam for an LLM later | Team (AI) |
| D-07 | Operational incidents are capped below P1 unless the zone is ≥98% full | They must never outrank life-safety without reason | A full gate is still escalated | Done |
| D-08 | Evidence counts independent *source systems*, not alerts | Repeats from one system are not confirmation | — | Done |
| D-09 | 1.5 s polling, no WebSockets/Redis/Celery | Simplest reliable option for one screen | ≤1.5 s latency | Done |
| D-10 | Synthetic event script: 263 signals, seed 2030, clearly labelled | Expo provided no data; reproducible demos and tests | Volumes are illustrative, not official | Done |
| D-11 | Illustrative site schematic (10 zones), not the official layout | The official plan is not available | Labelled on screen | Done |
| D-12 | ~~No authentication; operator name is a localized default ("مشرف العمليات" / "Ops supervisor")~~ Superseded by D-28 | Original MVP scope excluded authentication | Decision log was later updated to verified employee identities | Superseded |
| D-13 | Backend returns keys, never sentences; UI translates | Bilingual from day 1, no hard-coded text | Slightly more work per new reason/step | Done |
| D-14 | Camera fallback is labelled `replay_cv` everywhere | Never present a replay as live detection | — | Done |
| D-15 | ~~A new P1 auto-opens~~ → v2: a new P1 raises a persistent red toast that links to its decision page | With several pages, jumping pages under the operator is disruptive | One extra click | Open (validate with operators) |
| D-16 | v2 UI: multi-page app (hash router) instead of one dashboard; light "limestone" identity, one dark navigation rail, a site plan as the signature element | Each page answers one operator question; it avoids a generic dark AI-dashboard look | More files; still no build step | Done |
| D-17 | One shared store (`/api/state` poll) for all pages | All pages always show the same data | — | Done |
| D-18 | Store the *why linked* reasons per alert (`alerts.correlation`) and show a rule score | Operators must see why reports were merged; similar words never merge on their own | Extra column (migrated in place) | Done |
| D-19 | Synthetic team roster with hop-based ETA | Recommendations need "who" and "how soon"; no real roster is available | Labelled as demo data everywhere | Done |
| D-20 | Operator what-if is computed on the server and can be saved as an option | No static numbers presented as dynamic; the human can test alternatives | Crowd incidents only | Done |
| D-21 | Emergency proposals are updated in place as evidence arrives | The "why" must match the current evidence (a bug found in review showed "single source" with 3 sources) | — | Done |
| D-22 | Zones renamed and restructured to Zone A/B/C + six locations; internal ids `ZONE-A…`, location ids `FOOD-COURT…` | Final MVP spec; one source (`data/zones.json`) for every page | Old 10-zone ids replaced (not a display-only rename, because the structure changed); old decisions kept with snapshots | Done |
| D-23 | Location-aware linking for emergency and routine incidents; zone-level for operational pressure | Two fires at two named places are two events; a crowded zone is one state | A report without a location still links (reason shown) | Done |
| D-24 | Lexicon in `data/lexicon.json`, negation, ambiguity → review, zone-from-location marked | Spec: no guessing, editable keywords | Rules, not a model; limits in limitations.md | Done |
| D-25 | Phone camera = JPEG frames to the server, analysed by the SAME detector; plus video upload; replay kept | Works on any phone browser with HTTPS; no new dependency; honest origins | About 6 fps; needs a still phone | Done |
| D-26 | Operator name required; snapshot per decision; log survives reset and restart; explicit `--clear-decision-log` | "Who decided" must be recorded and kept | Name not authenticated (stated in UI) | Done |
| D-27 | ~~Fonts: Google Fonts link plus system fallback~~ Superseded by D-29 | Original build used a web-font link | v4 uses local/system fallback stacks so the interface renders offline | Superseded |
| D-28 | Local employee authentication: scrypt password hashes, opaque server-side sessions, CSRF protection, and employee identity on every decision | Decision authorship must be verified locally without inventing real employee accounts | No SSO, MFA, throttling or self-service recovery; host administrator provisions accounts | Done for MVP |
| D-29 | Warm Riyadh-inspired identity: deep green `#123D35`, cream `#F5F1E8`, warm-white panels, restrained brass `#C6A66B`; local panorama asset on login | A calm, legible operations interface that works offline in Arabic and English | Uses a locally bundled illustrative image, not an official Expo site image | Done for MVP |
