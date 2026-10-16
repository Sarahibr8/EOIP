"""Page routes. The pages are static shells; all data comes from /api."""
from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET


@require_GET
@ensure_csrf_cookie
def dashboard(request):
    return render(request, "eoip/app.html", {"employee": request.employee})


@require_GET
@ensure_csrf_cookie
def field(request):
    return render(request, "eoip/field.html", {"employee": request.employee})


@require_GET
def health(request):
    return JsonResponse({"status": "ok", "service": "EOIP"})


def static(request, path):
    """Serve static files in every mode (the demo runs with DEBUG off). Camera snapshots under
    /static/snapshots/ are only reachable after sign-in (enforced by the middleware)."""
    return staticfiles_serve(request, path, insecure=True)
