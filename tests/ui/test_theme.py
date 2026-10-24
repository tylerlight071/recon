"""The Theme singleton loads, matches CLAUDE.md's tokens, and switches accent and motion."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QEventLoop, QMetaObject, QObject, QTimer
from PySide6.QtGui import QColor, QFont, QFontInfo

from tests.ui.theme_probe import load_theme

# CLAUDE.md, Design system. If a value changes there, it changes here.
EXPECTED_COLOURS = {
    "bg": "#0b0c0e",
    "surface": "#111215",
    "raised": "#16181c",
    "overlay": "#1c1e23",
    "border": "#23252a",
    "textPrimary": "#ececef",
    "textSecondary": "#9a9ba3",
    "textTertiary": "#84868f",
    "textOnAccent": "#0b0c0e",
    "success": "#5fb47a",
    "warning": "#d9a441",
    "accentViolet": "#7c74d9",
    "accentVioletHover": "#8d86e3",
    "accentCyan": "#4fb3c9",
    "accentGreen": "#5fb47a",
}
EXPECTED_NUMBERS = {
    "fontSizeSmall": 13,
    "fontSizeBody": 14,
    "fontSizeLarge": 15,
    "fontSizeMono": 13,
    "space1": 4,
    "space2": 8,
    "space3": 12,
    "space4": 16,
    "space5": 20,
    "space6": 24,
    "space8": 32,
    "space12": 48,
    "hairline": 1,
    "radiusSmall": 6,
    "radiusCard": 8,
    "radiusDialog": 12,
    "panelWidthDefault": 420,
    "panelWidthMin": 360,
    "panelWidthMax": 520,
    "durationFast": 150,
    "durationBase": 200,
}
BLOCK_EDGES = {
    "command": "#4fb3c9",
    "table": "#8a8fa3",
    "screenshot": "#b37fd1",
    "question": "#d9a441",
    "confused": "#d98a5f",
    "room_question": "#5fb47a",
    "voice": "#7c9fd9",
}


@pytest.fixture
def theme() -> Iterator[QObject]:
    engine, singleton = load_theme()
    yield singleton
    engine.deleteLater()


def _colour(theme: QObject, name: str) -> str:
    value = theme.property(name)
    assert isinstance(value, QColor), name
    return value.name()


def _edge(theme: QObject, block_type: str) -> str:
    value = QMetaObject.invokeMethod(
        theme, "blockEdge", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", block_type)
    )
    assert isinstance(value, QColor)
    return value.name()


@pytest.mark.parametrize(("name", "hex_value"), EXPECTED_COLOURS.items())
def test_colour_tokens_match_claude_md(theme: QObject, name: str, hex_value: str) -> None:
    assert _colour(theme, name) == hex_value


@pytest.mark.parametrize(("name", "value"), EXPECTED_NUMBERS.items())
def test_number_tokens_match_claude_md(theme: QObject, name: str, value: int) -> None:
    assert theme.property(name) == value


def test_weights_and_families(theme: QObject) -> None:
    assert theme.property("fontUi") == "Inter"
    assert theme.property("fontMono") == "JetBrains Mono"
    assert theme.property("weightRegular") == QFont.Weight.Normal.value
    assert theme.property("weightMedium") == QFont.Weight.Medium.value
    assert theme.property("weightSemiBold") == QFont.Weight.DemiBold.value


def test_bundled_fonts_load_and_resolve(theme: QObject) -> None:
    loop = QEventLoop()
    QTimer.singleShot(200, loop.quit)
    loop.exec()

    assert theme.property("fontsReady") is True
    for family, weight, style in [
        ("Inter", QFont.Weight.Normal, "Regular"),
        ("Inter", QFont.Weight.Medium, "Medium"),
        ("Inter", QFont.Weight.DemiBold, "SemiBold"),
        ("JetBrains Mono", QFont.Weight.Normal, "Regular"),
    ]:
        font = QFont(family, 13)
        font.setWeight(weight)
        info = QFontInfo(font)
        assert (info.family(), info.styleName()) == (family, style)


@pytest.mark.parametrize(
    ("name", "accent", "hover"),
    [
        ("violet", "#7c74d9", "#8d86e3"),
        ("cyan", "#4fb3c9", "#66bdd0"),
        ("green", "#5fb47a", "#74be8b"),
        ("magenta", "#7c74d9", "#8d86e3"),
    ],
)
def test_accent_follows_the_setting(theme: QObject, name: str, accent: str, hover: str) -> None:
    theme.setProperty("accentName", name)

    assert _colour(theme, "accent") == accent
    assert _colour(theme, "accentHover") == hover
    assert _colour(theme, "focusRing") == accent
    assert _edge(theme, "key_idea") == accent


def test_reduce_motion_makes_every_duration_zero(theme: QObject) -> None:
    theme.setProperty("reduceMotion", True)

    assert (theme.property("durationFast"), theme.property("durationBase")) == (0, 0)

    theme.setProperty("reduceMotion", False)
    assert (theme.property("durationFast"), theme.property("durationBase")) == (150, 200)


@pytest.mark.parametrize(("block_type", "hex_value"), BLOCK_EDGES.items())
def test_block_edges(theme: QObject, block_type: str, hex_value: str) -> None:
    assert _edge(theme, block_type) == hex_value


def test_unknown_block_type_gets_the_border_colour(theme: QObject) -> None:
    assert _edge(theme, "mystery") == EXPECTED_COLOURS["border"]


def test_block_edges_are_muted(theme: QObject) -> None:
    assert 0 < theme.property("blockEdgeOpacity") < 1
