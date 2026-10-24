"""Start Recon: `uv run python -m recon` (normally through packaging/recon-launch)."""

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from recon.app import GALLERY_QML, create_application, create_engine, load_qml, load_windows
from recon.bridge.navigation import NavigationBridge
from recon.bridge.settings import SettingsBridge
from recon.config import load_settings, save_settings
from recon.logging_setup import configure_logging
from recon.paths import AppPaths

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

    app = create_application(sys.argv[:1])
    settings_bridge = SettingsBridge(
        settings, lambda changed: save_settings(paths.settings_file, changed), parent=app
    )
    navigation = NavigationBridge(parent=app)
    app.aboutToQuit.connect(settings_bridge.flush)
    qml = create_engine({"AppSettings": settings_bridge, "Navigation": navigation})

    loaded = load_qml(qml.engine, GALLERY_QML) if args.gallery else load_windows(qml.engine)
    if not loaded:
        return 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
