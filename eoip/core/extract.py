"""Information extraction from short field reports (radio transcripts), Arabic-first.

Rule-based (`rules_v2_lexicon`), NOT a trained model: Arabic normalization + the central
keyword lists in data/lexicon.json (zones, the six locations, event terms, negation cues).
Why rules in the MVP: it works offline on the demo laptop, answers instantly, and every
extracted field is traceable to the words that produced it. The extract() contract
(text -> fields + review reasons + evidence) is the seam where an LLM extractor could be
plugged in later and compared against the golden cases in tests/test_extract.py.

What it does NOT do: guess. A field that is not said stays None ("unknown"). The one
derivation is zone-from-location, because every location belongs to exactly one zone in
the layout; it is marked zone_source="location" and shown to the reporter for review.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

LEXICON_PATH = Path(__file__).resolve().parents[2] / "data" / "lexicon.json"

_DIACRITICS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
_NON_WORD = re.compile(r"[^\w\s]")
_LATIN = re.compile(r"[a-z]")
_ARABIC = re.compile("[\u0600-\u06ff]")


def normalize_ar(text):
    t = _DIACRITICS.sub("", text or "")
    t = re.sub("[إأآٱ]", "ا", t)
    t = t.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    t = _NON_WORD.sub(" ", t.lower())
    # attached prefixes: بالساحه / وبالبوابه / للبوابه -> الساحه / البوابه
    t = re.sub(r"(?<!\w)(?:و|ف)?(?:ب|ك)?ال", "ال", t)
    t = re.sub(r"(?<!\w)(?:و|ف)?لل", "ال", t)
    return re.sub(r"\s+", " ", t).strip()


@lru_cache(maxsize=1)
def lexicon():
    raw = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
    norm = lambda xs: sorted({normalize_ar(x) for x in xs if normalize_ar(x)}, key=len, reverse=True)  # noqa: E731
    return {
        "zones": {z: norm(v) for z, v in raw["zones"].items()},
        "locations": {loc: norm(v) for loc, v in raw["locations"].items()},
        "events": [{"event": e["event"], "category": e["category"], "terms": norm(e["terms"])} for e in raw["events"]],
        "negation": norm(raw["negation_cues"]),
        "window": int(raw.get("negation_window_tokens", 2)),
        "false_alarm": norm(raw.get("false_alarm_terms", [])),
        "urgency": norm(raw["urgency_terms"]),
    }


@lru_cache(maxsize=1)
def location_zone():
    layout = json.loads((LEXICON_PATH.parent / "zones.json").read_text(encoding="utf-8"))
    return {loc["id"]: loc["zone_id"] for loc in layout["locations"]}


EVENT_OF = {"smoke_report": "fire", "medical_report": "medical", "crowd_report": "crowding",
            "staff_shortage_report": "staff_shortage"}
EMERGENCY_EVENTS = ("fire", "medical")


def _spans(text, term, prefixes=True, place=False):
    """(start, end) character spans of a whole-word match. Category words may carry و/ف/ب + ال;
    place names may carry و/ف/ب/ل (بزون A, وزون B)."""
    arabic = _ARABIC.search(term) and not term.startswith("ال")
    pre = ""
    if arabic and place:
        pre = r"(?:و|ف|ب|ل)?"
    elif arabic and prefixes:
        pre = r"(?:و|ف|ب)?(?:ال)?"
    return [(m.start(), m.end()) for m in re.finditer(rf"(?<!\w){pre}{re.escape(term)}(?!\w)", text)]


def _tok(text, pos):
    """Token index of a character position."""
    return len(text[:pos].split())


def _overlaps(span, taken):
    return any(span[0] < e and s < span[1] for s, e in taken)


def _find_places(t, table):
    """Longest-alias matches for zones / locations. Returns ({id: alias}, spans)."""
    found, spans = {}, []
    for pid, aliases in table.items():
        for alias in aliases:
            for sp in _spans(t, alias, place=True):
                if not _overlaps(sp, spans):
                    spans.append(sp)
                    found.setdefault(pid, alias)
    return found, spans


def detect_language(text):
    ar, en = len(_ARABIC.findall(text or "")), len(_LATIN.findall((text or "").lower()))
    return "ar" if ar >= en else "en"


def extract(text, language=None):
    """Return extracted fields, review reasons and evidence. Never raises on bad text."""
    lx = lexicon()
    raw = (text or "").strip()
    t = normalize_ar(raw)
    lang = language or detect_language(raw)

    zones, zone_spans = _find_places(t, lx["zones"])
    locs, loc_spans = _find_places(t, lx["locations"])
    taken = zone_spans + loc_spans          # place names are masked before looking for event words

    # event terms, with negation in a short window before each term
    cues = []
    for cue in lx["negation"]:
        cues += [sp for sp in _spans(t, cue, prefixes=False)]
    hits, negated = {}, []
    for ev in lx["events"]:
        for term in ev["terms"]:
            for sp in _spans(t, term):
                if _overlaps(sp, taken):
                    continue
                taken.append(sp)
                start_tok = _tok(t, sp[0])
                is_neg = any(c[1] <= sp[0] and 0 <= start_tok - _tok(t, c[1]) <= lx["window"] and not _overlaps(c, [sp])
                             for c in cues)
                (negated if is_neg else hits.setdefault(ev["category"], [])).append(term)
    if any(_spans(t, f, prefixes=False) for f in lx["false_alarm"]):
        negated += hits.pop("smoke_report", [])

    reasons = []
    events = {EVENT_OF[c] for c in hits}
    emergencies = [e for e in EMERGENCY_EVENTS if e in events]
    category = None
    if len(emergencies) > 1:
        reasons.append("multiple_events")            # e.g. fire AND a medical case: the reporter must choose
    elif emergencies:
        category = next(c for c, e in EVENT_OF.items() if e == emergencies[0])
    elif hits:
        # crowd vs staffing feed the same operational incident: pick the one with more evidence
        category = max(hits, key=lambda c: (len(hits[c]), c == "crowd_report"))
    elif negated:
        reasons.append("negated")
    else:
        reasons.append("no_event")
    candidates = sorted(EVENT_OF[c] for c in hits) if "multiple_events" in reasons else []

    zone_id, zone_source = None, None
    if len(zones) > 1:
        reasons.append("multiple_zones")
    elif zones:
        zone_id, zone_source = next(iter(zones)), "stated"
    location_id = None
    if len(locs) > 1:
        reasons.append("multiple_locations")
    elif locs:
        location_id = next(iter(locs))
        loc_zone = location_zone().get(location_id)
        if zone_id is None and "multiple_zones" not in reasons:
            zone_id, zone_source = loc_zone, "location"
        elif zone_id and loc_zone != zone_id:
            reasons.append("zone_location_mismatch")
    if zone_id is None and "multiple_zones" not in reasons:
        reasons.append("no_zone")

    urgency = [u for u in lx["urgency"] if _spans(t, u)]
    confidence = 0.1
    if category:
        confidence += 0.4 + min(0.1, 0.05 * (len(hits[category]) - 1))
    if zone_id:
        confidence += 0.3 if zone_source == "stated" else 0.2
    if location_id:
        confidence += 0.1
    if urgency:
        confidence += 0.05
    if reasons:
        confidence -= 0.15
    confidence = round(max(0.05, min(0.95, confidence)), 2)

    event = EVENT_OF.get(category)
    severity = 3 if event in EMERGENCY_EVENTS else 2
    severity = min(5, severity + (1 if urgency else 0))
    return {
        "text": raw,
        "language": lang,
        "event": event,
        "category": category,
        "report_kind": "support_request" if event == "staff_shortage" else ("incident_report" if event else None),
        "zone_id": zone_id,
        "zone_source": zone_source,
        "location_id": location_id,
        "severity_hint": severity,
        "confidence": confidence,
        "needs_review": bool(reasons),
        "review_reasons": reasons,
        "candidates": candidates,
        "evidence": {"zone_term": zones.get(zone_id) if zone_source == "stated" else None,
                     "location_term": locs.get(location_id), "category_terms": hits.get(category, []),
                     "negated_terms": negated, "urgency_terms": urgency},
        "method": "rules_v2_lexicon",
    }


def to_signal(fields, origin="voice", category_override=None, zone_override=None, location_override=None):
    """Turn extraction output into a raw signal for the pipeline (source: field radio)."""
    category = category_override or fields["category"]
    return {
        "source_system": "radio",
        "signal_type": "radio_message",
        "category": category,
        "zone_id": zone_override or fields["zone_id"],
        "location_id": location_override if location_override is not None else fields.get("location_id"),
        "raw_text": fields["text"],
        "language": fields["language"],
        "severity_hint": fields["severity_hint"],
        "confidence": fields["confidence"],
        "origin": origin,
        "payload": {"extraction": {"method": fields["method"], "evidence": fields["evidence"],
                                   "auto_category": fields["category"], "auto_zone": fields["zone_id"],
                                   "auto_location": fields.get("location_id"),
                                   "zone_source": fields.get("zone_source"),
                                   "review_reasons": fields.get("review_reasons", []),
                                   "report_kind": "support_request" if EVENT_OF.get(category) == "staff_shortage"
                                   else "incident_report"}},
    }
