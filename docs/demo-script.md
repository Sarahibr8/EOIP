# Demo Script — EOIP (5:00 max, rehearsed target 4:50)

**On stage:**
- **Laptop (ops app):** full-screen, Arabic, connected to the projector. Camera agent window minimized next to it.
- **Phone (radio):** `https://<laptop-ip>:8000/field`, already open, microphone allowed.
- **Presenter roles:**
  - **A** narrates and clicks.
  - **B** holds the phone and is the person who "collapses" in front of the camera.

The event plays live at 1× (or 2× if short on time). Times match the synthetic script: the crowd builds from about 0:25, smoke appears at about 1:00, and radio confirmation arrives at about 1:10. **Presenter tools** (أدوات العرض) are at the bottom of the side rail.

| Time | Page | Say (short) | Do |
|---|---|---|---|
| 0:00 | **Overview**: intro + funnel at 0, "بيانات محاكاة للعرض" label | «في فعالية مباشرة يستقبل مركز العمليات مئات الإشارات من جهات منفصلة. التحدي 3.6: كيف يعرف ما يحتاج تدخلًا فوريًا؟ كل البيانات هنا محاكاة من إعدادنا.» | — |
| 0:20 | Overview: funnel counts, signal stream | «EOIP طبقة فوق الأنظمة الموجودة: يستبعد الضجيج، يحوّل الروتيني، يدمج المكرر.» | Presenter tools → **Start live event** |
| 0:50 | Overview → "Needs a decision": Crowding + staff shortage · Zone C · Main Gate, P2 | «أربع جهات منفصلة صارت حالة واحدة.» | — |
| 1:10 | Red toast: **Critical: Fire / smoke · Zone A · Food Court** | «كاشف دخان واحد لا يكفي… عندما يؤكده مصدر مستقل تصبح حرجة.» | Click **Incidents** → the fire row |
| 1:20 | **Incident details**: linked reports | «هنا لماذا رُبط كل بلاغ: نفس النوع، نفس المنطقة، بعد ثانيتين، ومصدر مستقل جديد. والتكرار يُدمج ولا يُحسب دليلًا. الدرجة قاعدية، ليست نموذجًا مدرّبًا.» | Point at the *why linked* chips and the priority scale |
| 1:45 | **Decision support** (fire): plan + team + ETA | «في السلامة لا نحاكي، نتصرف: خطة جاهزة، وأقرب فريق إطفاء متاح يصل خلال نحو 6 دقائق، والإسعاف نحو 3.5. الفرق هنا قائمة تجريبية.» | **Activate response plan** → the team is now assigned |
| 2:00 | Decision support: type your name in **Deciding as** | «كل قرار يُسجَّل باسم المسؤول.» | Type the name once |
| 2:05 | Decision support (crowd): 3 ranked options, before/after | «التشغيلي يحتاج مفاضلة: بلا تدخل 136٪، نقل 3 موظفين من الشرقية: 88٪، والشرقية تبقى فوق الحد الأدنى.» | Choose the crowd incident in the picker |
| 2:30 | **Crowd simulation** tab (or **Staffing simulation**) | «والمشرف يجرّب بنفسه: تحويل 60٪ من القادمين… الأرقام تُحسب الآن من الخادم، مع فحص السعة والحد الأدنى للموظفين.» | Move the slider → **Add as option** → **Approve** the recommended one |
| 2:55 | Camera | «مصدر حي: كاميرا موقع.» | B lies down in front of the camera → Medical · Zone B · Main Walkway appears (**Live camera** tag). Phone-camera alternative: Field reporting → Camera tab |
| 3:20 | Phone | «المشرف الميداني يبلّغ صوتيًا بالعربي…» | B: «شخص مغمى عليه في زون B عند الممر الرئيسي» → **Check report** → **Send**. The incident becomes **P1, 2 independent sources** |
| 3:50 | **Operations map** | «الخريطة: كثافة التظليل = الإشغال، الحلقة = أعلى أولوية، والنقاط = الفرق في مواقعها.» | Click Main Gate (Zone C) |
| 4:10 | **Decision log** | «كل قرار مسجّل: من، متى، والأولوية التي رآها، وسبب الرفض.» | — |
| 4:25 | Close | «الذكاء الاصطناعي فقط حيث يضيف قيمة: الصوت والكاميرا. الربط والأولوية والتوصيات قواعد قابلة للتفسير. القرار دائمًا للإنسان.» | (Optional) **English** to show LTR |

## Fallbacks: decide in one second, never debug on stage

| Failure | Sign | Do this | Say |
|---|---|---|---|
| Camera doesn't alert | No medical incident ~5 s after lying down | (1) Phone → Field reporting → Camera → **Analyse a video file** with the prepared clip; (2) Presenter tools → **Send recorded camera detection** | (1) «تحليل ملف فيديو، وليس بثًا مباشرًا» (2) «هذا رصد مسجّل، ويظهر بوسم إعادة تشغيل» |
| Mic error / no transcript | Red note under the mic | Tap a **Sample report**, or type it | «الإدخال الصوتي يعتمد على المتصفح؛ النص يمر بنفس التحليل» |
| Phone can't reach laptop | Network error on the phone | Laptop: Presenter tools → **Send sample field report** (same text, same pipeline) | — |
| Wrong type/zone understood | Wrong values in "What EOIP understood" | Correct them in the dropdowns before sending (logged as corrected) | «المشرف يصحح قبل الإرسال» |
| Internet down | Speech fails | Everything else is local; use a sample or typing | — |
| Server stopped | Persistent red notice | Restart `python run.py --host 0.0.0.0 --https`. Data survives; "Connection restored" appears | — |
| Running late | — | Speed 2×, or **Load full event** and walk the pages | — |

## Pre-demo checklist (15 minutes before)
- [ ] `python -m unittest discover -s tests -t .` → OK
- [ ] `python run.py --host 0.0.0.0 --https --reset` is running
- [ ] Phone: open `https://<laptop-ip>:8000/field`, accept the certificate, allow the mic, send one test sentence
- [ ] Camera: `python cv/fall_detector.py --zone ZONE-B --location MAIN-WALKWAY`; scene empty for 3 s; one rehearsal fall detected
- [ ] Ops app: open `https://localhost:8000`, Arabic, full-screen; Presenter tools → **Reset event** (the decision log is kept; to empty rehearsal decisions: `run.py --reset --clear-decision-log`)
- [ ] Phone camera: Field reporting → Camera tab; allow the camera; phone on a stand; one rehearsal; keep a 15 s fall clip on the phone for *Analyse a video file* (clears the rehearsal data)
- [ ] Restart the camera agent after Reset (the YOLO model reloads in a few seconds)
- [ ] Laptop on power, notifications off, sleep off; phone brightness up, auto-lock off
- [ ] Backup: `docs/screenshots/` + a screen recording of one full run
