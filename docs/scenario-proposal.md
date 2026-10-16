# Scenario Proposal & Decision — EOIP MVP

Status: **DECIDED** (Team Leader delegated the decision on 2026-10-08; open for review).

## 1. What the scenarios must prove

Challenge 3.6 is not "detect events". It is: *the ops center cannot tell what needs immediate intervention when hundreds of alerts, radio messages, service requests and system notifications arrive from separate parties during a live event.*

So every scenario must exercise at least one of:
1. **Volume** — many signals, most of them not urgent.
2. **Separation** — the same situation reported by different, unconnected parties.
3. **Discrimination** — the system ranks the truly urgent above the merely loud.
4. **Decision** — the operator knows what to do and what it will cause.

## 2. Review of the earlier plan (4 cases)

| Earlier case | Earlier source | Finding | Change |
|---|---|---|---|
| Fire | Camera CV | Venues detect fire through fire-alarm panels and smoke detectors, not laptop CCTV. Camera fire detection is unreliable and unrealistic. | Fire now comes from **mock fire-alarm system + smoke detector + radio confirmation**. |
| Fainting / fall | Camera CV | Feasible with a YOLO person detector + posture rule under controlled conditions. | Keep on **live CV**, corroborated by **voice/radio** or a **medical service request**. |
| Crowding | Voice | Crowding is normally measured by sensors; radio adds context. | **Crowd sensors + queue sensor + radio**. |
| Staff shortage | Voice | On its own it is rarely "immediate". It matters because it *causes* crowding. | **Merged with crowding** into one operational incident (roster system + radio). |

## 3. Final scenario set

| ID | Scenario | Kind | Sources (official input type) | Simulation |
|---|---|---|---|---|
| S1 | Fire / smoke in Zone A at the Food Court | Emergency | Smoke detector (alert), fire-alarm panel (alert/system), radio (radio message) | **No** — playbook only |
| S2 | Person down in Zone B at the Main Walkway | Emergency | Live CV (alert), field voice report (radio message) or medical request (service request) | **No** — playbook only |
| S3 | Crowding + staff shortage in Zone C at the Main Gate | Operational | Crowd sensor + queue sensor (alerts), staff roster (system notification), radio | **Yes** — ranked options with impact preview |
| S0 | Background load | Routine/noise | All four input types: heartbeats, test alarms, auto-clears, duplicates, cleaning, Wi-Fi, POS, elevator, HVAC… | No |

S0 is not a "case" but it is what makes 3.6 visible: without it, the demo would show 3 alerts producing 3 incidents, proving nothing about triage.

## 4. Scenario details

### S1 — Fire / smoke in Zone A at the Food Court
- **Why 3.6:** the classic "separate parties" case. A detector, the fire panel and a supervisor's radio all report the same thing on different channels.
- **Start:** smoke detector in Zone A (Food Court) reports smoke (confidence 0.74), then repeats (duplicate).
- **Input:** `alert/smoke_detector/smoke_detected`, then radio "فيه دخان طالع من قاعة ج…", then `fire_alarm_panel/fire_alarm stage 2` (and panel repeats).
- **System understanding:** radio text → category `smoke_report`, zone `ZONE-A`, location `FOOD-COURT` (rule-based Arabic extraction).
- **Alert → incident:** same incident family (fire) + same zone + inside the 15-minute window → correlated into one incident. Repeats from the same device inside 2 minutes are marked duplicate.
- **Priority:** one sensor → P2 "unconfirmed". A second independent source → confirmation bonus → **P1**.
- **Shown to operator:** P1 badge, the reasons ("confirmed by 3 independent sources", "fire panel stage 2", "high-occupancy zone"), source chips, and a timeline.
- **System suggests:** playbook FIRE-01 (dispatch fire team, notify civil-defense liaison, evacuate the zone via PA and stewards, hold entry at adjacent gates, medical standby).
- **Simulation:** not used. In a life-safety case, a simulation delays action.
- **AI:** voice extraction only. **Rules:** correlation, duplicate detection, priority, playbook.
- **Human decision:** "Activate playbook", or "Dismiss as false alarm" (a note is required).
- **End:** incident status → `action_approved` → `resolved`. Every step is logged.
- **Demo value:** high. Live escalation P2 → P1 is the strongest visual proof of "telling what is urgent".
- **Complexity:** low. **Risk:** low (fully scripted, deterministic).

### S2 — Person down in Zone B at the Main Walkway
- **Why 3.6:** an AI camera signal on its own is uncertain. Corroboration from a human channel is what makes it urgent.
- **Start:** a presenter falls or lies down in front of the laptop camera.
- **Input:** `alert/cctv_ai/person_down` (origin `live_cv` with confidence), then a voice report on the phone, "شخص مغمى عليه في زون B عند الممر الرئيسي", or a medical service request.
- **Alert → incident:** medical family + same zone + time window → correlated.
- **Priority:** CV alone → P2. CV + human confirmation → **P1**.
- **System suggests:** playbook MED-01 (dispatch the nearest medical team, a steward secures the space, notify the zone supervisor).
- **Simulation:** none.
- **AI:** CV (person-down detection) + voice extraction. **Rules:** everything else.
- **Fallback:** CV replay button, clearly labelled `REPLAY — recorded detection`. It is never presented as live.
- **Demo value:** high, because it is live and physical. **Risk:** medium (lighting, background). Mitigated by the replay fallback.

### S3 — Crowding + staff shortage in Zone C at the Main Gate
- **Why 3.6:** an operational problem that needs judgment, not a reflex. Several weak signals add up to one incident.
- **Inputs:** occupancy rises 78% → 88% → 94%; queue wait reaches 18 minutes; the roster reports 3 of 6 staff on duty; a radio report says the gate needs support.
- **Alert → incident:** crowd family (crowd and staffing both) + same zone → one incident. Zone state (occupancy, staff) is updated from the signal payloads.
- **Priority:** P2. Operational incidents are capped below P1 unless occupancy reaches ≥ 98%, so they never outrank life-safety without reason.
- **System suggests (ranked):**
  1. Redeploy surplus staff from a neighbouring gate.
  2. Divert part of the inflow to the least-loaded neighbouring gate.
  3. Meter entry at the gate.
- **Simulation:** yes. A 15-minute arithmetic projection shows source vs. target occupancy, queue wait, and side effects (target > 85%, donor below required staff, queue outside the gate).
- **Human decision:** approve one option or reject it with a reason. The other options are marked superseded.
- **Demo value:** high. It shows "what happens if I choose this?", which answers the decision part of the problem. **Risk:** low.

## 5. Scope decisions
- **Cut:** fire detection by camera; drones (listed as a track skill, not required by 3.6); a real radio/PTT integration; maps or GIS; authentication; WebSockets.
- **Kept small:** zones are an illustrative site schematic, **not** the official Expo 2030 layout.

## 6. Relation to evaluation
Expo's evaluation criteria and weights were not available. The scenarios are mapped instead to the official 3.6 wording and to the required project-file items (see `expo-requirements-matrix.md`).
