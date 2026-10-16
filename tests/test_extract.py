"""Golden cases for field-report extraction (rules_v2_lexicon, data/lexicon.json).

Arabic first, English supported. The extractor must return event type, zone and location
when they are said, leave them unknown when they are not, respect negation, and send
ambiguous reports to review instead of guessing.
"""
import unittest

from eoip.core.extract import extract, normalize_ar, to_signal

# (text, event, zone, location) — the 8 phrases from the final MVP spec first
SPEC = [
    ("فيه حريق في زون A عند منطقة المطاعم", "fire", "ZONE-A", "FOOD-COURT"),
    ("شخص مغمى عليه في زون B عند الممر الرئيسي", "medical", "ZONE-B", "MAIN-WALKWAY"),
    ("ازدحام شديد في زون C عند البوابة الرئيسية", "crowding", "ZONE-C", "MAIN-GATE"),
    ("نحتاج منظمين إضافيين في زون A عند منطقة الفعاليات", "staff_shortage", "ZONE-A", "EVENT-AREA"),
    ("There's smoke in Zone A near the Food Court.", "fire", "ZONE-A", "FOOD-COURT"),
    ("Someone is unconscious in Zone B at the Main Walkway.", "medical", "ZONE-B", "MAIN-WALKWAY"),
    ("Heavy crowding in Zone C near the Main Gate.", "crowding", "ZONE-C", "MAIN-GATE"),
    ("We need more staff in Zone A at the Event Area.", "staff_shortage", "ZONE-A", "EVENT-AREA"),
]

# vocabulary from the spec, each with an explicit zone so the event term is what is tested
VOCAB = {
    "fire": ["حريق", "فيه حريق", "دخان", "أشم ريحة احتراق", "اشتعال", "Fire", "There's a fire", "Smoke",
             "Burning smell", "Flames"],
    "medical": ["شخص طاح", "شخص سقط", "شخص مغمى عليه", "إغماء", "فاقد الوعي", "يحتاج إسعاف", "Person down",
                "Someone fell", "Fainting", "Unconscious", "Medical emergency", "Need an ambulance"],
    "crowding": ["زحمة", "ازدحام", "ازدحام شديد", "تدافع", "كثافة عالية", "الممر مزدحم", "نحتاج تنظيم الحشود",
                 "Crowding", "Overcrowding", "Heavy crowd", "Crowd surge", "Congested entrance", "Crowd control needed"],
    "staff_shortage": ["نقص موظفين", "نحتاج دعم", "نحتاج منظمين", "ما فيه عدد كافٍ", "نحتاج فريق إضافي",
                       "Staff shortage", "Need support", "Need more staff", "Not enough staff", "Request additional team"],
}


class SpecPhrases(unittest.TestCase):
    def test_spec_phrases(self):
        failures = []
        for text, event, zone, loc in SPEC:
            r = extract(text)
            got = (r["event"], r["zone_id"], r["location_id"], r["needs_review"])
            if got != (event, zone, loc, False):
                failures.append((text, got))
        self.assertEqual(failures, [])

    def test_vocabulary(self):
        failures = []
        for event, phrases in VOCAB.items():
            for p in phrases:
                suffix = " in Zone C" if p.isascii() else " في زون C"
                r = extract(p + suffix)
                if r["event"] != event or r["zone_id"] != "ZONE-C":
                    failures.append((p, r["event"], r["review_reasons"]))
        self.assertEqual(failures, [])

    def test_keeps_original_text_and_method(self):
        text = "فيه حريق في زون A عند منطقة المطاعم"
        r = extract(text)
        self.assertEqual(r["text"], text)
        self.assertEqual(r["method"], "rules_v2_lexicon")
        self.assertEqual(r["zone_source"], "stated")
        self.assertEqual(r["evidence"]["location_term"], "منطقه المطاعم")


class NoGuessing(unittest.TestCase):
    def test_unstated_fields_stay_unknown(self):
        r = extract("فيه دخان")
        self.assertEqual(r["event"], "fire")
        self.assertIsNone(r["zone_id"])
        self.assertIsNone(r["location_id"])
        self.assertIn("no_zone", r["review_reasons"])

    def test_location_without_zone_takes_its_zone_and_says_so(self):
        r = extract("شخص طاح عند منطقة المطاعم")
        self.assertEqual((r["zone_id"], r["location_id"], r["zone_source"]), ("ZONE-A", "FOOD-COURT", "location"))
        self.assertFalse(r["needs_review"])

    def test_zone_and_location_that_disagree_go_to_review(self):
        r = extract("حريق في زون C عند منطقة المطاعم")
        self.assertIn("zone_location_mismatch", r["review_reasons"])
        self.assertTrue(r["needs_review"])

    def test_two_zones_is_ambiguous(self):
        r = extract("زحمة في زون A وزون B")
        self.assertIsNone(r["zone_id"])
        self.assertIn("multiple_zones", r["review_reasons"])

    def test_irrelevant_text(self):
        r = extract("الوضع طبيعي والحمد لله")
        self.assertIsNone(r["event"])
        self.assertTrue(r["needs_review"])

    def test_empty_text_never_raises(self):
        self.assertTrue(extract("")["needs_review"])
        self.assertTrue(extract(None)["needs_review"])


class Negation(unittest.TestCase):
    def test_negated_fire_is_not_a_fire(self):
        for text in ("ما فيه حريق في زون A", "لا يوجد دخان في زون A", "There is no fire in Zone A",
                     "No smoke in Zone A", "False alarm, no fire in Zone A", "ما فيه دخان ولا حريق بزون A"):
            r = extract(text)
            self.assertIsNone(r["event"], text)
            self.assertIn("negated", r["review_reasons"], text)

    def test_negation_of_one_event_keeps_the_other(self):
        r = extract("ما فيه حريق بس فيه شخص طاح في زون B")
        self.assertEqual(r["event"], "medical")
        self.assertIn("حريق", r["evidence"]["negated_terms"])

    def test_negative_phrase_inside_a_term_is_not_negation(self):
        r = extract("ما فيه عدد كافٍ من المنظمين في زون C")
        self.assertEqual(r["event"], "staff_shortage")


class Ambiguity(unittest.TestCase):
    def test_fire_and_medical_together_go_to_review(self):
        r = extract("حريق وشخص مغمى عليه في زون B")
        self.assertIsNone(r["event"])
        self.assertEqual(r["candidates"], ["fire", "medical"])
        self.assertIn("multiple_events", r["review_reasons"])

    def test_support_request_vs_incident(self):
        self.assertEqual(extract("نحتاج دعم في زون C")["report_kind"], "support_request")
        self.assertEqual(extract("نحتاج إسعاف في زون C")["report_kind"], "incident_report")
        self.assertEqual(extract("نحتاج إسعاف في زون C")["event"], "medical")

    def test_location_name_is_not_an_event_word(self):
        # "نقطة الإسعافات الأولية" is a place; it must not make the report medical by itself
        r = extract("زحمة عند نقطة الإسعافات الأولية")
        self.assertEqual((r["event"], r["location_id"]), ("crowding", "FIRST-AID"))


class Basics(unittest.TestCase):
    def test_language_detection(self):
        self.assertEqual(extract("دخان في زون A")["language"], "ar")
        self.assertEqual(extract("smoke in zone a")["language"], "en")

    def test_confidence_higher_with_evidence(self):
        self.assertGreater(extract("حريق في زون A عند منطقة المطاعم عاجل")["confidence"],
                           extract("فيه دخان")["confidence"])

    def test_normalization(self):
        self.assertEqual(normalize_ar("البوابةُ الرئيسية"), "البوابه الرييسيه")
        self.assertEqual(normalize_ar("بالبوابة"), "البوابه")
        self.assertEqual(normalize_ar("زون A"), "زون a")

    def test_to_signal_keeps_evidence_and_location(self):
        s = to_signal(extract("دخان في زون A عند منطقة المطاعم"))
        self.assertEqual((s["source_system"], s["signal_type"]), ("radio", "radio_message"))
        self.assertEqual((s["zone_id"], s["location_id"]), ("ZONE-A", "FOOD-COURT"))
        self.assertEqual(s["payload"]["extraction"]["method"], "rules_v2_lexicon")
        self.assertEqual(s["payload"]["extraction"]["report_kind"], "incident_report")


if __name__ == "__main__":
    unittest.main()
