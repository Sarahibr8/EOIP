"""Authentication (Django auth), CSRF and identity attribution checks on disposable SQLite databases."""
import os
import unittest

from tests.helpers import (TEST_EMPLOYEE_NUMBER, TEST_PASSWORD, anonymous_client, make_client, page_csrf)


class Auth(unittest.TestCase):
    def setUp(self):
        self.app, self.client, self.path = make_client()

    def tearDown(self):
        from django.db import connections
        connections.close_all()   # Windows cannot delete an open SQLite file
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.path + suffix)
            except OSError:
                pass

    def test_unauthenticated_pages_and_apis_are_blocked(self):
        anonymous = anonymous_client()
        self.assertEqual(anonymous.get("/").status_code, 302)
        self.assertIn("/login", anonymous.get("/field").headers["Location"])
        self.assertEqual(anonymous.get("/api/state").status_code, 401)
        self.assertEqual(anonymous.get("/api/state").get_json(), {"error": "unauthorized"})
        self.assertEqual(anonymous.get("/api/health").status_code, 200)

    def test_login_page_has_employee_and_password_fields_only(self):
        html = anonymous_client().get("/login?lang=en").get_data(as_text=True)
        self.assertIn('name="employee_number"', html)
        self.assertIn('name="password"', html)
        self.assertNotIn('name="operator"', html)
        self.assertNotIn("forgot", html.lower())
        self.assertIn('dir="ltr"', html)

    def test_empty_and_wrong_credentials_are_rejected(self):
        anonymous = anonymous_client()
        csrf = page_csrf(anonymous.get("/login"))
        self.assertTrue(csrf)
        empty = anonymous.post("/login", data={"csrfmiddlewaretoken": csrf, "employee_number": "", "password": ""})
        self.assertEqual(empty.status_code, 401)
        wrong = anonymous.post("/login", data={"csrfmiddlewaretoken": csrf, "employee_number": TEST_EMPLOYEE_NUMBER,
                                               "password": "incorrect password"})
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(anonymous.get("/api/state").status_code, 401)

    def test_login_without_csrf_shows_csrf_error(self):
        anonymous = anonymous_client()
        anonymous.get("/login")
        r = anonymous.post("/login", data={"employee_number": TEST_EMPLOYEE_NUMBER, "password": TEST_PASSWORD})
        self.assertEqual(r.status_code, 403)
        self.assertIn('data-i18n="login.csrf"', r.get_data(as_text=True))

    def test_arabic_indic_digits_sign_in(self):
        anonymous = anonymous_client()
        csrf = page_csrf(anonymous.get("/login"))
        arabic = "".join("٠١٢٣٤٥٦٧٨٩"[int(c)] for c in TEST_EMPLOYEE_NUMBER)
        r = anonymous.post("/login", data={"csrfmiddlewaretoken": csrf, "employee_number": arabic,
                                           "password": TEST_PASSWORD, "next": "/field"})
        self.assertEqual((r.status_code, r.headers["Location"]), (302, "/field"))

    def test_next_cannot_redirect_off_site(self):
        anonymous = anonymous_client()
        csrf = page_csrf(anonymous.get("/login"))
        r = anonymous.post("/login", data={"csrfmiddlewaretoken": csrf, "employee_number": TEST_EMPLOYEE_NUMBER,
                                           "password": TEST_PASSWORD, "next": "https://evil.example/"})
        self.assertEqual(r.headers["Location"], "/")

    def test_authenticated_dashboard_shows_verified_employee(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertIn('data-employee-name="Test Employee"', html)
        self.assertIn(f'data-employee-number="{TEST_EMPLOYEE_NUMBER}"', html)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.get(username=TEST_EMPLOYEE_NUMBER)
        self.assertNotEqual(user.password, TEST_PASSWORD)
        self.assertTrue(user.password.startswith("scrypt$"))

    def test_mutations_require_csrf_and_logout_revokes_session(self):
        wrong = self.client.post("/api/demo/reset", headers={"X-CSRF-Token": "wrong-token"})
        self.assertEqual(wrong.status_code, 403)
        self.assertEqual(wrong.get_json(), {"error": "csrf_failed"})
        self.assertEqual(self.client.post("/logout").status_code, 302)
        self.assertEqual(self.client.get("/api/state").status_code, 401)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_snapshots_need_sign_in_but_static_files_do_not(self):
        anonymous = anonymous_client()
        self.assertEqual(anonymous.get("/static/css/eoip.css").status_code, 200)
        self.assertEqual(anonymous.get("/static/snapshots/x.jpg").status_code, 302)


if __name__ == "__main__":
    unittest.main()
