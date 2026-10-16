"""Recommendations: playbooks for emergencies, simulated options for operational
incidents, routing for routine ones. Rule-based: response procedures must be
predictable and pre-approved, so we do not generate them with AI.
Text is never produced here — only step keys + params that the UI translates.

Teams come from the SYNTHETIC roster (data/teams.json); ETAs are estimates from
the illustrative walkway graph (core/teams.py). Both are labelled in the UI.
"""
from . import simulate, teams as teams_mod

PLAYBOOKS = {
    "fire": ("FIRE-01", ["dispatch_fire_team", "notify_civil_defense", "evacuate_zone",
                         "hold_entry_adjacent", "medical_standby"], ["fire", "medical"]),
    "medical": ("MED-01", ["dispatch_medical_team", "steward_secure_area",
                           "notify_zone_supervisor", "prepare_ambulance_route"], ["medical", "steward"]),
}
# Every case offers three ranked decision options. For life-safety incidents the pre-approved
# playbook is always option 1; options 2 and 3 are lighter, also pre-approved, variants.
ALTERNATIVES = {
    "fire": [("FIRE-02", ["dispatch_fire_team", "evacuate_location", "notify_civil_defense"], ["fire"]),
             ("FIRE-03", ["dispatch_fire_team", "verify_on_site", "notify_zone_supervisor"], ["fire"])],
    "medical": [("MED-02", ["dispatch_medical_team", "notify_zone_supervisor"], ["medical"]),
                ("MED-03", ["dispatch_medical_team", "request_ambulance", "prepare_ambulance_route"], ["medical"])],
}
ROUTE_TEAM = {"facility": "facilities", "it_system": "it", "visitor_conduct": "steward"}
# a fight between visitors goes to security; other visitor behaviour to the stewards
ROUTE_TEAM_BY_CATEGORY = {"visitor_fight": "security"}


def _pick_teams(conn, kinds, zone_id, location_id=None):
    picked, taken = [], set()
    for kind in kinds:
        t = teams_mod.nearest_available(conn, kind, zone_id, location_id, exclude=taken) if conn else None
        if t:
            taken.add(t["id"])
            picked.append({"team_id": t["id"], "kind": kind, "from_zone": t["base_zone"],
                           "from_location": t["base_location"], "walk_min": t["walk_min"],
                           "eta_min": t["eta_min"], "members": t["members"]})
        else:
            picked.append({"team_id": None, "kind": kind})
    return picked


def build(incident, zone, zones_by_id, conn=None):
    """Return a list of recommendation dicts (without ids) for the incident."""
    itype = incident["type"]
    if itype in PLAYBOOKS:
        adjacent = [n for n in zone["neighbors"] if n in zones_by_id]
        plans = [PLAYBOOKS[itype]] + ALTERNATIVES.get(itype, [])
        out = []
        for rank, (code, steps, kinds) in enumerate(plans, start=1):
            crew = _pick_teams(conn, kinds, zone["id"], incident.get("location_id"))
            why = [{"key": "life_safety_protocol", "params": {"type": itype}}]
            if incident.get("source_count", 0) >= 2:
                why.append({"key": "confirmed_sources", "params": {"n": incident["source_count"]}})
            else:
                why.append({"key": "act_before_confirmation", "params": {}})
            for c in crew:
                if c["team_id"]:
                    why.append({"key": "nearest_available_team",
                                "params": {"team": c["team_id"], "eta": c["eta_min"], "from_location": c["from_location"]}})
                else:
                    why.append({"key": "no_team_available", "params": {"kind": c["kind"]}})
            out.append({"code": code, "rec_type": "playbook", "rank": rank,
                        "params": {"steps": steps, "zone": zone["id"], "location": incident.get("location_id"),
                                   "adjacent": adjacent, "teams": crew, "why": why},
                        "simulation": None})
        return out
    if itype == "crowd_pressure":
        return [{"code": o["code"], "rec_type": "option", "rank": o["rank"],
                 "params": o["params"], "simulation": o["simulation"]}
                for o in simulate.crowd_options(zone, zones_by_id)]
    kind = ROUTE_TEAM.get(itype, "facilities")
    for cat in incident.get("categories") or ():
        kind = ROUTE_TEAM_BY_CATEGORY.get(cat, kind)
    crew = _pick_teams(conn, [kind], zone["id"], incident.get("location_id"))
    why = [{"key": "routine_owner", "params": {"kind": kind}}]
    team = {"facilities": "facilities", "it": "it_support", "steward": "stewards", "security": "security"}[kind]
    base = {"team": team, "zone": zone["id"], "location": incident.get("location_id"), "why": why}
    return [{"code": "route_team", "rec_type": "route", "rank": 1, "params": {**base, "teams": crew}, "simulation": None},
            {"code": "route_supervisor", "rec_type": "route", "rank": 2, "params": {**base, "teams": []}, "simulation": None},
            {"code": "monitor_only", "rec_type": "route", "rank": 3, "params": {**base, "teams": []}, "simulation": None}]
