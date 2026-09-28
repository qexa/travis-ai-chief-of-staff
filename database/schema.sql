-- ─────────────────────────────────────────────────────────────────────────
-- Travis Core schema. Written for SQLite; runs on Postgres with the notes
-- at the bottom. Timestamps are ISO-8601 strings with timezone offset.
-- ─────────────────────────────────────────────────────────────────────────

-- People TRAVIS knows. VIPs live in the profile YAML; everyone else lands here
-- automatically the first time they call.
CREATE TABLE IF NOT EXISTS contacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    phone         TEXT UNIQUE,
    email         TEXT,
    company       TEXT,
    tier          TEXT NOT NULL DEFAULT 'known',   -- vip | inner_circle | known | new_opportunity | vendor | spam
    relationship  TEXT,
    notes         TEXT,
    call_count    INTEGER NOT NULL DEFAULT 0,
    last_call_at  TEXT,
    created_at    TEXT NOT NULL
);

-- One row per phone call.
CREATE TABLE IF NOT EXISTS calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id       TEXT UNIQUE,                      -- voice platform call id
    caller_phone  TEXT,
    caller_name   TEXT,
    company       TEXT,
    tier          TEXT,
    reason        TEXT,
    priority      TEXT,                             -- critical | high | normal | low
    outcome       TEXT,                             -- transferred | booked | rescheduled | message | screened | blocked | answered
    summary       TEXT,
    transcript    TEXT,
    recording_url TEXT,
    ended_reason  TEXT,
    started_at    TEXT NOT NULL,
    ended_at      TEXT
);

-- Messages taken for the executive or the team.
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id         TEXT,
    for_key         TEXT NOT NULL DEFAULT 'exec',   -- exec | team member key
    from_name       TEXT,
    from_phone      TEXT,
    company         TEXT,
    reason          TEXT,
    details         TEXT,
    priority        TEXT NOT NULL DEFAULT 'normal',
    callback_window TEXT,
    status          TEXT NOT NULL DEFAULT 'new',    -- new | delivered | handled
    created_at      TEXT NOT NULL
);

-- Long-term memory: facts the exec told TRAVIS, and facts learned on calls.
CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject     TEXT NOT NULL,                       -- 'exec' or a contact name / topic
    fact        TEXT NOT NULL,
    source      TEXT NOT NULL,                       -- exec_sms | call | onboarding
    visibility  TEXT NOT NULL DEFAULT 'private',     -- private (exec only) | callers (safe to use on calls)
    created_at  TEXT NOT NULL
);

-- Follow-ups with an owner and a due date. "No slipping."
CREATE TABLE IF NOT EXISTS followups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    owner_key       TEXT NOT NULL DEFAULT 'exec',
    due_at          TEXT,
    related_contact TEXT,
    related_call_id TEXT,
    status          TEXT NOT NULL DEFAULT 'open',   -- open | done
    created_at      TEXT NOT NULL
);

-- Audit log of everything TRAVIS changed. Feeds "Actions I took" in the briefing.
CREATE TABLE IF NOT EXISTS actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    actor       TEXT NOT NULL,                       -- travis_voice | travis_sms | exec | system
    action      TEXT NOT NULL,                       -- booked | rescheduled | cancelled | blocked_time | transferred | ...
    detail      TEXT NOT NULL,
    call_id     TEXT,
    created_at  TEXT NOT NULL
);

-- Every outbound SMS / email (also the demo-mode "sent" box).
CREATE TABLE IF NOT EXISTS outbox (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel     TEXT NOT NULL,                       -- sms | email
    recipient   TEXT NOT NULL,
    subject     TEXT,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL,                       -- sent | demo | failed
    error       TEXT,
    created_at  TEXT NOT NULL
);

-- Demo calendar (used when CALENDAR_BACKEND=demo).
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    start       TEXT NOT NULL,
    end         TEXT NOT NULL,
    attendees   TEXT,                                -- JSON list of {name,email,phone}
    location    TEXT,
    notes       TEXT,
    kind        TEXT NOT NULL DEFAULT 'meeting',     -- meeting | travel | focus | personal
    status      TEXT NOT NULL DEFAULT 'confirmed'
);

-- Key/value state (e.g. last briefing time).
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_calls_started   ON calls(started_at);
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
CREATE INDEX IF NOT EXISTS idx_followups_due   ON followups(status, due_at);
CREATE INDEX IF NOT EXISTS idx_events_start    ON events(start);
CREATE INDEX IF NOT EXISTS idx_memories_subj   ON memories(subject);

-- Postgres notes:
--   INTEGER PRIMARY KEY AUTOINCREMENT  ->  BIGSERIAL PRIMARY KEY
--   TEXT timestamps                    ->  TIMESTAMPTZ
--   attendees TEXT (JSON)              ->  JSONB
--   Add row-level security per tenant_id if you host many executives in one DB.
