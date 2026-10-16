"""Employee sign-in with Django's authentication system.

No account is seeded. Employees are provisioned with `python manage.py employee_add`
(username = employee number, first_name = display name, scrypt password hash).
"""
import unicodedata

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST

from ..middleware import safe_next


def normalize_employee_number(value):
    """Return canonical ASCII digits, accepting Arabic-Indic digit input too."""
    value = "" if value is None else str(value).strip()
    if not value or len(value) > 24:
        return None
    digits = []
    for char in value:
        try:
            digits.append(str(unicodedata.digit(char)))
        except (TypeError, ValueError):
            return None
    return "".join(digits)


def _lang(request):
    lang = request.POST.get("lang") or request.GET.get("lang") or "ar"
    return lang if lang in ("ar", "en") else "ar"


def _login_page(request, *, next_url="/", error=None, status=200):
    return render(request, "eoip/login.html",
                  {"next_url": safe_next(next_url), "error": error, "lang": _lang(request),
                   "dir": "rtl" if _lang(request) == "ar" else "ltr"}, status=status)


@never_cache
@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def login_view(request):
    next_url = safe_next(request.GET.get("next") or request.POST.get("next"))
    if request.user.is_authenticated and request.user.is_active:
        return HttpResponseRedirect(next_url)
    if request.method == "GET":
        return _login_page(request, next_url=next_url)

    number = normalize_employee_number(request.POST.get("employee_number"))
    password = request.POST.get("password", "")[:1024]
    # authenticate() runs the password hasher even for unknown users (no timing hint).
    user = authenticate(request, username=number or "", password=password) if password else None
    if user is None or not user.is_active:
        return _login_page(request, next_url=next_url, error="invalid", status=401)
    login(request, user)          # new session id + rotated CSRF token
    if next_url == "/" and settings.EOIP_AUTOSTART:
        _start_event(request.eoip_db)
    return HttpResponseRedirect(next_url)


def _start_event(conn):
    """A supervisor signing in to the operations center starts a fresh live event right away:
    the three stored example cases, then the live feed from second 0. The decision log is kept.
    (Refreshing the page or opening a second screen does not restart anything.)"""
    from .. import demo, examples
    from ..db import reset_all
    reset_all(conn)
    if settings.EOIP_EXAMPLES:
        examples.seed(conn)
    demo.start(conn)


@require_POST
def logout_view(request):
    logout(request)
    response = HttpResponseRedirect("/login")
    response["Cache-Control"] = "no-store"
    return response


def csrf_failure(request, reason=""):
    """Same answers as before: JSON for the API, the login page with an error for sign-in."""
    if request.path.startswith("/api/"):
        return JsonResponse({"error": "csrf_failed"}, status=403)
    if request.path == "/login":
        return _login_page(request, next_url=request.POST.get("next"), error="csrf", status=403)
    return HttpResponse("CSRF validation failed", status=403, content_type="text/plain")
