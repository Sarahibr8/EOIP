"""Normalization: any source payload -> one validated Alert shape.

Rule-based on purpose: validation must be deterministic and explainable.
"""
from .. import catalog
from ..db import now_iso, parse_iso


class ValidationError(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def normalize(raw, zone_ids, locations=None):
    """Return a normalized alert dict or raise ValidationError.

    `zone_ids` is the set of known zone ids; `locations` maps location id -> zone id.
    A missing zone is allowed only when the signal carries free text (it becomes
    `needs_review`). A location without a zone takes the zone the location belongs to
    (a fixed fact of the layout, not a guess); a location in a different zone is rejected.
    """
    locations = locations or {}
    errors = []
    if not isinstance(raw, dict):
        raise ValidationError(["body must be a JSON object"])

    source = raw.get("source_system")
    if source not in catalog.SOURCE_SYSTEMS:
        errors.append(f"source_system must be one of {sorted(catalog.SOURCE_SYSTEMS)}")

    category = raw.get("category")
    if category not in catalog.CATEGORIES:
        errors.append("unknown category")

    signal_type = raw.get("signal_type") or catalog.SOURCE_SYSTEMS.get(source)
    if signal_type not in catalog.SIGNAL_TYPES:
        errors.append(f"signal_type must be one of {catalog.SIGNAL_TYPES}")

    zone_id = raw.get("zone_id") or None
    location_id = raw.get("location_id") or None
    if location_id is not None:
        if location_id not in locations:
            errors.append(f"unknown location_id '{location_id}'")
        elif zone_id is None:
            zone_id = locations[location_id]
        elif locations[location_id] != zone_id:
            errors.append(f"location '{location_id}' is not in zone '{zone_id}'")
    if zone_id is not None and zone_id not in zone_ids:
        errors.append(f"unknown zone_id '{zone_id}'")
    if zone_id is None and not raw.get("raw_text"):
        errors.append("zone_id is required when raw_text is empty")

    origin = raw.get("origin", "mock")
    if origin not in catalog.ORIGINS:
        errors.append(f"origin must be one of {catalog.ORIGINS}")

    confidence = 0.0
    try:
        confidence = float(raw.get("confidence", 1.0))
        if not 0.0 <= confidence <= 1.0:
            errors.append("confidence must be between 0 and 1")
    except (TypeError, ValueError):
        errors.append("confidence must be a number")

    severity = 1
    try:
        severity = min(5, max(1, int(raw.get("severity_hint", 1))))
    except (TypeError, ValueError):
        errors.append("severity_hint must be an integer")

    language = raw.get("language")
    if language not in (None, "ar", "en"):
        errors.append("language must be 'ar' or 'en'")

    payload = raw.get("payload") or {}
    if not isinstance(payload, dict):
        errors.append("payload must be an object")

    received = now_iso()
    occurred = raw.get("occurred_at") or received
    try:
        parse_iso(occurred)
    except (TypeError, ValueError):
        errors.append("occurred_at must be ISO-8601")

    if errors:
        raise ValidationError(errors)

    return {
        "external_ref": raw.get("external_ref"),
        "signal_type": signal_type,
        "source_system": source,
        "category": category,
        "zone_id": zone_id,
        "location_id": location_id,
        "location_detail": (raw.get("location_detail") or None),
        "raw_text": (raw.get("raw_text") or None),
        "language": language,
        "severity_hint": severity,
        "confidence": round(confidence, 3),
        "payload": payload,
        "origin": origin,
        "occurred_at": occurred,
        "received_at": received,
    }
