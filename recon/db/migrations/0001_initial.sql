-- 0001: Phase 1 tables (docs/BUILD_PLAN.md, Data model).
-- STRICT tables reject values of the wrong type; CHECKs keep the enums honest.
-- Timestamps are ISO 8601 UTC text, e.g. 2026-10-25T09:30:00+00:00.

CREATE TABLE rooms (
    id              INTEGER PRIMARY KEY,
    platform        TEXT    NOT NULL,
    path            TEXT    NOT NULL DEFAULT '',
    module          TEXT    NOT NULL DEFAULT '',
    name            TEXT    NOT NULL CHECK (length(name) > 0),
    task_count      INTEGER NOT NULL CHECK (task_count > 0),
    mode            TEXT    NOT NULL DEFAULT 'new' CHECK (mode IN ('new', 'from_memory')),
    status          TEXT    NOT NULL DEFAULT 'capturing'
                    CHECK (status IN ('capturing', 'queued', 'processing', 'in_review', 'done')),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    time_spent_s    INTEGER NOT NULL DEFAULT 0 CHECK (time_spent_s >= 0),
    last_task_index INTEGER NOT NULL DEFAULT 1 CHECK (last_task_index >= 1)
) STRICT;

CREATE INDEX rooms_by_updated ON rooms (updated_at DESC);

CREATE TABLE tasks (
    id          INTEGER PRIMARY KEY,
    room_id     INTEGER NOT NULL REFERENCES rooms (id) ON DELETE CASCADE,
    task_index  INTEGER NOT NULL CHECK (task_index >= 1),
    title       TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'skipped')),
    UNIQUE (room_id, task_index)
) STRICT;

CREATE TABLE blocks (
    id          INTEGER PRIMARY KEY,
    task_id     INTEGER NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    type        TEXT    NOT NULL CHECK (type IN (
                    'key_idea', 'command', 'table', 'screenshot',
                    'question', 'confused', 'room_question', 'voice')),
    position    INTEGER NOT NULL CHECK (position >= 0),
    content     TEXT    NOT NULL CHECK (json_valid(content)),
    pass        TEXT    NOT NULL DEFAULT 'fill' CHECK (pass IN ('recall', 'fill')),
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
) STRICT;

CREATE INDEX blocks_by_task ON blocks (task_id, position);

CREATE TABLE sessions (
    id            INTEGER PRIMARY KEY,
    room_id       INTEGER NOT NULL REFERENCES rooms (id) ON DELETE CASCADE,
    started_at    TEXT    NOT NULL,
    ended_at      TEXT,
    focus_minutes INTEGER CHECK (focus_minutes IS NULL OR focus_minutes > 0)
) STRICT;

CREATE TABLE settings_kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

CREATE TABLE undo_log (
    id         INTEGER PRIMARY KEY,
    entity     TEXT    NOT NULL,
    entity_id  INTEGER NOT NULL,
    before     TEXT    NOT NULL CHECK (json_valid(before)),
    created_at TEXT    NOT NULL
) STRICT;
