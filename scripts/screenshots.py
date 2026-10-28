"""Render every screen headless into a folder (CLAUDE.md, Testing: screenshots at gates).

Builds the app exactly as `python -m recon` does (`create_bridges`), against a
throwaway data folder seeded with an invented room, so nothing of the user's is
read or written. Run: `uv run python -m scripts.screenshots tests/screenshots`.
"""

import os
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import NoReturn

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow

from recon.__main__ import create_bridges, open_database, processing_for
from recon.app import create_application, create_engine, load_windows, root_window
from recon.bridge.library import LibraryBridge
from recon.bridge.navigation import NavigationBridge
from recon.bridge.review import ReviewBridge
from recon.bridge.session import RoomSessionBridge
from recon.bridge.settings import SettingsBridge
from recon.config import Settings
from recon.db.connection import Database
from recon.db.models import BlockContent, NewRoom
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository
from recon.engine.capture import capture_room
from recon.engine.extract import check
from recon.engine.notes import render_room
from recon.engine.schemas import RoomExtract
from recon.paths import AppPaths


def fail(reason: str) -> NoReturn:
    """Stop with a one-line reason."""
    raise SystemExit("screenshots: " + reason)


def typed[T](bridges: dict[str, QObject], name: str, kind: type[T]) -> T:
    """The bridge called `name`, as its own type."""
    bridge = bridges[name]
    if not isinstance(bridge, kind):
        fail(f"{name} isn't a {kind.__name__}")
    return bridge


def wait(ms: int) -> None:
    """Let Qt run for `ms` milliseconds (animations, bindings, layout)."""
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        QCoreApplication.processEvents()


def seed(paths: AppPaths) -> int:
    """An invented room, part way through, with one of each written block. Returns its ID."""
    db = open_database(paths)
    if db is None:
        fail("couldn't open the scratch database")
    rooms, tasks, blocks = RoomRepository(db), TaskRepository(db), BlockRepository(db)
    done = rooms.create(
        NewRoom(name="Linux Basics", task_count=4, path="Pre Security", module="Linux")
    )
    rooms.update_progress(done.id, status="done")
    room = rooms.create(
        NewRoom(
            name="DNS in Detail", task_count=7, path="Pre Security", module="Network Fundamentals"
        )
    )
    all_tasks = tasks.for_room(room.id)
    for task in all_tasks[:2]:
        tasks.set_status(task.id, "done")
    third = all_tasks[2]
    tasks.set_title(third.id, "Record types")
    rooms.update_progress(room.id, last_task_index=3)
    key = blocks.ensure_starter_block(third.id)
    blocks.update_content(
        key.id, BlockContent(text="Each record type answers a different question.")
    )
    blocks.add(third.id, "command", BlockContent(text="dig example.com MX  # who handles mail"))
    blocks.add(
        third.id, "table", BlockContent(text="Type, Holds\nA, IPv4 address\nMX, mail server")
    )
    blocks.add(
        third.id, "room_question", BlockContent(text="Which record holds mail?", answer="MX")
    )
    db.close()
    return room.id


def stage_review(paths: AppPaths, settings: Settings, db: Database, room_id: int) -> None:
    """Stage notes for the seeded room from an invented extract, as processing would."""
    rooms, tasks, blocks = RoomRepository(db), TaskRepository(db), BlockRepository(db)
    room = rooms.get(room_id)
    if room is None:
        fail("the seeded room is missing")
    rows = [(task, blocks.for_task(task.id)) for task in tasks.for_room(room_id)]
    capture = capture_room(room, rows, date(2026, 10, 28))
    key = next(b for b in capture.blocks() if b.type == "key_idea")
    invented = RoomExtract.model_validate(
        {
            "summary": [
                "DNS turns names into addresses.",
                "Each record type answers a different question.",
                "dig shows the records for a name.",
            ],
            "tasks": [{"task": 3, "points": [{"block": key.id, "text": key.text}]}],
            "concepts": [{"name": "Record type", "aliases": ["record"], "topic": "DNS"}],
            "tools": [{"name": "dig", "purpose": "Looks up DNS records."}],
            "answers": [],
        }
    )
    processing = processing_for(paths, settings, db)
    run = processing.runs.start()
    processing.stage_room(room_id, render_room(capture, check(invented, capture)), run)


def grab_after_finishing(
    bridges: dict[str, QObject], main_window: QQuickWindow, out: Path, room_id: int
) -> None:
    """The review, done and Library screens for a staged room (Apply goes to the scratch vault)."""
    navigation = typed(bridges, "Navigation", NavigationBridge)
    review = typed(bridges, "ReviewModel", ReviewBridge)
    review.open(room_id)
    wait_for(lambda: navigation.property("currentScreen") == "review")
    grab(main_window, out, "review")
    review.apply()
    wait_for(lambda: navigation.property("currentScreen") == "done")
    grab(main_window, out, "done")
    navigation.open("library")
    library = typed(bridges, "LibraryModel", LibraryBridge)
    wait_for(lambda: len(library.property("history")) > 0)
    grab(main_window, out, "library")


def wait_for(condition: Callable[[], bool], timeout_ms: int = 3000) -> None:
    """Process events until `condition` holds (the review loads on a worker)."""
    timer = QElapsedTimer()
    timer.start()
    while not condition():
        if timer.elapsed() > timeout_ms:
            fail("the screen didn't open in time")
        QCoreApplication.processEvents()


def grab(window: QQuickWindow, out: Path, name: str) -> None:
    """Save a window's current frame as `name`.png."""
    wait(300)
    window.grabWindow().save(str(out / f"{name}.png"))


def main(out: Path) -> list[str]:
    """Render the screens into `out`; returns the file names written."""
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        paths = AppPaths(
            data=Path(scratch) / "data",
            config=Path(scratch) / "config",
            cache=Path(scratch) / "cache",
        )
        paths.ensure()
        room_id = seed(paths)
        db = open_database(paths)
        if db is None:
            fail("couldn't reopen the scratch database")
        existing = QGuiApplication.instance()
        app = (
            existing if isinstance(existing, QGuiApplication) else create_application(sys.argv[:1])
        )
        # A throwaway vault too: start-up creates the vault (task 2.1).
        initial = Settings(kwin_pinning="off", vault_path=str(Path(scratch) / "vault"))
        bridges, _pinning = create_bridges(app, paths, initial, db)
        qml = create_engine(bridges)
        main_window, panel = (
            (root_window(qml.engine, 0), root_window(qml.engine, 1))
            if load_windows(qml.engine)
            else (None, None)
        )
        if main_window is None or panel is None:
            fail("the windows didn't load; run the UI tests for the QML errors")
        navigation = typed(bridges, "Navigation", NavigationBridge)
        settings = typed(bridges, "AppSettings", SettingsBridge)
        session = typed(bridges, "RoomSession", RoomSessionBridge)

        grab(main_window, out, "home")
        navigation.open("start")
        grab(main_window, out, "start")
        session.open(room_id)
        navigation.showPanel()
        panel.setHeight(900)
        grab(panel, out, "panel-session")
        navigation.open("settings")
        main_window.setHeight(900)
        grab(main_window, out, "settings")
        settings.setProperty("accent", "cyan")
        grab(main_window, out, "settings-cyan")
        settings.setProperty("accent", "violet")
        stage_review(paths, initial, db, room_id)
        grab_after_finishing(bridges, main_window, out, room_id)
        session.finishRequested.emit(room_id)
        grab(panel, out, "panel-finish")

        app.aboutToQuit.emit()  # save and stop the autosave thread, as at a real quit
        del qml
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        for bridge in bridges.values():
            if isinstance(bridge, QObject):
                bridge.deleteLater()
        db.close()
    return sorted(p.name for p in out.glob("*.png"))


if __name__ == "__main__":
    for name in main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/screenshots")):
        print(name)
