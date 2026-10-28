"""The gate screenshot script still renders every screen from the real app wiring."""

from pathlib import Path

from scripts.screenshots import main
from tests.ui.qml_harness import app


def test_renders_every_screen(tmp_path: Path) -> None:
    app()

    written = main(tmp_path / "shots")

    assert written == [
        "home.png",
        "panel-finish.png",
        "panel-session.png",
        "review.png",
        "settings-cyan.png",
        "settings.png",
        "start.png",
    ]
    assert all((tmp_path / "shots" / name).stat().st_size > 1000 for name in written)
