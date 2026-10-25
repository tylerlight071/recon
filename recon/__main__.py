"""Start Recon: `uv run python -m recon` (normally through packaging/recon-launch)."""

import argparse
import datetime as dt
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from recon.app import GALLERY_QML, create_application, create_engine, load_qml, load_windows
from recon.bridge.flags import FlagGuard
from recon.bridge.flow import connect_room_flow
from recon.bridge.home import HomeBridge
from recon.bridge.navigation import NavigationBridge
from recon.bridge.pinning import PinningBridge
from recon.bridge.settings import SettingsBridge
from recon.bridge.start import StartRoomBridge
from recon.config import Settings, load_settings, save_settings
from recon.db import backup
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.repositories import BlockRepository, RoomRepository, utc_now
from recon.errors import StorageError
from recon.logging_setup import configure_logging
from recon.paths import AppPaths
from recon.services.kwin import KWinPinning, run_command

_log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Command-line options."""
    parser = argparse.ArgumentParser(prog="recon", description="Recon study companion.")
    parser.add_argument(
        "--gallery", action="store_true", help="show the developer component gallery"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run Recon.

    Args:
        argv: Arguments without the program name; defaults to sys.argv[1:].

    Returns:
        The process exit code.
    """
    args = build_parser().parse_args(sys.argv[1:] if argv is None else list(argv))
    paths = AppPaths.from_environ(dict(os.environ), Path.home())
    paths.ensure()
    configure_logging(paths.log_file)
    settings, problem = load_settings(paths.settings_file)
    if problem is not None:
        _log.warning("starting with default settings")
    db = open_database(paths)
    if db is None:
        print(StorageError.user_message, file=sys.stderr)  # noqa: T201 - no window yet
        return 1
    try:
        return _run(args, paths, settings, db)
    finally:
        db.close()


def open_database(paths: AppPaths, today: dt.date | None = None) -> Database | None:
    """Open and migrate app.db, then take today's snapshot if there isn't one.

    A failed snapshot is logged and start-up carries on: the live data is fine.

    Returns:
        The database, or None if it couldn't be opened or migrated.
    """
    try:
        db = Database.open(paths.data / "app.db")
    except StorageError:
        return None
    try:
        migrate(db)
    except StorageError:
        db.close()
        return None
    try:
        backup.snapshot_if_due(db, paths.data / "backups" / "db", today or dt.date.today())
    except StorageError:
        _log.warning("starting without today's database snapshot")
    return db


def _run(args: argparse.Namespace, paths: AppPaths, settings: Settings, db: Database) -> int:
    """Create the app and its windows, then run the event loop."""
    app = create_application(sys.argv[:1])
    settings_bridge = SettingsBridge(
        settings, lambda changed: save_settings(paths.settings_file, changed), parent=app
    )
    navigation = NavigationBridge(parent=app)
    pinning = PinningBridge(
        settings_bridge,
        KWinPinning(run_command, paths.data / "kwin-panel.js"),
        lambda: _screen_area(app),
        parent=app,
    )
    blocks = BlockRepository(db)
    flag_guard = FlagGuard(blocks.keep_lookalike, parent=app)
    rooms = RoomRepository(db)
    home = HomeBridge(rooms, blocks, utc_now, parent=app)
    start = StartRoomBridge(rooms, parent=app)
    connect_room_flow(navigation, home, start)
    app.aboutToQuit.connect(settings_bridge.flush)
    qml = create_engine(
        {
            "AppSettings": settings_bridge,
            "Navigation": navigation,
            "Pinning": pinning,
            "FlagGuard": flag_guard,
            "HomeModel": home,
            "StartRoom": start,
        }
    )

    loaded = load_qml(qml.engine, GALLERY_QML) if args.gallery else load_windows(qml.engine)
    if not loaded:
        return 1
    # Rewrite the pin each launch (if on), so a new screen or width is picked up.
    pinning.applyIfOn()
    code = app.exec()
    # Engine first: its bindings must never re-run against already-deleted bridges.
    del qml
    return code


def _screen_area(app: QGuiApplication) -> tuple[int, int, int, int]:
    """The primary screen's area in logical pixels (KWin fits the height to the taskbar)."""
    area = app.primaryScreen().geometry()
    return area.x(), area.y(), area.width(), area.height()


if __name__ == "__main__":
    sys.exit(main())
