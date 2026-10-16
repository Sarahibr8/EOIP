"""Impact simulation for operational (crowd pressure) incidents.

A deliberately simple, explainable flow model — NOT a crowd-dynamics model:

    processing/min   = staff_on_duty x GATE_PROCESSING_PER_STAFF   (gates)
    net/min          = inflow - processing
    occupancy(t)     = occupancy + net x t          (clamped at 0)
    queue wait (min) = occupancy / processing

All numbers come from the zone state that the incoming signals update.
"""
from .. import catalog

H = catalog.SIM_HORIZON_MIN
RATE = catalog.GATE_PROCESSING_PER_STAFF


def processing(zone, staff=None):
    staff = zone["staff_on_duty"] if staff is None else staff
    if zone["kind"] == "gate":
        return max(1.0, staff * RATE)
    return max(1.0, zone["outflow_per_min"])


def project(zone, inflow=None, staff=None, minutes=H):
    inflow = zone["inflow_per_min"] if inflow is None else inflow
    proc = processing(zone, staff)
    net = inflow - proc
    occ_end = max(0.0, zone["occupancy"] + net * minutes)
    return {
        "capacity": zone["capacity"],
        "occupancy_now": zone["occupancy"],
        "occupancy_end": round(occ_end),
        "load_now": round(zone["occupancy"] / zone["capacity"], 3),
        "load_end": round(occ_end / zone["capacity"], 3),
        "net_per_min": round(net, 1),
        "wait_now_min": round(zone["occupancy"] / processing(zone), 1),
        "wait_end_min": round(occ_end / proc, 1),
        "minutes_to_capacity": (round((zone["capacity"] - zone["occupancy"]) / net, 1)
                                if net > 0 and zone["occupancy"] < zone["capacity"] else None),
    }


def _load(zone):
    return zone["occupancy"] / zone["capacity"]


class SimulationError(ValueError):
    pass


TARGET_WARN, TARGET_FAIL = 0.85, 1.0


def _check(key, status, **params):
    return {"key": key, "status": status, "params": params}


def whatif(zone, zones_by_id, action, target_id=None, share_pct=None, staff=None, reduction_pct=None):
    """Compute the 15-minute effect of one operator action on the source zone and the
    other zone it touches. Pure arithmetic on the current zone state (see module doc).

    action: 'divert'   - send share_pct % of the source inflow to target_id
            'redeploy' - move `staff` people from target_id (donor) to the source zone
            'meter'    - slow entry at the source by reduction_pct %
    Returns {action, params, baseline, source, other_zone, other_before, other, checks, side_effects}.
    """
    before = project(zone)
    params, other_zone, other_before, other, checks, side = {}, None, None, None, [], []

    if action == "divert":
        tgt = zones_by_id.get(target_id)
        if tgt is None or target_id == zone["id"]:
            raise SimulationError("invalid_target")
        share = float(share_pct if share_pct is not None else 40)
        if not 5 <= share <= 80:
            raise SimulationError("invalid_share")
        diverted = zone["inflow_per_min"] * share / 100
        after = project(zone, inflow=zone["inflow_per_min"] - diverted)
        other_zone, other_before = tgt["id"], project(tgt)
        other = project(tgt, inflow=tgt["inflow_per_min"] + diverted)
        params = {"to_zone": tgt["id"], "share_pct": int(round(share)), "diverted_per_min": round(diverted)}
        load = other["load_end"]
        checks.append(_check("target_capacity", "fail" if load > TARGET_FAIL else "warn" if load >= TARGET_WARN else "ok",
                             zone=tgt["id"], load=load))
        if load >= TARGET_WARN:
            side.append({"key": "target_overloaded", "params": {"zone": tgt["id"], "load": load}})
        side.append({"key": "longer_walk", "params": {"zone": tgt["id"]}})

    elif action == "redeploy":
        donor = zones_by_id.get(target_id)
        if donor is None or target_id == zone["id"]:
            raise SimulationError("invalid_target")
        moved = int(staff if staff is not None else 1)
        if not 1 <= moved <= donor["staff_on_duty"]:
            raise SimulationError("invalid_staff")
        after = project(zone, staff=zone["staff_on_duty"] + moved)
        other_zone, other_before = donor["id"], project(donor)
        other = project(donor, staff=donor["staff_on_duty"] - moved)
        params = {"from_zone": donor["id"], "to_zone": zone["id"], "staff_moved": moved,
                  "staff_after": zone["staff_on_duty"] + moved}
        left = donor["staff_on_duty"] - moved
        checks.append(_check("donor_min_staff", "ok" if left >= donor["staff_required"] else "fail",
                             zone=donor["id"], left=left, required=donor["staff_required"]))
        if left < donor["staff_required"]:
            side.append({"key": "donor_below_required", "params": {"zone": donor["id"]}})
        load = other["load_end"]
        checks.append(_check("target_capacity", "fail" if load > TARGET_FAIL else "warn" if load >= TARGET_WARN else "ok",
                             zone=donor["id"], load=load))
        if zone["kind"] != "gate":
            # information, not a risk: in a hall or plaza extra staff raise coverage, not throughput
            checks.append(_check("staff_no_flow_effect", "info", zone=zone["id"]))

    elif action == "meter":
        red = float(reduction_pct if reduction_pct is not None else 50)
        if not 10 <= red <= 80:
            raise SimulationError("invalid_reduction")
        held = zone["inflow_per_min"] * red / 100
        after = project(zone, inflow=zone["inflow_per_min"] - held)
        params = {"reduction_pct": int(round(red)), "held_per_min": round(held)}
        people = round(held * H)
        side.append({"key": "outside_queue", "params": {"people": people}})
        checks.append(_check("outside_queue", "warn" if people > 300 else "ok", people=people))
    else:
        raise SimulationError("invalid_action")

    # common checks on the source zone
    src_status = "ok" if after["load_end"] < TARGET_WARN else "warn" if after["load_end"] < TARGET_FAIL else "fail"
    checks.insert(0, _check("source_capacity", src_status, zone=zone["id"], load=after["load_end"]))
    if action == "redeploy" and zone["kind"] != "gate":
        # Staff do not change visitor flow in a hall or plaza (see processing()), so the relief of a
        # staff move there is the staffing gap it closes, not a change in occupancy.
        staff_after = params["staff_after"]
        checks.insert(1, _check("staff_relief", "ok" if staff_after > zone["staff_on_duty"] else "fail",
                                zone=zone["id"], on_duty=zone["staff_on_duty"], staff_after=staff_after,
                                required=zone["staff_required"]))
    else:
        checks.insert(1, _check("source_relief", "ok" if after["load_end"] < before["load_end"] else "fail",
                                zone=zone["id"], before=before["load_end"], after=after["load_end"]))
    if zone["staff_required"]:
        staff_after = params.get("staff_after", zone["staff_on_duty"])
        checks.append(_check("source_min_staff", "ok" if staff_after >= zone["staff_required"] else "warn",
                             zone=zone["id"], on_duty=staff_after, required=zone["staff_required"]))
    # staffing before/after for both zones (shown for every action, so coverage is never hidden)
    moved = params.get("staff_moved", 0)
    staff = {"source": {"zone": zone["id"], "before": zone["staff_on_duty"], "after": zone["staff_on_duty"] + moved,
                        "required": zone["staff_required"]}}
    if action == "redeploy":
        d = zones_by_id[other_zone]
        staff["other"] = {"zone": d["id"], "before": d["staff_on_duty"], "after": d["staff_on_duty"] - moved,
                          "required": d["staff_required"]}
    return {"action": action, "params": params, "baseline": before, "source": after,
            "source_zone": zone["id"], "other_zone": other_zone, "other_before": other_before, "other": other,
            "staff": staff, "checks": checks, "side_effects": side, "horizon_min": H}


ACTION_CODE = {"divert": "divert_inflow", "redeploy": "redeploy_staff", "meter": "meter_entry"}


def divert_targets(zone, zones_by_id):
    """Zones arriving visitors can be redirected to: every other zone of the layout."""
    return [z for z in zones_by_id.values() if z["id"] != zone["id"]]


def staff_donors(zone, zones_by_id):
    return [z for z in zones_by_id.values() if z["id"] != zone["id"] and z["staff_on_duty"] > 0]


def crowd_options(zone, zones_by_id):
    """Return ranked options [{code, params, simulation}] for a crowded or under-staffed zone."""
    others = [z for z in zones_by_id.values() if z["id"] != zone["id"]]
    options = []

    # 1) Redeploy surplus staff from the zone with the most staff above its minimum.
    gap = zone["staff_required"] - zone["staff_on_duty"]
    donors = sorted((n for n in others if n["staff_on_duty"] - n["staff_required"] > 0),
                    key=lambda n: n["staff_on_duty"] - n["staff_required"], reverse=True)
    if gap > 0 and donors:
        donor = donors[0]
        moved = min(gap, donor["staff_on_duty"] - donor["staff_required"])
        sim = whatif(zone, zones_by_id, "redeploy", donor["id"], staff=moved)
        options.append({"code": "redeploy_staff", "params": sim["params"], "simulation": sim})

    # Divert / meter only make sense when the zone is actually under crowd pressure.
    crowded = _load(zone) >= TARGET_WARN or project(zone)["load_end"] >= TARGET_WARN
    if crowded:
        # 2) Divert 40 % of arrivals to the least-loaded other zone.
        targets = sorted(others, key=_load)
        if targets:
            sim = whatif(zone, zones_by_id, "divert", targets[0]["id"], share_pct=40)
            options.append({"code": "divert_inflow", "params": sim["params"], "simulation": sim})
        # 3) Meter entry (halve arrivals) — the queue moves outside the fence.
        sim = whatif(zone, zones_by_id, "meter", reduction_pct=50)
        options.append({"code": "meter_entry", "params": sim["params"], "simulation": sim})

    # Every case offers three options: fill up with other real, simulated variants.
    def add(action, target=None, **kw):
        try:
            sim = whatif(zone, zones_by_id, action, target, **kw)
        except SimulationError:
            return
        code = {"redeploy": "redeploy_staff", "divert": "divert_inflow", "meter": "meter_entry"}[action]
        if all(o["code"] != code or o["params"] != sim["params"] for o in options):
            options.append({"code": code, "params": sim["params"], "simulation": sim})
    extras = []
    if gap > 0:
        if donors:
            extras.append(("redeploy", donors[0]["id"], {"staff": max(1, min(gap, donors[0]["staff_on_duty"] - donors[0]["staff_required"]) // 2)}))
        for n in sorted(others, key=lambda n: n["staff_on_duty"] - n["staff_required"], reverse=True):
            if n["staff_on_duty"] > 0:
                extras.append(("redeploy", n["id"], {"staff": max(1, min(gap, 2))}))
    targets = sorted(others, key=_load)
    for tgt in targets:
        extras.append(("divert", tgt["id"], {"share_pct": 25}))
    extras.append(("meter", None, {"reduction_pct": 30}))
    for action, target, kw in extras:
        if len(options) >= 3:
            break
        add(action, target, **kw)

    options.sort(key=lambda o: score(o["simulation"]))
    options = options[:3]
    for i, opt in enumerate(options, start=1):
        opt["rank"] = i
        opt["simulation"]["score"] = score(opt["simulation"])
    return options


def score(sim):
    """Ranking cost: projected source load + penalties for real trade-offs (lower is better)."""
    penalty = 0
    for s in sim["side_effects"]:
        penalty += {"target_overloaded": 0.30, "donor_below_required": 0.30,
                    "outside_queue": 0.10 if s["params"].get("people", 0) > 300 else 0.0,
                    "longer_walk": 0.02}.get(s["key"], 0)
    return round(sim["source"]["load_end"] + penalty, 3)
