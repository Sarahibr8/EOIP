"""HTTP API (see docs/api-contract.md). Thin layer: validation errors -> 400,
business logic lives in eoip/core (unchanged from the original MVP)."""
import json

from django.views.decorators.http import require_GET, require_POST

from .. import catalog, demo, queries
from ..core import decisions, escalation, extract, pipeline, simulate, teams as teams_mod
from ..core.decisions import DecisionError
from ..core.simulate import SimulationError
from ..db import current_run as db_current_run, layout as db_layout, now_iso, reset_all, rows, to_dict, transaction
from ..http import api, body, error


@require_GET
@api
def get_layout(request):
    """Static illustrative site layout (zone shapes, location points, walkways) for the map."""
    data = db_layout()
    return {"note": data["_note"], "zones": [{"id": z["id"], "shape": z["shape"], "map": z["map"]} for z in data["zones"]],
            "locations": data["locations"], "walkways": data["walkways"]}


@require_GET
@api
def health(request):
    return {"status": "ok", "service": "EOIP"}


@require_GET
@api
def get_catalog(request):
    return {"signal_types": catalog.SIGNAL_TYPES, "source_systems": catalog.SOURCE_SYSTEMS,
            "categories": catalog.CATEGORIES, "incident_types": catalog.INCIDENT_TYPES,
            "origins": catalog.ORIGINS}


@require_GET
@api
def state(request):
    conn = request.eoip_db
    return {
        "counters": queries.counters(conn),
        "incidents": queries.incident_list(conn),
        "signals": queries.recent_signals(conn, int(request.GET.get("signals", 40))),
        "zones": queries.zones(conn),
        "locations": queries.locations(conn),
        "decisions": queries.decision_log(conn, 15, current_only=True),
        "teams": teams_mod.all_teams(conn),
        "demo": demo.state(conn),
        "escalation": escalation.matrix(),
    }


@require_GET
@api
def zones(request):
    return {"zones": queries.zones(request.eoip_db)}


@require_GET
@api
def incident(request, incident_id):
    detail = queries.incident_detail(request.eoip_db, incident_id)
    return detail if detail else error("not_found", 404)


@require_POST
@api
def decide(request, incident_id):
    b, conn, emp = body(request), request.eoip_db, request.employee
    try:
        did = decisions.decide(conn, incident_id, b.get("action"), b.get("recommendation_id"),
                               b.get("note"), emp["display_name"], emp["id"], emp["employee_number"])
    except DecisionError as e:
        if str(e) == "team_unavailable":   # re-plan with the teams that are free now
            with transaction(conn):
                pipeline.refresh_incident(conn, incident_id, rebuild=True)
        elif str(e) == "incident_escalated":
            escalation.sweep(conn)
        raise
    return {"decision_id": did, "incident": queries.incident_detail(conn, incident_id)}, 201


def _crowd_incident(conn, incident_id):
    inc = to_dict(conn.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone())
    if inc is None:
        return None, error("not_found", 404)
    if inc["kind"] != "operational":
        return None, error("simulation_operational_only")
    return inc, None


def _whatif(conn, inc, b):
    """divert / meter act on the incident zone. redeploy moves staff FROM target_zone TO to_zone
    (default: the incident zone), so a staffing what-if can name both ends."""
    zone_map = {z["id"]: z for z in rows(conn.execute("SELECT * FROM zones"))}
    receiving = inc["zone_id"]
    if b.get("action") == "redeploy" and b.get("to_zone"):
        if b["to_zone"] not in zone_map:
            raise SimulationError("invalid_target")
        receiving = b["to_zone"]
    return simulate.whatif(zone_map[receiving], zone_map, b.get("action"), b.get("target_zone"),
                           share_pct=b.get("share_pct"), staff=b.get("staff"), reduction_pct=b.get("reduction_pct"))


@require_POST
@api
def simulate_whatif(request, incident_id):
    """What-if: compute an operator-chosen action on the CURRENT zone state. Nothing is stored."""
    inc, err = _crowd_incident(request.eoip_db, incident_id)
    if err:
        return err
    return _whatif(request.eoip_db, inc, body(request))


@require_POST
@api
def add_option(request, incident_id):
    """Save an operator-defined option (computed now) so it can be approved or rejected."""
    conn = request.eoip_db
    inc, err = _crowd_incident(conn, incident_id)
    if err:
        return err
    if inc["status"] != "open":
        return error("incident_closed", 409)
    sim = _whatif(conn, inc, body(request))
    sim["score"] = simulate.score(sim)
    params = {**sim["params"], "custom": True}
    with transaction(conn):
        n = conn.execute("SELECT COUNT(*) FROM recommendations WHERE incident_id=? AND rank>=90",
                         (incident_id,)).fetchone()[0]
        cur = conn.execute(
            """INSERT INTO recommendations (incident_id, code, rec_type, rank, params, simulation, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (incident_id, simulate.ACTION_CODE[sim["action"]], "option", 90 + n, json.dumps(params),
             json.dumps(sim), now_iso()))
    return {"recommendation_id": cur.lastrowid, "incident": queries.incident_detail(conn, incident_id)}, 201


@require_GET
@api
def teams(request):
    return {"teams": teams_mod.all_teams(request.eoip_db)}


@require_GET
@api
def decision_log(request):
    conn = request.eoip_db
    limit = int(request.GET.get("limit", 300))
    return {"decisions": queries.decision_log(conn, limit), "escalations": escalation.log(conn, limit),
            "current_run": db_current_run(conn)}


@require_POST
@api
def ingest(request):
    """Any source system (or adapter) posts one signal here."""
    return pipeline.ingest(request.eoip_db, body(request)), 201


@require_POST
@api
def voice_extract(request):
    b = body(request)
    return extract.extract(b.get("text", ""), b.get("language"))


@require_POST
@api
def voice_report(request):
    """Field supervisor report (phone = radio). Text comes from speech-to-text or typing.

    The reporter reviews what EOIP understood and may correct it. Event type is required;
    zone and location may stay unknown: such a report is stored as `needs_review` and is not
    linked to any incident (EOIP never guesses where it happened)."""
    b, conn = body(request), request.eoip_db
    text = (b.get("text") or "").strip()
    if not text:
        return error("text_required")
    fields = extract.extract(text, b.get("language"))
    category = b.get("category") or fields["category"]
    if not category:
        return error("needs_review", 422, extraction=fields)
    zone = (b.get("zone_id") or None) if "zone_id" in b else fields["zone_id"]
    loc_choice = b.get("location_id") if "location_id" in b else fields.get("location_id")
    other_text = (b.get("location_other") or "").strip()[:120] or None
    location = None if loc_choice in (None, "", "other") else loc_choice
    origin = "voice" if b.get("input_mode") == "voice" else "text"
    signal = extract.to_signal(fields, origin=origin, category_override=category, zone_override=zone,
                               location_override=location)
    signal["zone_id"] = zone
    if loc_choice == "other" and other_text:
        signal["location_detail"] = other_text
    if b.get("recorded_at"):
        signal["occurred_at"] = b["recorded_at"]
    ex = signal["payload"]["extraction"]
    ex["corrected_by_user"] = (category != fields["category"] or zone != fields["zone_id"]
                               or location != fields.get("location_id"))
    if isinstance(b.get("stt_confidence"), (int, float)):
        ex["stt_confidence"] = round(float(b["stt_confidence"]), 2)
    result = pipeline.ingest(conn, signal)
    inc = None
    if result.get("incident_id"):
        inc = to_dict(conn.execute("SELECT id, code, priority, status FROM incidents WHERE id=?",
                                   (result["incident_id"],)).fetchone())
    return {**result, "incident": inc, "extraction": fields}, 201


# --- demo control -----------------------------------------------------------
@require_POST
@api
def demo_reset(request):
    reset_all(request.eoip_db)
    return {"ok": True, "demo": demo.state(request.eoip_db)}


@require_POST
@api
def demo_start(request):
    conn = request.eoip_db
    st = demo.state(conn)
    if st["finished"] or st["cursor"] > 0:
        reset_all(conn)
    demo.start(conn, body(request).get("speed", 1.0))
    return {"ok": True, "demo": demo.state(conn)}


@require_POST
@api
def demo_autostart(request):
    """Called by the dashboard when it opens: starts the event once (never restarts it)."""
    started = demo.autostart(request.eoip_db)
    if started:
        from django.conf import settings
        if settings.EOIP_EXAMPLES:
            from .. import examples
            examples.seed(request.eoip_db)      # the three stored example cases of this event
    return {"ok": True, "started": started, "demo": demo.state(request.eoip_db)}


@require_POST
@api
def demo_stop(request):
    demo.stop(request.eoip_db)
    return {"ok": True, "demo": demo.state(request.eoip_db)}


@require_POST
@api
def demo_tick(request):
    n = demo.tick(request.eoip_db)
    return {"ingested": n, "demo": demo.state(request.eoip_db)}


@require_POST
@api
def demo_skip(request):
    """Load the whole scripted event instantly (review mode / fallback)."""
    n = demo.tick(request.eoip_db, ingest_all=True)
    return {"ingested": n, "demo": demo.state(request.eoip_db)}


@require_POST
@api
def demo_cv_replay(request):
    """Fallback when the live camera fails: replays a recorded detection, labelled replay_cv."""
    signal = dict(demo.CV_REPLAY_SIGNAL, payload=dict(demo.CV_REPLAY_SIGNAL["payload"]))
    return pipeline.ingest(request.eoip_db, signal), 201
