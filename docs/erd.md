# مخطط قاعدة البيانات (ERD) · EOIP

قاعدة البيانات **SQLite** (وضع WAL)، والمخطط الكامل في [`eoip/schema.sql`](../eoip/schema.sql). حسابات الموظفين والجلسات من جداول Django الأساسية (`auth_user`, `django_session`).

![ERD](erd.png)

الصورة أعلاه هي المخطط الكامل (كل أعمدة `schema.sql`، مطابق للنسخة النهائية). وهذه نسخة مختصرة بصيغة Mermaid يرسمها GitHub تلقائيًا:

```mermaid
erDiagram
    ZONES ||--o{ LOCATIONS : "contains"
    ZONES ||--o{ INCIDENTS : "happens in"
    LOCATIONS |o--o{ INCIDENTS : "at"
    ZONES |o--o{ ALERTS : "reported in"
    LOCATIONS |o--o{ ALERTS : "at"
    INCIDENTS |o--o{ ALERTS : "groups"
    ALERTS |o--o{ ALERTS : "duplicate of"
    INCIDENTS ||--o{ RECOMMENDATIONS : "gets"
    INCIDENTS |o--o{ DECISIONS : "decided by"
    RECOMMENDATIONS |o--o{ DECISIONS : "chosen in"
    AUTH_USER |o..o{ DECISIONS : "made by"
    INCIDENTS |o--o| ESCALATIONS : "escalated to L1-L3"
    ZONES ||--o{ TEAMS : "based in"
    LOCATIONS |o--o{ TEAMS : "based at"
    INCIDENTS |o--o{ TEAMS : "assigned to"

    ZONES {
        text id PK "ZONE-A / B / C"
        text name_ar
        text name_en
        text kind "gate, hall, plaza"
        int criticality "1-3"
        int capacity
        int occupancy
        real inflow_per_min
        real outflow_per_min
        int staff_on_duty
        int staff_required
    }
    LOCATIONS {
        text id PK "FOOD-COURT ..."
        text zone_id FK
        text name_ar
        text name_en
    }
    ALERTS {
        int id PK
        text signal_type "alert, radio_message"
        text source_system "cctv_ai, radio"
        text category "smoke, person_down ..."
        text zone_id FK
        text location_id FK
        text raw_text "radio transcript"
        real confidence "0-1"
        text origin "live_cv, video_file, voice"
        text disposition "correlated, duplicate, noise"
        int duplicate_of FK
        int incident_id FK
        text received_at
    }
    INCIDENTS {
        int id PK
        text code UK "INC-0001"
        text type "fire, medical, crowd"
        text kind "emergency, operational"
        text zone_id FK
        text location_id FK
        text status "open, approved, resolved"
        text priority "P1-P4"
        int priority_score
        text priority_reasons "JSON why"
        int source_count
        text opened_at
    }
    RECOMMENDATIONS {
        int id PK
        int incident_id FK
        text code "FIRE-01, divert_inflow"
        text rec_type "playbook, option, route"
        int rank "1-3"
        text simulation "JSON 15-min impact"
        text status "proposed, approved"
    }
    DECISIONS {
        int id PK
        int incident_id FK
        int recommendation_id FK
        int employee_id "auth_user.id"
        text action "approve, reject, resolve"
        text operator
        text priority_at_decision
        text created_at
        text snapshot "JSON, permanent log"
    }
    ESCALATIONS {
        int id PK
        int incident_id FK
        int level "1-3 = L1-L3"
        text priority
        text created_at
        text snapshot "JSON"
    }
    TEAMS {
        text id PK "FIRE-1, MED-1"
        text kind "fire, medical, steward"
        text base_zone FK
        text base_location FK
        text status "available, assigned"
        int incident_id FK
    }
    AUTH_USER {
        int id PK
        text username UK "employee number"
        text first_name "display name"
        text password "scrypt hash"
    }
```

## الجداول

| الجدول | الدور | أهم القيود |
|---|---|---|
| `zones` | مناطق المعرض (A/B/C): السعة، الإشغال الحالي، التدفق، الموظفون | `CHECK` على السعة والإشغال والأهمية (1–3) |
| `locations` | المواقع داخل كل منطقة (منطقة المطاعم، البوابة الرئيسية…) | `zone_id → zones` |
| `alerts` | **كل بلاغ وارد** من الكاميرا أو اللاسلكي بصيغة موحدة، مع نتيجة الفرز (`disposition`) وسبب الربط (`correlation`) | `CHECK` على النوع والمصدر والثقة (0–1)، `duplicate_of → alerts` (مكرر)، `incident_id → incidents` |
| `incidents` | **الحالة** التي يراها المسؤول: تجمع عدة بلاغات عن حدث واحد، مع الأولوية وسببها | `code` فريد، `CHECK` على الحالة والأولوية (P1–P4) |
| `recommendations` | خيارات القرار لكل حالة: خطة جاهزة أو خيار تشغيلي مع **محاكاة 15 دقيقة** | `incident_id → incidents`، `CHECK` على النوع والحالة |
| `decisions` | **سجل القرارات الدائم**: من قرّر، ماذا، متى، مع لقطة (`snapshot`) تبقى بعد إعادة التشغيل | `CHECK` على الإجراء، `employee_id` = رقم المستخدم في `auth_user` |
| `escalations` | التصعيد عند تأخر القرار: المستوى L1–L3 ووقت الوصول إليه (دائم) | `CHECK (level BETWEEN 1 AND 3)` |
| `teams` | فرق الاستجابة (إطفاء، طبي، تنظيم، أمن) وحالة التكليف | `base_zone → zones`، `incident_id → incidents` |
| `demo_state` | حالة الفعالية التجريبية (صف واحد) ورقم الجولة `run_id` | `CHECK (id = 1)` |
| `auth_user` | حسابات الموظفين (الرقم الوظيفي = اسم المستخدم)، كلمات مرور مشفرة scrypt | جدول Django |

## العلاقات

- منطقة واحدة ← عدة مواقع، وعدة حالات، وعدة بلاغات، وعدة فرق.
- **حالة واحدة ← عدة بلاغات** (هذا جوهر الحل: مئات البلاغات تصبح حالات قليلة).
- بلاغ ← قد يكون **مكررًا** لبلاغ سابق (علاقة ذاتية `duplicate_of`).
- حالة ← عدة توصيات، وعدة قرارات، وتصعيد واحد كحد أقصى.
- قرار ← مرتبط بتوصية (الخيار المعتمد) وبالموظف الذي اتخذه.

## الفهارس

`ix_alerts_dup (source_system, category, zone_id, received_at)` لكشف المكرر بسرعة · `ix_alerts_incident` · `ix_incidents_open (status, type, zone_id)` لإيجاد الحالة المفتوحة للربط · `ix_recs_incident` · `ix_decisions_incident` · `ix_escalations_incident`.
