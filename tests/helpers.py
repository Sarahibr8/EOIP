"""Test helpers for the Django edition.

Every test gets its own fresh SQLite file (copied from a migrated template that already holds one
test employee), so the Django app and the core pipeline run exactly as in production, CSRF
checks included. `TestClient` keeps the small Flask-style interface the test-suite was written
with (post(json=...), get_json(), get_data(as_text=True)).
"""
import io
import json
import os
import re
import shutil
import tempfile

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "eoip_project.settings")
os.environ["EOIP_EXAMPLES"] = "0"      # tests start from an empty event (examples have their own test)
os.environ["EOIP_AUTOSTART"] = "0"     # signing in during tests must not start the live feed
_TEMPLATE_DIR = tempfile.mkdtemp(prefix="eoip-test-")
os.environ["EOIP_DB"] = os.path.join(_TEMPLATE_DIR, "template.sqlite3")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connections  # noqa: E402
from django.test import Client  # noqa: E402

from eoip import db  # noqa: E402

TEST_EMPLOYEE_NUMBER = "100123"
TEST_PASSWORD = "Temporary Test Password 123!"
OPERATOR = "Test Employee"
_template_ready = False


def _use_database(path):
    """Point Django and the EOIP layer at `path` (a fresh process would do the same at start-up)."""
    connections.close_all()
    settings.DATABASES["default"]["NAME"] = path
    connections["default"].settings_dict["NAME"] = path
    settings.EOIP_DB = path


def _template():
    global _template_ready
    path = os.environ["EOIP_DB"]
    if not _template_ready:
        _use_database(path)
        call_command("migrate", verbosity=0)
        from django.contrib.auth import get_user_model
        get_user_model().objects.create_user(username=TEST_EMPLOYEE_NUMBER, password=TEST_PASSWORD,
                                             first_name=OPERATOR)
        connections.close_all()
        _template_ready = True
    return path


class Response:
    def __init__(self, r):
        self._r = r
        self.status_code = r.status_code
        self.headers = r.headers

    def get_json(self):
        try:
            return json.loads(self._r.content.decode("utf-8"))
        except ValueError:
            return None

    @property
    def json(self):
        return self.get_json()

    def get_data(self, as_text=False):
        return self._r.content.decode("utf-8") if as_text else self._r.content


class TestClient:
    """Flask-test-client-like wrapper around django.test.Client (CSRF enforced)."""

    def __init__(self):
        self.django = Client(enforce_csrf_checks=True)
        self.csrf_token = None

    def _headers(self, method, headers):
        h = dict(headers or {})
        if method != "GET" and self.csrf_token:
            h.setdefault("X-CSRF-Token", self.csrf_token)
        return h

    def get(self, path, headers=None):
        return Response(self.django.get(path, headers=self._headers("GET", headers)))

    def delete(self, path, headers=None):
        return Response(self.django.delete(path, headers=self._headers("DELETE", headers)))

    def post(self, path, json=None, data=None, headers=None, content_type=None):
        headers = self._headers("POST", headers)
        ctype = content_type or headers.pop("Content-Type", None)
        if json is not None:
            r = self.django.post(path, data=_json_dumps(json), content_type="application/json", headers=headers)
        elif isinstance(data, (bytes, bytearray, memoryview)):
            r = self.django.post(path, data=bytes(data), content_type=ctype or "application/octet-stream",
                                 headers=headers)
        elif isinstance(data, io.IOBase):
            r = self.django.post(path, data=data.read(), content_type=ctype or "application/octet-stream",
                                 headers=headers)
        elif isinstance(data, dict):
            form = {}
            for k, v in data.items():
                if isinstance(v, tuple):              # Flask style: (file object, file name)
                    f, name = v[0], v[1]
                    form[k] = SimpleUploadedFile(name, f.read())
                else:
                    form[k] = v
            r = self.django.post(path, data=form, headers=headers)
        else:
            r = self.django.post(path, headers=headers)
        return Response(r)


def _json_dumps(value):
    return json.dumps(value, ensure_ascii=False)


def page_csrf(response):
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.get_data(as_text=True))
    return match.group(1) if match else None


def authenticate_test_client(client):
    token = page_csrf(client.get("/login"))
    if not token:
        raise AssertionError("login page did not include a CSRF token")
    response = client.post("/login", data={"csrfmiddlewaretoken": token, "employee_number": TEST_EMPLOYEE_NUMBER,
                                           "password": TEST_PASSWORD, "next": "/", "lang": "en"})
    if response.status_code != 302:
        raise AssertionError(f"test employee login failed: {response.status_code}")
    client.csrf_token = page_csrf(client.get("/"))
    if not client.csrf_token:
        raise AssertionError("authenticated page did not include a CSRF token")
    return client


def anonymous_client():
    return TestClient()


def restart_client(path):
    """A new client signed in again on the same database file (= an app restart)."""
    _use_database(path)
    return authenticate_test_client(TestClient())


def make_client():
    """Returns (None, signed-in client, database path). The first value used to be the Flask app."""
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    shutil.copyfile(_template(), path)
    _use_database(path)
    client = authenticate_test_client(TestClient())
    client.post("/api/demo/reset")
    return None, client, path


def sig(**kw):
    base = {"source_system": "fire_system", "category": "smoke_detected", "zone_id": "ZONE-A", "confidence": 0.8}
    base.update(kw)
    return base


def decide(conn, incident_id, action, recommendation_id=None, note=None, operator=OPERATOR):
    """core decision helper with a local test reason."""
    from eoip.core.decisions import decide as _decide
    return _decide(conn, incident_id, action, recommendation_id, note or "test decision reason", operator)
