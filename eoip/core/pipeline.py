"""Ingestion pipeline:

    Source -> normalize -> classify (noise / routine / incident) -> duplicate check
           -> correlate (attach to open incident or create one) -> update zone state
           -> recompute priority -> refresh recommendations

Everything runs inside one IMMEDIATE transaction so the dashboard never sees a
half-processed signal.
"""
import json
from datetime import timedelta

from .. import catalog
from ..db import now_iso, parse_iso, rows, to_dict, transaction
from . import normalize as norm
from . import priority, recommend, teams as teams_mod


def _zones(conn):
    return {z["id"]: z for z in rows(conn.execute("SELECT * FROM zones"))}


def _locations(conn):
    return {r[0]: r[1] for r in conn.execute("SELECT id, zone_id FROM locations")}


def _insert_alert(conn, a, disposition, incident_id=None, duplicate_of=None, correlation=None):
    cur = conn.execute(
        """INSERT INTO alerts (external_ref, signal_type, source_system, category, zone_id, location_id,
               location_detail, raw_text, language, severity_hint, confidence, payload, origin,
               occurred_at, received_at, disposition, duplicate_of, incident_id, correlation)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (a["external_ref"], a["signal_type"], a["source_system"], a["category"], a["zone_id"],
         a.get("location_id"), a["location_detail"], a["raw_text"], a["language"], a["severity_hint"], a["confidence"],
         json.dumps(a["payload"], ensure_ascii=False), a["origin"], a["occurred_at"],
         a["received_at"], disposition, duplicate_of, incident_id,
         json.dumps(correlation, ensure_ascii=False) if correlation is not None else None))
    return cur.lastrowid


def _norm_loc(text):
    return " ".join((text or "").lower().split())


def correlation_for(conn, a, inc, itype, conflict=None):
    """Explain the link decision with explicit rules (rules_v3) and a 0..1 rule score.

    A link requires ALL of: same incident family (from the signal category, not from
    free-text similarity), same zone, incident still open, last update inside the
    correlation window, and - for emergencies and routine faults - no conflicting stated
    location (two fires at two named locations are two incidents). The score only
    expresses how strong the match is:
        0.50 family+zone match  +  0.30 x time proximity  +  0.20 if a new independent source
    """
    window = catalog.CORRELATION_WINDOW_SEC
    if inc is None:
        reasons = [{"key": "no_open_match", "params": {"type": itype, "zone": a["zone_id"],
                                                       "window_min": window // 60}}]
        if conflict is not None:
            reasons.append({"key": "different_location", "params": {
                "code": conflict["code"], "location": conflict["location_id"], "this_location": a.get("location_id")}})
        return {"method": "rules_v3", "linked": False, "score": None, "reasons": reasons}
    gap = _gap(inc["updated_at"], a["received_at"])
    prior = {r[0] for r in conn.execute(
        "SELECT DISTINCT source_system FROM alerts WHERE incident_id=? AND disposition='correlated'", (inc["id"],))}
    independent = a["source_system"] not in prior
    reasons = [
        {"key": "same_family", "params": {"type": itype, "category": a["category"]}},
        {"key": "same_zone", "params": {"zone": a["zone_id"]}},
    ]
    loc, inc_loc = a.get("location_id"), inc.get("location_id")
    if loc and inc_loc and loc == inc_loc:
        reasons.append({"key": "same_location", "params": {"location": loc}})
    elif loc or inc_loc:
        reasons.append({"key": "location_not_stated", "params": {"location": loc or inc_loc}})
    reasons += [
        {"key": "within_window", "params": {"seconds": gap, "window_min": window // 60}},
        {"key": "incident_open", "params": {"code": inc["code"]}},
        {"key": "independent_source" if independent else "same_source_update",
         "params": {"source": a["source_system"]}},
    ]
    score = 0.5 + 0.3 * max(0.0, 1 - gap / window) + (0.2 if independent else 0.0)
    return {"method": "rules_v3", "linked": True, "score": round(min(score, 1.0), 2), "reasons": reasons}


def _find_duplicate(conn, a):
    since = (parse_iso(a["received_at"]) - timedelta(seconds=catalog.DUPLICATE_WINDOW_SEC)).isoformat()
    # Only a repeat of an alert whose incident is still OPEN is a duplicate. After an incident
    # was resolved or dismissed, a repeat is new evidence and must not be swallowed.
    row = conn.execute(
        """SELECT a.id, a.duplicate_of, a.incident_id, a.received_at FROM alerts a
             JOIN incidents i ON i.id = a.incident_id
           WHERE a.source_system=? AND a.category=? AND a.zone_id=? AND a.received_at>=?
             AND a.disposition IN ('correlated','duplicate')
             AND i.status IN ('open','action_approved')
             AND (? IS NULL OR a.location_id IS NULL OR a.location_id = ?)
           ORDER BY a.id DESC LIMIT 1""",
        (a["source_system"], a["category"], a["zone_id"], since, a.get("location_id"), a.get("location_id"))).fetchone()
    if row is None:
        return None
    return {"root_id": row["duplicate_of"] or row["id"], "incident_id": row["incident_id"],
            "seconds": _gap(row["received_at"], a["received_at"])}


def _gap(t0, t1):
    return max(0, round((parse_iso(t1) - parse_iso(t0)).total_seconds()))


def _find_open_incident(conn, itype, zone_id, received_at, location_id=None):
    """Return (incident to link or None, incident skipped because of a different location or None)."""
    since = (parse_iso(received_at) - timedelta(seconds=catalog.CORRELATION_WINDOW_SEC)).isoformat()
    cands = rows(conn.execute(
        """SELECT * FROM incidents WHERE type=? AND zone_id=? AND status IN ('open','action_approved')
             AND updated_at>=? ORDER BY id DESC""", (itype, zone_id, since)))
    if catalog.INCIDENT_TYPES[itype] not in catalog.LOCATION_SPECIFIC_KINDS:
        return (cands[0] if cands else None), None
    conflict = None
    for inc in cands:
        if location_id and inc["location_id"] and inc["location_id"] != location_id:
            conflict = conflict or inc
            continue
        return inc, None
    return None, conflict


def _create_incident(conn, itype, zone_id, ts, location_id=None):
    cur = conn.execute(
        """INSERT INTO incidents (code, type, kind, zone_id, location_id, opened_at, updated_at)
           VALUES ('pending', ?, ?, ?, ?, ?, ?)""",
        (itype, catalog.INCIDENT_TYPES[itype], zone_id, location_id, ts, ts))
    iid = cur.lastrowid
    conn.execute("UPDATE incidents SET code=? WHERE id=?", (f"INC-{iid:04d}", iid))
    return iid


def _apply_zone_state(conn, a):
    """Stateful signals carry measurements that update the live zone state."""
    p, z = a["payload"], a["zone_id"]
    if a["category"] == "occupancy_high" and "occupancy" in p:
        conn.execute("UPDATE zones SET occupancy=? WHERE id=?", (int(p["occupancy"]), z))
    if a["category"] == "staff_shortage" and "on_duty" in p:
        conn.execute("UPDATE zones SET staff_on_duty=? WHERE id=?", (int(p["on_duty"]), z))
        if "required" in p:
            conn.execute("UPDATE zones SET staff_required=? WHERE id=?", (int(p["required"]), z))
    if "inflow_per_min" in p:
        conn.execute("UPDATE zones SET inflow_per_min=? WHERE id=?", (float(p["inflow_per_min"]), z))


def refresh_incident(conn, incident_id, ts=None, rebuild=False):  # rebuild kept for callers; content always refreshes
    """Recompute counts, priority, confidence and recommendations for an incident."""
    ts = ts or now_iso()
    inc = to_dict(conn.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone())
    zones = _zones(conn)
    zone = zones[inc["zone_id"]]
    alerts = rows(conn.execute(
        "SELECT * FROM alerts WHERE incident_id=? ORDER BY id", (incident_id,)))
    primary = [a for a in alerts if a["disposition"] == "correlated"]
    level, score, reasons, confidence = priority.compute(inc["type"], primary, zone)
    escalated_at = inc["escalated_at"]
    if inc["priority"] and level < inc["priority"] and inc["priority_score"] > 0:  # "P1" < "P2"
        escalated_at = ts
    conn.execute(
        """UPDATE incidents SET priority=?, priority_score=?, priority_reasons=?, confidence=?,
               alert_count=?, source_count=?, updated_at=?, escalated_at=? WHERE id=?""",
        (level, score, json.dumps(reasons, ensure_ascii=False), confidence, len(alerts),
         len({a["source_system"] for a in primary}), ts, escalated_at, incident_id))

    # Recommendations: keep decided ones; regenerate proposals while undecided.
    decided = conn.execute(
        "SELECT COUNT(*) FROM recommendations WHERE incident_id=? AND status='approved'",
        (incident_id,)).fetchone()[0]
    if decided:
        return
    existing = conn.execute(
        "SELECT COUNT(*) FROM recommendations WHERE incident_id=?", (incident_id,)).fetchone()[0]
    inc["priority"] = level
    inc["source_count"] = len({a["source_system"] for a in primary})
    inc["categories"] = sorted({a["category"] for a in primary})
    built = recommend.build(inc, zone, zones, conn)
    if inc["kind"] != "operational" and existing:
        # Emergency / routine: keep the SAME proposal row (stable id for the operator's click) and
        # refresh its content, so reasons, confirmation and nearest free team follow the evidence.
        for r in built:
            conn.execute("""UPDATE recommendations SET params=? WHERE incident_id=? AND code=? AND status='proposed'""",
                         (json.dumps(r["params"]), incident_id, r["code"]))
        return
    # operational (or first build): regenerate system options; operator-defined ones (rank >= 90) are kept
    conn.execute("DELETE FROM recommendations WHERE incident_id=? AND status='proposed' AND rank < 90",
                 (incident_id,))
    rejected = {r["code"] for r in rows(conn.execute(
        "SELECT code FROM recommendations WHERE incident_id=? AND status='rejected' AND rank < 90",
        (incident_id,)))}
    for r in built:
        if r["code"] in rejected:
            continue  # an operator already said no; do not re-propose it
        conn.execute(
            """INSERT INTO recommendations (incident_id, code, rec_type, rank, params, simulation, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (incident_id, r["code"], r["rec_type"], r["rank"], json.dumps(r["params"]),
             json.dumps(r["simulation"]) if r["simulation"] is not None else None, ts))


def rebuild_stale_team_proposals(conn, ts=None):
    """Re-plan open emergency/routine incidents whose proposed team is now busy elsewhere,
    or which had no team available (one may have been released)."""
    for r in rows(conn.execute(
            """SELECT r.incident_id, r.params FROM recommendations r JOIN incidents i ON i.id=r.incident_id
               WHERE r.status='proposed' AND i.status='open' AND i.kind<>'operational'""")):
        crew = (r["params"] or {}).get("teams") or []
        ids = [t["team_id"] for t in crew if t.get("team_id")]
        if any(t.get("team_id") is None for t in crew) or teams_mod.unavailable(conn, ids, r["incident_id"]):
            refresh_incident(conn, r["incident_id"], ts, rebuild=True)


def _refresh_zone_incidents(conn, zone_id, except_id, ts):
    """Zone state changed: operational incidents in this zone must re-score."""
    for r in conn.execute(
            """SELECT id FROM incidents WHERE zone_id=? AND kind='operational'
               AND status IN ('open','action_approved') AND id<>?""", (zone_id, except_id or -1)).fetchall():
        refresh_incident(conn, r["id"], ts)


def ingest(conn, raw, zone_ids=None):
    """Process one raw signal. Returns {alert_id, disposition, incident_id}."""
    if zone_ids is None:
        zone_ids = {r[0] for r in conn.execute("SELECT id FROM zones")}
    a = norm.normalize(raw, zone_ids, _locations(conn))
    rule = catalog.CATEGORIES[a["category"]]

    with transaction(conn):
        if rule["handling"] in ("noise", "routine"):
            aid = _insert_alert(conn, a, rule["handling"])
            return {"alert_id": aid, "disposition": rule["handling"], "incident_id": None}

        if a["zone_id"] is None:
            aid = _insert_alert(conn, a, "needs_review")
            return {"alert_id": aid, "disposition": "needs_review", "incident_id": None}

        if not rule.get("stateful"):
            dup = _find_duplicate(conn, a)
            if dup and dup["incident_id"]:
                corr = {"method": "rules_v3", "linked": True, "score": None,
                        "reasons": [{"key": "duplicate_of", "params": {"alert": dup["root_id"],
                                                                        "seconds": dup["seconds"],
                                                                        "window_s": catalog.DUPLICATE_WINDOW_SEC}}]}
                aid = _insert_alert(conn, a, "duplicate", dup["incident_id"], dup["root_id"], corr)
                conn.execute("UPDATE incidents SET alert_count=alert_count+1, updated_at=? WHERE id=?",
                             (a["received_at"], dup["incident_id"]))
                return {"alert_id": aid, "disposition": "duplicate", "incident_id": dup["incident_id"]}

        itype = rule["family"]
        inc, conflict = _find_open_incident(conn, itype, a["zone_id"], a["received_at"], a.get("location_id"))
        corr = correlation_for(conn, a, inc, itype, conflict)
        if inc:
            iid = inc["id"]
            if a.get("location_id") and not inc["location_id"]:
                conn.execute("UPDATE incidents SET location_id=? WHERE id=?", (a["location_id"], iid))
        else:
            iid = _create_incident(conn, itype, a["zone_id"], a["received_at"], a.get("location_id"))
        aid = _insert_alert(conn, a, "correlated", iid, correlation=corr)
        if rule.get("stateful") or "inflow_per_min" in a["payload"]:
            _apply_zone_state(conn, a)
            _refresh_zone_incidents(conn, a["zone_id"], iid, a["received_at"])
        refresh_incident(conn, iid, a["received_at"])
        return {"alert_id": aid, "disposition": "correlated", "incident_id": iid, "new_incident": inc is None}
