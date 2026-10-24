"""Phase 1 acceptance: every text token meets 4.5:1 on every surface (read from Theme.qml)."""

import itertools

import pytest

from tests.ui.theme_probe import literal_colours

MIN_CONTRAST = 4.5
SURFACES = ("bg", "surface", "raised", "overlay")
TEXT_ON_SURFACES = ("textPrimary", "textSecondary", "textTertiary", "success", "warning")
ACCENT_FILLS = (
    "accentViolet",
    "accentVioletHover",
    "accentCyan",
    "accentCyanHover",
    "accentGreen",
    "accentGreenHover",
)
COLOURS = literal_colours()


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    """WCAG 2 contrast ratio between two #rrggbb colours."""
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_contrast_formula_matches_wcag_reference_points() -> None:
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)
    assert contrast("#123456", "#123456") == pytest.approx(1.0)


def test_every_token_the_checks_need_is_defined() -> None:
    # A renamed or removed token must fail here, not silently drop out of the checks.
    missing = {*SURFACES, *TEXT_ON_SURFACES, *ACCENT_FILLS, "textOnAccent"} - set(COLOURS)

    assert missing == set()


PAIRS = list(itertools.product(TEXT_ON_SURFACES, SURFACES))


@pytest.mark.parametrize(("text", "surface"), PAIRS, ids=[f"{t}-on-{b}" for t, b in PAIRS])
def test_text_on_every_surface(text: str, surface: str) -> None:
    assert contrast(COLOURS[text], COLOURS[surface]) >= MIN_CONTRAST


@pytest.mark.parametrize("fill", ACCENT_FILLS)
def test_text_on_every_accent_fill(fill: str) -> None:
    assert contrast(COLOURS["textOnAccent"], COLOURS[fill]) >= MIN_CONTRAST


def test_white_text_would_fail_on_violet_and_cyan() -> None:
    # Why textOnAccent is near-black (CLAUDE.md, Design system).
    assert contrast("#ffffff", COLOURS["accentViolet"]) < MIN_CONTRAST
    assert contrast("#ffffff", COLOURS["accentCyan"]) < MIN_CONTRAST
