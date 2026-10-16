"""Escalation matrix: when a case waits for a decision longer than its response time, it is
escalated to the managers above the duty officer, one level at a time (L1 -> L2 -> L3).

Rule-based and explainable: the time per level depends only on the priority. The clock starts when
the case opened, or when it was raised to its current priority. Illustrative values for the MVP —
the real times and names would come from the Expo operations procedures.
"""
import json

from .. import catalog
from ..db import parse_iso


def step_seconds(priority):
    return catalog.ESCALATION_STEP_SEC.get(priority, catalog.ESCALATION_STEP_SEC["P3"])


def level(priority, started_iso, now_iso):
    """0 = still inside the response time; 1..3 = escalated to L1..L3."""
    if not started_iso or not now_iso:
        return 0
    waited = (parse_iso(now_iso) - parse_iso(started_iso)).total_seconds()
    return max(0, min(len(catalog.ESCALATION_LEVELS), int(waited // step_seconds(priority))))


def matrix():
    """What the UI needs to show countdowns and the matrix in Settings."""
    return {"step_s": dict(catalog.ESCALATION_STEP_SEC), "levels": list(catalog.ESCALATION_LEVELS)}


def start_of(inc):
    return inc.get("escalated_at") or inc["opened_at"]


def sweep(conn, now=None):
    """Escalate every case still waiting for a decision past its response time, and raise the level of
    cases already escalated (L1 -> L2 -> L3) while nobody has handled them. Returns cases changed."""
    from datetime import timedelta
    from ..db import current_run, now_iso, to_dict, transaction
    from .decisions import snapshot
    now = now or now_iso()
    changed = 0
    with transaction(conn):
        run = current_run(conn)
        for row in conn.execute("SELECT * FROM incidents WHERE status='open'").fetchall():
            inc = to_dict(row)
            lvl = level(inc["priority"], start_of(inc), now)
            if not lvl:
                continue
            reached = (parse_iso(start_of(inc)) + timedelta(seconds=lvl * step_seconds(inc["priority"])))
            reached = reached.isoformat(timespec="milliseconds")
            cur = conn.execute("SELECT id, level FROM escalations WHERE incident_id=?", (inc["id"],)).fetchone()
            if cur is None:
                first = (parse_iso(start_of(inc)) + timedelta(seconds=step_seconds(inc["priority"])))
                snap = snapshot(conn, inc, None, [])
                conn.execute("""INSERT INTO escalations (run_id, incident_id, level, priority, created_at, updated_at, snapshot)
                                VALUES (?,?,?,?,?,?,?)""",
                             (run, inc["id"], lvl, inc["priority"], first.isoformat(timespec="milliseconds"), reached,
                              json.dumps(snap, ensure_ascii=False)))
                changed += 1
            elif lvl > cur["level"]:
                conn.execute("UPDATE escalations SET level=?, updated_at=? WHERE id=?", (lvl, reached, cur["id"]))
                changed += 1
    return changed


def by_incident(conn):
    """{incident_id: {"level", "code", "at"}} for escalated cases of the current event."""
    out = {}
    for r in conn.execute("SELECT incident_id, level, created_at FROM escalations WHERE incident_id IS NOT NULL"):
        out[r["incident_id"]] = {"level": r["level"], "code": catalog.ESCALATION_LEVELS[r["level"] - 1], "at": r["created_at"]}
    return out


def log(conn, limit=500):
    from ..db import current_run, rows
    run = current_run(conn)
    items = rows(conn.execute("SELECT * FROM escalations ORDER BY id DESC LIMIT ?", (limit,)))
    for e in items:
        e["code"] = catalog.ESCALATION_LEVELS[e["level"] - 1]
        e["current_run"] = e["run_id"] == run
    return items
