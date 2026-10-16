"""Response teams: availability, nearest-team choice, ETA estimate, assignment.

The roster is SYNTHETIC (data/teams.json). ETA is an *estimate*: mobilisation time +
shortest walking time on the illustrative walkway graph between the six demo locations
(data/teams.json "walk_minutes"). When the incident location is not stated, the ETA is
to the nearest location of the incident's zone. It is labelled as an estimate in the UI.
"""
import heapq
import json
from functools import lru_cache

from ..db import TEAMS_PATH, layout, rows


@lru_cache(maxsize=1)
def _config():
    d = json.loads(TEAMS_PATH.read_text(encoding="utf-8"))
    graph = {}
    for a, b, m in d["walk_minutes"]:
        graph.setdefault(a, []).append((b, float(m)))
        graph.setdefault(b, []).append((a, float(m)))
    zone_locs = {}
    for loc in layout()["locations"]:
        zone_locs.setdefault(loc["zone_id"], []).append(loc["id"])
    return graph, zone_locs, float(d.get("mobilise_minutes", 1.0))


def walk_minutes(src, dst):
    """Shortest walking time in minutes between two locations (None if unreachable)."""
    graph, _, _ = _config()
    if src == dst:
        return 0.0
    best, heap = {src: 0.0}, [(0.0, src)]
    while heap:
        d, node = heapq.heappop(heap)
        if node == dst:
            return d
        if d > best.get(node, 1e9):
            continue
        for nxt, m in graph.get(node, []):
            nd = d + m
            if nd < best.get(nxt, 1e9):
                best[nxt] = nd
                heapq.heappush(heap, (nd, nxt))
    return None


def walk_to(base_location, zone_id, location_id=None):
    """Walking minutes from a base to the incident location, or to the nearest location of the zone."""
    _, zone_locs, _ = _config()
    targets = [location_id] if location_id else zone_locs.get(zone_id, [])
    times = [t for t in (walk_minutes(base_location, x) for x in targets) if t is not None]
    return min(times) if times else None


def eta_minutes(base_location, zone_id, location_id=None):
    w = walk_to(base_location, zone_id, location_id)
    return None if w is None else round(_config()[2] + w, 1)


def all_teams(conn):
    return rows(conn.execute("SELECT * FROM teams ORDER BY kind, id"))


def nearest_available(conn, kind, zone_id, location_id=None, exclude=()):
    """Nearest available team of a kind, or None. Returns team dict + walk_min + eta_min."""
    best = None
    for t in rows(conn.execute("SELECT * FROM teams WHERE kind=? AND status='available'", (kind,))):
        if t["id"] in exclude:
            continue
        w = walk_to(t["base_location"], zone_id, location_id)
        if w is None:
            continue
        if best is None or (w, t["id"]) < (best["walk_min"], best["id"]):
            best = {**t, "walk_min": w, "eta_min": eta_minutes(t["base_location"], zone_id, location_id)}
    return best


def unavailable(conn, team_ids, incident_id):
    """Team ids that are now assigned to a *different* incident."""
    out = []
    for tid in team_ids:
        r = conn.execute("SELECT status, incident_id FROM teams WHERE id=?", (tid,)).fetchone()
        if r is None or (r["status"] == "assigned" and r["incident_id"] != incident_id):
            out.append(tid)
    return out


def assign(conn, team_ids, incident_id, ts):
    for tid in team_ids:
        conn.execute("UPDATE teams SET status='assigned', incident_id=?, assigned_at=? WHERE id=?",
                     (incident_id, ts, tid))


def release(conn, incident_id):
    conn.execute("UPDATE teams SET status='available', incident_id=NULL, assigned_at=NULL WHERE incident_id=?",
                 (incident_id,))
