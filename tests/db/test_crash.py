"""Phase 1 acceptance: killing the process mid-typing loses no more than the last second.

A child process types into a block through the real AutosaveQueue and
database, printing each edit's number and time. The test kills it with
SIGKILL, reopens the database, and checks that everything typed more than
a second before the kill was saved, and that the file is intact.
"""

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LOSS_BUDGET_S = 1.0

CHILD = """
import sys, time
from pathlib import Path
from recon.db.autosave import AutosaveQueue
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.models import BlockContent, NewRoom
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository

db = Database.open(Path(sys.argv[1]))
migrate(db)
rooms, tasks, blocks = RoomRepository(db), TaskRepository(db), BlockRepository(db)
task = tasks.for_room(rooms.create(NewRoom(name="Crash", task_count=1)).id)[0]
block = blocks.ensure_starter_block(task.id)
queue = AutosaveQueue(blocks.update_content)
print("ready", block.id, flush=True)
n = 0
while True:
    n += 1
    queue.put(block.id, BlockContent(text=str(n)))
    print(n, time.monotonic(), flush=True)
    time.sleep(0.02)
"""


@pytest.mark.slow
def test_kill_9_mid_typing_loses_at_most_a_second(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    child = subprocess.Popen(  # noqa: S603 - this interpreter running the inline child above
        [sys.executable, "-c", CHILD, str(db_path)],
        cwd=REPO,
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )
    assert child.stdout is not None
    header = child.stdout.readline().split()
    assert header[0] == "ready"
    block_id = int(header[1])

    time.sleep(1.5)
    killed_at = time.monotonic()
    child.send_signal(signal.SIGKILL)
    child.wait(timeout=5)
    typed = [(int(n), float(t)) for n, t in (line.split() for line in child.stdout)]

    conn = sqlite3.connect(db_path)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    saved_text = conn.execute("SELECT content FROM blocks WHERE id = ?", (block_id,)).fetchone()[0]
    conn.close()
    saved = int(json.loads(saved_text)["text"] or 0)

    must_have = max(n for n, t in typed if t <= killed_at - LOSS_BUDGET_S)
    assert child.returncode == -signal.SIGKILL
    assert len(typed) > 40  # it really was typing
    last_typed_at = typed[-1][1]
    saved_at = next(t for n, t in typed if n == saved)
    print(f"lost {last_typed_at - saved_at:.2f} s of typing (budget {LOSS_BUDGET_S} s)")  # noqa: T201
    assert saved >= must_have, (
        f"saved edit {saved}, but {must_have} was typed over a second earlier"
    )
