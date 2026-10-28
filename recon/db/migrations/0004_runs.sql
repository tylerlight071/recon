-- Task 2.4: one row per processing run, so Apply is recorded and Library's
-- History (task 2.8) can list runs and restore their backups.
CREATE TABLE runs (
    id          TEXT    PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 64),
    room_id     INTEGER NOT NULL REFERENCES rooms (id) ON DELETE CASCADE,
    status      TEXT    NOT NULL DEFAULT 'staged'
                CHECK (status IN ('staged', 'applied', 'discarded')),
    created_at  TEXT    NOT NULL,
    finished_at TEXT,
    written     INTEGER NOT NULL DEFAULT 0 CHECK (written >= 0),
    backed_up   INTEGER NOT NULL DEFAULT 0 CHECK (backed_up >= 0)
) STRICT;

CREATE INDEX runs_by_room ON runs (room_id, created_at DESC);
