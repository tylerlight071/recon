-- Task 1.12: time spent per task (the room's total is rooms.time_spent_s).
ALTER TABLE tasks ADD COLUMN time_spent_s INTEGER NOT NULL DEFAULT 0 CHECK (time_spent_s >= 0);
