"""v2 behaviour: correlation reasons, duplicate-after-close fix, synthetic teams + ETA,
team assignment conflicts, what-if simulation, operator-defined options."""
import os
import unittest

from eoip import db
from eoip.core import pipeline, simulate
from tests.helpers import make_client, sig


class Base(unittest.TestCase):
    def setUp(self):
        self.app, self.c, self.path = make_client()
        self.conn = db.connect(self.path)

    def tearDown(self):
        self.conn.close()
        from django.db import connections
        connections.close_all()   # Windows cannot delete an open SQLite file
        for s in ("", "-wal", "-shm"):
            try:
                os.remove(self.path + s)
            except OSError:
                pass

    def post(self, url, **body):
        if url.endswith("/decisions"):
            body.setdefault("operator", "Test Operator")
            body.setdefault("note", "test decision reason")
        return self.c.post(url, json=body)

    def ingest(self, **kw):
        return self.post("/api/ingest", **sig(**kw)).get_json()

    def detail(self, iid):
        return self.c.get(f"/api/incidents/{iid}").get_json()


class Correlation(Base):
    def test_first_alert_explains_new_incident(self):
        r = self.ingest()
        a = self.detail(r["incident_id"])["alerts"][0]
        self.assertFalse(a["correlation"]["linked"])
        self.assertEqual(a["correlation"]["reasons"][0]["key"], "no_open_match")

    def test_linked_alert_has_reasons_and_score(self):
        r1 = self.ingest(source_system="cctv_ai", category="person_down", zone_id="ZONE-B")
        r2 = self.post("/api/voice/report", text="شخص مغمى عليه في زون B").get_json()
        self.assertEqual(r1["incident_id"], r2["incident_id"])
        a = self.detail(r2["incident_id"])["alerts"][1]["correlation"]
        keys = [x["key"] for x in a["reasons"]]
        for k in ("same_family", "same_zone", "within_window", "incident_open", "independent_source"):
            self.assertIn(k, keys)
        self.assertGreaterEqual(a["score"], 0.9)  # immediate + independent

    def test_same_zone_different_family_not_merged(self):
        r1 = self.ingest(zone_id="ZONE-B")                                            # fire family
        r2 = self.ingest(source_system="cctv_ai", category="person_down", zone_id="ZONE-B")
        self.assertNotEqual(r1["incident_id"], r2["incident_id"])

    def test_words_alone_do_not_link_other_zone(self):
        r1 = self.ingest(source_system="cctv_ai", category="person_down", zone_id="ZONE-B")
        r2 = self.post("/api/voice/report", text="شخص مغمى عليه في زون A").get_json()
        self.assertNotEqual(r1["incident_id"], r2["incident_id"])

    def test_duplicate_has_reason(self):
        self.ingest()
        r = self.ingest()
        self.assertEqual(r["disposition"], "duplicate")
        a = self.detail(r["incident_id"])["alerts"][1]["correlation"]
        self.assertEqual(a["reasons"][0]["key"], "duplicate_of")

    def test_repeat_after_dismiss_opens_new_incident(self):
        r1 = self.ingest()
        self.post(f"/api/incidents/{r1['incident_id']}/decisions", action="dismiss", note="test alarm")
        r2 = self.ingest()
        self.assertEqual(r2["disposition"], "correlated")
        self.assertNotEqual(r1["incident_id"], r2["incident_id"])


class Teams(Base):
    def test_playbook_reasons_follow_evidence(self):
        r = self.ingest(confidence=0.74)
        why = lambda: [w["key"] for w in self.detail(r["incident_id"])["recommendations"][0]["params"]["why"]]
        self.assertIn("act_before_confirmation", why())
        self.post("/api/voice/report", text="فيه دخان طالع في زون A")
        self.assertIn("confirmed_sources", why())
        self.assertNotIn("act_before_confirmation", why())

    def test_playbook_proposes_nearest_team_with_eta(self):
        r = self.ingest(source_system="cctv_ai", category="person_down", zone_id="ZONE-B")
        rec = self.detail(r["incident_id"])["recommendations"][0]
        crew = {t["kind"]: t for t in rec["params"]["teams"]}
        self.assertEqual(crew["medical"]["team_id"], "MED-1")   # based at the First Aid Point, Zone B
        self.assertEqual(crew["medical"]["walk_min"], 0)
        self.assertEqual(crew["medical"]["eta_min"], 1.0)        # mobilisation only
        self.assertIsNotNone(crew["medical"]["eta_min"])
        self.assertIn("nearest_available_team", [w["key"] for w in rec["params"]["why"]])

    def test_assignment_blocks_double_dispatch_and_release(self):
        a = self.ingest(source_system="cctv_ai", category="person_down", zone_id="ZONE-B", location_id="FIRST-AID")["incident_id"]
        b = self.ingest(source_system="cctv_ai", category="person_down", zone_id="ZONE-B", location_id="MAIN-WALKWAY")["incident_id"]
        self.assertNotEqual(a, b)   # same zone, two different named locations = two medical cases
        rec_a = self.detail(a)["recommendations"][0]
        rec_b = self.detail(b)["recommendations"][0]
        med_b = [t for t in rec_b["params"]["teams"] if t["kind"] == "medical"][0]["team_id"]
        self.assertEqual(med_b, "MED-1")    # both incidents see MED-1 as nearest before any approval
        self.assertEqual(self.post(f"/api/incidents/{a}/decisions", action="approve",
                                   recommendation_id=rec_a["id"]).status_code, 201)
        teams = {t["id"]: t for t in self.c.get("/api/teams").get_json()["teams"]}
        self.assertEqual((teams["MED-1"]["status"], teams["MED-1"]["incident_id"]), ("assigned", a))
        # B's proposal was re-planned automatically to the next free medical team
        rec_b2 = [r for r in self.detail(b)["recommendations"] if r["status"] == "proposed"][0]
        med_b2 = [t for t in rec_b2["params"]["teams"] if t["kind"] == "medical"][0]["team_id"]
        self.assertNotEqual(med_b2, "MED-1")
        # the same proposal id now carries the free team, so approving it dispatches MED-2/3, never MED-1
        self.assertEqual(rec_b2["id"], rec_b["id"])
        r = self.post(f"/api/incidents/{b}/decisions", action="approve", recommendation_id=rec_b["id"])
        self.assertEqual(r.status_code, 201)
        teams = {t["id"]: t for t in self.c.get("/api/teams").get_json()["teams"]}
        self.assertEqual((teams[med_b2]["status"], teams[med_b2]["incident_id"]), ("assigned", b))
        self.assertEqual(teams["MED-1"]["incident_id"], a)
        self.post(f"/api/incidents/{a}/decisions", action="resolve")
        teams = {t["id"]: t for t in self.c.get("/api/teams").get_json()["teams"]}
        self.assertEqual(teams["MED-1"]["status"], "available")

    def test_team_unavailable_triggers_replan(self):
        a = self.ingest(source_system="cctv_ai", category="person_down", zone_id="ZONE-B")["incident_id"]
        rec = self.detail(a)["recommendations"][0]
        self.conn.execute("UPDATE teams SET status='assigned', incident_id=NULL WHERE id='MED-1'")
        r = self.post(f"/api/incidents/{a}/decisions", action="approve", recommendation_id=rec["id"])
        self.assertEqual((r.status_code, r.get_json()["error"]), (409, "team_unavailable"))
        new = [x for x in self.detail(a)["recommendations"] if x["status"] == "proposed"][0]
        self.assertNotIn("MED-1", [t["team_id"] for t in new["params"]["teams"]])


class WhatIf(Base):
    def crowd(self):
        self.ingest(source_system="staff_roster", category="staff_shortage", zone_id="ZONE-C",
                    payload={"on_duty": 3, "required": 6})
        return self.ingest(source_system="crowd_sensors", category="occupancy_high", zone_id="ZONE-C",
                           payload={"occupancy": 1410})["incident_id"]

    def test_divert_before_after_and_checks(self):
        iid = self.crowd()
        r = self.post(f"/api/incidents/{iid}/simulate", action="divert", target_zone="ZONE-B", share_pct=20).get_json()
        self.assertEqual(r["params"]["share_pct"], 20)
        self.assertLess(r["source"]["load_end"], r["baseline"]["load_end"])
        self.assertGreater(r["other"]["net_per_min"], r["other_before"]["net_per_min"])
        keys = {c["key"]: c["status"] for c in r["checks"]}
        self.assertIn("target_capacity", keys)
        self.assertEqual(keys["source_relief"], "ok")
        # numbers follow the documented formula
        z = {x["id"]: x for x in self.c.get("/api/zones").get_json()["zones"]}
        g = z["ZONE-C"]
        expected = max(0, g["occupancy"] + (g["inflow_per_min"] * 0.8 - g["staff_on_duty"] * 16) * 15)
        self.assertEqual(r["source"]["occupancy_end"], round(expected))

    def test_more_share_means_more_relief(self):
        iid = self.crowd()
        lo = self.post(f"/api/incidents/{iid}/simulate", action="divert", target_zone="ZONE-B", share_pct=10).get_json()
        hi = self.post(f"/api/incidents/{iid}/simulate", action="divert", target_zone="ZONE-B", share_pct=60).get_json()
        self.assertLess(hi["source"]["load_end"], lo["source"]["load_end"])
        self.assertGreater(hi["other"]["net_per_min"], lo["other"]["net_per_min"])

    def test_redeploy_min_staff_check_fails_when_donor_drops_below(self):
        iid = self.crowd()
        r = self.post(f"/api/incidents/{iid}/simulate", action="redeploy", target_zone="ZONE-B", staff=5).get_json()
        chk = {c["key"]: c for c in r["checks"]}
        self.assertEqual(chk["donor_min_staff"]["status"], "fail")     # 12 - 5 = 7 < 8 required
        ok = self.post(f"/api/incidents/{iid}/simulate", action="redeploy", target_zone="ZONE-B", staff=3).get_json()
        self.assertEqual({c["key"]: c for c in ok["checks"]}["donor_min_staff"]["status"], "ok")

    def test_validation(self):
        iid = self.crowd()
        self.assertEqual(self.post(f"/api/incidents/{iid}/simulate", action="divert", target_zone="ZONE-C").status_code, 400)
        self.assertEqual(self.post(f"/api/incidents/{iid}/simulate", action="divert", target_zone="ZONE-B",
                                   share_pct=95).status_code, 400)
        fire = self.ingest()["incident_id"]
        self.assertEqual(self.post(f"/api/incidents/{fire}/simulate", action="meter").status_code, 400)

    def test_operator_option_saved_survives_refresh_and_is_approvable(self):
        iid = self.crowd()
        r = self.post(f"/api/incidents/{iid}/options", action="divert", target_zone="ZONE-A", share_pct=25)
        self.assertEqual(r.status_code, 201)
        rid = r.get_json()["recommendation_id"]
        self.ingest(source_system="crowd_sensors", category="occupancy_high", zone_id="ZONE-C",
                    payload={"occupancy": 1420})    # triggers re-planning of system options
        recs = {x["id"]: x for x in self.detail(iid)["recommendations"]}
        self.assertIn(rid, recs)
        self.assertTrue(recs[rid]["params"]["custom"])
        self.assertEqual(self.post(f"/api/incidents/{iid}/decisions", action="approve",
                                   recommendation_id=rid).status_code, 201)
        log = self.c.get("/api/decisions").get_json()["decisions"][0]
        self.assertEqual((log["action"], log["snapshot"]["recommendation"]["code"]), ("approve", "divert_inflow"))
        self.assertTrue(log["snapshot"]["recommendation"]["params"]["custom"])

    def test_auto_options_carry_checks(self):
        iid = self.crowd()
        for rec in self.detail(iid)["recommendations"]:
            self.assertTrue(rec["simulation"]["checks"])
            self.assertIn("other_before", rec["simulation"])


class Migration(unittest.TestCase):
    OLD = """
    CREATE TABLE zones (id TEXT PRIMARY KEY, name_ar TEXT, name_en TEXT);
    CREATE TABLE incidents (id INTEGER PRIMARY KEY, code TEXT, type TEXT, zone_id TEXT);
    CREATE TABLE recommendations (id INTEGER PRIMARY KEY, incident_id INTEGER, code TEXT, rec_type TEXT,
                                  params TEXT, simulation TEXT);
    CREATE TABLE decisions (id INTEGER PRIMARY KEY, incident_id INTEGER, recommendation_id INTEGER, action TEXT,
                            operator TEXT, note TEXT, priority_at_decision TEXT, created_at TEXT);
    INSERT INTO zones VALUES ('GATE-N', 'البوابة الشمالية', 'North Gate');
    INSERT INTO incidents VALUES (1, 'INC-0001', 'crowd_pressure', 'GATE-N');
    INSERT INTO recommendations VALUES (1, 1, 'redeploy_staff', 'option', '{"staff_moved": 3}', NULL);
    INSERT INTO decisions VALUES (1, 1, 1, 'approve', 'مشرف العمليات', NULL, 'P2', '2026-10-08T10:00:00+00:00');
    """

    def test_v2_database_upgrades_and_keeps_decisions(self):
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            conn = db.connect(path)
            conn.executescript(self.OLD)
            conn.close()
            conn = db.init_db(path)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
            self.assertEqual({r[0] for r in conn.execute("SELECT id FROM zones")}, {"ZONE-A", "ZONE-B", "ZONE-C"})
            cols = {r[1] for r in conn.execute("PRAGMA table_info(alerts)")}
            self.assertTrue({"correlation", "location_id"} <= cols)
            d = db.rows(conn.execute("SELECT * FROM decisions"))
            self.assertEqual(len(d), 1)
            self.assertEqual((d[0]["operator"], d[0]["action"]), ("مشرف العمليات", "approve"))
            snap = d[0]["snapshot"]
            self.assertEqual(snap["incident_code"], "INC-0001")
            self.assertEqual(snap["names"]["GATE-N"]["en"], "North Gate")
            self.assertEqual(snap["recommendation"]["code"], "redeploy_staff")
            conn.close()
        finally:
            for sfx in ("", "-wal", "-shm"):
                try:
                    os.remove(path + sfx)
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
