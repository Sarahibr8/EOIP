"""v3 behaviour: Zone A/B/C + six locations, location-aware linking, field reports with
unknown fields, staffing what-if, permanent decision log with operator name, phone
camera (live frames + uploaded video) vs replay."""
import os
import unittest
from pathlib import Path

from tests.helpers import OPERATOR, make_client, restart_client, sig
from eoip import db  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
OP = OPERATOR


class Base(unittest.TestCase):
    def setUp(self):
        self.app, self.c, self.path = make_client()

    def tearDown(self):
        from django.db import connections
        connections.close_all()   # Windows cannot delete an open SQLite file
        for s in ("", "-wal", "-shm"):
            try:
                os.remove(self.path + s)
            except OSError:
                pass

    def post(self, url, **body):
        return self.c.post(url, json=body)

    def ingest(self, **kw):
        r = self.post("/api/ingest", **sig(**kw))
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def detail(self, iid):
        return self.c.get(f"/api/incidents/{iid}").get_json()

    def decide(self, iid, **body):
        body.setdefault("operator", OP)
        body.setdefault("note", "test decision reason")
        return self.post(f"/api/incidents/{iid}/decisions", **body)


class Layout(Base):
    def test_three_zones_six_locations_everywhere(self):
        s = self.c.get("/api/state").get_json()
        self.assertEqual(sorted(z["name_en"] for z in s["zones"]), ["Zone A", "Zone B", "Zone C"])
        self.assertEqual(sorted(z["name_ar"] for z in s["zones"]), ["زون A", "زون B", "زون C"])
        self.assertEqual(sorted(l["name_en"] for l in s["locations"]),
                         ["Event Area", "First Aid Point", "Food Court", "Main Gate", "Main Walkway", "Waiting Area"])
        lay = self.c.get("/api/layout").get_json()
        self.assertEqual(len(lay["zones"]), 3)
        self.assertEqual(len(lay["locations"]), 6)
        self.assertIn("NOT the official", lay["note"])

    def test_no_old_zone_names_left_in_data_or_ui_text(self):
        old = ["القاعة أ", "القاعة ب", "القاعة ج", "القاعة د", "Hall A", "Hall B", "Hall C", "Hall D",
               "HALL-", "GATE-N", "GATE-E", "GATE-S", "PLAZA", "الساحة المركزية", "North Gate"]
        files = [ROOT / "data" / f for f in ("zones.json", "teams.json", "demo_script.json", "lexicon.json")]
        files += list((ROOT / "eoip" / "static" / "i18n").glob("*.json"))
        files += list((ROOT / "eoip" / "static" / "js").rglob("*.js"))
        files += [ROOT / "eoip" / "demo.py", ROOT / "eoip" / "templates" / "eoip" / "field.html",
                  ROOT / "eoip" / "templates" / "eoip" / "app.html"]
        hits = [(f.name, o) for f in files for o in old if o in f.read_text(encoding="utf-8")]
        self.assertEqual(hits, [])

    def test_location_must_belong_to_zone(self):
        r = self.post("/api/ingest", **sig(zone_id="ZONE-C", location_id="FOOD-COURT"))
        self.assertEqual(r.status_code, 400)
        r = self.ingest(location_id="FOOD-COURT", zone_id=None)        # zone taken from the layout
        inc = self.detail(r["incident_id"])
        self.assertEqual((inc["zone_id"], inc["location_id"]), ("ZONE-A", "FOOD-COURT"))


class LocationLinking(Base):
    def test_same_zone_different_location_emergencies_are_separate(self):
        a = self.ingest(location_id="FOOD-COURT")
        b = self.ingest(source_system="radio", category="smoke_report", raw_text="دخان", location_id="EVENT-AREA")
        self.assertNotEqual(a["incident_id"], b["incident_id"])
        first = self.detail(b["incident_id"])["alerts"][0]["correlation"]
        self.assertEqual([r["key"] for r in first["reasons"]], ["no_open_match", "different_location"])

    def test_unstated_location_still_links_with_reason(self):
        a = self.ingest(location_id="FOOD-COURT")
        b = self.ingest(source_system="radio", category="smoke_report", raw_text="دخان في زون A")
        self.assertEqual(a["incident_id"], b["incident_id"])
        keys = [r["key"] for r in self.detail(a["incident_id"])["alerts"][1]["correlation"]["reasons"]]
        self.assertIn("location_not_stated", keys)

    def test_same_location_reason(self):
        a = self.ingest(location_id="FOOD-COURT")
        self.ingest(source_system="service_desk", category="burning_smell", location_id="FOOD-COURT")
        keys = [r["key"] for r in self.detail(a["incident_id"])["alerts"][1]["correlation"]["reasons"]]
        self.assertIn("same_location", keys)

    def test_operational_pressure_links_by_zone(self):
        a = self.ingest(source_system="crowd_sensors", category="occupancy_high", zone_id="ZONE-C",
                        location_id="MAIN-GATE", payload={"occupancy": 1300})
        b = self.ingest(source_system="radio", category="crowd_report", zone_id="ZONE-C",
                        location_id="WAITING-AREA", raw_text="زحمة")
        self.assertEqual(a["incident_id"], b["incident_id"])

    def test_repeat_at_another_location_is_not_a_duplicate(self):
        self.ingest(location_id="FOOD-COURT")
        r = self.ingest(location_id="EVENT-AREA")
        self.assertEqual(r["disposition"], "correlated")

    def test_incident_location_is_filled_by_later_evidence(self):
        a = self.ingest()                                                 # no location
        self.ingest(source_system="radio", category="smoke_report", raw_text="x", location_id="EVENT-AREA")
        self.assertEqual(self.detail(a["incident_id"])["location_id"], "EVENT-AREA")


class FieldReport(Base):
    def test_camera_ui_keeps_live_primary_and_video_upload_secondary(self):
        html = self.c.get("/field").get_data(as_text=True)
        zone = html.index('id="camZone"')
        location = html.index('id="camLoc"')
        live = html.index('id="camStart"')
        upload = html.index('id="camFileOption"')
        analyze = html.index('id="camAnalyze"')
        self.assertLess(zone, live)
        self.assertLess(location, live)
        self.assertIn('class="btn btn-primary f-wide cam-start"', html)
        self.assertLess(live, upload)
        self.assertLess(upload, analyze)

    def test_full_report_structured(self):
        r = self.post("/api/voice/report", text="فيه حريق في زون A عند منطقة المطاعم", input_mode="voice",
                      recorded_at="2026-10-09T10:00:00+03:00", stt_confidence=0.82)
        self.assertEqual(r.status_code, 201)
        j = r.get_json()
        self.assertEqual(j["incident"]["code"][:4], "INC-")
        a = self.detail(j["incident_id"])["alerts"][0]
        self.assertEqual((a["zone_id"], a["location_id"], a["origin"], a["source_system"]),
                         ("ZONE-A", "FOOD-COURT", "voice", "radio"))
        self.assertEqual(a["raw_text"], "فيه حريق في زون A عند منطقة المطاعم")
        self.assertEqual(a["occurred_at"], "2026-10-09T10:00:00+03:00")
        self.assertNotEqual(a["received_at"], a["occurred_at"])
        self.assertEqual(a["payload"]["extraction"]["stt_confidence"], 0.82)
        self.assertFalse(a["payload"]["extraction"]["corrected_by_user"])

    def test_unknown_zone_is_stored_for_review_not_linked(self):
        r = self.post("/api/voice/report", text="فيه دخان", zone_id="", location_id="")
        self.assertEqual(r.status_code, 201)
        j = r.get_json()
        self.assertEqual((j["disposition"], j["incident_id"]), ("needs_review", None))

    def test_other_location_text(self):
        r = self.post("/api/voice/report", text="شخص طاح في زون C", location_id="other",
                      location_other="خلف كشك التذاكر").get_json()
        a = self.detail(r["incident_id"])["alerts"][0]
        self.assertEqual((a["location_id"], a["location_detail"]), (None, "خلف كشك التذاكر"))

    def test_no_event_type_is_refused(self):
        r = self.post("/api/voice/report", text="ما فيه حريق في زون A")
        self.assertEqual(r.status_code, 422)
        self.assertIn("negated", r.get_json()["extraction"]["review_reasons"])

    def test_support_request_kind_is_kept(self):
        r = self.post("/api/voice/report", text="نحتاج منظمين إضافيين في زون A عند منطقة الفعاليات").get_json()
        sigs = self.c.get("/api/state").get_json()["signals"]
        self.assertEqual(sigs[0]["report_kind"], "support_request")
        self.assertEqual(self.detail(r["incident_id"])["label"], "staff_shortage")

    def test_wheelchair_request_is_routine_and_does_not_create_incident(self):
        r = self.post("/api/ingest", source_system="service_desk", category="wheelchair_request",
                      zone_id="ZONE-C", raw_text="طلب كرسي متحرك")
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual((r.get_json()["disposition"], r.get_json()["incident_id"]), ("routine", None))


class StaffingWhatIf(Base):
    def staff_incident(self):
        # Zone A short of staff, not crowded
        return self.ingest(source_system="staff_roster", category="staff_shortage", zone_id="ZONE-A",
                           location_id="EVENT-AREA", payload={"on_duty": 9, "required": 12})["incident_id"]

    def test_staff_only_incident_offers_staffing_not_crowd_control(self):
        iid = self.staff_incident()
        d = self.detail(iid)
        self.assertEqual(d["label"], "staff_shortage")
        codes = [r["code"] for r in d["recommendations"]]
        self.assertEqual(codes, ["redeploy_staff"] * 3)   # three staffing options, no crowd control
        st = d["recommendations"][0]["simulation"]["staff"]
        self.assertEqual((st["source"]["before"], st["source"]["after"], st["source"]["required"]), (9, 12, 12))
        self.assertGreaterEqual(st["other"]["after"], st["other"]["required"])

    def test_choose_source_and_receiving_zone_and_count(self):
        iid = self.staff_incident()
        r = self.post(f"/api/incidents/{iid}/simulate", action="redeploy", target_zone="ZONE-C",
                      to_zone="ZONE-A", staff=2).get_json()
        st = r["staff"]
        self.assertEqual((st["source"]["zone"], st["source"]["before"], st["source"]["after"]), ("ZONE-A", 9, 11))
        self.assertEqual((st["other"]["zone"], st["other"]["before"], st["other"]["after"]), ("ZONE-C", 6, 4))
        chk = {c["key"]: c["status"] for c in r["checks"]}
        self.assertEqual(chk["donor_min_staff"], "fail")        # Zone C drops below its minimum of 6
        self.assertEqual(chk["source_min_staff"], "warn")       # 11 < 12 still short
        self.assertEqual(chk["staff_no_flow_effect"], "info")   # staff do not change hall flow in this model
        self.assertEqual(chk["staff_relief"], "ok")              # the relief is the staffing gap closed

    def test_numbers_follow_current_state(self):
        iid = self.staff_incident()
        a = self.post(f"/api/incidents/{iid}/simulate", action="redeploy", target_zone="ZONE-B", staff=2).get_json()
        self.ingest(source_system="staff_roster", category="staff_shortage", zone_id="ZONE-A", payload={"on_duty": 7})
        b = self.post(f"/api/incidents/{iid}/simulate", action="redeploy", target_zone="ZONE-B", staff=2).get_json()
        self.assertEqual((a["staff"]["source"]["after"], b["staff"]["source"]["after"]), (11, 9))

    def test_crowd_divert_shows_capacity_and_both_zones(self):
        self.ingest(source_system="staff_roster", category="staff_shortage", zone_id="ZONE-C",
                    payload={"on_duty": 3, "required": 6})
        iid = self.ingest(source_system="crowd_sensors", category="occupancy_high", zone_id="ZONE-C",
                          payload={"occupancy": 1410})["incident_id"]
        r = self.post(f"/api/incidents/{iid}/simulate", action="divert", target_zone="ZONE-B", share_pct=50).get_json()
        self.assertEqual((r["source_zone"], r["other_zone"]), ("ZONE-C", "ZONE-B"))
        self.assertEqual(r["source"]["capacity"], 1500)
        self.assertEqual(r["other"]["capacity"], 5000)
        self.assertLess(r["source"]["occupancy_end"], r["baseline"]["occupancy_end"])
        self.assertGreater(r["other"]["occupancy_end"], r["other_before"]["occupancy_end"])


class DecisionLog(Base):
    def test_each_action_is_logged_with_operator_and_details(self):
        fire = self.ingest(location_id="FOOD-COURT")["incident_id"]
        rec = self.detail(fire)["recommendations"][0]
        self.assertEqual(self.decide(fire, action="approve", recommendation_id=rec["id"]).status_code, 201)
        self.assertEqual(self.decide(fire, action="resolve", note="extinguished").status_code, 201)
        med = self.ingest(source_system="cctv_ai", category="person_down", zone_id="ZONE-B")["incident_id"]
        self.assertEqual(self.decide(med, action="dismiss", note="false alarm, mannequin").status_code, 201)
        self.ingest(source_system="staff_roster", category="staff_shortage", zone_id="ZONE-C",
                    payload={"on_duty": 3, "required": 6})
        crowd = self.ingest(source_system="crowd_sensors", category="occupancy_high", zone_id="ZONE-C",
                            payload={"occupancy": 1410})["incident_id"]
        opt = self.detail(crowd)["recommendations"][0]
        self.assertEqual(self.decide(crowd, action="reject", recommendation_id=opt["id"],
                                     note="Zone B staff needed for VIP").status_code, 201)
        log = self.c.get("/api/decisions").get_json()["decisions"]
        self.assertEqual([d["action"] for d in log], ["reject", "dismiss", "resolve", "approve"])
        self.assertTrue(all(d["operator"] == OP and d["created_at"] for d in log))
        approve = log[3]
        self.assertEqual(approve["snapshot"]["incident_code"], self.detail(fire)["code"])
        self.assertEqual(approve["snapshot"]["location_id"], "FOOD-COURT")
        self.assertEqual({t["id"] for t in approve["snapshot"]["teams"]},
                         {t["team_id"] for t in rec["params"]["teams"] if t["team_id"]})
        self.assertEqual(approve["priority_at_decision"], self.detail(fire)["priority"])
        reject = log[0]
        self.assertEqual(reject["note"], "Zone B staff needed for VIP")
        self.assertIsNotNone(reject["snapshot"]["recommendation"]["simulation"]["load_with_option"])
        resolve = log[2]
        self.assertTrue(resolve["snapshot"]["teams"])           # which teams were released

    def test_client_operator_is_ignored_and_authenticated_employee_is_logged(self):
        fire = self.ingest()["incident_id"]
        rec = self.detail(fire)["recommendations"][0]
        r = self.post(f"/api/incidents/{fire}/decisions", action="approve", recommendation_id=rec["id"],
                      operator="Forged Client Identity", note="Verified test approval reason")
        self.assertEqual(r.status_code, 201, r.get_json())
        decision = self.c.get("/api/decisions").get_json()["decisions"][0]
        self.assertEqual((decision["operator"], decision["employee_number"]), (OP, "100123"))

    def test_log_survives_reset_and_app_restart(self):
        fire = self.ingest()["incident_id"]
        rec = self.detail(fire)["recommendations"][0]
        self.decide(fire, action="approve", recommendation_id=rec["id"])
        self.c.post("/api/demo/reset")
        log = self.c.get("/api/decisions").get_json()
        self.assertEqual(len(log["decisions"]), 1)
        self.assertFalse(log["decisions"][0]["current_run"])
        self.assertIsNone(log["decisions"][0]["incident_id"])        # incident row gone, snapshot remains
        self.assertEqual(log["decisions"][0]["snapshot"]["incident_code"], "INC-0001")
        self.assertEqual(self.c.get("/api/state").get_json()["decisions"], [])   # overview: current run only
        # a new app process on the same database file = restart
        client2 = restart_client(self.path)
        log2 = client2.get("/api/decisions").get_json()["decisions"]
        self.assertEqual([(d["operator"], d["employee_number"], d["action"]) for d in log2],
                         [(OP, "100123", "approve")])


class Camera(Base):
    """Server camera paths with a scripted stand-in detector (no YOLO weights needed): these
    check frames -> state machine -> alert -> incident, not detection accuracy."""

    def setUp(self):
        super().setUp()
        from tests import helpers_cv
        self.cvh = helpers_cv
        self.stand = 45
        helpers_cv.install(stand=self.stand)

    def tearDown(self):
        self.cvh.uninstall()
        super().tearDown()

    def upload(self, name, **form):
        with open(FIX / name, "rb") as f:
            data = {"zone_id": "ZONE-B", "location_id": "MAIN-WALKWAY", **form, "video": (f, name)}
            return self.c.post("/api/cv/video", data=data, content_type="multipart/form-data")

    def test_status_reports_the_yolo_detector(self):
        self.cvh.uninstall()
        s = self.c.get("/api/cv/status").get_json()
        self.assertTrue(s["detector"].startswith("yolo:"))
        self.assertTrue(s["trained_model"])

    def test_uploaded_fall_video_creates_video_file_alert(self):
        r = self.upload("synthetic_fall.avi")
        self.assertEqual(r.status_code, 201)
        j = r.get_json()
        self.assertEqual(len(j["events"]), 1)
        alert = j["alerts"][0]
        self.assertEqual((alert["zone_id"], alert["location_id"], alert["origin"]),
                         ("ZONE-B", "MAIN-WALKWAY", "video_file"))
        self.assertTrue(alert["event_at"])
        self.assertGreater(alert["event_offset_s"], 0)
        inc = self.detail(j["alerts"][0]["incident_id"])
        self.assertEqual((inc["type"], inc["zone_id"], inc["location_id"]), ("medical", "ZONE-B", "MAIN-WALKWAY"))
        self.assertEqual(inc["alerts"][0]["origin"], "video_file")
        self.assertEqual(inc["alerts"][0]["payload"]["detector"], "scripted_test_detector")

    def test_walking_video_is_not_a_detection(self):
        self.cvh.install(stand=10_000)                      # a person who only ever stands
        j = self.upload("cv_walk.avi").get_json()
        self.assertEqual((j["events"], j["alerts"]), ([], []))
        self.assertEqual(self.c.get("/api/state").get_json()["counters"]["received"], 0)

    def test_video_requires_a_zone(self):
        self.assertEqual(self.upload("cv_walk.avi", zone_id="", location_id="").get_json()["error"], "zone_required")

    def test_cv_unavailable_without_detector(self):
        import analyzer
        old = analyzer.detector_available
        analyzer.detector_available = lambda: False
        try:
            self.assertEqual(self.upload("cv_walk.avi").get_json()["error"], "cv_unavailable")
        finally:
            analyzer.detector_available = old

    def test_model_load_failure_is_a_clear_error(self):
        class Broken:
            info = {"id": "yolo:broken.pt", "trained_model": True, "model": "broken.pt"}
            def load(self):
                raise RuntimeError("weights missing")
            def __call__(self, frame):
                return None, {}
        import analyzer
        analyzer.set_detector_factory(Broken)
        r = self.post("/api/cv/sessions", zone_id="ZONE-B")
        self.assertEqual((r.status_code, r.get_json()["error"]), (503, "cv_model_unavailable"))

    def test_live_frames_create_live_cv_alert(self):
        import cv2
        sid = self.post("/api/cv/sessions", zone_id="ZONE-B", location_id="FIRST-AID").get_json()["session_id"]
        cap, i, alert, states = cv2.VideoCapture(str(FIX / "synthetic_fall.avi")), 0, None, set()
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            i += 1
            buf = cv2.imencode(".jpg", cv2.resize(fr, (320, 240)))[1].tobytes()
            j = self.c.post(f"/api/cv/sessions/{sid}/frame", data=buf,
                            headers={"Content-Type": "image/jpeg", "X-Frame-Time": str(i * 1000 // 15)}).get_json()
            states.add(j["state"])
            alert = alert or j["alert"]
        self.assertIn("upright", states)
        self.assertNotIn("learning", states)               # YOLO needs no background learning
        self.assertIsNotNone(alert)
        self.assertEqual((alert["zone_id"], alert["location_id"], alert["origin"]),
                         ("ZONE-B", "FIRST-AID", "live_cv"))
        self.assertTrue(alert["event_at"])
        inc = self.detail(alert["incident_id"])
        self.assertEqual(inc["alerts"][0]["origin"], "live_cv")
        self.assertEqual(inc["alerts"][0]["occurred_at"], alert["event_at"])
        self.assertEqual(inc["alerts"][0]["payload"]["device"], "phone_camera")
        self.assertEqual(self.c.delete(f"/api/cv/sessions/{sid}").get_json()["alerts"], 1)

    def test_opening_the_camera_is_not_a_detection(self):
        import cv2
        import numpy as np
        self.cvh.install(nobody=True)
        sid = self.post("/api/cv/sessions", zone_id="ZONE-B").get_json()["session_id"]
        frame = cv2.imencode(".jpg", np.full((240, 320, 3), 128, np.uint8))[1].tobytes()
        for i in range(60):
            j = self.c.post(f"/api/cv/sessions/{sid}/frame", data=frame,
                            headers={"Content-Type": "image/jpeg", "X-Frame-Time": str(i * 166)}).get_json()
            self.assertIsNone(j["alert"])
        self.assertEqual(self.c.get("/api/state").get_json()["counters"]["received"], 0)

    def test_replay_is_labelled_replay(self):
        r = self.post("/api/demo/cv-replay").get_json()
        a = self.detail(r["incident_id"])["alerts"][0]
        self.assertEqual((a["origin"], a["zone_id"], a["location_id"]), ("replay_cv", "ZONE-B", "MAIN-WALKWAY"))


if __name__ == "__main__":
    unittest.main()
