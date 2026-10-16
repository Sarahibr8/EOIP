"""Stand-in person detector for tests.

The real detector is YOLO (cv/analyzer.py: YoloPersonDetector). Tests must not depend on a
model download, so the pipeline mechanics (frames -> posture state machine -> alert -> incident)
are exercised with a detector that returns scripted person boxes. It does NOT test YOLO's
accuracy; see docs/testing.md for the manual camera test.
"""
STAND = (100, 50, 60, 180)
LIE = (100, 200, 180, 60)


class ScriptedDetector:
    """Returns STAND for the first `stand` frames, then LIE (or nothing if lie=False)."""

    def __init__(self, stand=45, lie=True, nobody=False):
        self.stand, self.lie, self.nobody, self.i = stand, lie, nobody, 0
        self.info = {"id": "scripted_test_detector", "trained_model": False, "model": None}

    def reset(self):
        self.i = 0

    def __call__(self, frame):
        self.i += 1
        if self.nobody:
            return None, {"people": 0}
        if self.i <= self.stand or not self.lie:
            return STAND, {"people": 1}
        return LIE, {"people": 1}


def install(**kw):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cv"))
    import analyzer
    analyzer.set_detector_factory(lambda: ScriptedDetector(**kw))
    return analyzer


def uninstall():
    import analyzer
    analyzer.set_detector_factory(None)
