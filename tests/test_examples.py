"""The three stored example cases (fire, crowding, staff shortage) are added when a new event starts."""
import unittest

from django.test import override_settings

from tests.helpers import make_client


class StoredExamples(unittest.TestCase):
    def setUp(self):
        _, self.client, _ = make_client()
        self.override = override_settings(EOIP_EXAMPLES=True)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def start_event(self):
        self.client.post("/api/demo/reset")
        self.assertTrue(self.client.post("/api/demo/autostart").get_json()["started"])
        return self.client.get("/api/state").get_json()

    def test_three_handled_examples_when_the_event_starts(self):
        s = self.start_event()
        closed = {i["label"]: i["status"] for i in s["incidents"] if i["status"] in ("resolved", "dismissed")}
        self.assertEqual(closed, {"fire": "resolved", "crowding": "resolved", "staff_shortage": "dismissed"})
        log = self.client.get("/api/decisions").get_json()["decisions"]
        current = [d for d in log if d["current_run"]]
        self.assertTrue(current and all("مثال" in d["operator"] for d in current))
        # test history of the previous months: labelled, with sources, never in the current event
        history = [d for d in log if not d["current_run"]]
        self.assertTrue(history and all("تجريبي" in d["operator"] for d in history))
        self.assertTrue(all(set(d["snapshot"]["sources"]) <= {"cctv_ai", "radio"} for d in log))
        months = {d["created_at"][:7] for d in history}
        self.assertEqual(len(months), 5)
        self.assertEqual(s["counters"]["awaiting_decision"], 0)       # examples never wait for a decision

    def test_examples_do_not_pile_up_and_never_restart_a_running_event(self):
        self.start_event()
        n = len(self.client.get("/api/decisions").get_json()["decisions"])
        self.assertFalse(self.client.post("/api/demo/autostart").get_json()["started"])   # refresh: nothing re-seeded
        self.start_event()                                                                 # a new event
        self.assertEqual(len(self.client.get("/api/decisions").get_json()["decisions"]), n)


if __name__ == "__main__":
    unittest.main()


class StartOnSignIn(unittest.TestCase):
    """Signing in to the operations center starts the event at once (with the stored cases)."""
    def setUp(self):
        _, self.client, _ = make_client()
        self.override = override_settings(EOIP_EXAMPLES=True, EOIP_AUTOSTART=True)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def sign_in(self, next_url):
        from tests.helpers import TEST_EMPLOYEE_NUMBER, TEST_PASSWORD, TestClient, page_csrf
        c = TestClient()
        token = page_csrf(c.get("/login"))
        r = c.post("/login", data={"csrfmiddlewaretoken": token, "employee_number": TEST_EMPLOYEE_NUMBER,
                                   "password": TEST_PASSWORD, "next": next_url})
        self.assertEqual(r.status_code, 302)
        c.csrf_token = page_csrf(c.get(next_url))
        return c

    def test_sign_in_starts_the_live_event_immediately(self):
        c = self.sign_in("/")
        s = c.get("/api/state").get_json()
        self.assertTrue(s["demo"]["running"])
        self.assertEqual(len([i for i in s["incidents"] if i["status"] in ("resolved", "dismissed")]), 3)
        self.assertFalse(c.post("/api/demo/autostart").get_json()["started"])   # the dashboard does not restart it

    def test_field_phone_sign_in_does_not_restart_the_event(self):
        c = self.sign_in("/field")
        self.assertFalse(c.get("/api/state").get_json()["demo"]["running"])
