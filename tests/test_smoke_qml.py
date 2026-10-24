"""QML window smoke test: evaluation rules, plus a real headless run."""

from pathlib import Path

import pytest
from PySide6.QtGui import QFont, QFontInfo, QImage

from scripts.smoke import qml_window
from scripts.smoke.qml_window import Measurements


def _good(**changes: object) -> Measurements:
    m = Measurements(
        platform="wayland",
        families=["Inter"],
        label_family="Inter",
        started=10.0,
        finished=10.2,
        frames=[10.0 + i / 60 for i in range(13)],
    )
    for key, value in changes.items():
        setattr(m, key, value)
    return m


def test_good_measurements_pass() -> None:
    outcome = qml_window.evaluate(_good(), "wayland")

    assert outcome.passed
    assert outcome.detail == "wayland; label in Inter; animation 200 ms over 13 frames"


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"platform": "xcb"}, "platform is xcb, expected wayland"),
        ({"families": []}, "Inter wasn't registered"),
        ({"label_family": "Noto Sans"}, "label rendered with 'Noto Sans'"),
        ({"finished": 10.6}, "animation took 600 ms"),
        ({"finished": 10.1}, "animation took 100 ms"),
        ({"frames": [10.0, 10.1]}, "only 2 frames drawn"),
    ],
)
def test_each_problem_fails_with_a_reason(changes: dict[str, object], problem: str) -> None:
    outcome = qml_window.evaluate(_good(**changes), "wayland")

    assert not outcome.passed
    assert problem in outcome.detail


def test_timeout_fails_plainly() -> None:
    outcome = qml_window.evaluate(_good(timed_out=True), "wayland")

    assert not outcome.passed
    assert "timed out" in outcome.detail


def test_frames_are_counted_only_during_the_animation() -> None:
    m = _good(frames=[9.0, 10.05, 10.1, 11.0])

    assert m.animation_frames == 2


@pytest.mark.parametrize(
    ("weight", "style"),
    [
        (QFont.Weight.Normal, "Regular"),
        (QFont.Weight.Medium, "Medium"),
        (QFont.Weight.DemiBold, "SemiBold"),
    ],
)
def test_bundled_inter_weights_use_real_files(weight: QFont.Weight, style: str) -> None:
    qml_window._app()
    assert "Inter" in qml_window.load_fonts()
    font = QFont("Inter", 15)
    font.setWeight(weight)

    info = QFontInfo(font)

    assert (info.family(), info.styleName()) == ("Inter", style)


def test_headless_window_renders_inter_and_animates(tmp_path: Path) -> None:
    shot = tmp_path / "shot.png"

    m = qml_window.measure(screenshot=shot)
    outcome = qml_window.evaluate(m, "offscreen")

    assert outcome.passed, outcome.detail
    image = QImage(str(shot))
    assert not image.isNull()
    assert image.width() >= 420
