"""Human-in-the-loop decisions. EOIP never acts on its own: every state change
of an incident's response comes from an operator decision, and every decision
is written to the `decisions` log with the priority the operator saw.

New HTTP decisions receive their identity only from a verified employee session.
Each action requires a reason and stores a self-contained snapshot so the log
stays readable after a demo reset."""
import json

from .. import catalog
from ..db import current_run, now_iso, rows, to_dict, transaction
from . import escalation, teams as teams_mod

OPERATOR_MAX = 80


def _names(conn):
    names = {}
    for table in ("zones", "locations", "teams"):
        for r in conn.execute(f"SELECT id, name_ar, name_en FROM {table}"):
            names[r["id"]] = {"ar": r["name_ar"], "en": r["name_en"]}
    return names


def _sim_summary(sim):
    if not sim:
        return None
    out = {"action": sim.get("action"), "horizon_min": sim.get("horizon_min"),
           "source_zone": sim.get("source_zone"), "other_zone": sim.get("other_zone"),
           "load_now": sim["baseline"]["load_now"], "load_no_action": sim["baseline"]["load_end"],
           "load_with_option": sim["source"]["load_end"],
           "checks": {k: sum(1 for c in sim.get("checks", []) if c["status"] == k) for k in ("ok", "warn", "fail")},
           "staff": sim.get("staff")}
    if sim.get("other"):
        out["other_load_before"] = sim["other_before"]["load_end"] if sim.get("other_before") else None
        out["other_load_after"] = sim["other"]["load_end"]
    return out


def snapshot(conn, inc, rec, teams):
    rec_snap = None
    if rec:
        rec_snap = {"id": rec["id"], "code": rec["code"], "rec_type": rec["rec_type"], "rank": rec["rank"],
                    "params": rec["params"], "simulation": _sim_summary(rec.get("simulation"))}
    labels = {r["category"] for r in conn.execute(
        "SELECT DISTINCT category FROM alerts WHERE incident_id=? AND disposition='correlated'", (inc["id"],))}
    sources = sorted({r[0] for r in conn.execute(
        "SELECT DISTINCT source_system FROM alerts WHERE incident_id=? AND disposition='correlated'", (inc["id"],))})
    return {"sources": sources,"incident_code": inc["code"], "incident_type": inc["type"], "incident_kind": inc["kind"],
            "incident_label": incident_label(inc["type"], labels),
            "zone_id": inc["zone_id"], "location_id": inc.get("location_id"),
            "recommendation": rec_snap,
            "teams": [{"id": t["id"], "kind": t["kind"], "base_location": t["base_location"]} for t in teams],
            "names": _names(conn)}


STAFF_CATEGORIES = {"staff_shortage", "staff_shortage_report"}
VISITOR_LABELS = {"visitor_fight": "visitor_fight", "visitor_sitting_path": "visitor_sitting_path",
                  "visitor_wrong_way": "visitor_wrong_way"}


def incident_label(itype, categories):
    """Display label for an incident: crowd_pressure incidents built only from staffing signals
    are shown as a staff shortage, mixed ones as crowding + staff shortage."""
    if itype == "visitor_conduct":
        for cat in VISITOR_LABELS:
            if cat in categories:
                return VISITOR_LABELS[cat]
        return itype
    if itype != "crowd_pressure":
        return itype
    staff = bool(categories & STAFF_CATEGORIES)
    crowd = bool(categories - STAFF_CATEGORIES)
    return "crowding_staff" if staff and crowd else "staff_shortage" if staff else "crowding"


class DecisionError(ValueError):
    pass


def decide(conn, incident_id, action, recommendation_id=None, note=None, operator=None,
           employee_id=None, employee_number=None):
    if action not in catalog.DECISION_ACTIONS:
        raise DecisionError("invalid_action")
    operator = " ".join((operator or "").split())[:OPERATOR_MAX]
    if not operator:
        raise DecisionError("operator_required")
    note = (note or "").strip()[:500] or None
    ts = now_iso()
    with transaction(conn):
        inc = to_dict(conn.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone())
        if inc is None:
            raise DecisionError("incident_not_found")
        if inc["status"] in ("resolved", "dismissed"):
            raise DecisionError("incident_closed")
        # past its response time the case has been escalated to the managers: the duty officer can no longer decide
        if inc["status"] == "open" and (
                escalation.level(inc["priority"], escalation.start_of(inc), ts)
                or conn.execute("SELECT 1 FROM escalations WHERE incident_id=?", (incident_id,)).fetchone()):
            raise DecisionError("incident_escalated")

        rec = None
        if action in ("approve", "reject"):
            if recommendation_id is None:
                raise DecisionError("recommendation_required")
            rec = to_dict(conn.execute(
                "SELECT * FROM recommendations WHERE id=? AND incident_id=?",
                (recommendation_id, incident_id)).fetchone())
            if rec is None:
                raise DecisionError("recommendation_not_found")
            if rec["status"] != "proposed":
                raise DecisionError("recommendation_not_open")
        involved = [r[0] for r in conn.execute("SELECT id FROM teams WHERE incident_id=?", (incident_id,))] \
            if action in ("resolve", "dismiss") else []
        if action == "approve":
            crew = [t["team_id"] for t in (rec["params"].get("teams") or []) if t.get("team_id")]
            if teams_mod.unavailable(conn, crew, incident_id):
                raise DecisionError("team_unavailable")   # assigned elsewhere since it was proposed
            teams_mod.assign(conn, crew, incident_id, ts)
            involved = crew
            conn.execute("UPDATE recommendations SET status='approved' WHERE id=?", (rec["id"],))
            conn.execute("""UPDATE recommendations SET status='superseded'
                            WHERE incident_id=? AND status='proposed'""", (incident_id,))
            conn.execute("UPDATE incidents SET status='action_approved', updated_at=? WHERE id=?",
                         (ts, incident_id))
        elif action == "reject":
            conn.execute("UPDATE recommendations SET status='rejected' WHERE id=?", (rec["id"],))
            conn.execute("UPDATE incidents SET updated_at=? WHERE id=?", (ts, incident_id))
        elif action == "resolve":
            conn.execute("UPDATE incidents SET status='resolved', closed_at=?, updated_at=? WHERE id=?",
                         (ts, ts, incident_id))
            teams_mod.release(conn, incident_id)
            conn.execute("""UPDATE recommendations SET status='superseded'
                            WHERE incident_id=? AND status='proposed'""", (incident_id,))
        elif action == "dismiss":
            conn.execute("UPDATE incidents SET status='dismissed', closed_at=?, updated_at=? WHERE id=?",
                         (ts, ts, incident_id))
            teams_mod.release(conn, incident_id)
            conn.execute("""UPDATE recommendations SET status='superseded'
                            WHERE incident_id=? AND status='proposed'""", (incident_id,))

        teams = rows(conn.execute(
            f"SELECT * FROM teams WHERE id IN ({','.join('?' * len(involved))})", involved)) if involved else []
        snap = snapshot(conn, inc, rec, teams)
        cur = conn.execute(
            """INSERT INTO decisions (run_id, incident_id, recommendation_id, action, operator, employee_id,
                   employee_number, note, priority_at_decision, created_at, snapshot)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (current_run(conn), incident_id, rec["id"] if rec else None, action, operator, employee_id,
             employee_number, note, inc["priority"], ts, json.dumps(snap, ensure_ascii=False)))
        if action in ("approve", "resolve", "dismiss"):
            # team availability changed: other incidents' team proposals may be stale
            from .pipeline import rebuild_stale_team_proposals
            rebuild_stale_team_proposals(conn, ts)
        return cur.lastrowid
