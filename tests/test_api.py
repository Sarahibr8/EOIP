"""HTTP contract tests (docs/api-contract.md)."""
import json
import unittest
from pathlib import Path

from tests.helpers import make_client, sig

ROOT = Path(__file__).resolve().parent.parent


class Api(unittest.TestCase):
    def setUp(self):
        self.app, self.c, _ = make_client()

    def test_health_and_pages(self):
        self.assertEqual(self.c.get("/api/health").status_code, 200)
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(self.c.get("/field").status_code, 200)

    def test_ingest_validation_400(self):
        r = self.c.post("/api/ingest", json={"source_system": "nope"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "validation_error")

    def test_ingest_201(self):
        r = self.c.post("/api/ingest", json=sig())
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["disposition"], "correlated")

    def test_state_shape(self):
        self.c.post("/api/ingest", json=sig())
        s = self.c.get("/api/state").get_json()
        for k in ("counters", "incidents", "signals", "zones", "decisions", "demo"):
            self.assertIn(k, s)
        self.assertEqual([z["id"] for z in sorted(s["zones"], key=lambda z: z["id"])], ["ZONE-A", "ZONE-B", "ZONE-C"])
        self.assertEqual(len(s["locations"]), 6)
        self.assertEqual({l["zone_id"] for l in s["locations"]}, {"ZONE-A", "ZONE-B", "ZONE-C"})

    def test_incident_404(self):
        self.assertEqual(self.c.get("/api/incidents/999").status_code, 404)

    def test_decision_errors(self):
        iid = self.c.post("/api/ingest", json=sig()).get_json()["incident_id"]
        self.assertEqual(self.c.post(f"/api/incidents/{iid}/decisions", json={"action": "approve", "operator": "Sara"}).get_json()["error"], "recommendation_required")
        rec = self.c.get(f"/api/incidents/{iid}").get_json()["recommendations"][0]["id"]
        # The identity is taken from the server session even if the browser sends none or a false name.
        self.assertEqual(self.c.get("/api/decisions").get_json()["decisions"], [])
        ok = {"action": "approve", "recommendation_id": rec, "operator": "  ", "note": "Approved for test."}
        self.assertEqual(self.c.post(f"/api/incidents/{iid}/decisions", json=ok).status_code, 201)
        logged = self.c.get("/api/decisions").get_json()["decisions"][0]
        self.assertEqual((logged["operator"], logged["employee_number"]), ("Test Employee", "100123"))
        r = self.c.post(f"/api/incidents/{iid}/decisions", json=ok)
        self.assertEqual(r.status_code, 409)


    def test_reason_is_optional_for_every_decision(self):
        iid = self.c.post("/api/ingest", json=sig()).get_json()["incident_id"]
        recs = self.c.get(f"/api/incidents/{iid}").get_json()["recommendations"]
        r = self.c.post(f"/api/incidents/{iid}/decisions", json={"action": "approve", "recommendation_id": recs[0]["id"]})
        self.assertEqual(r.status_code, 201)
        other = self.c.post("/api/ingest", json=sig(zone_id="ZONE-C", location_id="MAIN-GATE")).get_json()["incident_id"]
        self.assertEqual(self.c.post(f"/api/incidents/{other}/decisions", json={"action": "dismiss"}).status_code, 201)
        logged = self.c.get("/api/decisions").get_json()["decisions"]
        self.assertEqual({(d["action"], d["note"]) for d in logged}, {("approve", None), ("dismiss", None)})
        self.assertTrue(all(d["operator"] for d in logged))      # still logged with the employee identity
    def test_voice_report_needs_review_422(self):
        r = self.c.post("/api/voice/report", json={"text": "الوضع غريب شوي"})
        self.assertEqual(r.status_code, 422)
        self.assertTrue(r.get_json()["extraction"]["needs_review"])

    def test_voice_report_with_user_correction(self):
        r = self.c.post("/api/voice/report", json={"text": "فيه دخان", "zone_id": "ZONE-B"})
        self.assertEqual(r.status_code, 201)
        a = self.c.get(f"/api/incidents/{r.get_json()['incident_id']}").get_json()["alerts"][0]
        self.assertTrue(a["payload"]["extraction"]["corrected_by_user"])
        self.assertEqual(a["origin"], "text")

    def test_demo_tick_is_idempotent_per_signal(self):
        self.c.post("/api/demo/start", json={"speed": 10})
        for _ in range(3):
            self.c.post("/api/demo/tick")
        s = self.c.get("/api/state").get_json()
        self.assertEqual(s["counters"]["received"], s["demo"]["cursor"])

    def test_i18n_dictionaries_have_same_keys(self):
        def keys(d, p=""):
            out = set()
            for k, v in d.items():
                out |= keys(v, f"{p}{k}.") if isinstance(v, dict) else {p + k}
            return out
        ar = json.loads((ROOT / "eoip/static/i18n/ar.json").read_text(encoding="utf-8"))
        en = json.loads((ROOT / "eoip/static/i18n/en.json").read_text(encoding="utf-8"))
        self.assertEqual(keys(ar) ^ keys(en), set())

    def test_every_enum_has_labels(self):
        from eoip import catalog
        for lang in ("ar", "en"):
            d = json.loads((ROOT / f"eoip/static/i18n/{lang}.json").read_text(encoding="utf-8"))
            self.assertEqual(set(catalog.CATEGORIES) - set(d["category"]), set(), lang)
            self.assertEqual(set(catalog.SOURCE_SYSTEMS) - set(d["source_system"]), set(), lang)
            self.assertEqual(set(catalog.INCIDENT_TYPES) - set(d["incident_type"]), set(), lang)
            self.assertEqual(set(catalog.ORIGINS) - set(d["origin"]), set(), lang)


if __name__ == "__main__":
    unittest.main()
