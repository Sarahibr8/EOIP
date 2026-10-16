"""Person-down decision logic (pure Python, no OpenCV) so it can be unit-tested.

Input per frame: the bounding box of the largest moving body (or None) and a
timestamp. A fall is reported when a body that was recently UPRIGHT (tall box)
becomes LYING (wide box) and stays lying for `hold_s` seconds. Requiring the
upright->lying transition stops furniture, bags or a wide group of people from
triggering an alert on their own.

A second, weaker rule covers a fall the camera did not see (the person entered the view already
falling, or was found on the floor): a PERSON (YOLO only returns people) lying still for
`lying_alone_s` seconds raises a lower-confidence alert. A camera alone is never P1 in EOIP, so such
an alert asks the operator to verify.

One alert per fall: after an alert the machine is DISARMED. It re-arms only after
the person is seen upright again for `rearm_s` seconds, so a person who stays on
the floor (or flickers out of the mask and back while still lying) never produces a
second alert or a second report. The cooldown remains as an extra safety net.
"""
from collections import deque
from dataclasses import dataclass, field

UPRIGHT_MAX_ASPECT = 0.80   # w/h below this = standing / walking
LYING_MIN_ASPECT = 1.25     # w/h above this = lying on the floor


@dataclass
class FallEvent:
    t: float
    confidence: float
    aspect: float
    lying_s: float
    height_drop: float
    seen_fall: bool = True       # False = person found lying (the upright -> lying transition was not seen)


@dataclass
class FallStateMachine:
    hold_s: float = 1.0          # lying must persist this long
    upright_window_s: float = 4.0  # an upright posture must be seen this recently
    cooldown_s: float = 20.0
    rearm_s: float = 0.5         # sustained upright needed to re-arm after an alert
    lying_alone_s: float = 3.0   # a person lying this long raises an alert even without a seen fall
    dropout_s: float = 0.6       # a detector miss shorter than this does not reset the lying timer
    history: deque = field(default_factory=lambda: deque(maxlen=300))
    lying_since: float | None = None
    last_upright_t: float | None = None
    last_upright_h: float | None = None
    last_event_t: float = -1e9
    state: str = "empty"
    armed: bool = True
    upright_since: float | None = None

    last_seen_t: float | None = None

    def update(self, bbox, t):
        """bbox = (x, y, w, h) in pixels or None. Returns FallEvent or None."""
        if bbox is None:
            if self.last_seen_t is not None and t - self.last_seen_t <= self.dropout_s:
                return None          # brief detector miss (blur, partial occlusion): keep the timers
            self.state = "empty" if self.armed else "alerted"
            self.lying_since = None
            self.upright_since = None
            return None
        self.last_seen_t = t
        x, y, w, h = bbox
        aspect = w / max(h, 1)
        self.history.append((t, aspect, h))

        if aspect <= UPRIGHT_MAX_ASPECT:
            self.lying_since = None
            if self.upright_since is None:
                self.upright_since = t
            if not self.armed:
                if t - self.upright_since < self.rearm_s:
                    self.state = "alerted"
                    return None
                self.armed = True
            self.state = "upright"
            self.last_upright_t, self.last_upright_h = t, h
            return None
        self.upright_since = None
        if not self.armed:            # already reported this fall: wait for the person to get up
            self.state = "alerted"
            self.lying_since = None
            return None
        if aspect < LYING_MIN_ASPECT:
            self.state = "transition"
            return None

        self.state = "lying"
        if self.lying_since is None:
            self.lying_since = t
        lying_s = t - self.lying_since
        recently_upright = (self.last_upright_t is not None
                            and self.lying_since - self.last_upright_t <= self.upright_window_s)
        if t - self.last_event_t < self.cooldown_s:
            return None
        if recently_upright:
            if lying_s < self.hold_s:
                return None
            drop = 1 - h / self.last_upright_h if self.last_upright_h else 0.0
            conf = 0.55 + min(0.15, 0.15 * (aspect - LYING_MIN_ASPECT)) + min(0.15, 0.3 * max(0.0, drop)) \
                + min(0.1, 0.1 * (lying_s - self.hold_s))
            seen = True
        else:
            # fall not seen: only a person lying still for a longer time, with a lower confidence
            if lying_s < self.lying_alone_s:
                return None
            drop, seen = 0.0, False
            conf = 0.55 + min(0.1, 0.1 * (aspect - LYING_MIN_ASPECT))
        self.last_event_t = t
        self.state = "alerted"
        self.armed = False
        self.last_upright_t = None
        return FallEvent(t=t, confidence=round(min(conf, 0.95 if seen else 0.7), 2), aspect=round(aspect, 2),
                         lying_s=round(lying_s, 1), height_drop=round(drop, 2), seen_fall=seen)
