"""Generate the synthetic live-event script used by the demo engine.

    python data/generate_mock.py            -> writes data/demo_script.json

Deterministic (fixed seed) so every demo run and every test sees the same
signals. ALL DATA IS SYNTHETIC — designed by the EOIP team to resemble the
mix an operations centre receives; it is not Expo data and the volumes are
not official figures.

Every report reaches the centre over one of two channels only: a CAMERA (camera analytics,
source "cctv_ai") or the field RADIO (supervisors, source "radio"). No sensors, no service desk,
no automatic systems.

Each entry: {"t": seconds after start, "story": scenario id or null,
             "extract": true if raw_text must go through voice extraction,
             "signal": {...raw signal for POST /api/ingest...}}
"""
import json
import random
from pathlib import Path

SEED = 2030
DURATION = 60.0
OUT = Path(__file__).with_name("demo_script.json")
ZONES = ["ZONE-A", "ZONE-B", "ZONE-C"]   # illustrative demo zones (data/zones.json)
CAMS = ["03", "07", "11", "14", "18", "21", "25"]

rng = random.Random(SEED)
script = []


def add(t, signal, story=None, extract=False):
    signal.setdefault("origin", "mock")
    script.append({"t": round(t, 2), "story": story, "extract": extract, "signal": signal})


def spread(n, start=0.3, end=DURATION, front=1.0):
    """n times between start and end; front > 1 packs more of them near the start."""
    return sorted(start + (end - start) * (rng.random() ** front) for _ in range(n))


def radio(t, text, story):
    add(t, {"source_system": "radio", "raw_text": text}, story, extract=True)


def cam(t, story, category, zone, loc, conf, text, cam_id, **payload):
    add(t, {"source_system": "cctv_ai", "category": category, "zone_id": zone, "location_id": loc, "confidence": conf,
            "raw_text": text, "location_detail": f"Camera {cam_id}", "payload": {"camera_id": cam_id, **payload}}, story)


# --- background: camera health / motion (filtered as noise) and radio check-ins (routed) -----------------
# Packed towards the start so the screen is busy from the first seconds.
for t in spread(70, front=1.6):
    c = rng.choice(CAMS); z = rng.choice(ZONES)
    add(t, {"source_system": "cctv_ai", "category": "heartbeat", "zone_id": z,
            "payload": {"camera_id": f"CAM-{z[-1]}-{c}", "status": "ok"}})
for t in spread(28, front=1.4):
    c = rng.choice(CAMS); z = rng.choice(ZONES)
    add(t, {"source_system": "cctv_ai", "category": "unusual_motion", "zone_id": z, "confidence": round(rng.uniform(0.3, 0.55), 2),
            "raw_text": f"كاميرا {c}: حركة غير اعتيادية", "payload": {"camera_id": f"CAM-{z[-1]}-{c}"}})
STATUS = ["الوضع طبيعي في زون B", "Zone A checkpoint all clear", "تبديل وردية فريق الحراسة", "الفريق وصل نقطة التجمع",
          "تم فتح المسار رقم ٣ في البوابة الرئيسية", "Radio check, North team", "دورية زون C مستمرة، لا ملاحظات"]
for t in spread(32, front=1.4):
    add(t, {"source_system": "radio", "category": "status_update", "zone_id": rng.choice(ZONES),
            "raw_text": rng.choice(STATUS), "language": None})

# ======================= CRITICAL (P1): one case, camera + radio confirm each other =======================
# P1-a  Fire at the Food Court (Zone A): camera sees smoke, a supervisor confirms on the radio.
F1 = "P1-FIRE-A"
cam(1.0, F1, "smoke_detected", "ZONE-A", "FOOD-COURT", 0.82, "كاميرا 14: رصد دخان في منطقة المطاعم", "CAM-A-14")
radio(3.0, "دخان كثيف في زون A عند منطقة المطاعم، نحتاج إطفاء", F1)
cam(9.0, F1, "smoke_detected", "ZONE-A", "FOOD-COURT", 0.9, "كاميرا 18: الدخان يزيد في منطقة المطاعم", "CAM-A-18")
radio(16.0, "أكد الدخان في منطقة المطاعم زون A والزوار يبتعدون", F1)

# (Only one scripted critical case. The fainting case in Zone B comes live from the camera + phone.)

# ======================= MEDIUM (P2) =======================
# P2-a  Crowding at the Main Gate (Zone C): the gate camera counts people and the queue, the radio confirms.
C1 = "P2-CROWD-C"
cam(2.0, C1, "occupancy_high", "ZONE-C", "MAIN-GATE", 0.95, "كاميرا 07: عدّ الزوار عند البوابة الرئيسية", "CAM-C-07",
    occupancy=1170, capacity=1500, inflow_per_min=110)
cam(8.0, C1, "queue_long", "ZONE-C", "MAIN-GATE", 0.9, "كاميرا 07: الطابور طويل عند البوابة الرئيسية", "CAM-C-07", wait_min=12)
cam(17.0, C1, "occupancy_high", "ZONE-C", "MAIN-GATE", 0.95, "كاميرا 07: عدّ الزوار عند البوابة الرئيسية", "CAM-C-07",
    occupancy=1320, capacity=1500, inflow_per_min=120)
radio(21.0, "ازدحام شديد في زون C عند البوابة الرئيسية والطابور طويل ونحتاج دعم", C1)
cam(27.0, C1, "queue_long", "ZONE-C", "MAIN-GATE", 0.9, "كاميرا 07: الانتظار تجاوز 19 دقيقة", "CAM-C-07", wait_min=19)
cam(34.0, C1, "occupancy_high", "ZONE-C", "MAIN-GATE", 0.95, "كاميرا 07: عدّ الزوار عند البوابة الرئيسية", "CAM-C-07",
    occupancy=1410, capacity=1500, inflow_per_min=125)

# P2-b  Staff shortage at the Event Area (Zone A): two supervisors report on the radio.
S1 = "P2-STAFF-A"
add(10.0, {"source_system": "radio", "category": "staff_shortage", "zone_id": "ZONE-A", "location_id": "EVENT-AREA", "confidence": 0.9,
           "raw_text": "مشرف منطقة الفعاليات: الموجود 8 منظمين من 12", "payload": {"on_duty": 8, "required": 12}}, S1)
radio(24.0, "نحتاج منظمين إضافيين في زون A عند منطقة الفعاليات", S1)

# P2-c  Camera alone: a person on the ground in the Waiting Area (Zone C), not yet confirmed -> verify now.
V1 = "P2-VERIFY-C"
cam(26.0, V1, "person_down", "ZONE-C", "WAITING-AREA", 0.7, "كاميرا 25: احتمال شخص ساقط في منطقة الانتظار", "CAM-C-25")

# ======================= NORMAL (P3): visitor behaviour, sent to the field team =======================
N1 = "P3-FIGHT-C"
add(5.0, {"source_system": "radio", "category": "visitor_fight", "zone_id": "ZONE-C", "location_id": "WAITING-AREA", "confidence": 0.85,
          "raw_text": "مشاجرة بين زوار في زون C عند منطقة الانتظار"}, N1)
cam(7.5, N1, "visitor_fight", "ZONE-C", "WAITING-AREA", 0.76, "كاميرا 25: تدافع ومشادة بين زوار في منطقة الانتظار", "CAM-C-25")

N2 = "P3-SIT-B"
cam(12.0, N2, "visitor_sitting_path", "ZONE-B", "MAIN-WALKWAY", 0.8, "كاميرا 03: زوار جالسين في منتصف الممر الرئيسي", "CAM-B-03")
add(15.0, {"source_system": "radio", "category": "visitor_sitting_path", "zone_id": "ZONE-B", "location_id": "MAIN-WALKWAY", "confidence": 0.85,
           "raw_text": "زوار جالسين بنص المسار في الممر الرئيسي زون B"}, N2)

N3 = "P3-WRONGWAY-C"
cam(18.0, N3, "visitor_wrong_way", "ZONE-C", "MAIN-GATE", 0.78, "كاميرا 07: زوار يمشون عكس اتجاه المسار عند البوابة الرئيسية", "CAM-C-07")
add(23.0, {"source_system": "radio", "category": "visitor_wrong_way", "zone_id": "ZONE-C", "location_id": "MAIN-GATE", "confidence": 0.85,
           "raw_text": "زوار عاكسين المسار عند البوابة الرئيسية زون C"}, N3)

script.sort(key=lambda e: e["t"])
OUT.write_text(json.dumps({"_note": "SYNTHETIC demo data generated by data/generate_mock.py (seed %d). Not Expo data. "
                           "Sources: camera (cctv_ai) and field radio only." % SEED,
                           "duration_s": DURATION, "entries": script}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {len(script)} signals to {OUT}")
