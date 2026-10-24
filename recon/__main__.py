"""Start Recon: `uv run python -m recon` (normally through packaging/recon-launch)."""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtQml import QQmlApplicationEngine

from recon.app import GALLERY_QML, create_application, load_qml
from recon.logging_setup import configure_logging
from recon.paths import AppPaths

NOT_YET = "Recon's windows arrive in task 1.3. For now, `--gallery` shows the component gallery."


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
    if not args.gallery:
        print(NOT_YET, file=sys.stderr)  # noqa: T201 - plain message on the command line
        return 2
    app = create_application(sys.argv[:1])
    engine = QQmlApplicationEngine()
    if not load_qml(engine, GALLERY_QML):
        return 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
