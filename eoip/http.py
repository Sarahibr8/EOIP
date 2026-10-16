"""Small JSON helpers shared by the API views (Arabic stays readable: ensure_ascii=False)."""
import json
from functools import wraps

from django.http import JsonResponse

from .core.decisions import DecisionError
from .core.normalize import ValidationError
from .core.simulate import SimulationError

CONFLICT_DECISION_ERRORS = ("incident_closed", "incident_escalated", "recommendation_not_open", "team_unavailable")


def respond(data, status=200):
    return JsonResponse(data, status=status, safe=False, json_dumps_params={"ensure_ascii": False})


def error(code, status=400, **extra):
    return respond({"error": code, **extra}, status)


def body(request):
    """JSON body as a dict ({} when missing or malformed), like Flask's get_json(silent=True)."""
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def api(view):
    """Turn the core's domain errors into the same JSON errors the API contract defines."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            result = view(request, *args, **kwargs)
        except ValidationError as e:
            return error("validation_error", errors=e.errors)
        except DecisionError as e:
            return error(str(e), 409 if str(e) in CONFLICT_DECISION_ERRORS else 400)
        except SimulationError as e:
            return error(str(e))
        if isinstance(result, tuple):
            return respond(*result)
        if isinstance(result, dict):
            return respond(result)
        return result
    return wrapper
