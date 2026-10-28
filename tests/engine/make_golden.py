"""Rewrite the golden vault notes from the recorded replies.

Run after changing a template or re-recording, then read every diff before
committing: `uv run python -m tests.engine.make_golden`.
"""

import shutil

from recon.engine.extract import check
from recon.engine.notes import render_room
from tests.engine.pipeline import capture_of, recorded
from tests.engine.test_notes import GOLDEN, ROOMS

if __name__ == "__main__":
    for room in ROOMS:
        folder = GOLDEN / room
        shutil.rmtree(folder, ignore_errors=True)
        capture = capture_of(room)
        for note in render_room(capture, check(recorded(room), capture)).notes:
            path = folder / note.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(note.text, encoding="utf-8")
