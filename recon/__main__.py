"""Start Recon: `uv run python -m recon` (normally through packaging/recon-launch)."""

import argparse
import datetime as dt
import logging
import os
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Property, QLockFile, QObject
from PySide6.QtGui import QGuiApplication

from recon.app import (
    GALLERY_QML,
    STARTUP_PROBLEM_QML,
    create_application,
    create_engine,
    load_qml,
    load_windows,
)
from recon.bridge.editors import EditorsBridge
from recon.bridge.finish import FinishBridge
from recon.bridge.flags import FlagGuard
from recon.bridge.flow import connect_finish, connect_room_flow
from recon.bridge.focus import FocusBridge
from recon.bridge.home import HomeBridge
from recon.bridge.models import ModelsBridge
from recon.bridge.navigation import NavigationBridge
from recon.bridge.pinning import PinningBridge
from recon.bridge.session import RoomSessionBridge
from recon.bridge.settings import SettingsBridge
from recon.bridge.start import StartRoomBridge
from recon.bridge.vault import VaultBridge
from recon.bridge.workers import SerialWorker, drain_global_pool, thread_pool_submit
from recon.config import Settings, load_settings, save_settings, vault_folder
from recon.db import backup
from recon.db.autosave import AutosaveQueue
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.repositories import (
    BlockRepository,
    RoomRepository,
    TaskRepository,
    UndoRepository,
    utc_now,
)
from recon.db.runs import RunRepository
from recon.errors import (
    AlreadyRunningError,
    AutosaveFailedError,
    DatabaseTooNewError,
    DatabaseUnreadableError,
    DataFolderUnusableError,
    ReconError,
    StorageError,
)
from recon.logging_setup import Safe, configure_logging
from recon.paths import AppPaths, ensure_private_dir
from recon.processing import Processing
from recon.services.chime import Chime
from recon.services.kwin import KWinPinning, run_command
from recon.services.ollama import CHECK_TIMEOUT_S, OllamaService, make_client
from recon.services.open_url import open_folder
from recon.services.runs import RunStore

_log = logging.getLogger(__name__)

LOCK_FILE = "recon.lock"
"""Held while Recon runs, in the data folder: a second copy finds it and stops."""


def build_parser() -> argparse.ArgumentParser:
    """Command-line options."""
    parser = argparse.ArgumentParser(prog="recon", description="Recon study companion.")
    parser.add_argument(
        "--gallery", action="store_true", help="show the developer component gallery"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run Recon.

    Anything that stops start-up is shown in a small window, not just printed, so a
    launch from the app menu never fails silently (audit F-12).

    Args:
        argv: Arguments without the program name; defaults to sys.argv[1:].

    Returns:
        The process exit code.
    """
    args = build_parser().parse_args(sys.argv[1:] if argv is None else list(argv))
    paths = AppPaths.from_environ(dict(os.environ), Path.home())
    try:
        paths.ensure()
        # Qt's compiled-QML cache goes in Recon's private cache, not ~/.cache/Recon (F-22).
        ensure_private_dir(paths.cache / "qmlcache")
    except ReconError as exc:
        return show_startup_problem(exc)
    except OSError:
        return show_startup_problem(DataFolderUnusableError())
    os.environ["QML_DISK_CACHE_PATH"] = str(paths.cache / "qmlcache")
    configure_logging(paths.log_file)
    # One copy at a time: two writers on one database lose edits (audit F-10).
    lock = QLockFile(str(paths.data / LOCK_FILE))
    if not lock.tryLock(0):
        _log.info("another copy of recon is running")
        return show_startup_problem(AlreadyRunningError(), code=0)
    try:
        return _start(args, paths)
    finally:
        lock.unlock()


def _start(args: argparse.Namespace, paths: AppPaths) -> int:
    settings, problem = load_settings(paths.settings_file)
    if problem is not None:
        _log.warning("starting with default settings")
    try:
        db = open_database(paths)
    except ReconError as exc:
        return show_startup_problem(exc)
    try:
        return _run(args, paths, settings, db)
    finally:
        db.close()


def open_database(paths: AppPaths, today: dt.date | None = None) -> Database:
    """Open and migrate app.db, then take today's snapshot if there isn't one.

    A failed snapshot is logged and start-up carries on: the live data is fine.

    Raises:
        DatabaseTooNewError: A newer Recon wrote it.
        DatabaseUnreadableError: It couldn't be opened or brought up to date.
    """
    try:
        db = Database.open(paths.data / "app.db")
    except StorageError as exc:
        raise DatabaseUnreadableError from exc
    try:
        migrate(db)
    except DatabaseTooNewError:
        db.close()
        raise
    except StorageError as exc:
        db.close()
        raise DatabaseUnreadableError from exc
    try:
        backup.snapshot_if_due(db, paths.data / "backups" / "db", today or dt.date.today())
    except StorageError:
        _log.warning("starting without today's database snapshot")
    return db


class StartupProblem(QObject):
    """What the start-up problem window says (exposed to QML as `Problem`)."""

    def __init__(self, error: ReconError, parent: QObject | None = None) -> None:
        """Describe `error` in its own plain words."""
        super().__init__(parent)
        self._title = (
            "Recon is already open"
            if isinstance(error, AlreadyRunningError)
            else "Recon couldn't start"
        )
        self._message = error.user_message

    def _get_title(self) -> str:
        return self._title

    def _get_message(self) -> str:
        return self._message

    title = Property(str, _get_title, constant=True)
    message = Property(str, _get_message, constant=True)


def show_startup_problem(error: ReconError, code: int = 1) -> int:
    """Say what stopped start-up, in a small window and on stderr; returns `code`."""
    print(error.user_message, file=sys.stderr)  # noqa: T201 - also for terminal launches
    app = create_application(sys.argv[:1])
    problem = StartupProblem(error)
    qml = create_engine({"Problem": problem})
    if load_qml(qml.engine, STARTUP_PROBLEM_QML):
        app.exec()
    del qml
    return code


def _run(args: argparse.Namespace, paths: AppPaths, settings: Settings, db: Database) -> int:
    """Create the app and its windows, then run the event loop."""
    app = create_application(sys.argv[:1])
    bridges, pinning = create_bridges(app, paths, settings, db)
    qml = create_engine(bridges)

    loaded = load_qml(qml.engine, GALLERY_QML) if args.gallery else load_windows(qml.engine)
    if not loaded:
        return 1
    # Rewrite the pin each launch (if on), so a new screen or width is picked up.
    pinning.applyIfOn()
    code = app.exec()
    # Engine first: its bindings must never re-run against already-deleted bridges.
    del qml
    return code


def create_bridges(
    app: QGuiApplication, paths: AppPaths, settings: Settings, db: Database
) -> tuple[dict[str, QObject], PinningBridge]:
    """The objects QML binds to, by context-property name, wired to each other.

    Returns:
        The bridges, and the pinning bridge again (start-up re-applies the pin).
    """
    # Saves and KDE commands each get a serial worker: off the UI thread (audit F-05),
    # in order, and pin/unpin can't overtake each other (audit F-16).
    settings_worker, pin_worker = SerialWorker(app), SerialWorker(app)
    settings_bridge = SettingsBridge(
        settings,
        lambda changed: save_settings(paths.settings_file, changed),
        parent=app,
        submit=settings_worker,
    )
    navigation = NavigationBridge(parent=app)
    pinning = PinningBridge(
        settings_bridge,
        KWinPinning(run_command, paths.data / "kwin-panel.js"),
        lambda: _screen_area(app),
        submit=pin_worker,
        parent=app,
    )
    # Settings save first at quit (queued saves, then anything still unsaved);
    # the room's own savers follow in _room_bridges.
    app.aboutToQuit.connect(lambda: _drain(settings_worker, pin_worker))
    app.aboutToQuit.connect(settings_bridge.flush)
    models = ModelsBridge(
        settings_bridge,
        lambda host: OllamaService(make_client(host, CHECK_TIMEOUT_S)),
        lambda text: QGuiApplication.clipboard().setText(text),
        submit=thread_pool_submit,
        parent=app,
    )
    models.check()
    vault = vault_folder(settings, Path.home(), paths.data)
    thread_pool_submit(lambda: tidy_runs(paths, vault, db))
    bridges: dict[str, QObject] = {
        "AppSettings": settings_bridge,
        "Navigation": navigation,
        "Pinning": pinning,
        "Editors": EditorsBridge(parent=app),
        "Models": models,
        **_room_bridges(app, db, settings_bridge, navigation),
    }
    return bridges, pinning


def tidy_runs(paths: AppPaths, vault: Path, db: Database) -> None:
    """At launch: finish any Apply a crash interrupted, then delete runs over 30 days old.

    Runs still waiting for Apply or Discard are kept however old, so their
    review can still be applied.
    """
    # Thread boundary: whatever fails is logged and retried next launch.
    store = RunStore(paths.runs, utc_now, lambda: secrets.token_hex(4))
    records = RunRepository(db)
    processing = Processing(vault, store, paths.backups, RoomRepository(db), records)
    try:
        processing.recover_runs()
        store.prune(keep={run.id for run in records.staged()})
    except (OSError, ReconError) as exc:
        _log.warning("old runs not tidied: %s", Safe(type(exc).__name__))


def _room_bridges(
    app: QGuiApplication, db: Database, settings: SettingsBridge, navigation: NavigationBridge
) -> dict[str, QObject]:
    """Home, Start, the room session, its timer and Finish, sharing one worker."""
    rooms, tasks, blocks = RoomRepository(db), TaskRepository(db), BlockRepository(db)
    undo = UndoRepository(db)
    # One serial worker for the room's writes, so saves land before anything reads them back.
    room_worker = SerialWorker(app)
    flag_guard = FlagGuard(blocks.keep_lookalike, room_worker, parent=app)
    home = HomeBridge(rooms, blocks, utc_now, parent=app)
    start = StartRoomBridge(rooms, parent=app)
    autosave = AutosaveQueue(
        blocks.update_content,
        on_error=lambda _exc: session.failed.emit(AutosaveFailedError.user_message),
        on_recovered=lambda: session.saveRecovered.emit(),  # noqa: PLW0108 - session is made below
    )
    session = RoomSessionBridge(
        (rooms, tasks, blocks, undo),
        autosave,
        flag_guard,
        submit=room_worker,
        parent=app,
    )
    focus = FocusBridge(
        tasks,
        Chime(parent=app).play,
        lambda: settings.settings.chime,
        submit=room_worker,
        parent=app,
    )
    finish = FinishBridge(
        (rooms, tasks, blocks, undo), settings, open_folder, submit=room_worker, parent=app
    )
    # Create or complete the vault at start-up (task 2.1); Home shows the Obsidian step.
    vault = VaultBridge(
        settings,
        lambda text: QGuiApplication.clipboard().setText(text),
        submit=room_worker,
        parent=app,
    )
    vault.setUp()
    connect_room_flow(navigation, home, start, session, focus)
    connect_finish(navigation, home, session, focus, finish)
    # In order: finish every queued job (Next, deletes, undo steps), then the last title,
    # the last seconds and every queued keystroke, all before the database closes (F-06).
    app.aboutToQuit.connect(lambda: _drain(room_worker))
    app.aboutToQuit.connect(session.close)
    app.aboutToQuit.connect(focus.close)
    app.aboutToQuit.connect(autosave.close)
    return {
        "FlagGuard": flag_guard,
        "HomeModel": home,
        "StartRoom": start,
        "RoomSession": session,
        "Focus": focus,
        "Finish": finish,
        "Vault": vault,
    }


def _drain(*workers: SerialWorker) -> None:
    """At quit: let queued jobs (and the global pool's) finish before anything closes."""
    drained = [worker.drain() for worker in workers]  # every one, even after a timeout
    if not (all(drained) and drain_global_pool()):
        _log.warning("quit before every queued save finished")


def _screen_area(app: QGuiApplication) -> tuple[int, int, int, int]:
    """The primary screen's area in logical pixels (KWin fits the height to the taskbar)."""
    area = app.primaryScreen().geometry()
    return area.x(), area.y(), area.width(), area.height()


if __name__ == "__main__":
    sys.exit(main())
