# Expo Requirements Matrix — EOIP

Source of official facts: `EXPO_2030_GUIDE_CLEAN_ALL.pdf` (Project Knowledge). The PDF is image-based; requirements were read from the page images.

Legend for the "Basis" column:
**OFFICIAL** = written in the Expo guide · **DERIVED** = our interpretation of an official line · **TEAM** = team/leader decision (not an Expo requirement)

## 1. Official facts extracted

| Item | Official text / fact | Basis |
|---|---|---|
| Track | المسار 3: تشغيل المعرض وسلامته وأمنه | OFFICIAL |
| Track description | إدارة الموقع يومًا بيوم، ورصد المشكلة والوصول إليها بشكل أسرع عبر الحشود والمواقع والأجهزة المتصلة | OFFICIAL |
| Track skills | علم البيانات · الدرونز · تطبيقات الويب · UX/UI | OFFICIAL |
| Challenge 3.6 | يجد مركز عمليات المعرض صعوبة في تمييز ما يستدعي تدخلًا فوريًا **أثناء فعالية مباشرة**، عندما ترِد مئات التنبيهات والرسائل اللاسلكية وطلبات الخدمة وإشعارات الأنظمة من جهات منفصلة | OFFICIAL |
| Named input types | تنبيهات · رسائل لاسلكية · طلبات خدمة · إشعارات أنظمة — من جهات منفصلة | OFFICIAL |
| Deliverable type | نموذج برمجي أولي: تطبيق ويب أو منصة أو نموذج ذكاء اصطناعي قابل للتشغيل والعرض | OFFICIAL |
| Mandatory for all teams | ملف المشروع · عرض تقديمي (5 دقائق) · رفع المخرجات على المنصة | OFFICIAL |
| Project file must contain | التحدي والمشكلة · وصف الفكرة والحل وآلية عمله · التقنيات والأدوات · الأثر المتوقع ومواءمته لمستهدفات إكسبو 2030 الرياض | OFFICIAL |
| Completeness | لا يُشترط اكتمال المنتج نهائيًا، بل وضوح الفكرة وإثبات جدواها عمليًا | OFFICIAL |
| Team | 1–5 trainees, one team leader; commit to one challenge for the whole period | OFFICIAL |
| Evaluation criteria & weights | **Not present** in the provided pages. The guide only states all output types are evaluated by the same criteria. **No weights are invented here.** | GAP |
| Real operational data / alert volumes | **Not provided.** All operational data in the MVP is synthetic. | GAP |

## 2. Requirement → feature → evidence

| # | Expo requirement | EOIP feature | Evidence in MVP | Demo moment | Responsible role | Status |
|---|---|---|---|---|---|---|
| R1 | Distinguish what needs **immediate intervention** (3.6) | Priority engine P1–P4 with explained reasons | `eoip/core/priority.py`, reasons shown per incident | Fire incident jumps to P1 with "confirmed by 3 independent sources" | Data/AI + Backend | Done |
| R2 | **Hundreds** of signals (3.6) | Synthetic live stream (~270 signals) + triage funnel | `data/demo_script.json`, funnel in top bar | Counter climbs to ~270 while incident list stays ~10 | Data + Frontend | Done |
| R3 | **Separate parties / sources** (3.6) | Normalization of 10 source systems into one Alert schema | `eoip/catalog.py`, `alerts` table | Signal stream shows mixed sources; incident shows source chips | DB + Backend | Done |
| R4 | Alerts (تنبيهات) | Sensor/AI alerts (fire panel, smoke detector, crowd sensors, CCTV-AI) | signal_type `alert` | Smoke detector + fire panel | Backend | Done |
| R5 | Radio messages (رسائل لاسلكية) | Phone simulates radio; Arabic-first voice → structured alert | `/field` page, `eoip/core/extract.py` | Presenter speaks a report in Arabic; it attaches to an incident | AI + Frontend | Done (STT = browser; see limitations) |
| R6 | Service requests (طلبات خدمة) | Service-desk requests (medical, cleaning, lost item…) | signal_type `service_request` | Medical request corroborates CV fall | Backend | Done |
| R7 | System notifications (إشعارات أنظمة) | BMS / IT / roster notifications, heartbeats, auto-clears | signal_type `system_notification` | Heartbeats filtered as noise | Backend | Done |
| R8 | **During a live event** (3.6) | Live playback engine, polling dashboard, incident escalation over time | `eoip/demo.py` | Fire escalates P2 → P1 in real time | Backend + Frontend | Done |
| R9 | Detect problems faster across crowds / sites / connected devices (Track 3) | Crowd + staffing signals per zone, CV camera as connected device | zones table, `cv/fall_detector.py` | Gate crowding incident + live camera fall | CV + Data | Done (CV = YOLO + posture rule) |
| R10 | Runnable prototype (deliverable) | Flask + SQLite web app, one command to run | `run.py`, README | Whole demo | DevOps | Done |
| R11 | Clear idea + practical feasibility | End-to-end pipeline on real code, human-in-the-loop, decision log | `decisions` table | Approve option → logged | All | Done |
| R12 | Project file content | README + docs map 1:1 to the 4 required items | `README.md`, `docs/final-team-leader-report.md` | — | Tech writer | Draft done; team to localize |
| R13 | 5-minute presentation | Demo script with timings + fallbacks | `docs/demo-script.md` | — | Demo lead | Done |
| R14 | Upload to platform | Repo zip + docs | — | — | Team leader | **Pending (team)** |

## 3. Team-level requirements (not from Expo)

| Requirement | Basis | Status |
|---|---|---|
| Arabic + English, RTL/LTR switch from day 1 | TEAM | Done (i18n JSON, `dir` switch) |
| Human makes the final decision | TEAM | Done (approve/reject, no auto-action) |
| AI only where it adds value | TEAM | Done (see architecture.md "AI vs rules") |
| Mock data clearly labelled | TEAM | Done ("Synthetic demo data" banner + `origin` field) |
| Django + SQLite | TEAM | **Changed → Flask + SQLite** (see decisions.md D-01) |

## 4. Open items for the Team Leader
1. Obtain the official evaluation criteria/weights from the organizers and add them as §5 here.
2. Confirm the final demo date (team context mentions both 7 and ~10 days).
