"""Read models for the ops app pages (what the API returns). No writes here."""
from .core.decisions import incident_label
from .core import escalation
from .db import current_run, rows, to_dict

PRIORITY_ORDER = "CASE priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END"
# Same priority: life-safety (fire, medical) before operational pressure before routine faults.
KIND_ORDER = "CASE kind WHEN 'emergency' THEN 1 WHEN 'operational' THEN 2 ELSE 3 END"


def counters(conn):
    c = {r["disposition"]: r["n"] for r in conn.execute(
        "SELECT disposition, COUNT(*) n FROM alerts GROUP BY disposition")}
    by_type = {r["signal_type"]: r["n"] for r in conn.execute(
        "SELECT signal_type, COUNT(*) n FROM alerts GROUP BY signal_type")}
    inc = conn.execute(
        """SELECT COUNT(*) total,
                  SUM(status IN ('open','action_approved')) open,
                  SUM(status IN ('open','action_approved') AND priority='P1') critical,
                  SUM(status IN ('open','action_approved') AND priority='P2') high,
                  SUM(status='open' AND priority IN ('P1','P2')
                      AND id NOT IN (SELECT incident_id FROM escalations WHERE incident_id IS NOT NULL)) awaiting_decision,
                  SUM(status='open' AND id IN (SELECT incident_id FROM escalations WHERE incident_id IS NOT NULL)) escalated
           FROM incidents""").fetchone()
    received = sum(c.values())
    return {
        "received": received,
        "noise": c.get("noise", 0),
        "routine": c.get("routine", 0),
        "duplicate": c.get("duplicate", 0),
        "needs_review": c.get("needs_review", 0),
        "relevant": c.get("correlated", 0),
        "by_signal_type": by_type,
        "incidents_total": inc["total"] or 0,
        "incidents_open": inc["open"] or 0,
        "critical": inc["critical"] or 0,
        "high": inc["high"] or 0,
        "awaiting_decision": inc["awaiting_decision"] or 0,
        "escalated": inc["escalated"] or 0,
    }


def _mark_escalated(it, esc):
    """Read model: a waiting case that ran past its response time is shown as «escalated» (it has left
    the duty officer for the managers L1/L2/L3); in the database it stays open for the event."""
    e = esc.get(it["id"])
    if e and it["status"] == "open":
        it["status"] = "escalated"
        it["escalation"] = e


def _sources(conn, incident_id):
    return [r["source_system"] for r in conn.execute(
        """SELECT source_system, COUNT(*) n FROM alerts WHERE incident_id=?
           GROUP BY source_system ORDER BY MIN(id)""", (incident_id,))]


def incident_list(conn, include_closed=True):
    where = "" if include_closed else "WHERE status IN ('open','action_approved')"
    items = rows(conn.execute(
        f"""SELECT * FROM incidents {where}
            ORDER BY (status IN ('resolved','dismissed')), {PRIORITY_ORDER}, {KIND_ORDER}, priority_score DESC, updated_at DESC"""))
    cats = {}
    for r in conn.execute("SELECT DISTINCT incident_id, category FROM alerts WHERE disposition='correlated'"):
        cats.setdefault(r["incident_id"], set()).add(r["category"])
    esc = escalation.by_incident(conn)
    for it in items:
        _mark_escalated(it, esc)
        it["label"] = incident_label(it["type"], cats.get(it["id"], set()))
        it["sources"] = _sources(conn, it["id"])
        reasons = [r for r in it["priority_reasons"] if r["key"] != "type_base" and r["points"] > 0]
        it["top_reasons"] = sorted(reasons, key=lambda r: -r["points"])[:2]
    return items


def recent_signals(conn, limit=40):
    return rows(conn.execute(
        """SELECT a.id, a.signal_type, a.source_system, a.category, a.zone_id, a.location_id, a.location_detail,
                  a.raw_text, a.language, a.confidence, a.origin, a.occurred_at, a.received_at, a.disposition,
                  a.incident_id, i.code incident_code,
                  json_extract(a.payload, '$.extraction.report_kind') report_kind
           FROM alerts a LEFT JOIN incidents i ON i.id=a.incident_id
           ORDER BY a.id DESC LIMIT ?""", (limit,)))


def zones(conn):
    zs = rows(conn.execute("SELECT * FROM zones"))
    worst = {r["zone_id"]: r["p"] for r in conn.execute(
        f"""SELECT zone_id, MIN({PRIORITY_ORDER}) p FROM incidents
            WHERE status IN ('open','action_approved') GROUP BY zone_id""")}
    for z in zs:
        z["load"] = round(z["occupancy"] / z["capacity"], 3)
        p = worst.get(z["id"])
        z["worst_priority"] = f"P{p}" if p else None
    return zs


def locations(conn):
    locs = rows(conn.execute("SELECT * FROM locations ORDER BY zone_id, id"))
    stats = {r["location_id"]: r for r in conn.execute(
        f"""SELECT location_id, COUNT(*) n, MIN({PRIORITY_ORDER}) p FROM incidents
            WHERE status IN ('open','action_approved') AND location_id IS NOT NULL GROUP BY location_id""")}
    for loc in locs:
        st = stats.get(loc["id"])
        loc["open_incidents"] = st["n"] if st else 0
        loc["worst_priority"] = f"P{st['p']}" if st else None
    return locs


def incident_detail(conn, incident_id):
    inc = to_dict(conn.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone())
    if inc is None:
        return None
    inc["zone"] = to_dict(conn.execute("SELECT * FROM zones WHERE id=?", (inc["zone_id"],)).fetchone())
    inc["zone"]["load"] = round(inc["zone"]["occupancy"] / inc["zone"]["capacity"], 3)
    inc["alerts"] = rows(conn.execute("SELECT * FROM alerts WHERE incident_id=? ORDER BY id", (incident_id,)))
    inc["label"] = incident_label(inc["type"], {a["category"] for a in inc["alerts"] if a["disposition"] == "correlated"})
    inc["recommendations"] = rows(conn.execute(
        "SELECT * FROM recommendations WHERE incident_id=? ORDER BY status='proposed' DESC, rank", (incident_id,)))
    inc["decisions"] = rows(conn.execute(
        "SELECT * FROM decisions WHERE incident_id=? ORDER BY id", (incident_id,)))
    inc["teams"] = rows(conn.execute("SELECT * FROM teams WHERE incident_id=?", (incident_id,)))
    _mark_escalated(inc, escalation.by_incident(conn))
    if inc["kind"] == "operational":
        from .core import simulate
        zs = {z["id"]: z for z in rows(conn.execute("SELECT * FROM zones"))}
        src = zs[inc["zone_id"]]
        inc["whatif_targets"] = {
            "divert": [z["id"] for z in simulate.divert_targets(src, zs)],
            "redeploy": [z["id"] for z in simulate.staff_donors(src, zs)],
        }
    srcs = {}
    for a in inc["alerts"]:
        s = srcs.setdefault(a["source_system"], {"source_system": a["source_system"], "signal_type": a["signal_type"],
                                                 "count": 0, "duplicates": 0, "max_confidence": 0.0,
                                                 "origins": []})
        s["count"] += 1
        s["duplicates"] += a["disposition"] == "duplicate"
        s["max_confidence"] = max(s["max_confidence"], a["confidence"])
        if a["origin"] not in s["origins"]:
            s["origins"].append(a["origin"])
    inc["source_breakdown"] = list(srcs.values())
    return inc


def decision_log(conn, limit=30, current_only=False):
    """Permanent log, newest first. Each row carries its own snapshot (names, option, teams,
    simulation) so rows from earlier runs stay readable after a reset."""
    run = current_run(conn)
    where = "WHERE run_id=?" if current_only else ""
    args = (run, limit) if current_only else (limit,)
    items = rows(conn.execute(f"SELECT * FROM decisions {where} ORDER BY id DESC LIMIT ?", args))
    for d in items:
        d["current_run"] = d["run_id"] == run
    return items
