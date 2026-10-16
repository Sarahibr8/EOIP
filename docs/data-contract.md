# Data Contract — EOIP v3 (schema `PRAGMA user_version = 3`)

Single source of truth shared by AI, Backend, Frontend and Database.
Code mirrors: `eoip/schema.sql` (tables + CHECK constraints) and `eoip/catalog.py` (enums + rule parameters).
**Any change here needs Team Leader approval** and must update both files and the tests.

Data origin legend: **MOCK** synthetic by the team · **LIVE** produced at demo time by a real component · **DERIVED** computed by EOIP.

## 1. Entities and relationships

```
zones 1───* alerts *───0..1 incidents 1───* recommendations
                               │ 1
                               └──* decisions *───0..1 recommendations
demo_state (single row, demo playback cursor)
```

- An **alert** is one incoming signal from any source, after normalization.
- An **incident** is EOIP's grouping of related alerts (same family, same zone, within the time window).
- A **recommendation** is a playbook, a simulated option, or a routing.
- A **decision** is a human action. It is append-only and is never edited.

## 2. Signal input (what any source sends to `POST /api/ingest`)

| Field | Type | Req | Validation / notes |
|---|---|---|---|
| source_system | enum | ✔ | `fire_system, cctv_ai, crowd_sensors, queue_sensors, radio, service_desk, staff_roster, bms, it_monitoring, access_control` |
| category | enum | ✔ | see §6 |
| signal_type | enum | – | `alert, radio_message, service_request, system_notification` (the four input types named in Challenge 3.6). Defaults from source_system |
| zone_id | FK zones | ✔* | *may be empty only if raw_text is given → `needs_review` |
| confidence | float 0..1 | – | default 1.0 (deterministic systems); AI sources must send their real confidence |
| severity_hint | int 1..5 | – | default 1, clamped |
| raw_text | text | – | radio transcript / request text |
| language | `ar`/`en` | – | |
| location_detail | text | – | e.g. "East wing, near exit C3" |
| payload | object | – | source-specific (below) |
| origin | enum | – | `mock, live_cv, replay_cv, voice, text`; default `mock`. **Honesty field**: a replayed detection can never claim to be live |
| occurred_at | ISO-8601 | – | default = received time |
| external_ref | text | – | id in the source system |

Payload fields EOIP reads (others are stored as-is):

| category | payload key | effect |
|---|---|---|
| occupancy_high | `occupancy` (int) | updates `zones.occupancy` |
| staff_shortage | `on_duty`, `required` | updates zone staffing |
| any | `inflow_per_min` | updates zone inflow |
| queue_long | `wait_min` | priority reason "long queue" |
| fire_alarm | `stage` (1/2) | stage 2 adds +15 to priority |
| hvac_temp_high | `temp_c` | ≥ 30 °C adds +10 |
| person_down | `camera_id, detector, aspect, lying_s, height_drop, snapshot` | evidence shown to the operator |
| radio (voice) | `extraction{method, evidence, auto_category, auto_zone, corrected_by_user}` | traceability of AI output |

## 3. Tables

### zones (seeded from `data/zones.json`, MOCK, illustrative layout)
`id` PK text · `name_ar` · `name_en` · `kind` (gate|hall|plaza|food|transport) · `criticality` 1–3 · `capacity` >0 · `occupancy` · `inflow_per_min` · `outflow_per_min` · `staff_on_duty` · `staff_required` · `neighbors` JSON[] · `map_x/y/w/h` (schematic).

### alerts
All §2 fields plus:
- `received_at` (server time)
- `disposition`: `correlated | duplicate | noise | routine | needs_review` (DERIVED)
- `duplicate_of` FK alerts (the root alert)
- `incident_id` FK incidents
- `correlation` JSON (v2, DERIVED): why this alert was linked, for example:
  ```json
  {"reasons": ["same_family", "same_zone", "within_window", "incident_open", "independent_source"],
   "score": 1.0, "gap_s": 2, "incident_code": "INC-0002"}
  ```
  - Reason codes:
    - `same_family`
    - `same_zone`
    - `within_window`
    - `incident_open`
    - `independent_source` or `same_source_update`
    - `same_location`
    - `duplicate_of` (with `of` and `seconds`)
    - `no_open_match` (first alert of a new incident)
  - `score` is a **rule score** (0.5 + 0.3 × time proximity + 0.2 for a new independent source), not a model output.
  - Added by an idempotent migration (`ALTER TABLE`) for databases created before v2.

Indexes: `(incident_id)` and `(source_system, category, zone_id, received_at)` for the duplicate check.

### incidents (DERIVED)
- `id`, `code` (`INC-0001`)
- `type` (fire|medical|crowd_pressure|facility|it_system), `kind` (emergency|operational|routine)
- `zone_id`
- `status` (open|action_approved|resolved|dismissed)
- `priority` P1–P4, `priority_score` 0–100, `priority_reasons` JSON `[{key, points, params}]`
- `confidence` (combined evidence)
- `alert_count` (including duplicates), `source_count` (distinct independent systems)
- `opened_at`, `updated_at`, `escalated_at`, `closed_at`

### recommendations (DERIVED)
- `incident_id`
- `code` (`FIRE-01`, `MED-01`, `redeploy_staff`, `divert_inflow`, `meter_entry`, `route_team`), `rec_type` (playbook|option|route), `rank`
- `params` JSON
- `simulation` JSON (options only, see §5)
- `status` (proposed|approved|rejected|superseded)
- `created_at`

### teams (v2, seeded from `data/teams.json`, MOCK roster)
`id` (`FIRE-1`, `MED-1`, …) · `name_ar` · `name_en` · `kind` (fire|medical|steward|security|facilities|it) · `base_zone` FK zones · `members` · `status` (available|assigned) · `incident_id` · `assigned_at`.

- **ETA** = 1 min mobilisation + 2.5 min × hops on the zone-neighbour graph. This is an estimate on a synthetic layout, not routing.
- Recommendations carry the chosen team in `params.teams` as `[{team_id, kind, from_zone, hops, eta_min, members}]`, and the reason keys in `params.why`.

### decisions (append-only audit log)
`incident_id` · `recommendation_id` · `action` (approve|reject|resolve|dismiss) · `operator` · `note` (required for reject and dismiss) · `priority_at_decision` · `created_at`.

## 4. Lifecycles

**Incident:** `open` → approve → `action_approved` → resolve → `resolved`. From `open`, dismiss (note required) → `dismissed`. Closed incidents accept no decisions and new alerts open a new incident.

**Recommendation:** `proposed` → approved, or rejected (note required). On approval, the other proposals → `superseded`. Rejected codes are never re-proposed for the same incident. Operational options are regenerated as zone state changes, until one is approved. Operator-defined options (rank ≥ 90, `params.custom`) are kept. Emergency and routine proposals are updated **in place** (same id) as evidence arrives, so the "why" and the assigned team always match the current evidence.

## 5. Simulation JSON (option recommendations)

```json
{"baseline": Projection, "source": Projection, "other_zone": "GATE-E"|null, "other": Projection|null,
 "side_effects": [{"key": "outside_queue", "params": {"people": 675}}], "score": 0.88}
```

v2 adds:
- `action`, `params` (target / share / staff / reduction)
- `other_before`
- `checks[]` (`{code, status: ok|warn|fail, ...}`; see the API contract)
- `horizon_min`

Gate processing = staff × 16 people/min. Occupancy(t) = occupancy + (inflow − processing) × t.

`Projection = {occupancy_now, occupancy_end, load_now, load_end, net_per_min, wait_now_min, wait_end_min, minutes_to_capacity}` over a 15-minute horizon.

## 6. Category catalogue (rules in `catalog.CATEGORIES`)

| Family → incident type | Categories |
|---|---|
| fire (emergency) | smoke_detected, fire_alarm, smoke_report, burning_smell |
| medical (emergency) | person_down, medical_request, medical_report |
| crowd_pressure (operational) | occupancy_high\*, queue_long\*, crowd_report, staff_shortage\*, staff_shortage_report |
| facility (routine) | elevator_fault, hvac_temp_high, water_leak, cleaning_request, restroom_supply |
| it_system (routine) | wifi_degraded, pos_offline, display_offline |
| — routed, no incident | lost_item, info_request, wheelchair_request, status_update |
| — noise, filtered | heartbeat, test_alarm, auto_cleared, door_held |

\* stateful: these carry a measurement, update the zone, and are never treated as duplicates.

## 7. Rule parameters (tunable, `catalog.py`)

| Parameter | Value | Meaning |
|---|---|---|
| DUPLICATE_WINDOW_SEC | 120 | same system + category + zone inside this window = duplicate |
| CORRELATION_WINDOW_SEC | 900 | attach to an open incident of the same family and zone updated inside this window |
| GATE_PROCESSING_PER_STAFF | 16 /min | gate throughput per screener |
| SIM_HORIZON_MIN | 15 | simulation horizon |
| P1 / P2 / P3 thresholds | 75 / 50 / 25 | score → priority |
| OPERATIONAL_SCORE_CAP | 74 | operational incidents stay below P1 … |
| OVER_CAPACITY_RATIO | 0.98 | … unless the zone is effectively full |

## 8. Synthetic data (`data/demo_script.json`, seed 2030)
263 signals over 80 s:

- **Noise:** 144
- **Routed requests and radio chatter:** 62
- **Facility/IT clusters:** 43 signals, forming 8 low-priority incidents
- **S3 crowd story:** 7 signals
- **S1 fire story:** 7 signals

All four official input types are present. Regenerate with `python data/generate_mock.py`; the output is identical every time.

## v3 changes (2026-10-09)
- **Layout:** `zones` now holds ZONE-A / ZONE-B / ZONE-C. The new `locations` table (`id, zone_id, name_ar, name_en, map_x, map_y`) holds the six locations. Both are seeded from `data/zones.json`, which is illustrative, not the official plan.
- **New columns:**
  - `alerts.location_id` and `incidents.location_id` (NULL = not stated). `alerts.location_detail` keeps free text ("other location", device position).
  - `teams.base_location`; `teams.base_zone` is derived from it.
- **Origin `video_file`:** an uploaded or recorded video analysed by the detector (not live). `live_cv` is a live stream (laptop agent or phone camera); `replay_cv` is a re-sent recorded detection.
- **Decisions are permanent.** `decisions.incident_id` / `recommendation_id` are `ON DELETE SET NULL`, `operator` must be non-blank, and `run_id` is the event run (`demo_state.run_id`, incremented by every reset). `snapshot` is JSON taken at decision time:
  ```json
  {"incident_code", "incident_type", "incident_kind", "incident_label", "zone_id", "location_id",
   "recommendation": {"id", "code", "rec_type", "rank", "params",
                      "simulation": {"action", "source_zone", "other_zone", "load_now", "load_no_action",
                                     "load_with_option", "other_load_before", "other_load_after",
                                     "staff", "checks": {"ok", "warn", "fail"}}},
   "teams": [{"id", "kind", "base_location"}],
   "names": {"<zone|location|team id>": {"ar", "en"}}}
  ```
- **Migration from v1/v2 (automatic at start):**
  - Existing decisions are read with their incident, zone and option, and re-inserted with a snapshot (`legacy_layout: true`, run 1).
  - Operational tables (signals, incidents, recommendations, teams) are rebuilt; they are demo data.
  - Covered by `tests/test_v2.py::Migration`.
- **Linking (`rules_v3`):** reason keys add `same_location`, `location_not_stated` and `different_location`. For emergency and routine incidents, a stated location different from the incident's stated location starts a new incident. Operational pressure links by zone.
- **Lexicon:** `data/lexicon.json` holds the zone and location aliases, event terms, negation cues and urgency terms, all in one place.
