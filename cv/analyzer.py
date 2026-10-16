"""Shared person-down analyzer used by the laptop camera agent (fall_detector.py) AND by the
EOIP server for the phone camera (live frames) and uploaded video files.

Method (deep learning): a pretrained YOLO object detector (Ultralytics, COCO "person" class)
finds the people in every frame -> bounding box of the largest person -> FallStateMachine
(upright -> lying for >= hold_s). The YOLO model is general-purpose and NOT fine-tuned on falls;
the "fall" decision is a posture rule on top of its person boxes. There is no background to
learn: it works on a moving camera and with people already in view.
Accuracy on real falls has NOT been measured; verify every alert.

The detector is pluggable (anything callable as detector(frame) -> (bbox | None, meta)) so the
pipeline can be tested without the model (see tests/helpers_cv.py).
"""
import importlib.util
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fall_logic import FallStateMachine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = Path(__file__).resolve().parent / "models"
DEFAULT_MODEL = "yolov8n.pt"      # nano: fastest on a laptop CPU. Override: EOIP_YOLO_MODEL=yolo11n.pt
PERSON_CLASS = 0                  # COCO class id of "person"
MIN_CONF = 0.35                   # ignore person boxes below this YOLO confidence
MAX_WORK_WIDTH = 960              # frames wider than this are downscaled before inference


def model_name():
    """Model file/name to load: EOIP_YOLO_MODEL, else cv/models/yolov8n.pt if present, else the
    bare name (Ultralytics then downloads it once - needs internet the first time)."""
    env = os.environ.get("EOIP_YOLO_MODEL")
    if env:
        return env
    local = MODELS_DIR / DEFAULT_MODEL
    return str(local) if local.exists() else DEFAULT_MODEL


def _np(x):
    """Torch tensor / array-like -> numpy (so the parser is testable without torch)."""
    if hasattr(x, "cpu"):
        x = x.cpu()
    if hasattr(x, "numpy"):
        x = x.numpy()
    import numpy as np
    return np.asarray(x)


def largest_person(xyxy, conf, cls, min_conf=MIN_CONF):
    """Pick the largest 'person' box from raw detections. Returns ((x, y, w, h), conf, n_people)
    or (None, None, 0)."""
    people = []
    for (x1, y1, x2, y2), c, k in zip(xyxy, conf, cls):
        if int(k) == PERSON_CLASS and float(c) >= min_conf:
            people.append(((float(x1), float(y1), float(x2), float(y2)), float(c)))
    if not people:
        return None, None, 0
    (x1, y1, x2, y2), c = max(people, key=lambda p: (p[0][2] - p[0][0]) * (p[0][3] - p[0][1]))
    return (int(x1), int(y1), int(x2 - x1), int(y2 - y1)), c, len(people)


class YoloPersonDetector:
    """Ultralytics YOLO person detector. One model per process, shared by all sessions
    (inference is serialised with a lock)."""

    _shared = None
    _shared_lock = threading.Lock()

    def __init__(self, model=None, conf=MIN_CONF, imgsz=640, device=None):
        self.model_path = model or model_name()
        self.conf, self.imgsz, self.device = conf, imgsz, device
        self.model = None
        self._lock = threading.Lock()
        self.info = {"id": f"yolo:{Path(self.model_path).name}", "trained_model": True,
                     "model": Path(self.model_path).name}

    @classmethod
    def shared(cls):
        with cls._shared_lock:
            if cls._shared is None:
                cls._shared = cls()
            return cls._shared

    def load(self):
        with self._lock:
            if self.model is None:
                from ultralytics import YOLO  # heavy import: only when the camera is really used
                self.model = YOLO(self.model_path)
                import numpy as np
                self.model.predict(np.zeros((self.imgsz, self.imgsz, 3), np.uint8), verbose=False,
                                   imgsz=self.imgsz, device=self.device)   # warm-up inference
        return self

    def reset(self):
        pass  # stateless: nothing to re-learn

    def __call__(self, frame):
        self.load()
        with self._lock:
            res = self.model.predict(frame, classes=[PERSON_CLASS], conf=self.conf, imgsz=self.imgsz,
                                     device=self.device, verbose=False)
        boxes = res[0].boxes
        if boxes is None or len(boxes) == 0:
            return None, {"people": 0}
        bbox, c, n = largest_person(_np(boxes.xyxy), _np(boxes.conf), _np(boxes.cls), self.conf)
        return bbox, {"people": n, "yolo_conf": round(c, 2) if c is not None else None}


# --- detector selection (tests can inject a stand-in) --------------------------------------
_factory = None


def set_detector_factory(factory):
    """Install a callable returning a detector (tests / experiments). None restores YOLO."""
    global _factory
    _factory = factory


def create_detector():
    return _factory() if _factory is not None else YoloPersonDetector.shared()


def detector_available():
    """Can a detector be created here? (YOLO needs the `ultralytics` package.)"""
    return _factory is not None or importlib.util.find_spec("ultralytics") is not None


def detector_info():
    if _factory is not None:
        return dict(getattr(_factory(), "info", {"id": "custom", "trained_model": False}))
    return dict(YoloPersonDetector.shared().info)


class FallAnalyzer:
    """Feed frames (BGR numpy arrays) with timestamps; get the tracking state and, at most
    once per cooldown, a FallEvent."""

    def __init__(self, warmup_frames=0, hold_s=1.0, cooldown_s=20.0, detector=None):
        import cv2
        self.cv2 = cv2
        self.detector = detector if detector is not None else create_detector()
        self.warmup = warmup_frames
        self.fsm = FallStateMachine(hold_s=hold_s, cooldown_s=cooldown_s)
        self.frames = 0
        self.last_frame = None
        self.last_meta = {}

    @property
    def detector_id(self):
        return getattr(self.detector, "info", {}).get("id", "custom")

    @property
    def warming(self):
        return self.frames < self.warmup

    def feed(self, frame, t):
        cv2 = self.cv2
        if frame.shape[1] > MAX_WORK_WIDTH:
            scale = MAX_WORK_WIDTH / frame.shape[1]
            frame = cv2.resize(frame, (MAX_WORK_WIDTH, int(frame.shape[0] * scale)))
        self.frames += 1
        self.last_frame = frame
        bbox, meta = self.detector(frame)
        self.last_meta = meta or {}
        event = self.fsm.update(bbox, t)
        state = "learning" if self.warming else self.fsm.state
        return {"state": state, "bbox": list(bbox) if bbox else None, "event": event, "frames": self.frames,
                "warmup": self.warmup, "people": self.last_meta.get("people")}

    def snapshot(self, path, width=320):
        if self.last_frame is None:
            return False
        f = self.last_frame
        self.cv2.imwrite(str(path), self.cv2.resize(f, (width, int(f.shape[0] * width / f.shape[1]))),
                         [self.cv2.IMWRITE_JPEG_QUALITY, 70])
        return True
