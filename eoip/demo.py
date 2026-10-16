"""Demo playback engine: replays data/demo_script.json as a live event.

No background workers: the dashboard calls POST /api/demo/tick while it polls,
and each tick ingests every scripted signal whose time has come. The cursor is
advanced inside the same IMMEDIATE transaction, so two concurrent ticks can
never ingest the same signal twice.

The event starts by itself the first time a signed-in dashboard opens (autostart), and it
never "ends": after the scripted part, the event stays live and a light background trickle of
noise and routine traffic (camera health checks and motion, radio check-ins) keeps arriving.
The trickle never creates an incident; real incidents come from the script, the camera and
the phone.
"""
import json
import random
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .core import escalation, extract, pipeline
from .core.normalize import ValidationError
from .db import transaction, to_dict

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_script.json"


@lru_cache(maxsize=1)
def script():
    return json.loads(SCRIPT_PATH.read_text(encoding="utf-8"))


TRICKLE_EVERY_S = 1.0      # one background signal every second of live event time
TRICKLE_MAX_CATCHUP = 3     # after a long pause nobody polled, do not flood the log


def _raw_elapsed(s):
    return (time.time() - s["started_at"]) * s["speed"] if s["running"] and s["started_at"] else 0.0


def state(conn):
    s = to_dict(conn.execute("SELECT * FROM demo_state WHERE id=1").fetchone())
    sc = script()
    elapsed = _raw_elapsed(s)
    total = len(sc["entries"])
    finished = s["cursor"] >= total
    return {"running": bool(s["running"]), "speed": s["speed"], "cursor": min(s["cursor"], total),
            "total": total, "elapsed_s": round(min(elapsed, sc["duration_s"]), 1),
            "duration_s": sc["duration_s"], "finished": finished,
            "live": bool(s["running"]) and finished, "started": s["cursor"] > 0 or bool(s["running"]),
            "started_iso": (datetime.fromtimestamp(s["started_at"], timezone.utc).isoformat()
                            if s["running"] and s["started_at"] else None)}


def start(conn, speed=1.0):
    with transaction(conn):
        conn.execute("UPDATE demo_state SET running=1, started_at=?, speed=? WHERE id=1",
                     (time.time(), max(0.25, min(float(speed), 10.0))))


def autostart(conn):
    """Start the event once: only when it has never started since the last reset. Never restarts a
    running or finished event (refreshing the page or a second screen must not reset anything)."""
    with transaction(conn):
        n = conn.execute("""UPDATE demo_state SET running=1, started_at=?, speed=1.0
                            WHERE id=1 AND running=0 AND cursor=0""", (time.time(),)).rowcount
    return n == 1


def stop(conn):
    with transaction(conn):
        conn.execute("UPDATE demo_state SET running=0 WHERE id=1")


def _to_signal(entry):
    sig = dict(entry["signal"])
    if entry.get("extract"):
        fields = extract.extract(sig["raw_text"])
        voice = extract.to_signal(fields, origin="mock")
        sig = {**voice, "origin": "mock"}
    return sig


def _claim(conn, until_index):
    """Atomically reserve script entries [cursor, until_index)."""
    with transaction(conn):
        cur = conn.execute("SELECT cursor FROM demo_state WHERE id=1").fetchone()[0]
        if until_index <= cur:
            return cur, cur
        conn.execute("UPDATE demo_state SET cursor=? WHERE id=1", (until_index,))
        return cur, until_index


def tick(conn, ingest_all=False):
    """Ingest due signals. Returns number ingested.

    ingest_all loads the rest of the script at once (fallback / review) and keeps the event live."""
    escalation.sweep(conn)          # late cases leave the duty officer for the managers (L1 -> L2 -> L3)
    s = state(conn)
    row = to_dict(conn.execute("SELECT * FROM demo_state WHERE id=1").fetchone())
    entries = script()["entries"]
    total = len(entries)
    if not (s["running"] or ingest_all):
        return 0
    if ingest_all:
        until = max(total, row["cursor"])
    else:
        until = row["cursor"]
        while until < total and entries[until]["t"] <= s["elapsed_s"]:
            until += 1
        if until >= total:      # live: background trickle after the scripted part
            extra = int(max(0.0, _raw_elapsed(row) - script()["duration_s"]) / TRICKLE_EVERY_S)
            until = max(until, total + extra)
    lo, hi = _claim(conn, until)
    n = 0
    zone_ids = {r[0] for r in conn.execute("SELECT id FROM zones")}
    first_trickle = max(lo, total, hi - TRICKLE_MAX_CATCHUP)
    for idx in range(lo, hi):
        if idx < total:
            sig = _to_signal(entries[idx])
        elif idx >= first_trickle:
            sig = trickle_signal(idx - total)
        else:
            continue
        try:
            pipeline.ingest(conn, sig, zone_ids)
            n += 1
        except ValidationError:
            continue  # a broken scripted signal must never stop the demo
    if ingest_all:
        # the event goes live from now on (trickle starts after the scripted duration)
        with transaction(conn):
            conn.execute("UPDATE demo_state SET running=1, started_at=?, speed=1.0 WHERE id=1",
                         (time.time() - script()["duration_s"],))
    return n


_ZONES = ("ZONE-A", "ZONE-B", "ZONE-C")
_CAMS = ("03", "07", "11", "14", "18", "21", "25")
_STATUS = ("الوضع طبيعي في زون B", "Zone A checkpoint all clear", "تبديل وردية فريق الحراسة",
           "Radio check, North team", "الفريق وصل نقطة التجمع", "دورية زون C مستمرة، لا ملاحظات")


def trickle_signal(i):
    """Background signal number i of the live phase: camera or radio only, noise or routine (never an
    incident). Deterministic per index, so concurrent ticks and tests see the same traffic."""
    rng = random.Random(2030 + i)
    zone = rng.choice(_ZONES)
    cam = rng.choice(_CAMS)
    roll = rng.random()
    if roll < 0.5:
        return {"source_system": "cctv_ai", "category": "heartbeat", "zone_id": zone, "origin": "mock",
                "payload": {"camera_id": f"CAM-{zone[-1]}-{cam}", "status": "ok"}}
    if roll < 0.7:
        return {"source_system": "cctv_ai", "category": "unusual_motion", "zone_id": zone, "origin": "mock",
                "confidence": round(rng.uniform(0.3, 0.55), 2), "raw_text": f"كاميرا {cam}: حركة غير اعتيادية",
                "payload": {"camera_id": f"CAM-{zone[-1]}-{cam}"}}
    return {"source_system": "radio", "category": "status_update", "zone_id": zone, "origin": "mock",
            "raw_text": rng.choice(_STATUS)}


CV_REPLAY_SIGNAL = {
    "source_system": "cctv_ai", "signal_type": "alert", "category": "person_down", "zone_id": "ZONE-B",
    "location_id": "MAIN-WALKWAY", "confidence": 0.81, "origin": "replay_cv", "location_detail": "Camera CAM-B-03",
    "payload": {"camera_id": "CAM-B-03", "detector": "replay", "note": "Recorded detection replayed — not live"},
}

FIELD_REPORT_FALLBACK = "شخص مغمى عليه في زون B عند الممر الرئيسي، نحتاج إسعاف بسرعة"
