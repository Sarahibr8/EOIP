"""EOIP camera agent — person-down detection on the laptop camera (or a video file).

Simulates an AI-enabled site camera: it watches one view, detects a person who
falls / lies down, and sends ONE structured alert to EOIP. It is a source
system like any other; triage happens in EOIP, not here.

Method (deep learning):
    YOLO person detection (Ultralytics, pretrained COCO) -> largest person -> bounding box
    -> FallStateMachine (upright -> lying for >= 1 s) -> alert with confidence
    The model file is loaded from cv/models/ (or EOIP_YOLO_MODEL). The first run needs it
    downloaded once; after that it runs offline. No background learning is needed.

Usage:
    python cv/fall_detector.py                       # laptop camera 0, Zone B / Main Walkway
    python cv/fall_detector.py --camera 1 --zone ZONE-A --location FOOD-COURT
    python cv/fall_detector.py --video clip.mp4      # recorded clip (not live; origin=video_file)
    python cv/fall_detector.py --replay              # fallback: ask EOIP to replay a recorded detection
    python cv/fall_detector.py --backend dshow       # force a capture backend (Windows: dshow | msmf)
    python cv/fall_detector.py --server https://localhost:8000   # if the server was started with --https
    (signs in first: employee number + password, or EOIP_EMPLOYEE / EOIP_PASSWORD)
    python cv/fall_detector.py --model cv/models/yolov8n.pt --conf 0.4
Keys in the preview window:  q quit
Requires: ultralytics (installs torch), opencv-python (with GUI support, not the -headless build), numpy
"""
import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fall_logic import FallStateMachine  # noqa: E402
from analyzer import YoloPersonDetector  # noqa: E402  (shared with the EOIP server)

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "eoip" / "static" / "snapshots"


WINDOW = "EOIP camera agent"
READ_TIMEOUT_S = 5.0     # how long to wait for the first frame from one backend
MAX_READ_GAP_S = 3.0     # live camera: tolerate dropped frames this long before giving up


def _ssl_context(server):
    # run.py --https uses a self-signed certificate, so it cannot be verified
    return ssl._create_unverified_context() if server.startswith("https") else None


_OPENER = None
_CSRF = None


def _meta_csrf(html):
    import re
    m = re.search(r'<meta name="csrf-token" content="([^"]*)"', html)
    return m.group(1) if m else ""


def _origin_headers(base):
    # Django checks Origin/Referer on HTTPS requests (CSRF protection); urllib sends neither by itself.
    return {"Origin": base, "Referer": base + "/"}


def login(server, employee=None, password=None):
    """Sign in as an employee (every /api/ path requires it) and keep the session cookie.
    Credentials come from the arguments, EOIP_EMPLOYEE / EOIP_PASSWORD, or a prompt."""
    global _OPENER, _CSRF
    import getpass
    import http.cookiejar
    import os
    import urllib.parse
    employee = employee or os.environ.get("EOIP_EMPLOYEE") or input("Employee number: ").strip()
    password = password or os.environ.get("EOIP_PASSWORD") or getpass.getpass("Password: ")
    base = server.rstrip("/")
    handlers = [urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())]
    if base.startswith("https"):
        handlers.append(urllib.request.HTTPSHandler(context=_ssl_context(base)))
    opener = urllib.request.build_opener(*handlers)
    with opener.open(base + "/login", timeout=10) as r:
        pre = _meta_csrf(r.read().decode("utf-8"))
    form = urllib.parse.urlencode({"csrfmiddlewaretoken": pre, "employee_number": employee,
                                   "password": password, "next": "/"}).encode()
    req = urllib.request.Request(base + "/login", data=form, method="POST", headers=_origin_headers(base))
    try:
        with opener.open(req, timeout=10) as r:
            page = r.read().decode("utf-8")
    except urllib.error.HTTPError:
        raise SystemExit("Sign-in failed: check the employee number and password.")
    token = _meta_csrf(page)
    if not token or 'id="employeeNumber"' in page:
        raise SystemExit("Sign-in failed: check the employee number and password.")
    _OPENER, _CSRF = opener, token
    print("Signed in to EOIP.", flush=True)


def post(server, path, body=None):
    base = server.rstrip("/")
    req = urllib.request.Request(base + path, method="POST",
                                 data=json.dumps(body or {}).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "X-CSRF-Token": _CSRF or "",
                                          **_origin_headers(base)})
    if _OPENER is not None:
        with _OPENER.open(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    with urllib.request.urlopen(req, timeout=5, context=_ssl_context(server)) as r:
        return json.loads(r.read().decode("utf-8"))


def check_server(server):
    try:
        with urllib.request.urlopen(server.rstrip("/") + "/api/health", timeout=3,
                                    context=_ssl_context(server)) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def backend_order(cv2, choice):
    """Capture backends to try, in order. On Windows DirectShow first: the default
    Media Foundation (MSMF) backend can open a camera and then return no frames."""
    names = {"dshow": "CAP_DSHOW", "msmf": "CAP_MSMF", "v4l2": "CAP_V4L2",
             "avfoundation": "CAP_AVFOUNDATION", "any": "CAP_ANY"}
    if choice == "auto":
        order = ["dshow", "msmf", "any"] if sys.platform.startswith("win") else ["any"]
    else:
        order = [choice]
    return [(n, getattr(cv2, names[n])) for n in order if hasattr(cv2, names[n])]


def open_camera(cv2, index, choice):
    """Open the camera and prove it delivers frames. Returns (cap, backend, first_frame)."""
    for name, api in backend_order(cv2, choice):
        print(f"  trying camera {index} via {name.upper()} …", flush=True)
        cap = cv2.VideoCapture(index, api)
        if not cap.isOpened():
            print(f"    {name.upper()}: could not open the camera", flush=True)
            cap.release()
            continue
        deadline = time.time() + READ_TIMEOUT_S
        while time.time() < deadline:
            ok, frame = cap.read()
            if ok and frame is not None:
                h, w = frame.shape[:2]
                print(f"  camera {index} OK via {name.upper()}: {w}x{h}", flush=True)
                return cap, name, frame
            time.sleep(0.05)
        print(f"    {name.upper()}: opened, but no frames within {READ_TIMEOUT_S:.0f} s", flush=True)
        cap.release()
    return None, None, None


def run(args):
    import cv2
    live = args.video is None
    print(f"EOIP camera agent · {'LIVE camera ' + str(args.camera) if live else 'video ' + args.video} · zone {args.zone}",
          flush=True)
    if not check_server(args.server):
        print(f"WARNING: EOIP server not reachable at {args.server}. Detection will run, but alerts will not reach "
              f"the dashboard. Start run.py, or pass --server https://localhost:8000 if it runs with --https.",
              file=sys.stderr, flush=True)

    first = None
    if live:
        cap, backend, first = open_camera(cv2, args.camera, args.backend)
        if cap is None:
            print("Camera opened by no backend or delivered no frames. Close other apps using the camera, "
                  "check Windows camera privacy settings, try --camera 1, or use --replay.", file=sys.stderr)
            return 2
    else:
        cap = cv2.VideoCapture(args.video)
        if not cap.isOpened():
            print("Video could not be opened.", file=sys.stderr)
            return 2

    if not args.no_window:
        try:
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        except cv2.error:
            print("This OpenCV build has no window support (opencv-python-headless?). "
                  "Run with --no-window, or use the opencv-python package.", file=sys.stderr)
            cap.release()
            return 3

    detector = YoloPersonDetector(model=args.model, conf=args.conf)
    print(f"Loading YOLO model {detector.model_path} …", flush=True)
    try:
        detector.load()
    except Exception as e:  # missing package, missing weights, no internet for the first download
        print(f"Could not load the YOLO model: {e}\nInstall it with: pip install ultralytics, and place the "
              f"weights in cv/models/ (or use --replay).", file=sys.stderr)
        cap.release()
        return 5
    detector_id = detector.info["id"]
    fsm = FallStateMachine(hold_s=args.hold, cooldown_s=args.cooldown)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    frame_i = alerts = 0
    last_ok = time.time()
    exit_code = 0
    print("Model ready. Walk in, stand, then lie down.", flush=True)
    while True:
        if first is not None:
            ok, frame, first = True, first, None
        else:
            ok, frame = cap.read()
        if not ok or frame is None:
            if not live:
                break                                   # end of the video file
            if time.time() - last_ok > MAX_READ_GAP_S:  # live camera stopped delivering
                print(f"Camera stopped delivering frames after {frame_i} frames.", file=sys.stderr)
                exit_code = 4
                break
            time.sleep(0.02)
            continue
        last_ok = time.time()
        frame_i += 1
        scale = 640 / frame.shape[1]
        frame = cv2.resize(frame, (640, int(frame.shape[0] * scale)))
        t = time.time() if live else frame_i / fps
        bbox, meta = detector(frame)
        event = fsm.update(bbox, t)

        if event:
            snap_url = None
            if not args.no_snapshot:
                SNAP_DIR.mkdir(parents=True, exist_ok=True)
                name = f"cv_{int(time.time())}.jpg"
                cv2.imwrite(str(SNAP_DIR / name), cv2.resize(frame, (320, int(frame.shape[0] * 320 / 640))),
                            [cv2.IMWRITE_JPEG_QUALITY, 70])
                snap_url = f"/static/snapshots/{name}"
            signal = {
                "source_system": "cctv_ai", "signal_type": "alert", "category": "person_down",
                "zone_id": args.zone, "confidence": event.confidence,
                "location_id": None if args.location in (None, "", "none") else args.location,
                "origin": "live_cv" if live else "video_file",
                "location_detail": f"Camera {args.camera_id}",
                "payload": {"camera_id": args.camera_id, "detector": detector_id,
                            "aspect": event.aspect, "lying_s": event.lying_s,
                            "height_drop": event.height_drop, "snapshot": snap_url},
            }
            try:
                r = post(args.server, "/api/ingest", signal)
                alerts += 1
                print(f"[ALERT] person_down conf={event.confidence} origin={signal['origin']} "
                      f"-> incident {r.get('incident_id')} ({r.get('disposition')})", flush=True)
            except (urllib.error.URLError, OSError) as e:
                print(f"[ALERT] could not reach EOIP at {args.server}: {e}", file=sys.stderr, flush=True)

        if not args.no_window:
            color = {"upright": (120, 200, 120), "lying": (0, 165, 255), "alerted": (60, 60, 255)}.get(fsm.state, (200, 200, 200))
            if bbox:
                x, y, w, h = bbox
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            label = "LIVE" if live else "VIDEO (not live)"
            cv2.putText(frame, f"EOIP CV {label} | {args.zone} | {fsm.state}", (10, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            cv2.putText(frame, f"{detector_id} | people: {meta.get('people', 0)}", (10, 48),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.imshow(WINDOW, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    cap.release()
    if not args.no_window:
        cv2.destroyAllWindows()
    print(f"Stopped. Frames processed: {frame_i}. Alerts sent: {alerts}.", flush=True)
    return exit_code


def main():
    ap = argparse.ArgumentParser(description="EOIP camera agent (person-down detection)")
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--backend", default="auto", choices=["auto", "dshow", "msmf", "v4l2", "avfoundation", "any"],
                    help="capture backend (auto = DirectShow then MSMF on Windows)")
    ap.add_argument("--video", help="process a video file instead of the camera (sent as video_file)")
    ap.add_argument("--zone", default="ZONE-B", help="ZONE-A | ZONE-B | ZONE-C")
    ap.add_argument("--location", default="MAIN-WALKWAY",
                    help="FOOD-COURT | EVENT-AREA | MAIN-WALKWAY | FIRST-AID | MAIN-GATE | WAITING-AREA | none")
    ap.add_argument("--camera-id", default="CAM-B-03")
    ap.add_argument("--hold", type=float, default=1.0, help="seconds lying before alert")
    ap.add_argument("--cooldown", type=float, default=20.0)
    ap.add_argument("--model", default=None, help="YOLO weights (default: cv/models/yolov8n.pt or EOIP_YOLO_MODEL)")
    ap.add_argument("--conf", type=float, default=0.35, help="minimum YOLO person confidence")
    ap.add_argument("--no-window", action="store_true")
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--replay", action="store_true", help="fallback: send the recorded detection via EOIP")
    ap.add_argument("--employee", help="employee number for sign-in (or EOIP_EMPLOYEE; prompted if missing)")
    args = ap.parse_args()
    if check_server(args.server):
        login(args.server, args.employee)
    if args.replay:
        r = post(args.server, "/api/demo/cv-replay")
        print(f"Replay sent (origin=replay_cv) -> incident {r.get('incident_id')}")
        return 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
