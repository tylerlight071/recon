-- Audit F-04: block IDs must never be reused, or Undo can land on the wrong
-- block. INTEGER PRIMARY KEY hands out a deleted maximum again; AUTOINCREMENT
-- never does. SQLite can't add AUTOINCREMENT in place, so rebuild the table,
-- keeping every row and ID, then start the counter past any ID the undo log
-- still remembers (a deleted block that Undo may bring back).
CREATE TABLE blocks_new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
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

INSERT INTO blocks_new (id, task_id, type, position, content, pass, created_at, updated_at)
    SELECT id, task_id, type, position, content, pass, created_at, updated_at FROM blocks;

DROP TABLE blocks;
ALTER TABLE blocks_new RENAME TO blocks;
CREATE INDEX blocks_by_task ON blocks (task_id, position);

-- The rename carried the counter row across; an empty table has none yet.
INSERT INTO sqlite_sequence (name, seq)
    SELECT 'blocks', 0 WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'blocks');
UPDATE sqlite_sequence SET seq = max(
    seq,
    coalesce((SELECT max(id) FROM blocks), 0),
    coalesce((SELECT max(entity_id) FROM undo_log), 0)
) WHERE name = 'blocks';
