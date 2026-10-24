"""Settings: defaults, validation, round-trip, and never failing to start."""

import stat
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon.config import (
    PANEL_WIDTH_DEFAULT,
    PANEL_WIDTH_MAX,
    PANEL_WIDTH_MIN,
    Settings,
    clamp_panel_width,
    load_settings,
    save_settings,
)
from recon.errors import ConfigError
from recon.paths import AppPaths


def test_defaults() -> None:
    assert Settings().panel_width == PANEL_WIDTH_DEFAULT == 420


def test_missing_file_gives_defaults_without_a_problem(tmp_path: Path) -> None:
    settings, problem = load_settings(tmp_path / "settings.toml")

    assert settings == Settings()
    assert problem is None


def test_round_trip_is_private(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"

    save_settings(path, Settings(panel_width=470))
    settings, problem = load_settings(path)

    assert (settings.panel_width, problem) == (470, None)
    assert path.read_text() == "panel_width = 470\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "content",
    [
        "panel_width = 9000\n",
        "panel_width = 'wide'\n",
        "this is not toml = = =\n",
        "panel_width = 300\n",
    ],
)
def test_unusable_file_gives_defaults_and_a_plain_problem(tmp_path: Path, content: str) -> None:
    path = tmp_path / "settings.toml"
    path.write_text(content)

    settings, problem = load_settings(path)

    assert settings == Settings()
    assert isinstance(problem, ConfigError)
    assert "defaults are in use" in problem.user_message


def test_undecodable_file_gives_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_bytes(b"\xff\xfe\x00")

    settings, problem = load_settings(path)

    assert (settings, isinstance(problem, ConfigError)) == (Settings(), True)


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text("panel_width = 400\nfrom_a_newer_version = true\n")

    settings, problem = load_settings(path)

    assert (settings.panel_width, problem) == (400, None)


@given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6))
def test_clamped_width_is_always_valid(width: float) -> None:
    clamped = clamp_panel_width(width)

    assert PANEL_WIDTH_MIN <= clamped <= PANEL_WIDTH_MAX
    Settings(panel_width=clamped)


def test_settings_file_lives_in_the_config_folder(tmp_path: Path) -> None:
    paths = AppPaths.from_environ({}, tmp_path)

    assert paths.settings_file == tmp_path / ".config/recon/settings.toml"
