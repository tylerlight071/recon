"""Application-wide constants and the settings model (`settings.toml`)."""

import logging
import tomllib
from pathlib import Path
from typing import Final, Literal

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from recon.errors import ConfigError
from recon.fs import atomic_write_text
from recon.logging_setup import Safe

APP_ID: Final = "io.github.tylerlight071.Recon"
"""Reverse-DNS app ID used everywhere the desktop identifies Recon.

It must match the `.desktop` file name, `QGuiApplication.setDesktopFileName`,
the GlobalShortcuts portal `Registry.Register` call and the KWin window rule.
Changing it breaks all four, so treat it as permanent.
"""

REPO: Final = Path(__file__).resolve().parent.parent
"""This checkout: no vault may live inside it (it could end up committed)."""

APP_NAME: Final = "Recon"
"""Name shown to Tyler in window titles and notifications."""

PANEL_WIDTH_MIN: Final = 360
PANEL_WIDTH_MAX: Final = 520
PANEL_WIDTH_DEFAULT: Final = 420

type PinningChoice = Literal["ask", "on", "off"]
PINNING_CHOICES: Final = ("ask", "on", "off")
type Accent = Literal["violet", "cyan", "green"]
ACCENTS: Final = ("violet", "cyan", "green")
MODEL_NAME: Final = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$"
"""An Ollama model name such as "qwen3.5:9b" (no spaces, quotes or shell characters)."""
VAULT_DEFAULT: Final = "Cyber Vault"
"""The vault's folder name under the home folder, unless Settings says otherwise."""

_log = logging.getLogger(__name__)


class Settings(BaseModel):
    """Tyler's preferences (the Settings screen, task 1.14).

    Unknown keys are ignored, so a newer settings file still loads.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    panel_width: int = Field(default=PANEL_WIDTH_DEFAULT, ge=PANEL_WIDTH_MIN, le=PANEL_WIDTH_MAX)
    kwin_pinning: PinningChoice = "ask"
    """Pin the panel with a KWin rule: "ask" (first launch asks once), "on" or "off"."""
    chime: bool = False
    """Play a soft chime when a focus block ends (calm by default: off)."""
    export_folder: str = ""
    """Where the last Markdown export went ("" until the first one)."""
    vault_path: str = ""
    """The vault folder; "" means ~/Cyber Vault. Always absolute (see `_vault_path`)."""

    @field_validator("vault_path")
    @classmethod
    def _vault_path(cls, value: str) -> str:
        # Hand-edited settings.toml (audit F-20): "~/Cyber Vault" or "Vault" would
        # resolve against the launcher's working folder, the git checkout. Expand ~,
        # and fall back to the default for anything relative or inside the checkout.
        if not value:
            return ""
        path = Path(value).expanduser()
        if not path.is_absolute() or _inside(path, REPO):
            _log.warning("vault path ignored: not absolute, or inside recon's own folder")
            return ""
        return str(path)

    obsidian_vault: str = ""
    """The vault folder Tyler confirmed he opened in Obsidian once ("" until then).

    Obsidian only follows obsidian:// links to vaults it knows, so "Open in
    Obsidian" stays hidden until this matches the vault in use (task 2.1).
    """
    accent: Accent = "violet"
    reduce_motion: bool = False
    """Make every animation instant (Theme.reduceMotion)."""
    text_model: str = Field(default="qwen3.5:9b", pattern=MODEL_NAME)
    """Structuring, fact-checks, quizzes and Ask (the Phase 2 bake-off may change it)."""
    vision_model: str = Field(default="qwen3.5:9b", pattern=MODEL_NAME)
    """Reading screenshots; the same model as text by default, so nothing swaps."""
    embedding_model: str = Field(default="qwen3-embedding:0.6b", pattern=MODEL_NAME)
    """Matching concepts to existing notes."""
    model_thinking: bool = False
    """Let the text model reason before answering: slower, often more thorough (bake-off, 2.9)."""
    ollama_host: str = "http://127.0.0.1:11434"
    """Ollama's address. Only this computer is ever used (`services.ollama.loopback`)."""

    @property
    def models(self) -> tuple[str, ...]:
        """Every model Recon needs, once each, in the order Settings lists them."""
        return tuple(dict.fromkeys((self.text_model, self.vision_model, self.embedding_model)))


def vault_folder(settings: Settings, home: Path, data: Path | None = None) -> Path:
    """Where the vault lives: the chosen folder, or ~/Cyber Vault.

    A chosen folder inside Recon's own data folder isn't used (audit F-20).
    """
    default = home / VAULT_DEFAULT
    if not settings.vault_path:
        return default
    chosen = Path(settings.vault_path)
    if data is not None and _inside(chosen, data):
        _log.warning("vault path ignored: inside recon's data folder")
        return default
    return chosen


def _inside(path: Path, folder: Path) -> bool:
    resolved, root = path.resolve(strict=False), folder.resolve(strict=False)
    return resolved == root or root in resolved.parents


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
