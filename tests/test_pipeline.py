"""Pipeline, correlation, priority, decisions and the golden demo run."""
import os
import unittest

from eoip import catalog, db
from eoip.core import pipeline, priority, simulate
from eoip.core.decisions import DecisionError
from eoip.core.normalize import ValidationError
from tests.helpers import decide, make_client, sig


class PipelineBase(unittest.TestCase):
    def setUp(self):
        self.app, self.client, self.path = make_client()
        self.conn = db.connect(self.path)

    def tearDown(self):
        self.conn.close()
        from django.db import connections
        connections.close_all()   # Windows cannot delete an open SQLite file
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.path + suffix)
            except OSError:
                pass

    def ingest(self, **kw):
        return pipeline.ingest(self.conn, sig(**kw))

    def incident(self, iid):
        return db.to_dict(self.conn.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone())


class Normalization(PipelineBase):
    def test_rejects_unknown_source_category_zone(self):
        with self.assertRaises(ValidationError) as cm:
            pipeline.ingest(self.conn, {"source_system": "x", "category": "y", "zone_id": "Z"})
        self.assertGreaterEqual(len(cm.exception.errors), 3)

    def test_rejects_bad_confidence(self):
        with self.assertRaises(ValidationError):
            self.ingest(confidence=1.7)

    def test_signal_type_defaults_from_source(self):
        r = self.ingest(source_system="service_desk", category="lost_item")
        row = self.conn.execute("SELECT signal_type FROM alerts WHERE id=?", (r["alert_id"],)).fetchone()
        self.assertEqual(row[0], "service_request")


class Triage(PipelineBase):
    def test_noise_and_routine_never_create_incidents(self):
        self.assertEqual(self.ingest(source_system="bms", category="heartbeat")["disposition"], "noise")
        self.assertEqual(self.ingest(source_system="service_desk", category="info_request")["disposition"], "routine")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0], 0)

    def test_duplicate_from_same_device_is_merged(self):
        a = self.ingest()
        b = self.ingest()
        self.assertEqual(b["disposition"], "duplicate")
        self.assertEqual(a["incident_id"], b["incident_id"])
        inc = self.incident(a["incident_id"])
        self.assertEqual((inc["alert_count"], inc["source_count"]), (2, 1))

    def test_independent_sources_correlate_and_escalate(self):
        a = self.ingest(confidence=0.74, payload={"stage": 1})
        self.assertEqual(self.incident(a["incident_id"])["priority"], "P2")  # single source
        b = pipeline.ingest(self.conn, {"source_system": "radio", "category": "smoke_report",
                                         "zone_id": "ZONE-A", "raw_text": "دخان", "confidence": 0.85})
        self.assertEqual(b["incident_id"], a["incident_id"])
        inc = self.incident(a["incident_id"])
        self.assertEqual(inc["priority"], "P1")
        self.assertIsNotNone(inc["escalated_at"])

    def test_different_zone_or_family_is_a_separate_incident(self):
        a = self.ingest()
        b = self.ingest(zone_id="ZONE-B")
        c = self.ingest(source_system="cctv_ai", category="person_down")
        self.assertEqual(len({a["incident_id"], b["incident_id"], c["incident_id"]}), 3)

    def test_missing_zone_with_text_needs_review(self):
        r = pipeline.ingest(self.conn, {"source_system": "radio", "category": "crowd_report", "raw_text": "زحمة"})
        self.assertEqual(r["disposition"], "needs_review")
        self.assertIsNone(r["incident_id"])

    def test_stateful_signals_update_zone_and_are_not_duplicates(self):
        r1 = self.ingest(source_system="crowd_sensors", category="occupancy_high", zone_id="ZONE-C",
                         payload={"occupancy": 1200})
        r2 = self.ingest(source_system="crowd_sensors", category="occupancy_high", zone_id="ZONE-C",
                         payload={"occupancy": 1400})
        self.assertEqual(r2["disposition"], "correlated")
        occ = self.conn.execute("SELECT occupancy FROM zones WHERE id='ZONE-C'").fetchone()[0]
        self.assertEqual(occ, 1400)
        self.assertEqual(r1["incident_id"], r2["incident_id"])

    def test_closed_incident_is_not_reused(self):
        a = self.ingest()
        decide(self.conn, a["incident_id"], "dismiss", note="test alarm")
        b = self.ingest(source_system="radio", category="smoke_report", raw_text="دخان")
        self.assertNotEqual(a["incident_id"], b["incident_id"])


class Priority(unittest.TestCase):
    zone = {"id": "Z", "kind": "gate", "occupancy": 1410, "capacity": 1500, "inflow_per_min": 90,
            "outflow_per_min": 96, "staff_on_duty": 3, "staff_required": 6, "criticality": 3, "neighbors": []}

    def test_operational_never_reaches_p1_below_capacity(self):
        alerts = [{"source_system": s, "category": c, "confidence": 1.0, "payload": {"wait_min": 19}}
                  for s, c in [("crowd_sensors", "occupancy_high"), ("queue_sensors", "queue_long"),
                               ("radio", "crowd_report"), ("staff_roster", "staff_shortage")]]
        level, score, reasons, _ = priority.compute("crowd_pressure", alerts, self.zone)
        self.assertEqual(level, "P2")
        self.assertEqual(score, catalog.OPERATIONAL_SCORE_CAP)
        self.assertIn("operational_cap", [r["key"] for r in reasons])

    def test_operational_full_zone_can_be_p1(self):
        z = dict(self.zone, occupancy=1490)
        alerts = [{"source_system": "crowd_sensors", "category": "occupancy_high", "confidence": 1.0, "payload": {}},
                  {"source_system": "radio", "category": "crowd_report", "confidence": 0.9, "payload": {}}]
        self.assertEqual(priority.compute("crowd_pressure", alerts, z)[0], "P1")

    def test_low_confidence_single_camera_is_not_critical(self):
        z = dict(self.zone, kind="plaza", occupancy=2600, capacity=5000, criticality=2)
        alerts = [{"source_system": "cctv_ai", "category": "person_down", "confidence": 0.5, "payload": {}}]
        level, _, reasons, _ = priority.compute("medical", alerts, z)
        self.assertEqual(level, "P3")
        self.assertIn("low_confidence", [r["key"] for r in reasons])

    def test_single_detector_waits_for_confirmation(self):
        z = dict(self.zone, kind="plaza", occupancy=2600, capacity=5000, criticality=2)
        alerts = [{"source_system": "fire_system", "category": "smoke_detected", "confidence": 0.8, "payload": {}}]
        level, _, reasons, _ = priority.compute("fire", alerts, z)
        self.assertEqual(level, "P2")
        self.assertIn("single_source", [r["key"] for r in reasons])

    def test_verified_panel_alarm_is_critical_alone(self):
        z = dict(self.zone, kind="plaza", occupancy=2600, capacity=5000, criticality=2)
        alerts = [{"source_system": "fire_system", "category": "fire_alarm", "confidence": 0.95, "payload": {"stage": 2}}]
        level, score, reasons, _ = priority.compute("fire", alerts, z)
        self.assertEqual(level, "P1")
        self.assertIn("verified_panel_alarm", [r["key"] for r in reasons])
        self.assertEqual(score, sum(r["points"] for r in reasons))

    def test_staff_eyewitness_is_critical_alone(self):
        z = dict(self.zone, kind="plaza", occupancy=2600, capacity=5000, criticality=2)
        for itype, cat in (("medical", "medical_report"), ("fire", "smoke_report")):
            alerts = [{"source_system": "radio", "category": cat, "confidence": 0.9, "payload": {}}]
            level, _, reasons, _ = priority.compute(itype, alerts, z)
            self.assertEqual(level, "P1", itype)
            keys = [r["key"] for r in reasons]
            self.assertIn("eyewitness_report", keys)
            self.assertNotIn("single_source", keys)

    def test_unclear_staff_report_and_visitor_request_are_not_eyewitness(self):
        z = dict(self.zone, kind="plaza", occupancy=2600, capacity=5000, criticality=2)
        unclear = [{"source_system": "radio", "category": "medical_report", "confidence": 0.4, "payload": {}}]
        visitor = [{"source_system": "service_desk", "category": "medical_request", "confidence": 0.9, "payload": {}}]
        self.assertNotEqual(priority.compute("medical", unclear, z)[0], "P1")
        self.assertEqual(priority.compute("medical", visitor, z)[0], "P2")

    def test_evidence_confidence_combines_sources(self):
        c, _ = priority.evidence_confidence([
            {"source_system": "a", "confidence": 0.7}, {"source_system": "b", "confidence": 0.7}])
        self.assertAlmostEqual(c, 0.91, places=2)

    def test_reasons_sum_to_score(self):
        alerts = [{"source_system": "fire_system", "category": "fire_alarm", "confidence": 0.99, "payload": {"stage": 2}},
                  {"source_system": "radio", "category": "smoke_report", "confidence": 0.85, "payload": {}}]
        z = dict(self.zone, kind="hall", occupancy=1650, capacity=2000, criticality=2)
        _, score, reasons, _ = priority.compute("fire", alerts, z)
        self.assertEqual(score, min(100, sum(r["points"] for r in reasons)))


class Simulation(unittest.TestCase):
    def test_options_ranked_and_explained(self):
        conn = db.connect(":memory:")
        db.init_schema(conn)
        db.seed_zones(conn)
        conn.execute("UPDATE zones SET occupancy=1410, staff_on_duty=3 WHERE id='ZONE-C'")
        zones = {z["id"]: z for z in db.rows(conn.execute("SELECT * FROM zones"))}
        opts = simulate.crowd_options(zones["ZONE-C"], zones)
        self.assertEqual([o["rank"] for o in opts], [1, 2, 3])
        self.assertEqual(opts[0]["code"], "redeploy_staff")
        best = opts[0]["simulation"]
        self.assertLess(best["source"]["load_end"], best["baseline"]["load_end"])
        self.assertLess(best["source"]["load_end"], 0.9)
        meter = next(o for o in opts if o["code"] == "meter_entry")
        self.assertIn("outside_queue", [s["key"] for s in meter["simulation"]["side_effects"]])
        conn.close()

    def test_projection_arithmetic(self):
        z = {"kind": "gate", "occupancy": 1000, "capacity": 1500, "inflow_per_min": 100, "outflow_per_min": 0,
             "staff_on_duty": 5, "staff_required": 5}
        p = simulate.project(z, minutes=10)
        self.assertEqual(p["net_per_min"], 100 - 5 * catalog.GATE_PROCESSING_PER_STAFF)
        self.assertEqual(p["occupancy_end"], 1000 + 20 * 10)
        self.assertEqual(p["minutes_to_capacity"], 25.0)


class Decisions(PipelineBase):
    def _crowd(self):
        for occ in (1170, 1410):
            r = self.ingest(source_system="crowd_sensors", category="occupancy_high", zone_id="ZONE-C",
                            payload={"occupancy": occ})
        self.ingest(source_system="staff_roster", category="staff_shortage", zone_id="ZONE-C",
                    payload={"on_duty": 3, "required": 6})
        return r["incident_id"]

    def recs(self, iid):
        return db.rows(self.conn.execute("SELECT * FROM recommendations WHERE incident_id=? ORDER BY rank", (iid,)))

    def test_approve_option_supersedes_others_and_logs(self):
        iid = self._crowd()
        recs = self.recs(iid)
        self.assertEqual(len(recs), 3)
        decide(self.conn, iid, "approve", recs[0]["id"])
        statuses = sorted(r["status"] for r in self.recs(iid))
        self.assertEqual(statuses, ["approved", "superseded", "superseded"])
        self.assertEqual(self.incident(iid)["status"], "action_approved")
        log = self.conn.execute("SELECT action, priority_at_decision FROM decisions WHERE incident_id=?", (iid,)).fetchall()
        self.assertEqual([tuple(r) for r in log], [("approve", "P2")])
        snap = db.to_dict(self.conn.execute("SELECT snapshot FROM decisions WHERE incident_id=?", (iid,)).fetchone())["snapshot"]
        self.assertEqual(snap["recommendation"]["code"], recs[0]["code"])
        self.assertEqual(snap["recommendation"]["simulation"]["load_with_option"], recs[0]["simulation"]["source"]["load_end"])
        self.assertEqual(snap["names"]["ZONE-C"]["en"], "Zone C")

    def test_reject_without_note_is_logged_and_not_reproposed(self):
        iid = self._crowd()
        first = self.recs(iid)[0]
        from eoip.core.decisions import decide as decide_without_default_reason
        decide_without_default_reason(self.conn, iid, "reject", first["id"], operator="Test Operator")   # reason is optional
        self.ingest(source_system="crowd_sensors", category="occupancy_high", zone_id="ZONE-C", payload={"occupancy": 1420})
        proposed = [r["code"] for r in self.recs(iid) if r["status"] == "proposed"]
        self.assertNotIn(first["code"], proposed)

    def test_closed_incident_rejects_decisions(self):
        a = self.ingest()
        decide(self.conn, a["incident_id"], "resolve")
        with self.assertRaises(DecisionError):
            decide(self.conn, a["incident_id"], "resolve")

    def test_emergency_has_playbook_without_simulation(self):
        a = self.ingest()
        r = self.recs(a["incident_id"])
        self.assertEqual(len(r), 3)                      # three ranked options for every case
        self.assertTrue(all(x["rec_type"] == "playbook" and x["simulation"] is None for x in r))
        self.assertIn(r[0]["code"], ("FIRE-01", "MED-01"))   # the full pre-approved playbook comes first


class GoldenDemo(PipelineBase):
    """The scripted live event must always produce the same, explainable outcome."""

    def run_demo(self):
        self.client.post("/api/demo/reset")
        self.assertEqual(self.client.post("/api/demo/skip").get_json()["ingested"], 149)
        return self.client.get("/api/state").get_json()

    def test_triage_funnel(self):
        s = self.run_demo()
        c = s["counters"]
        self.assertEqual(c["received"], 149)
        self.assertEqual(c["incidents_open"], 7)          # 1 critical (fire) + 3 medium + 3 normal visitor-behaviour cases
        self.assertEqual(c["critical"], 1)
        self.assertEqual(c["noise"] + c["routine"] + c["duplicate"] + c["relevant"] + c["needs_review"], 149)
        # every report comes from a camera or the field radio
        self.assertEqual(set(c["by_signal_type"]), {"alert", "radio_message"})
        self.assertEqual({sg["source_system"] for sg in s["signals"]}, {"cctv_ai", "radio"})
        by_p = lambda p: sorted((i["label"], i["zone_id"]) for i in s["incidents"] if i["priority"] == p)
        self.assertEqual(by_p("P1"), [("fire", "ZONE-A")])
        self.assertTrue(all(i["source_count"] == 2 for i in s["incidents"] if i["priority"] == "P1"))   # camera + radio
        self.assertEqual(by_p("P2"), [("crowding", "ZONE-C"), ("medical", "ZONE-C"), ("staff_shortage", "ZONE-A")])
        self.assertEqual(by_p("P3"), [("visitor_fight", "ZONE-C"), ("visitor_sitting_path", "ZONE-B"),
                                      ("visitor_wrong_way", "ZONE-C")])
        self.assertEqual(s["incidents"][0]["priority"], "P1")       # critical cases come first
        self.assertEqual(c["awaiting_decision"], 4)            # P1 + P2 (the 3 normal cases go to the field team)

    def test_live_reports_complete_the_four_demo_cases(self):
        self.run_demo()
        fire = self.client.post("/api/voice/report", json={
            "text": "فيه دخان طالع في زون A عند منطقة المطاعم، جنب المخرج الشرقي", "input_mode": "voice"}).get_json()
        self.client.post("/api/demo/cv-replay")
        med = self.client.post("/api/voice/report", json={
            "text": "شخص مغمى عليه في زون B عند الممر الرئيسي، نحتاج إسعاف بسرعة", "input_mode": "voice"}).get_json()
        s = self.client.get("/api/state").get_json()
        fire_inc = next(i for i in s["incidents"] if i["id"] == fire["incident"]["id"])
        med_inc = next(i for i in s["incidents"] if i["id"] == med["incident"]["id"])
        self.assertEqual((fire_inc["label"], fire_inc["zone_id"], fire_inc["priority"]), ("fire", "ZONE-A", "P1"))
        self.assertEqual((med_inc["label"], med_inc["zone_id"], med_inc["priority"], med_inc["source_count"]),
                         ("medical", "ZONE-B", "P1", 2))
        self.assertEqual(s["counters"]["critical"], 2)

    def test_event_autostarts_once_and_stays_live(self):
        self.client.post("/api/demo/reset")
        first = self.client.post("/api/demo/autostart").get_json()
        self.assertTrue(first["started"])
        self.assertFalse(self.client.post("/api/demo/autostart").get_json()["started"])   # never restarts
        self.client.post("/api/demo/skip")
        d = self.client.get("/api/state").get_json()["demo"]
        self.assertTrue(d["running"] and d["finished"] and d["live"])
        self.assertFalse(self.client.post("/api/demo/autostart").get_json()["started"])

    def test_background_trickle_never_creates_incidents(self):
        from eoip import demo
        for i in range(300):
            sig = demo.trickle_signal(i)
            self.assertIn(catalog.CATEGORIES[sig["category"]]["handling"], ("noise", "routine"))

    def test_reproducible(self):
        a = self.run_demo()
        b = self.run_demo()
        strip = lambda s: sorted((i["code"], i["type"], i["zone_id"], i["priority"], i["priority_score"], i["alert_count"]) for i in s["incidents"])
        self.assertEqual(strip(a), strip(b))
        self.assertEqual(a["counters"], b["counters"])

    def test_medical_corroboration_live_flow(self):
        self.run_demo()
        r1 = self.client.post("/api/demo/cv-replay").get_json()
        inc = self.client.get(f"/api/incidents/{r1['incident_id']}").get_json()
        # a person-down from the vision model goes to the dashboard as critical at once (like a radio report)
        self.assertEqual((inc["type"], inc["priority"]), ("medical", "P1"))
        r2 = self.client.post("/api/voice/report", json={"text": "شخص مغمى عليه في زون B عند الممر الرئيسي", "input_mode": "voice"}).get_json()
        self.assertEqual(r2["incident_id"], r1["incident_id"])
        inc = self.client.get(f"/api/incidents/{r1['incident_id']}").get_json()
        self.assertEqual(inc["priority"], "P1")
        origins = {a["origin"] for a in inc["alerts"]}
        self.assertEqual(origins, {"replay_cv", "voice"})


class Escalation(unittest.TestCase):
    """Escalation matrix: late decisions go to L1, L2, L3 by priority."""
    def test_levels_by_priority(self):
        from eoip.core import escalation
        t0 = "2026-10-15T10:00:00.000+00:00"
        at = lambda s: f"2026-10-15T10:{s // 60:02d}:{s % 60:02d}.000+00:00"
        self.assertEqual(escalation.level("P1", t0, at(59)), 0)
        self.assertEqual(escalation.level("P1", t0, at(60)), 1)
        self.assertEqual(escalation.level("P1", t0, at(150)), 2)
        self.assertEqual(escalation.level("P1", t0, at(600)), 3)          # never above L3
        self.assertEqual(escalation.level("P2", t0, at(170)), 0)
        self.assertEqual(escalation.level("P3", t0, at(300)), 1)


class EscalationFlow(PipelineBase):
    """A case past its response time leaves the duty officer: no decision, logged as escalated."""
    def late_fire(self, seconds):
        from datetime import datetime, timedelta, timezone
        from eoip.core import escalation
        a = self.ingest(source_system="cctv_ai", category="smoke_detected", location_id="FOOD-COURT")
        self.ingest(source_system="radio", category="smoke_report", location_id="FOOD-COURT", confidence=0.9)
        past = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="milliseconds")
        with db.transaction(self.conn):
            self.conn.execute("UPDATE incidents SET opened_at=?, escalated_at=NULL WHERE id=?", (past, a["incident_id"]))
        escalation.sweep(self.conn)
        return a["incident_id"]

    def test_late_case_is_escalated_and_cannot_be_decided(self):
        iid = self.late_fire(70)
        s = self.client.get("/api/state").get_json()
        inc = next(i for i in s["incidents"] if i["id"] == iid)
        self.assertEqual((inc["status"], inc["escalation"]["code"]), ("escalated", "L1"))
        self.assertEqual(s["counters"]["awaiting_decision"], 0)
        rec = self.client.get(f"/api/incidents/{iid}").get_json()["recommendations"][0]["id"]
        r = self.client.post(f"/api/incidents/{iid}/decisions", json={"action": "approve", "recommendation_id": rec})
        self.assertEqual((r.status_code, r.get_json()["error"]), (409, "incident_escalated"))
        log = self.client.get("/api/decisions").get_json()
        self.assertEqual([(e["code"], e["snapshot"]["incident_label"]) for e in log["escalations"]], [("L1", "fire")])

    def test_level_rises_while_nobody_acts(self):
        iid = self.late_fire(150)
        s = self.client.get("/api/state").get_json()
        self.assertEqual(next(i for i in s["incidents"] if i["id"] == iid)["escalation"]["code"], "L2")


if __name__ == "__main__":
    unittest.main()
