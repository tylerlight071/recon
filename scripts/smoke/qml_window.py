"""Smoke test: a PySide6 Qt Quick window opens with Inter and a smooth 200 ms animation.

    uv run python -m scripts.smoke.qml_window [--screenshot PATH] [--hold SECONDS]

Checks the Qt platform (Wayland by default), that the label's font really
resolves to the bundled Inter, that a 200 ms animation takes about 200 ms, and
how many frames it drew. The window closes itself unless `--hold` is given.
"""

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import SIGNAL, QMetaObject, QObject, QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow

from recon.config import APP_ID, APP_NAME
from scripts.smoke._common import Outcome, run

REPO = Path(__file__).resolve().parents[2]
FONTS = REPO / "recon" / "ui" / "theme" / "fonts"
QML = Path(__file__).resolve().parent / "qml" / "SmokeWindow.qml"
ANIMATION_MS = 200
ANIMATION_TOLERANCE_MS = (180, 400)
"""Lower bound: QML can't finish early. Upper: first-frame jitter on a busy desktop."""
MIN_FRAMES = 8
"""At 60 Hz a 200 ms animation draws about 12 frames; 8 allows one missed vsync or two."""
_START_DELAY_MS = 400
_SETTLE_MS = 300
_TIMEOUT_MS = 10_000


@dataclass(slots=True)
class Measurements:
    """What the event loop observed."""

    platform: str = ""
    families: list[str] = field(default_factory=list)
    label_family: str = ""
    started: float = 0.0
    finished: float = 0.0
    frames: list[float] = field(default_factory=list)
    timed_out: bool = False

    @property
    def animation_ms(self) -> float:
        """Wall-clock duration of the animation."""
        return (self.finished - self.started) * 1000

    @property
    def animation_frames(self) -> int:
        """Frames swapped while the animation ran."""
        return sum(self.started <= t <= self.finished for t in self.frames)


def load_fonts(folder: Path = FONTS) -> list[str]:
    """Register every bundled .ttf with Qt.

    Args:
        folder: Folder holding the font files.

    Returns:
        The font families Qt registered, without duplicates, sorted.
    """
    families: set[str] = set()
    for path in sorted(folder.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.update(QFontDatabase.applicationFontFamilies(font_id))
    return sorted(families)


def evaluate(m: Measurements, expected_platform: str) -> Outcome:
    """Turn measurements into PASS or FAIL with every problem listed.

    Args:
        m: What the run observed.
        expected_platform: Qt platform plugin that should be in use.

    Returns:
        The outcome.
    """
    if m.timed_out:
        return Outcome(False, "The window never finished its animation (timed out after 10 s)")
    problems: list[str] = []
    if m.platform != expected_platform:
        problems.append(f"platform is {m.platform}, expected {expected_platform}")
    if "Inter" not in m.families:
        problems.append(f"Inter wasn't registered (got {m.families})")
    if m.label_family != "Inter":
        problems.append(f"label rendered with {m.label_family!r}, not Inter")
    low, high = ANIMATION_TOLERANCE_MS
    if not low <= m.animation_ms <= high:
        problems.append(f"animation took {m.animation_ms:.0f} ms, expected about {ANIMATION_MS}")
    if m.animation_frames < MIN_FRAMES:
        problems.append(f"only {m.animation_frames} frames drawn during the animation")
    summary = (
        f"{m.platform}; label in {m.label_family or 'unknown'}; "
        f"animation {m.animation_ms:.0f} ms over {m.animation_frames} frames"
    )
    if problems:
        return Outcome(False, f"{summary}. Problems: {'; '.join(problems)}")
    return Outcome(True, summary)


def _label_family(window: QQuickWindow) -> str:
    label = window.findChild(QQuickItem, "label")
    font = label.property("font") if label is not None else None
    return QFontInfo(font).family() if isinstance(font, QFont) else ""


def _app() -> QGuiApplication:
    existing = QGuiApplication.instance()
    if isinstance(existing, QGuiApplication):
        return existing
    QGuiApplication.setDesktopFileName(APP_ID)
    QGuiApplication.setApplicationName(APP_NAME)
    return QGuiApplication(sys.argv[:1])


def measure(screenshot: Path | None = None, hold_s: float = 0.0) -> Measurements:
    """Open the window, run the animation once and record what happened.

    Args:
        screenshot: Where to save a PNG of the window after the animation.
        hold_s: Seconds to keep the window open afterwards.

    Returns:
        The measurements.
    """
    app = _app()
    m = Measurements(platform=QGuiApplication.platformName(), families=load_fonts())
    engine = QQmlApplicationEngine()
    engine.load(QUrl.fromLocalFile(str(QML)))
    roots = engine.rootObjects()
    window = roots[0] if roots else None
    if not isinstance(window, QQuickWindow):
        m.timed_out = True
        return m
    window.frameSwapped.connect(lambda: m.frames.append(time.monotonic()))

    def start() -> None:
        m.label_family = _label_family(window)
        m.started = time.monotonic()
        QMetaObject.invokeMethod(window, "startAnimation")

    def finished() -> None:
        m.finished = time.monotonic()
        QTimer.singleShot(_SETTLE_MS + int(hold_s * 1000), done)

    def done() -> None:
        if screenshot is not None:
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            window.grabWindow().save(str(screenshot))
        app.quit()

    def give_up() -> None:
        m.timed_out = m.finished == 0.0
        app.quit()

    QObject.connect(window, SIGNAL("animationFinished()"), finished)
    QTimer.singleShot(_START_DELAY_MS, start)
    QTimer.singleShot(_TIMEOUT_MS + int(hold_s * 1000), give_up)
    app.exec()
    window.close()
    return m


def main(argv: list[str]) -> int:
    """Parse arguments and run the smoke test.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        0 on pass, 1 on fail.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path, help="save a PNG of the window here")
    parser.add_argument("--hold", type=float, default=0.0, help="seconds to keep it open")
    parser.add_argument("--expect-platform", default="wayland", help="Qt platform plugin")
    args = parser.parse_args(argv)
    return run(
        f"QML window (PySide6, {args.expect_platform})",
        lambda: evaluate(measure(args.screenshot, args.hold), args.expect_platform),
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
