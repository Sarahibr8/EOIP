"""Camera input from the phone / browser, analysed on the EOIP server.

Two honest paths, both using the SAME detector as the laptop agent (cv/analyzer.py: a YOLO
person detector + a posture rule):

  * live   - the phone page streams camera frames (JPEG, ~6 fps) to a session; each frame is
             analysed as it arrives. A detection is sent as origin "live_cv".
  * video  - an uploaded video file is analysed frame by frame. A detection is sent as
             origin "video_file" (analysed, but not live).

Opening the camera or playing a video is NOT a detection: an alert is only created when the
state machine sees an upright person become a lying person and stay lying for hold_s seconds.
The replay fallback (/api/demo/cv-replay, origin "replay_cv") does no analysis at all.
"""
import logging
import os
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..core import pipeline
from ..core.normalize import ValidationError
from ..db import now_iso, to_dict
from ..http import api, body, error

log = logging.getLogger("eoip")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cv"))
SNAP_DIR = Path(__file__).resolve().parents[1] / "static" / "snapshots"

LIVE_WARMUP_FRAMES = 0       # YOLO needs no empty-scene background learning
VIDEO_WARMUP_FRAMES = 0
MAX_VIDEO_S = 180            # analyse at most this much video
VIDEO_ANALYSE_FPS = 8        # an uploaded video is sampled at ~8 frames/s: the fall rule is time-based
                             # (lying held >= 1 s), so 8 frames/s is enough and ~4x faster than 30 frames/s
SESSION_IDLE_S = 120
MAX_FRAME_BYTES = 600_000

_sessions = {}
_lock = threading.Lock()


def _cv():
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        import analyzer
        return analyzer.detector_available()
    except ImportError:
        return False


def _place(conn, b):
    """Validate zone / location chosen on the phone. Location must belong to the zone."""
    zone = b.get("zone_id") or None
    loc = b.get("location_id") or None
    zone_ids = {r[0] for r in conn.execute("SELECT id FROM zones")}
    locs = {r[0]: r[1] for r in conn.execute("SELECT id, zone_id FROM locations")}
    if loc and loc not in locs:
        return None, None, "invalid_location"
    if loc and not zone:
        zone = locs[loc]
    if zone not in zone_ids:
        return None, None, "zone_required"
    if loc and locs[loc] != zone:
        return None, None, "location_not_in_zone"
    return zone, loc, None


def _alert(conn, event, zone, loc, origin, camera_id, analyzer, extra=None):
    extra = extra or {}
    event_at = now_iso()
    snap_url = None
    try:
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        name = f"cv_{origin}_{int(time.time() * 1000)}.jpg"
        if analyzer.snapshot(SNAP_DIR / name):
            snap_url = f"/static/snapshots/{name}"
    except OSError:
        pass
    signal = {
        "source_system": "cctv_ai", "signal_type": "alert", "category": "person_down",
        "zone_id": zone, "location_id": loc, "confidence": event.confidence, "origin": origin,
        "location_detail": f"Camera {camera_id}", "occurred_at": event_at,
        "payload": {"camera_id": camera_id, "detector": analyzer.detector_id, "aspect": event.aspect,
                    "lying_s": event.lying_s, "height_drop": event.height_drop, "snapshot": snap_url,
                    "seen_fall": getattr(event, "seen_fall", True),
                    **extra},
    }
    result = pipeline.ingest(conn, signal)
    inc = to_dict(conn.execute("SELECT id, code, priority, status FROM incidents WHERE id=?",
                               (result["incident_id"],)).fetchone()) if result.get("incident_id") else None
    return {**result, "incident": inc, "confidence": event.confidence, "snapshot": snap_url,
            "event_at": event_at, "zone_id": zone, "location_id": loc, "origin": origin,
            "event_offset_s": extra.get("video_t_s")}


def _gc():
    now = time.time()
    for sid in [s for s, v in _sessions.items() if now - v["last_seen"] > SESSION_IDLE_S]:
        _sessions.pop(sid, None)


def _new_analyzer(warmup):
    from analyzer import FallAnalyzer
    analyzer = FallAnalyzer(warmup_frames=warmup)
    if hasattr(analyzer.detector, "load"):
        analyzer.detector.load()          # load YOLO now, not during the first frame
    return analyzer


@require_GET
@api
def status(request):
    import analyzer
    info = analyzer.detector_info()
    return {"available": _cv(), "detector": info["id"], "trained_model": bool(info["trained_model"]),
            "model": info.get("model")}


@require_POST
@api
def start_session(request):
    """Start a live phone-camera session for one zone / location."""
    if not _cv():
        return error("cv_unavailable", 503)
    zone, loc, err = _place(request.eoip_db, body(request))
    if err:
        return error(err)
    try:
        analyzer = _new_analyzer(LIVE_WARMUP_FRAMES)
    except Exception as e:                    # weights missing and no internet, torch error, ...
        log.error("YOLO model could not be loaded: %s", e)
        return error("cv_model_unavailable", 503)
    sid = uuid.uuid4().hex[:12]
    with _lock:
        _gc()
        _sessions[sid] = {"analyzer": analyzer, "zone": zone, "location": loc,
                          "camera_id": f"PHONE-{sid[:4].upper()}", "last_seen": time.time(), "alerts": [],
                          "lock": threading.Lock()}
    return {"session_id": sid, "camera_id": _sessions[sid]["camera_id"], "warmup_frames": LIVE_WARMUP_FRAMES}, 201


@require_POST
@api
def session_frame(request, sid):
    """One JPEG frame (raw body, Content-Type image/jpeg). Header X-Frame-Time: client ms."""
    s = _sessions.get(sid)
    if s is None:
        return error("session_not_found", 404)
    data = request.body
    if not data or len(data) > MAX_FRAME_BYTES:
        return error("invalid_frame")
    import cv2
    import numpy as np
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return error("invalid_frame")
    try:
        t = float(request.headers.get("X-Frame-Time", "")) / 1000.0
    except ValueError:
        t = time.time()
    with s["lock"]:
        s["last_seen"] = time.time()
        out = s["analyzer"].feed(frame, t)
        alert = None
        if out["event"]:
            alert = _alert(request.eoip_db, out["event"], s["zone"], s["location"], "live_cv", s["camera_id"],
                           s["analyzer"], {"device": "phone_camera"})
            s["alerts"].append(alert)
    return {"state": out["state"], "frames": out["frames"], "warmup": out["warmup"], "bbox": out["bbox"],
            "alert": alert}


@require_http_methods(["DELETE"])
@api
def end_session(request, sid):
    with _lock:
        s = _sessions.pop(sid, None)
    if s is None:
        return error("session_not_found", 404)
    return {"frames": s["analyzer"].frames, "alerts": len(s["alerts"])}


@require_POST
@api
def analyse_video(request):
    """Analyse an uploaded video file (multipart field 'video' + zone_id / location_id)."""
    if not _cv():
        return error("cv_unavailable", 503)
    conn = request.eoip_db
    zone, loc, err = _place(conn, request.POST)
    if err:
        return error(err)
    f = request.FILES.get("video")
    if f is None or not f.name:
        return error("video_required")
    import cv2
    suffix = Path(f.name).suffix.lower()[:8] or ".mp4"
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as out_file:
            for chunk in f.chunks():
                out_file.write(chunk)
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return error("video_unreadable", 422)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        if not 1 <= fps <= 120:
            fps = 15.0
        try:
            analyzer = _new_analyzer(VIDEO_WARMUP_FRAMES)
        except Exception as e:
            cap.release()
            log.error("YOLO model could not be loaded: %s", e)
            return error("cv_model_unavailable", 503)
        events, alerts, n, analysed = [], [], 0, 0
        camera_id = "VIDEO-" + uuid.uuid4().hex[:4].upper()
        started = time.time()
        step = max(1, round(fps / VIDEO_ANALYSE_FPS))
        while n < MAX_VIDEO_S * fps:
            if n % step:                     # skipped frame: grab() advances without decoding
                if not cap.grab():
                    break
                n += 1
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            n += 1
            analysed += 1
            out = analyzer.feed(frame, n / fps)
            if out["event"]:
                ev = out["event"]
                events.append({"t_s": round(n / fps, 1), "confidence": ev.confidence})
                alerts.append(_alert(conn, ev, zone, loc, "video_file", camera_id, analyzer,
                                     {"file": f.name[:80], "video_t_s": round(n / fps, 1)}))
                break                        # one fall = one report: stop here and answer at once
        cap.release()
        if n == 0:
            return error("video_unreadable", 422)
        return {"frames": n, "analysed_frames": analysed, "fps": round(fps, 1), "duration_s": round(n / fps, 1),
                "events": events, "alerts": alerts,
                "processing_s": round(time.time() - started, 1)}, 201
    except ValidationError as e:
        return error("validation_error", errors=e.errors)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
