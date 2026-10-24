"""Phase 1 acceptance: no literal colours or sizes in QML outside ui/theme/."""

import re
from pathlib import Path

import pytest

from tests.ui.theme_probe import THEME_DIR, UI_DIR

_COLOUR = re.compile(
    r"""#[0-9a-fA-F]{3,8}\b|Qt\.(?:rgba|hsla|hsva|rgb|lighter|darker|tint)\s*\(|"(?:white|black|red|green|blue|grey|gray|transparent)\""""
)
_SIZE_PROPS = (
    "pixelSize|pointSize|radius|spacing|width|height|implicitWidth|implicitHeight|"
    "minimumWidth|maximumWidth|minimumHeight|maximumHeight|margins|leftMargin|rightMargin|"
    "topMargin|bottomMargin|padding|leftPadding|rightPadding|topPadding|bottomPadding|"
    "horizontalPadding|verticalPadding|duration|letterSpacing|lineHeight"
)
# A size property set straight to a non-zero number (0 is allowed: it means "none").
_SIZE = re.compile(rf"\b(?:{_SIZE_PROPS})\s*:\s*-?(?:0*[1-9][0-9]*(?:\.[0-9]+)?|0?\.[0-9]*[1-9])\b")


def offenders(source: str) -> list[str]:
    """Literal colours and sizes in QML source, ignoring // comments."""
    found: list[str] = []
    for line in source.splitlines():
        code = line.split("//", 1)[0]
        found += [m.group(0) for m in _COLOUR.finditer(code)]
        found += [m.group(0) for m in _SIZE.finditer(code)]
    return found


@pytest.mark.parametrize(
    "source",
    [
        'color: "#7c74d9"',
        'border.color: "#fff"',
        "color: Qt.rgba(1, 0, 0, 1)",
        'color: "white"',
        "font.pixelSize: 14",
        "radius: 8",
        "anchors.margins: 16",
        "width: 420",
        "Behavior on opacity { NumberAnimation { duration: 200 } }",
        "spacing: 0.5",
    ],
)
def test_detector_catches_literals(source: str) -> None:
    assert offenders(source), source


@pytest.mark.parametrize(
    "source",
    [
        "color: Theme.accent",
        "font.pixelSize: Theme.fontSizeBody",
        "radius: Theme.radiusCard",
        "anchors.margins: 0",
        "width: parent.width",
        "duration: Theme.durationBase",
        "opacity: 0.5",
        "z: 2",
        "// a comment mentioning #7c74d9 and width: 420",
        'text: qsTr("Task 3 of 7")',
    ],
)
def test_detector_allows_tokens(source: str) -> None:
    assert offenders(source) == []


def _qml_outside_theme() -> list[Path]:
    return [path for path in UI_DIR.rglob("*.qml") if THEME_DIR not in path.parents]


def test_no_qml_outside_the_theme_uses_literals() -> None:
    found = {
        str(path.relative_to(UI_DIR)): hits
        for path in _qml_outside_theme()
        if (hits := offenders(path.read_text(encoding="utf-8")))
    }

    assert found == {}
