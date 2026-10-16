"""Computer-vision tests: posture logic, YOLO output parsing, and the analyzer with a stand-in
detector. None of these measure YOLO's accuracy on real people (see docs/testing.md).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cv"))
from fall_logic import FallStateMachine  # noqa: E402


def feed(fsm, boxes, fps=15):
    events = []
    for i, b in enumerate(boxes):
        e = fsm.update(b, i / fps)
        if e:
            events.append(e)
    return events


STAND = (100, 50, 60, 180)
LIE = (100, 200, 180, 60)


class FallLogic(unittest.TestCase):
    def test_fall_sequence_alerts_once(self):
        ev = feed(FallStateMachine(), [STAND] * 20 + [LIE] * 40)
        self.assertEqual(len(ev), 1)
        self.assertGreaterEqual(ev[0].confidence, 0.6)
        self.assertGreater(ev[0].height_drop, 0.5)

    def test_standing_or_walking_never_alerts(self):
        self.assertEqual(feed(FallStateMachine(), [STAND] * 100), [])

    def test_person_found_lying_alerts_after_longer_hold_with_lower_confidence(self):
        # the fall itself was not seen (e.g. the person entered the view already falling)
        self.assertEqual(feed(FallStateMachine(), [None] * 10 + [LIE] * 40), [])          # < 3 s
        ev = feed(FallStateMachine(), [None] * 10 + [LIE] * 60)                              # 4 s
        self.assertEqual(len(ev), 1)
        self.assertFalse(ev[0].seen_fall)
        self.assertLessEqual(ev[0].confidence, 0.7)

    def test_brief_detector_miss_does_not_reset_the_lying_timer(self):
        seq = [STAND] * 20 + [LIE] * 8 + [None] * 3 + [LIE] * 12      # 3 missed frames = 0.2 s
        self.assertEqual(len(feed(FallStateMachine(), seq)), 1)

    def test_short_lying_below_hold_does_not_alert(self):
        self.assertEqual(feed(FallStateMachine(hold_s=1.0), [STAND] * 20 + [LIE] * 10 + [STAND] * 20), [])

    def test_lying_for_a_long_time_alerts_only_once(self):
        # 2 minutes on the floor (well past the 20 s cooldown) must still be ONE alert
        self.assertEqual(len(feed(FallStateMachine(), [STAND] * 20 + [LIE] * 15 * 120)), 1)

    def test_lying_with_mask_dropouts_alerts_only_once(self):
        # a still body fades into the background (None) and comes back, still lying
        seq = [STAND] * 20 + ([LIE] * 30 + [None] * 10) * 20
        self.assertEqual(len(feed(FallStateMachine(), seq)), 1)

    def test_brief_upright_flicker_does_not_rearm(self):
        seq = [STAND] * 20 + ([LIE] * 40 + [STAND] * 2) * 10   # 2 frames < rearm 0.5 s
        self.assertEqual(len(feed(FallStateMachine(cooldown_s=0), seq)), 1)

    def test_gets_up_and_falls_again_alerts_twice(self):
        seq = [STAND] * 20 + [LIE] * 40 + [STAND] * 30 + [LIE] * 40
        self.assertEqual(len(feed(FallStateMachine(cooldown_s=0), seq)), 2)

    def test_state_stays_alerted_while_lying(self):
        fsm = FallStateMachine()
        feed(fsm, [STAND] * 20 + [LIE] * 60)
        self.assertEqual(fsm.state, "alerted")

    def test_cooldown(self):
        seq = ([STAND] * 15 + [LIE] * 30) * 3
        self.assertEqual(len(feed(FallStateMachine(cooldown_s=60), seq)), 1)


class YoloOutputParsing(unittest.TestCase):
    """The YOLO wrapper: picks the right person box from raw model output. Uses a fake model, so
    it needs neither torch nor the weights; it does NOT measure YOLO's accuracy."""

    def test_largest_person_wins_and_other_classes_are_ignored(self):
        import numpy as np
        from analyzer import largest_person
        xyxy = np.array([[0, 0, 50, 100], [10, 10, 210, 110], [0, 0, 400, 400]])   # small, large, car
        conf = np.array([0.9, 0.8, 0.99])
        cls = np.array([0, 0, 2])
        bbox, c, n = largest_person(xyxy, conf, cls)
        self.assertEqual((bbox, n), ((10, 10, 200, 100), 2))
        self.assertAlmostEqual(c, 0.8)

    def test_low_confidence_person_is_ignored(self):
        import numpy as np
        from analyzer import largest_person
        self.assertEqual(largest_person(np.array([[0, 0, 50, 100]]), np.array([0.1]), np.array([0])),
                         (None, None, 0))

    def test_wrapper_calls_model_for_persons_only(self):
        import numpy as np
        from analyzer import YoloPersonDetector

        class Boxes:
            xyxy, conf, cls = np.array([[5, 5, 65, 185]]), np.array([0.77]), np.array([0])
            def __len__(self):
                return 1

        class Fake:
            calls = []
            def predict(self, frame, **kw):
                Fake.calls.append(kw)
                return [type("R", (), {"boxes": Boxes()})()]

        det = YoloPersonDetector(model="yolov8n.pt")
        det.model = Fake()
        bbox, meta = det(np.zeros((240, 320, 3), np.uint8))
        self.assertEqual(bbox, (5, 5, 60, 180))
        self.assertEqual(meta["people"], 1)
        self.assertEqual(Fake.calls[0]["classes"], [0])
        self.assertEqual(det.info["id"], "yolo:yolov8n.pt")
        self.assertTrue(det.info["trained_model"])

    def test_empty_result_is_no_person(self):
        import numpy as np
        from analyzer import YoloPersonDetector

        class Fake:
            def predict(self, frame, **kw):
                return [type("R", (), {"boxes": None})()]

        det = YoloPersonDetector()
        det.model = Fake()
        self.assertEqual(det(np.zeros((10, 10, 3), np.uint8))[0], None)

    def test_model_name_can_be_overridden(self):
        import os
        from analyzer import model_name
        old = os.environ.get("EOIP_YOLO_MODEL")
        os.environ["EOIP_YOLO_MODEL"] = "yolo11n.pt"
        try:
            self.assertEqual(model_name(), "yolo11n.pt")
        finally:
            os.environ.pop("EOIP_YOLO_MODEL", None)
            if old:
                os.environ["EOIP_YOLO_MODEL"] = old


class AnalyzerWithStandInDetector(unittest.TestCase):
    """FallAnalyzer + a scripted detector: mechanics only (frames -> state machine -> one event)."""

    def run_frames(self, n, **kw):
        import numpy as np
        from analyzer import FallAnalyzer
        from tests.helpers_cv import ScriptedDetector
        an, events, states = FallAnalyzer(detector=ScriptedDetector(**kw)), [], []
        for i in range(n):
            out = an.feed(np.zeros((240, 320, 3), np.uint8), i / 15)
            states.append(out["state"])
            if out["event"]:
                events.append(out["event"])
        return events, states

    def test_stand_then_lie_alerts_once(self):
        events, states = self.run_frames(300, stand=30)
        self.assertEqual(len(events), 1)
        self.assertIn("upright", states)
        self.assertEqual(states[-1], "alerted")

    def test_standing_only_never_alerts(self):
        self.assertEqual(self.run_frames(300, stand=30, lie=False)[0], [])

    def test_nobody_in_view_never_alerts(self):
        events, states = self.run_frames(100, nobody=True)
        self.assertEqual((events, set(states)), ([], {"empty"}))

    def test_no_background_learning_phase(self):
        _, states = self.run_frames(5, stand=30)
        self.assertNotIn("learning", states)


class RealYolo(unittest.TestCase):
    """Runs the real model only where it is installed and the weights are present."""

    def test_blank_frame_has_no_person(self):
        import importlib.util
        import analyzer
        weights = analyzer.MODELS_DIR / analyzer.DEFAULT_MODEL
        if importlib.util.find_spec("ultralytics") is None or not weights.exists():
            self.skipTest("ultralytics or cv/models/yolov8n.pt not available")
        import numpy as np
        bbox, _ = analyzer.YoloPersonDetector(model=str(weights))(np.full((480, 640, 3), 128, np.uint8))
        self.assertIsNone(bbox)


if __name__ == "__main__":
    unittest.main()
