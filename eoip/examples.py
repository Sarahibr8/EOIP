"""Three example cases stored in the database when a new event starts.

They are cases "already handled earlier in the shift" (data/examples.json): a fire, a crowding case
and a staff shortage. Each goes through the real pipeline (normalise -> correlate -> priority ->
recommendation), gets the decision written in the file (approved + closed, closed, or rejected by
the operator) and is then moved back in time. So the dashboard's handled list and the log are never
empty when someone signs in, and the examples look exactly like real cases.

They are clearly labelled: the operator name says "مثال مخزّن" and nobody's account is used.
Re-seeding replaces the previous example decisions, so the permanent decision log never fills up
with copies; real decisions are never touched.
"""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import decisions, extract, pipeline
from .db import layout, parse_iso, transaction

PATH = Path(__file__).resolve().parent.parent / "data" / "examples.json"


def _data():
    return json.loads(PATH.read_text(encoding="utf-8"))


def _signal(s):
    s = dict(s)
    if s.pop("extract", False):
        voice = extract.to_signal(extract.extract(s["raw_text"]), origin="mock")
        voice["payload"] = {**(s.get("payload") or {}), **voice["payload"]}
        return voice
    s.setdefault("origin", "mock")
    return s


def _shift(conn, table, cols, where, args, delta):
    for row in conn.execute(f"SELECT id, {', '.join(cols)} FROM {table} WHERE {where}", args).fetchall():
        sets, vals = [], []
        for c in cols:
            if row[c]:
                sets.append(f"{c}=?")
                vals.append((parse_iso(row[c]) - delta).isoformat(timespec="milliseconds"))
        if sets:
            conn.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id=?", (*vals, row["id"]))


def seed(conn):
    """Insert the example cases (call when a new event starts, before the live feed)."""
    data = _data()
    seed_history(conn, data)
    operator = data["operator"]
    with transaction(conn):
        conn.execute("DELETE FROM decisions WHERE operator=? AND employee_number IS NULL", (operator,))
    for case in data["cases"]:
        incident_id = None
        for s in case["signals"]:
            r = pipeline.ingest(conn, _signal(s))
            incident_id = incident_id or r.get("incident_id")
        if incident_id is None:
            continue
        outcome = case.get("outcome", "approve_resolve")
        if outcome == "approve_resolve":
            rec = conn.execute("""SELECT id FROM recommendations WHERE incident_id=? AND status='proposed'
                                  ORDER BY rank LIMIT 1""", (incident_id,)).fetchone()
            if rec:
                decisions.decide(conn, incident_id, "approve", rec["id"], None, operator)
            decisions.decide(conn, incident_id, "resolve", None, case["note"], operator)
        elif outcome == "dismiss":
            decisions.decide(conn, incident_id, "dismiss", None, case["note"], operator)
        else:
            decisions.decide(conn, incident_id, "resolve", None, case["note"], operator)
        delta = timedelta(minutes=case["minutes_ago"])
        handled = timedelta(minutes=case["minutes_ago"] - case["handled_after_min"])
        with transaction(conn):
            _shift(conn, "alerts", ("occurred_at", "received_at"), "incident_id=?", (incident_id,), delta)
            _shift(conn, "incidents", ("opened_at", "escalated_at"), "id=?", (incident_id,), delta)
            _shift(conn, "incidents", ("updated_at", "closed_at"), "id=?", (incident_id,), handled)
            _shift(conn, "recommendations", ("created_at",), "incident_id=?", (incident_id,), delta)
            _shift(conn, "decisions", ("created_at",), "incident_id=?", (incident_id,), handled)


# --- Test history: cases handled in the months before the current one -----------------------------
# Only decision-log rows (run 0, no live incident) with a full snapshot, so the log's monthly view
# shows earlier months. Clearly labelled (operator "سجل تجريبي") and replaced on every new event.
RIYADH = timezone(timedelta(hours=3))
HISTORY_MONTHS = 5          # the five months before the current month
_HIST = [
    # (incident_type, label, priority, sources, recommendation code, rec params, outcome, note)
    ("fire", "fire", "P1", ["cctv_ai", "radio"], "FIRE-01", {}, "approve_resolve",
     "أُرسل فريق الإطفاء وأُطفئ مصدر الدخان، ولا إصابات."),
    ("medical", "medical", "P1", ["cctv_ai", "radio"], "MED-01", {}, "approve_resolve",
     "وصل الفريق الطبي خلال 3 دقائق ونُقل الزائر للإسعاف."),
    ("medical", "medical", "P1", ["radio"], "MED-01", {}, "approve_resolve", "إسعاف أولي في الموقع، والزائر بخير."),
    ("crowd_pressure", "crowding", "P2", ["cctv_ai", "radio"], "meter_entry", {"reduction_pct": 30, "held_per_min": 25},
     "approve_resolve", "نُظّم الدخول وخفّ الطابور خلال 15 دقيقة."),
    ("crowd_pressure", "staff_shortage", "P2", ["radio"], "redeploy_staff",
     {"staff_moved": 3, "from_zone": "ZONE-B", "to_zone": "ZONE-A", "staff_after": 12}, "approve_resolve",
     "نُقل 3 منظمين واكتمل العدد."),
    ("medical", "medical", "P2", ["cctv_ai"], None, {}, "dismiss", "رُفض: تحقق المشرف ولم يكن هناك شخص ساقط."),
    ("visitor_conduct", "visitor_fight", "P3", ["radio", "cctv_ai"], "route_team", {"team": "security"}, "approve_resolve",
     "فصل الأمن بين الطرفين وانتهى الموقف."),
    ("visitor_conduct", "visitor_sitting_path", "P3", ["cctv_ai"], "route_team", {"team": "stewards"}, "approve_resolve",
     "وجّه المنظمون الزوار إلى منطقة الجلوس."),
    ("visitor_conduct", "visitor_wrong_way", "P3", ["cctv_ai", "radio"], "route_team", {"team": "stewards"}, "approve_resolve",
     "أُعيد توجيه الزوار لاتجاه المسار."),
]


def _history_places():
    lay = layout()
    names = {z["id"]: {"ar": z["name_ar"], "en": z["name_en"]} for z in lay["zones"]}
    names.update({l["id"]: {"ar": l["name_ar"], "en": l["name_en"]} for l in lay["locations"]})
    return [(l["zone_id"], l["id"]) for l in lay["locations"]], names


def seed_history(conn, data=None):
    data = data or _data()
    operator = data.get("history_operator", "سجل تجريبي · بيانات تجريبية")
    places, names = _history_places()
    now = datetime.now(RIYADH)
    out = []
    for back in range(1, HISTORY_MONTHS + 1):
        y, m = now.year, now.month - back
        while m < 1:
            y, m = y - 1, m + 12
        rng = random.Random(f"eoip-history-{y}-{m:02d}")
        days = 30 if m != 2 else 28
        n_cases = rng.randint(9, 13)
        for n in range(1, n_cases + 1):
            itype, label, prio, sources, code, params, outcome, note = rng.choice(_HIST)
            zone, loc = rng.choice(places)
            if label in ("crowding", "staff_shortage"):
                loc = None
            opened = datetime(y, m, rng.randint(1, days), rng.randint(10, 22), rng.randint(0, 59), tzinfo=RIYADH)
            snap_base = {"sources": sources, "incident_code": f"INC-{y % 100:02d}{m:02d}-{n:02d}",
                         "incident_type": itype, "incident_kind": {"fire": "emergency", "medical": "emergency",
                                                                   "crowd_pressure": "operational"}.get(itype, "routine"),
                         "incident_label": label, "zone_id": zone, "location_id": loc, "teams": [], "names": names,
                         "history": True}
            rec = None
            if code:
                rec = {"id": None, "code": code, "rec_type": "playbook" if code[:4] in ("FIRE", "MED-") else
                       "route" if code == "route_team" else "option", "rank": 1,
                       "params": {"zone": zone, "location": loc, **params}, "simulation": None}
            t1 = opened + timedelta(minutes=rng.randint(1, 4))
            if outcome == "dismiss":
                out.append(("dismiss", note, prio, t1, {**snap_base, "recommendation": None}))
            else:
                out.append(("approve", None, prio, t1, {**snap_base, "recommendation": rec}))
                t2 = t1 + timedelta(minutes=rng.randint(8, 40))
                out.append(("resolve", note, prio, t2, {**snap_base, "recommendation": None}))
    out.sort(key=lambda r: r[3])
    with transaction(conn):
        conn.execute("DELETE FROM decisions WHERE operator=? AND employee_number IS NULL", (operator,))
        for action, note, prio, ts, snap in out:
            conn.execute("""INSERT INTO decisions (run_id, incident_id, recommendation_id, action, operator, employee_id,
                                employee_number, note, priority_at_decision, created_at, snapshot)
                            VALUES (0, NULL, NULL, ?, ?, NULL, NULL, ?, ?, ?, ?)""",
                         (action, operator, note, prio,
                          ts.astimezone(timezone.utc).isoformat(timespec="milliseconds"),
                          json.dumps(snap, ensure_ascii=False)))
    return len(out)
