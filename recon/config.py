"""Application-wide constants and the settings model (`settings.toml`)."""

import logging
import tomllib
from pathlib import Path
from typing import Final, Literal

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from recon.errors import ConfigError
from recon.fs import atomic_write_text
from recon.logging_setup import Safe

APP_ID: Final = "io.github.tylerlight071.Recon"
"""Reverse-DNS app ID used everywhere the desktop identifies Recon.

It must match the `.desktop` file name, `QGuiApplication.setDesktopFileName`,
the GlobalShortcuts portal `Registry.Register` call and the KWin window rule.
Changing it breaks all four, so treat it as permanent.
"""

APP_NAME: Final = "Recon"
"""Name shown to Tyler in window titles and notifications."""

PANEL_WIDTH_MIN: Final = 360
PANEL_WIDTH_MAX: Final = 520
PANEL_WIDTH_DEFAULT: Final = 420

type PinningChoice = Literal["ask", "on", "off"]
PINNING_CHOICES: Final = ("ask", "on", "off")

_log = logging.getLogger(__name__)


class Settings(BaseModel):
    """Tyler's preferences. Task 1.14 adds the rest of the Settings screen's fields.

    Unknown keys are ignored, so a newer settings file still loads.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    panel_width: int = Field(default=PANEL_WIDTH_DEFAULT, ge=PANEL_WIDTH_MIN, le=PANEL_WIDTH_MAX)
    kwin_pinning: PinningChoice = "ask"
    """Pin the panel with a KWin rule: "ask" (first launch asks once), "on" or "off"."""
    chime: bool = False
    """Play a soft chime when a focus block ends (calm by default: off)."""


def clamp_panel_width(width: float) -> int:
    """The nearest allowed panel width, in whole pixels."""
    return max(PANEL_WIDTH_MIN, min(PANEL_WIDTH_MAX, round(width)))


def load_settings(path: Path) -> tuple[Settings, ConfigError | None]:
    """Read settings, falling back to defaults rather than failing to start.

    Args:
        path: `settings.toml`.

    Returns:
        The settings, and a ConfigError when the file existed but couldn't be
        used (the defaults are then in use until it's fixed).
    """
    if not path.exists():
        return Settings(), None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return Settings.model_validate(data), None
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValidationError) as exc:
        _log.warning("settings unreadable, using defaults: %s", Safe(type(exc).__name__))
        return Settings(), ConfigError()


def save_settings(path: Path, settings: Settings) -> None:
    """Write settings atomically as TOML, private to Tyler (0600).

    Args:
        path: `settings.toml`; its folder must exist.
        settings: What to save.
    """
    atomic_write_text(path, tomli_w.dumps(settings.model_dump(mode="json")))
