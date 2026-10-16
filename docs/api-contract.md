# API Contract — EOIP v1

Base: `http://<host>:8000/api`. JSON in and out (UTF-8, Arabic not escaped). Operations APIs require an employee session and CSRF tokens on mutations. `GET /health` is public.
Errors: `{"error": "<code>", ...}`.

| Status | Codes |
|---|---|
| 400 | `validation_error` (with `errors[]`), `note_required`, `recommendation_required`, `invalid_action`, `text_required` |
| 404 | `not_found`, `incident_not_found` |
| 409 | `incident_closed`, `recommendation_not_open` |
| 422 | `needs_review` (voice report with no category or zone; returns `extraction`) |

## Ingestion
### `POST /ingest`
Body: a signal (see data-contract §2).
→ `201 {alert_id, disposition, incident_id, new_incident?}`

```json
{"source_system":"fire_system","category":"fire_alarm","zone_id":"ZONE-A","location_id":"FOOD-COURT","confidence":0.99,
 "payload":{"stage":2,"panel":"FACP-2"}}
```

### `POST /voice/extract`
`{text, language?}` → extraction only, nothing is stored:
`{text, language, category, zone_id, severity_hint, confidence, needs_review, evidence{zone_term, category_terms[], urgency_terms[]}, method}`

### `POST /voice/report`
`{text, language?, category?, zone_id?, input_mode: "voice"|"text"}`. Runs extraction, applies the user's corrections, then ingests the report as a `radio_message`.
→ `201 {alert_id, disposition, incident_id, extraction}`, or `422 needs_review`.

## Ops app reads
### `GET /state?signals=40`
```
{counters:{received, noise, routine, duplicate, needs_review, relevant, by_signal_type{}, incidents_total,
           incidents_open, critical, high, awaiting_decision},
 incidents:[{id, code, type, kind, zone_id, status, priority, priority_score, priority_reasons[], confidence,
             alert_count, source_count, sources[], top_reasons[], opened_at, updated_at, escalated_at, closed_at}],
 signals:[latest alerts with disposition + incident_code],
 zones:[zone + load + worst_priority],
 decisions:[latest 15], demo:{running, speed, cursor, total, elapsed_s, duration_s, finished}}
```
Incidents are ordered: open first, then by priority, score, and recency.

- `GET /incidents/{id}`: the incident plus `zone`, `alerts[]` (including duplicates, each with a `correlation` object: `{reasons[], score, ...}`), `recommendations[]`, `decisions[]`, `source_breakdown[]`, `teams[]`, and `whatif_targets {divert[], redeploy[]}` for operational incidents.
- `GET /zones`, `GET /decisions`, `GET /catalog`, `GET /health`.

## Decisions
### `POST /incidents/{id}/decisions`
`{action: approve|reject|resolve|dismiss, recommendation_id?, note}`. `operator` is ignored if sent.
→ `201 {decision_id, incident}`

| Action | Rules |
|---|---|
| approve | needs `recommendation_id`; the incident becomes `action_approved`; other proposals become `superseded` |
| reject | needs `recommendation_id` + `note` |
| dismiss | needs `note`; the incident becomes `dismissed` |
| resolve | needs `note`; the incident becomes `resolved` |

v2 team rules (synthetic roster):
- **Approving** an emergency or routine plan assigns the teams listed in `params.teams`.
- If one of them is already assigned elsewhere, the response is `409 {error: "team_unavailable"}`, and the proposal is re-planned with the next free team (same `recommendation_id`).
- **resolve** and **dismiss** release the incident's teams.

## What-if simulation (v2, operational incidents only)
### `POST /incidents/{id}/simulate`
Computes an operator-chosen action on the **current** zone state. Nothing is stored.

Body: `{action, target_zone?, share_pct?, staff?, reduction_pct?}`

| action | Required | Range |
|---|---|---|
| `divert` | `target_zone` (same zone kind), `share_pct` | 5–80 |
| `redeploy` | `target_zone` (donor), `staff` | 1 to donor staff |
| `meter` | `reduction_pct` | 10–80 |

→ `200 {action, params, baseline, source, other_zone, other_before, other, checks[], side_effects[], horizon_min: 15}`

Each `checks[]` item is `{code, status: ok|warn|fail, ...values}`. The codes are:
- `source_capacity`
- `source_relief`
- `target_capacity`
- `donor_min_staff`
- `source_min_staff`
- `outside_queue`
- `staff_no_flow_effect`

Errors (`400`): `invalid_action`, `invalid_target`, `invalid_share`, `invalid_staff`, `invalid_reduction`. `simulation_operational_only` is returned for a non-operational incident.

### `POST /incidents/{id}/options`
Same body as `/simulate`. Computes and **saves** the result as an approvable recommendation:
- `rank` is 90 or higher.
- `params.custom = true`.
- It survives refreshes.

→ `201 {recommendation_id, incident}`, or `409 incident_closed`.

## Teams (v2)
- `GET /teams` returns `{teams: [{id, name_ar, name_en, kind, base_zone, members, status, incident_id, assigned_at}]}`.
- `/state` also includes `teams`.

## Demo control (presenter only)

| Endpoint | Effect |
|---|---|
| `POST /demo/reset` | Wipe operational data, restore baseline zones |
| `POST /demo/start {speed}` | Start playback (resets first if a previous run exists). Speed is 0.25–10 |
| `POST /demo/tick` | Ingest the signals that are due. Called by the ops app each poll while running |
| `POST /demo/stop` | Pause |
| `POST /demo/skip` | Ingest the whole script now (review mode / fallback) |
| `POST /demo/cv-replay` | Camera fallback. Sends a recorded person-down detection with `origin: replay_cv`, shown as "Camera replay" in the UI |

## v3 additions (2026-10-09)

### Layout
- `GET /layout` returns the illustrative map: `{note, zones: [{id, shape, map}], locations: [{id, zone_id, name_ar, name_en, map}], walkways}`.
- `/state` also returns `locations` (with `open_incidents`, `worst_priority`).
- Incidents carry `location_id` and `label` (`fire | medical | crowding | staff_shortage | crowding_staff | facility | it_system`).

### Signals with a location
`POST /ingest` accepts an optional `location_id`:
- It must be one of the six locations and belong to `zone_id` (400 otherwise).
- When `zone_id` is omitted, the zone is taken from the location.

### Field report
`POST /voice/report` accepts:
```json
{"text", "category"?, "zone_id"?, "location_id"?, "location_other"?, "input_mode": "voice|text",
 "recorded_at"?, "stt_confidence"?}
```
- `zone_id: ""` means the zone is not known. The report is stored as `needs_review` and is not linked to an incident.
- `location_id: "other"` together with `location_other` stores free-text details.
- The event type is required: `422 needs_review` if it is missing.
- Response: `{alert_id, disposition, incident_id, incident: {id, code, priority, status} | null, extraction}`.

`POST /voice/extract` returns `{event, category, report_kind, zone_id, zone_source, location_id, review_reasons[], candidates[], confidence, evidence, method: "rules_v2_lexicon"}`.

### Decisions
- The server uses the authenticated employee record as the decision author; it ignores client-supplied operator names.
- Approve, reject, resolve and dismiss require a non-empty `note` reason. New rows store the verified display name, `employee_id`, `employee_number`, `created_at`, and reason.
- Unauthenticated API requests return `401 unauthorized`; missing or invalid `X-CSRF-Token` on mutations returns `403 csrf_failed`.
- Each decision stores a `snapshot` and a `run_id`.
- `GET /decisions` returns `{decisions: [{..., snapshot, current_run}], current_run}`.
- The log is permanent: `/demo/reset` keeps it.

### Authentication
- `GET /login` returns the employee-number/password form and a pre-authentication CSRF token.
- `POST /login` verifies the employee number, password hash and CSRF token. Invalid credentials receive the same generic response.
- `POST /logout` revokes the current server-side session and requires CSRF.
- Sessions expire after eight hours. No employee is seeded; create accounts with `flask --app run.py employee-add`. Password recovery is not implemented.

### Staffing what-if
`/simulate` and `/options` with `action: "redeploy"` take `target_zone` (where the staff come from), an optional `to_zone` (the receiving zone; default is the incident zone) and `staff`. Every result includes `staff: {source: {zone, before, after, required}, other?: {...}}`, plus `source_zone` and `capacity` in each projection.

### Camera (phone / browser), analysed on the server with the same detector as the laptop agent

| Endpoint | Body | Result |
|---|---|---|
| `GET /cv/status` | | `{available, detector, trained_model: false}` |
| `POST /cv/sessions` | `{zone_id, location_id?}` | `201 {session_id, camera_id, warmup_frames}` |
| `POST /cv/sessions/{id}/frame` | raw JPEG (`Content-Type: image/jpeg`), header `X-Frame-Time` (ms) | `{state: learning\|empty\|upright\|transition\|lying\|alerted, frames, warmup, bbox, alert}` |
| `DELETE /cv/sessions/{id}` | | `{frames, alerts}` |
| `POST /cv/video` | multipart `video`, `zone_id`, `location_id?` | `201 {frames, fps, duration_s, events[], alerts[]}` |

- A detection from live frames is sent as origin `live_cv`; one from a video file as `video_file`; `/demo/cv-replay` sends `replay_cv` and does no analysis.
- Errors: `cv_unavailable` (503), `zone_required`, `location_not_in_zone`, `video_required`, `video_unreadable` (422), `session_not_found` (404), `invalid_frame`.
