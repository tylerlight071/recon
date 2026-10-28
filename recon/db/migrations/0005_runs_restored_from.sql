-- Task 2.8: a restore from History is recorded as a run of its own, so History
-- can show it as a restore and it can be undone the same way (restoring it).
ALTER TABLE runs ADD COLUMN restored_from TEXT CHECK (restored_from IS NULL OR length(restored_from) BETWEEN 1 AND 64);
