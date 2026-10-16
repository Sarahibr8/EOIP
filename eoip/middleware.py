"""Request gate for the operations app.

* Every page and API path requires a signed-in, active employee (Django auth session).
  Pages redirect to /login, API calls get 401 JSON - the same contract as before.
* Public: /login, /api/health, /health, static files (except camera snapshots), Django admin
  (which has its own staff login).
* Each request gets one EOIP SQLite connection (request.eoip_db) for the core pipeline,
  closed when the response is sent.
* Pages and API answers are never cached (Cache-Control: no-store).
"""
import threading
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponseRedirect, JsonResponse

from . import db

_init_lock = threading.Lock()
_initialised = set()


def ensure_operational_tables():
    """Create the EOIP tables once per process (normally already done by `migrate`)."""
    path = str(settings.EOIP_DB)
    if path in _initialised:
        return
    with _init_lock:
        if path not in _initialised:
            db.init_db(path).close()
            _initialised.add(path)


def safe_next(value):
    """Only allow redirects back to our own two pages."""
    from urllib.parse import urlsplit
    if not value:
        return "/"
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or not parts.path.startswith("/") or parts.path.startswith("//") or "\\" in value:
        return "/"
    return value if parts.path in ("/", "/field") else "/"


def _is_public(path):
    return (path in ("/login", "/health", "/api/health")
            or path.startswith("/admin/")
            or (path.startswith("/static/") and not path.startswith("/static/snapshots/")))


class EmployeeGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith("/static/") and not path.startswith("/static/snapshots/"):
            return self.get_response(request)

        if not _is_public(path):
            user = request.user
            if not (user.is_authenticated and user.is_active):
                if path.startswith("/api/"):
                    return JsonResponse({"error": "unauthorized"}, status=401)
                target = safe_next(request.get_full_path().rstrip("?"))
                return HttpResponseRedirect(f"/login?next={quote(target)}")
            request.employee = {"id": user.id, "employee_number": user.username,
                                "display_name": user.first_name or user.username}

        ensure_operational_tables()
        request.eoip_db = db.connect(settings.EOIP_DB)
        try:
            response = self.get_response(request)
        finally:
            request.eoip_db.close()
        if path != "/health":
            response["Cache-Control"] = "no-store"
        return response
