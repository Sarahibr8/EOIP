-- EOIP schema v4 (SQLite, PRAGMA user_version = 4). Django edition: employee accounts and sessions
-- are Django's own auth tables (auth_user, django_session); decisions.employee_id stores auth_user.id.
-- Mirrors docs/data-contract.md.
-- Text enums are validated in the application layer (eoip/catalog.py) and by CHECK constraints here.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS zones (
    id              TEXT PRIMARY KEY,                 -- ZONE-A | ZONE-B | ZONE-C
    name_ar         TEXT NOT NULL,
    name_en         TEXT NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('gate','hall','plaza','food','transport')),
    criticality     INTEGER NOT NULL DEFAULT 1 CHECK (criticality BETWEEN 1 AND 3),
    capacity        INTEGER NOT NULL CHECK (capacity > 0),
    occupancy       INTEGER NOT NULL DEFAULT 0 CHECK (occupancy >= 0),
    inflow_per_min  REAL    NOT NULL DEFAULT 0,       -- people entering per minute
    outflow_per_min REAL    NOT NULL DEFAULT 0,       -- people leaving / processed per minute
    staff_on_duty   INTEGER NOT NULL DEFAULT 0,
    staff_required  INTEGER NOT NULL DEFAULT 0,
    neighbors       TEXT    NOT NULL DEFAULT '[]',    -- JSON array of zone ids
    map_x REAL, map_y REAL, map_w REAL, map_h REAL    -- schematic map geometry (illustrative)
);

-- Six operational locations (illustrative demo names), each inside one zone.
CREATE TABLE IF NOT EXISTS locations (
    id       TEXT PRIMARY KEY,                        -- e.g. FOOD-COURT
    zone_id  TEXT NOT NULL REFERENCES zones(id),
    name_ar  TEXT NOT NULL,
    name_en  TEXT NOT NULL,
    map_x REAL, map_y REAL
);

CREATE TABLE IF NOT EXISTS incidents (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    code             TEXT UNIQUE NOT NULL,            -- INC-0001
    type             TEXT NOT NULL,                   -- fire | medical | crowd_pressure | facility | it_system
    kind             TEXT NOT NULL CHECK (kind IN ('emergency','operational','routine')),
    zone_id          TEXT NOT NULL REFERENCES zones(id),
    location_id      TEXT REFERENCES locations(id),   -- NULL = location not stated
    status           TEXT NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open','action_approved','resolved','dismissed')),
    priority         TEXT NOT NULL DEFAULT 'P4' CHECK (priority IN ('P1','P2','P3','P4')),
    priority_score   INTEGER NOT NULL DEFAULT 0,
    priority_reasons TEXT NOT NULL DEFAULT '[]',      -- JSON [{key, params}]
    confidence       REAL NOT NULL DEFAULT 0,
    alert_count      INTEGER NOT NULL DEFAULT 0,      -- includes duplicates
    source_count     INTEGER NOT NULL DEFAULT 0,      -- distinct independent source systems
    opened_at        TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    escalated_at     TEXT,                            -- last time priority went up
    closed_at        TEXT
);
CREATE INDEX IF NOT EXISTS ix_incidents_open ON incidents(status, type, zone_id);

CREATE TABLE IF NOT EXISTS alerts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    external_ref     TEXT,                            -- id in the source system
    signal_type      TEXT NOT NULL CHECK (signal_type IN ('alert','radio_message','service_request','system_notification')),
    source_system    TEXT NOT NULL,                   -- see catalog.SOURCE_SYSTEMS
    category         TEXT NOT NULL,                   -- see catalog.CATEGORIES
    zone_id          TEXT REFERENCES zones(id),       -- NULL only if extraction failed (needs review)
    location_id      TEXT REFERENCES locations(id),   -- one of the six locations, NULL = unknown / other
    location_detail  TEXT,                            -- free text (e.g. "other location" details, device position)
    raw_text         TEXT,                            -- radio transcript / request text
    language         TEXT CHECK (language IN ('ar','en') OR language IS NULL),
    severity_hint    INTEGER NOT NULL DEFAULT 1 CHECK (severity_hint BETWEEN 1 AND 5),
    confidence       REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    payload          TEXT NOT NULL DEFAULT '{}',      -- JSON, source-specific fields
    origin           TEXT NOT NULL CHECK (origin IN ('mock','live_cv','video_file','replay_cv','voice','text')),
    occurred_at      TEXT NOT NULL,
    received_at      TEXT NOT NULL,
    disposition      TEXT NOT NULL CHECK (disposition IN ('correlated','duplicate','noise','routine','needs_review')),
    duplicate_of     INTEGER REFERENCES alerts(id),
    incident_id      INTEGER REFERENCES incidents(id),
    correlation      TEXT                             -- JSON: why this alert was linked / not linked (rules_v2)
);
CREATE INDEX IF NOT EXISTS ix_alerts_incident ON alerts(incident_id);
CREATE INDEX IF NOT EXISTS ix_alerts_dup ON alerts(source_system, category, zone_id, received_at);

CREATE TABLE IF NOT EXISTS recommendations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id  INTEGER NOT NULL REFERENCES incidents(id),
    code         TEXT NOT NULL,                       -- FIRE-01 | MED-01 | redeploy_staff | divert_inflow | meter_entry | route_team
    rec_type     TEXT NOT NULL CHECK (rec_type IN ('playbook','option','route')),
    rank         INTEGER NOT NULL DEFAULT 1,
    params       TEXT NOT NULL DEFAULT '{}',          -- JSON: steps / target zone / staff moved …
    simulation   TEXT,                                -- JSON projection, NULL for playbooks
    status       TEXT NOT NULL DEFAULT 'proposed'
                 CHECK (status IN ('proposed','approved','rejected','superseded')),
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_recs_incident ON recommendations(incident_id, status);

-- Permanent decision log. Survives demo resets: operational rows of a previous run are
-- deleted, so the decision keeps a self-contained `snapshot` (incident code, zone/location
-- names, chosen option, teams assigned, simulation result) taken at decision time.
CREATE TABLE IF NOT EXISTS decisions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            INTEGER NOT NULL DEFAULT 1,     -- demo/event run (demo_state.run_id at decision time)
    incident_id       INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    recommendation_id INTEGER REFERENCES recommendations(id) ON DELETE SET NULL,
    action            TEXT NOT NULL CHECK (action IN ('approve','reject','resolve','dismiss')),
    operator          TEXT NOT NULL CHECK (length(trim(operator)) > 0),   -- verified employee display name for new rows
    employee_id       INTEGER,                        -- auth_user.id of the verified employee
    employee_number   TEXT,
    note              TEXT,
    priority_at_decision TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    snapshot          TEXT NOT NULL DEFAULT '{}'      -- JSON, see docs/data-contract.md
);
CREATE INDEX IF NOT EXISTS ix_decisions_incident ON decisions(incident_id);

-- Escalations (core/escalation.py): a case that waited longer than its response time leaves the duty
-- officer and goes to the managers above (L1 -> L2 -> L3). Permanent like the decision log.
CREATE TABLE IF NOT EXISTS escalations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL DEFAULT 1,
    incident_id  INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    level        INTEGER NOT NULL CHECK (level BETWEEN 1 AND 3),
    priority     TEXT NOT NULL,
    created_at   TEXT NOT NULL,      -- when the response time ran out (escalated to L1)
    updated_at   TEXT NOT NULL,      -- when the current level was reached
    snapshot     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_escalations_incident ON escalations(incident_id);


-- Response teams. SYNTHETIC demo roster (data/teams.json), not real Expo staffing.
CREATE TABLE IF NOT EXISTS teams (
    id           TEXT PRIMARY KEY,                    -- MED-1
    name_ar      TEXT NOT NULL,
    name_en      TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('fire','medical','steward','security','facilities','it')),
    base_zone    TEXT NOT NULL REFERENCES zones(id),
    base_location TEXT REFERENCES locations(id),
    members      INTEGER NOT NULL DEFAULT 2,
    status       TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','assigned')),
    incident_id  INTEGER REFERENCES incidents(id),
    assigned_at  TEXT
);

CREATE TABLE IF NOT EXISTS demo_state (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    running     INTEGER NOT NULL DEFAULT 0,
    started_at  REAL,                                 -- unix seconds
    speed       REAL NOT NULL DEFAULT 1.0,
    cursor      INTEGER NOT NULL DEFAULT 0,           -- index of next scripted signal
    run_id      INTEGER NOT NULL DEFAULT 1            -- incremented by every reset
);
INSERT OR IGNORE INTO demo_state (id) VALUES (1);
