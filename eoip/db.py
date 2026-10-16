"""SQLite access layer for the EOIP operational tables (stdlib sqlite3).

The Django project uses the SAME database file (settings.DATABASES / EOIP_DB): Django owns its
own tables (users, sessions, admin) through migrations; the operational tables below are created
from schema.sql and mapped read-only as unmanaged Django models (eoip/models.py).

Every request / unit of work opens its own connection. Writes that must be
serialized (ingestion, demo ticks, decisions) run inside `transaction()` which
uses BEGIN IMMEDIATE so concurrent writers queue instead of interleaving.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
ZONES_PATH = ROOT / "data" / "zones.json"
TEAMS_PATH = ROOT / "data" / "teams.json"
DEFAULT_DB = ROOT / "db.sqlite3"   # same file as Django (eoip_project/settings.py)

JSON_FIELDS = {"payload", "priority_reasons", "params", "simulation", "neighbors", "recommendation_params",
               "correlation", "snapshot"}
SCHEMA_VERSION = 4


def db_path():
    return Path(os.environ.get("EOIP_DB", DEFAULT_DB))


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def parse_iso(value):
    return datetime.fromisoformat(value)


def connect(path=None):
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)  # autocommit; explicit BEGIN
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction(conn):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def to_dict(row):
    if row is None:
        return None
    d = dict(row)
    for k in JSON_FIELDS & d.keys():
        if isinstance(d[k], str):
            d[k] = json.loads(d[k])
    return d


def rows(cursor):
    return [to_dict(r) for r in cursor.fetchall()]


def _table_names(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _legacy_decisions(conn):
    """Read decisions written by schema v1/v2 together with what they referred to, so the
    permanent log keeps them (with names) after the operational tables are rebuilt."""
    out = []
    has_params = "params" in {r[1] for r in conn.execute("PRAGMA table_info(recommendations)")}
    for d in conn.execute(
            f"""SELECT d.*, i.code incident_code, i.type incident_type, i.zone_id zone_id,
                       z.name_ar zone_ar, z.name_en zone_en, r.code rec_code, r.rec_type rec_type
                       {", r.params rec_params, r.simulation rec_sim" if has_params else ""}
                FROM decisions d LEFT JOIN incidents i ON i.id=d.incident_id
                LEFT JOIN zones z ON z.id=i.zone_id LEFT JOIN recommendations r ON r.id=d.recommendation_id
                ORDER BY d.id""").fetchall():
        d = dict(d)
        rec = None
        if d.get("rec_code"):
            rec = {"code": d["rec_code"], "rec_type": d["rec_type"],
                   "params": json.loads(d.get("rec_params") or "{}")}
            sim = json.loads(d.get("rec_sim") or "null")
            if sim:
                rec["simulation"] = sim
        names = {d["zone_id"]: {"ar": d["zone_ar"], "en": d["zone_en"]}} if d.get("zone_id") else {}
        snap = {"incident_code": d.get("incident_code"), "incident_type": d.get("incident_type"),
                "zone_id": d.get("zone_id"), "location_id": None, "names": names, "recommendation": rec,
                "teams": [], "legacy_layout": True}
        out.append((d["action"], d["operator"] or "?", d["note"], d["priority_at_decision"], d["created_at"],
                    json.dumps(snap, ensure_ascii=False)))
    return out


def init_schema(conn):
    """Create the schema, migrating older databases to v4.

    v1/v2 -> v3 changes the site layout (Zone A/B/C + six locations), adds location columns, a
    'video_file' origin and a permanent decision log. Operational rows (signals, incidents,
    recommendations, teams) are demo data and are rebuilt; DECISIONS ARE KEPT, each with a
    self-contained snapshot of what it referred to.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    existing = _table_names(conn)
    # The old v1/v2 -> v3 migration rebuilds demo-operational tables while
    # preserving the decisions as snapshots. Keep that behavior scoped to
    # those old versions: v3 -> v4 only adds auth tables and nullable identity
    # columns, and must never rebuild or clear an existing v3 database.
    if version < 3 and "zones" in existing:
        kept = _legacy_decisions(conn) if "decisions" in existing else []
        conn.execute("PRAGMA foreign_keys = OFF")
        for t in ("decisions", "recommendations", "alerts", "incidents", "teams", "locations", "zones", "demo_state"):
            conn.execute(f"DROP TABLE IF EXISTS {t}")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        for row in kept:
            conn.execute("""INSERT INTO decisions (run_id, action, operator, note, priority_at_decision, created_at,
                                snapshot) VALUES (1,?,?,?,?,?,?)""", row)
        conn.execute("UPDATE demo_state SET run_id=2 WHERE id=1")
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    if version < 4 and "decisions" in _table_names(conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(decisions)")}
        if "employee_id" not in cols:
            conn.execute("ALTER TABLE decisions ADD COLUMN employee_id INTEGER")
        if "employee_number" not in cols:
            conn.execute("ALTER TABLE decisions ADD COLUMN employee_number TEXT")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def layout():
    return json.loads(ZONES_PATH.read_text(encoding="utf-8"))


def seed_teams(conn):
    data = json.loads(TEAMS_PATH.read_text(encoding="utf-8"))
    zone_of = {loc["id"]: loc["zone_id"] for loc in layout()["locations"]}
    for t in data["teams"]:
        conn.execute(
            """INSERT OR REPLACE INTO teams (id, name_ar, name_en, kind, base_zone, base_location, members, status,
                   incident_id, assigned_at) VALUES (?,?,?,?,?,?,?, 'available', NULL, NULL)""",
            (t["id"], t["name_ar"], t["name_en"], t["kind"], zone_of[t["base_location"]], t["base_location"],
             t["members"]))


def seed_zones(conn):
    data = layout()
    for z in data["zones"]:
        x, y, w, h = z["map"]
        conn.execute(
            """INSERT OR REPLACE INTO zones (id, name_ar, name_en, kind, criticality, capacity, occupancy,
                   inflow_per_min, outflow_per_min, staff_on_duty, staff_required, neighbors,
                   map_x, map_y, map_w, map_h)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (z["id"], z["name_ar"], z["name_en"], z["kind"], z["criticality"], z["capacity"],
             z["occupancy"], z["inflow_per_min"], z["outflow_per_min"], z["staff_on_duty"],
             z["staff_required"], json.dumps(z["neighbors"]), x, y, w, h),
        )
    for loc in data["locations"]:
        conn.execute("""INSERT OR REPLACE INTO locations (id, zone_id, name_ar, name_en, map_x, map_y)
                        VALUES (?,?,?,?,?,?)""",
                     (loc["id"], loc["zone_id"], loc["name_ar"], loc["name_en"], *loc["map"]))


def current_run(conn):
    return conn.execute("SELECT run_id FROM demo_state WHERE id=1").fetchone()[0]


def reset_all(conn, keep_decisions=True):
    """Wipe operational data (signals, incidents, recommendations, team assignments) and restore
    the baseline layout. The decision log is permanent: its rows are kept (their incident links
    become NULL, the snapshot keeps the details) and a new run id starts."""
    with transaction(conn):
        if not keep_decisions:
            conn.execute("DELETE FROM decisions")
            conn.execute("DELETE FROM escalations")
        for table in ("teams", "recommendations", "alerts", "incidents", "locations"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('recommendations','alerts','incidents')")
        seed_zones(conn)
        seed_teams(conn)
        conn.execute("""UPDATE demo_state SET running=0, started_at=NULL, speed=1.0, cursor=0, run_id=run_id+1
                        WHERE id=1""")


def init_db(path=None, reset=False):
    conn = connect(path)
    init_schema(conn)
    expected = {z["id"] for z in layout()["zones"]}
    have = {r[0] for r in conn.execute("SELECT id FROM zones")}
    if (reset or have != expected or conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 0
            or conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 0):
        reset_all(conn)
    return conn
