"""Priority engine — deterministic, explainable scoring.

Why rules and not ML: there is no labelled Expo data, the operator must be able
to see *why* something is P1, and the scoring must be auditable after an event.
Every point added to the score emits a reason {key, params, points}; the UI
translates the key in AR/EN.
"""
from .. import catalog
from . import simulate

BASE = {"fire": 55, "medical": 55, "crowd_pressure": 30, "facility": 15, "it_system": 8, "visitor_conduct": 30}
# Field staff reports (radio) that count as an eyewitness of a life-safety event.
EYEWITNESS_CATEGORIES = ("smoke_report", "medical_report")
EYEWITNESS_MIN_CONFIDENCE = 0.6
# A person-down detected by the vision model on a real camera feed or video (not scripted demo data)
# is raised to critical at once, like a radio eyewitness: someone on the floor cannot wait for a 2nd source.
CV_ORIGINS = ("live_cv", "video_file", "replay_cv")


def level_for(score):
    for level, threshold in catalog.PRIORITY_LEVELS:
        if score >= threshold:
            return level
    return "P4"


def evidence_confidence(alerts):
    """Combine the best confidence per independent source: 1 - prod(1 - c)."""
    best = {}
    for a in alerts:
        best[a["source_system"]] = max(best.get(a["source_system"], 0.0), a["confidence"])
    miss = 1.0
    for c in best.values():
        miss *= (1.0 - c)
    return round(1.0 - miss, 3), best


def compute(incident_type, alerts, zone):
    """alerts: non-duplicate alerts of the incident. Returns (level, score, reasons, confidence)."""
    reasons = []

    def add(key, points, **params):
        reasons.append({"key": key, "points": points, "params": params})
        return points

    score = add("type_base", BASE[incident_type], type=incident_type)
    confidence, per_source = evidence_confidence(alerts)
    sources = sorted(per_source)
    n_sources = len(sources)
    load = zone["occupancy"] / zone["capacity"]
    kind = catalog.INCIDENT_TYPES[incident_type]

    if kind == "emergency":
        # Evidence that is already verified at the source does not wait for a second source:
        #  * a fire panel in stage-2 alarm (the panel has confirmed the alarm itself)
        #  * a field staff member reporting what they see (radio eyewitness, understood with confidence)
        # A single automatic detector or a camera alone stays P2 "verify now" until confirmed.
        verified_panel = any(a["category"] == "fire_alarm" and (a.get("payload") or {}).get("stage", 1) >= 2
                             for a in alerts)
        eyewitness = any(a["source_system"] == "radio" and a["category"] in EYEWITNESS_CATEGORIES
                         and a["confidence"] >= EYEWITNESS_MIN_CONFIDENCE for a in alerts)
        cv_person_down = any(a["source_system"] == "cctv_ai" and a["category"] == "person_down"
                             and a.get("origin") in CV_ORIGINS and a["confidence"] >= EYEWITNESS_MIN_CONFIDENCE
                             for a in alerts)
        if n_sources >= 2:
            score += add("confirmed_independent", 20 + 5 * (n_sources - 2), n=n_sources, sources=sources)
        elif not (verified_panel or eyewitness or cv_person_down):
            score += add("single_source", 0, source=sources[0] if sources else None)
            if confidence < 0.6:
                score += add("low_confidence", -10, confidence=confidence)
        if verified_panel:
            score += add("fire_panel_alarm", 15)
        if load >= 0.8:
            score += add("high_occupancy_zone", 5, load=round(load, 2))
        if zone["criticality"] >= 3:
            score += add("critical_zone", 5)
        floor = catalog.PRIORITY_LEVELS[0][1]          # the P1 threshold
        if score < floor and verified_panel:
            score += add("verified_panel_alarm", floor - score)
        elif score < floor and eyewitness:
            score += add("eyewitness_report", floor - score)
        elif score < floor and cv_person_down:
            score += add("cv_person_down", floor - score)

    elif kind == "operational":
        if load >= 0.9:
            score += add("occupancy", 20, load=round(load, 2))
        elif load >= 0.8:
            score += add("occupancy", 10, load=round(load, 2))
        if zone["staff_required"] and zone["staff_on_duty"] / zone["staff_required"] < 0.75:
            score += add("staff_shortage", 10, on_duty=zone["staff_on_duty"], required=zone["staff_required"])
        waits = [a["payload"].get("wait_min", 0) for a in alerts if a["category"] == "queue_long"]
        if waits and waits[-1] >= 15:
            score += add("long_queue", 5, wait_min=waits[-1])
        if n_sources >= 2:
            score += add("multi_source", 5, n=n_sources, sources=sources)
        ttc = simulate.project(zone)["minutes_to_capacity"]
        if ttc is not None and ttc <= 10:
            score += add("capacity_soon", 10, minutes=ttc)
        if score > catalog.OPERATIONAL_SCORE_CAP and load < catalog.OVER_CAPACITY_RATIO:
            # Operational pressure must not outrank life-safety unless the zone is full.
            add("operational_cap", catalog.OPERATIONAL_SCORE_CAP - score, cap=catalog.OPERATIONAL_SCORE_CAP)
            score = catalog.OPERATIONAL_SCORE_CAP
        elif load >= catalog.OVER_CAPACITY_RATIO:
            score += add("over_capacity", 10, load=round(load, 2))

    else:  # routine
        cats = {a["category"] for a in alerts}
        if "elevator_fault" in cats:
            score += add("accessibility_impact", 15)
        if "water_leak" in cats:
            score += add("slip_hazard", 12)
        if "hvac_temp_high" in cats:
            temps = [a["payload"].get("temp_c", 0) for a in alerts if a["category"] == "hvac_temp_high"]
            if temps and max(temps) >= 30:
                score += add("high_temperature", 10, temp_c=max(temps))
        if len(alerts) >= 5:
            score += add("repeated_reports", 5, n=len(alerts))

    score = max(0, min(100, int(round(score))))
    return level_for(score), score, reasons, confidence
