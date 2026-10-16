"""Static catalogue: enums, source systems, signal categories and their rules.

This file is the code-level single source of truth for the enums documented in
docs/data-contract.md. Human-readable labels live in static/i18n/{ar,en}.json,
never here, so the backend stays language-neutral.
"""

SIGNAL_TYPES = ("alert", "radio_message", "service_request", "system_notification")
# live_cv    = a camera stream analysed as it happens (laptop agent or phone camera)
# video_file = an uploaded / recorded video file analysed by the same detector (not live)
# replay_cv  = a pre-recorded detection re-sent as a fallback (no analysis happens)
ORIGINS = ("mock", "live_cv", "video_file", "replay_cv", "voice", "text")
DISPOSITIONS = ("correlated", "duplicate", "noise", "routine", "needs_review")
INCIDENT_STATUSES = ("open", "action_approved", "resolved", "dismissed")
OPEN_STATUSES = ("open", "action_approved")
DECISION_ACTIONS = ("approve", "reject", "resolve", "dismiss")

# Source system -> default signal type.  A "source system" is one independent
# channel: two alerts from the same system never count as independent evidence.
SOURCE_SYSTEMS = {
    "fire_system": "alert",            # smoke detectors + fire-alarm panel
    "cctv_ai": "alert",                # camera analytics (our CV agent)
    "crowd_sensors": "alert",          # occupancy counters
    "queue_sensors": "alert",          # queue length / wait estimation
    "radio": "radio_message",          # field supervisors (simulated by phone)
    "service_desk": "service_request", # visitor / staff service requests
    "staff_roster": "system_notification",
    "bms": "system_notification",      # building management (HVAC, elevators, water)
    "it_monitoring": "system_notification",
    "access_control": "system_notification",
}

# Incident families.  kind decides UX: emergency -> playbook, operational ->
# ranked options + simulation, routine -> route to owning team.
INCIDENT_TYPES = {
    "fire": "emergency",
    "medical": "emergency",
    "crowd_pressure": "operational",
    "facility": "routine",
    "it_system": "routine",
    "visitor_conduct": "routine",      # visitor behaviour (normal priority): sent to the field team
}

# category -> rule metadata
#   family:   incident type it feeds (None = never creates an incident)
#   handling: 'incident' | 'routine' (auto-routed, no ops incident) | 'noise' (filtered)
#   stateful: carries a measurement that updates zone state; never a duplicate
CATEGORIES = {
    # fire
    "smoke_detected":   {"family": "fire", "handling": "incident"},
    "fire_alarm":       {"family": "fire", "handling": "incident"},
    "smoke_report":     {"family": "fire", "handling": "incident"},
    "burning_smell":    {"family": "fire", "handling": "incident"},
    # medical
    "person_down":      {"family": "medical", "handling": "incident"},
    "medical_request":  {"family": "medical", "handling": "incident"},
    "medical_report":   {"family": "medical", "handling": "incident"},
    # crowd / staffing
    "occupancy_high":   {"family": "crowd_pressure", "handling": "incident", "stateful": True},
    "queue_long":       {"family": "crowd_pressure", "handling": "incident", "stateful": True},
    "crowd_report":     {"family": "crowd_pressure", "handling": "incident"},
    "staff_shortage":   {"family": "crowd_pressure", "handling": "incident", "stateful": True},
    "staff_shortage_report": {"family": "crowd_pressure", "handling": "incident"},
    # facility
    "elevator_fault":   {"family": "facility", "handling": "incident"},
    "hvac_temp_high":   {"family": "facility", "handling": "incident"},
    "water_leak":       {"family": "facility", "handling": "incident"},
    "cleaning_request": {"family": "facility", "handling": "incident"},
    "restroom_supply":  {"family": "facility", "handling": "incident"},
    # IT
    "wifi_degraded":    {"family": "it_system", "handling": "incident"},
    "pos_offline":      {"family": "it_system", "handling": "incident"},
    "display_offline":  {"family": "it_system", "handling": "incident"},
    "gate_fault":       {"family": "facility", "handling": "incident"},    # turnstile / gate system fault
    # visitor behaviour (camera or radio): normal priority, the field team handles it
    "visitor_fight":        {"family": "visitor_conduct", "handling": "incident"},
    "visitor_sitting_path": {"family": "visitor_conduct", "handling": "incident"},
    "visitor_wrong_way":    {"family": "visitor_conduct", "handling": "incident"},
    # routine service requests: handled by visitor services, not the ops floor
    "lost_item":        {"family": None, "handling": "routine"},
    "info_request":     {"family": None, "handling": "routine"},
    "wheelchair_request": {"family": None, "handling": "routine"},
    "status_update":    {"family": None, "handling": "routine"},   # radio check-ins / chatter
    "supply_request":   {"family": None, "handling": "routine"},   # chairs, water, stationery: visitor services
    # noise
    "heartbeat":        {"family": None, "handling": "noise"},
    "test_alarm":       {"family": None, "handling": "noise"},
    "auto_cleared":     {"family": None, "handling": "noise"},
    "door_held":        {"family": None, "handling": "noise"},
    "unusual_motion":   {"family": None, "handling": "noise"},     # camera analytics: movement without a person-down pattern
}

# --- tunable rule parameters (documented in docs/architecture.md) ----------
DUPLICATE_WINDOW_SEC = 120        # same system + category + zone inside this = duplicate
CORRELATION_WINDOW_SEC = 15 * 60  # attach to an open incident updated inside this
GATE_PROCESSING_PER_STAFF = 16    # visitors processed per staff member per minute
SIM_HORIZON_MIN = 15
PRIORITY_LEVELS = (("P1", 75), ("P2", 50), ("P3", 25), ("P4", 0))
OPERATIONAL_SCORE_CAP = 74        # operational incidents stay below P1 …
OVER_CAPACITY_RATIO = 0.98        # … unless the zone is effectively full

# Incident kinds where a different stated location means a different event (two fires in two
# places are two incidents). Operational pressure is a zone-level state, so it links by zone.
LOCATION_SPECIFIC_KINDS = ("emergency", "routine")

# Escalation matrix (core/escalation.py): a case still waiting for a decision after one response time
# goes to L1, after two to L2, after three to L3. Seconds per level, by priority (illustrative MVP values).
ESCALATION_STEP_SEC = {"P1": 60, "P2": 180, "P3": 300, "P4": 300}
ESCALATION_LEVELS = ("L1", "L2", "L3")   # L1 shift manager, L2 operations-centre manager, L3 operations & safety director
