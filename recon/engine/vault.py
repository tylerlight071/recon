"""Create the vault Recon owns, and keep its scaffolding in place (task 2.1).

`bootstrap` makes the folders from SPEC.md's vault structure, `Home.md` (a
Bases dashboard), the `.base` files behind it, and Obsidian's settings:
wikilinks, "Automatically update internal links", and attachments to
`Attachments/`. It's safe to run on every launch:

- A file that exists is never replaced. Home and the dashboards are the user's
  to change once written.
- `.obsidian/app.json` only gains keys it doesn't have; the user's own values
  win, and an unreadable file is left alone.

This is fixed scaffolding, not room output: generated notes still reach the
vault only through Apply (hard rule 3, ADR 0006).
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from recon.errors import VaultSetupError
from recon.fs import atomic_create_text, atomic_write_text
from recon.logging_setup import Safe
from recon.paths import ensure_private_dir

TEMPLATES: Final = Path(__file__).resolve().parent / "templates" / "vault"
FOLDERS: Final = (
    "00 Raw notes",
    "01 Rooms",
    "02 Concepts",
    "03 Tools",
    "Attachments",
    "Recaps",
    "Bases",
)
OBSIDIAN_SETTINGS: Final[dict[str, object]] = {
    "useMarkdownLinks": False,  # wikilinks
    "alwaysUpdateLinks": True,  # renaming a concept doesn't break rooms
    "attachmentFolderPath": "Attachments",
}
"""Keys in `.obsidian/app.json` (checked against Obsidian 1.14.5)."""

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Bootstrap:
    """What a bootstrap did."""

    created: bool
    """The vault folder itself was new."""
    written: tuple[str, ...] = field(default=())
    """Files written or updated, relative to the vault."""


def bootstrap(vault: Path) -> Bootstrap:
    """Create or complete the vault's scaffolding, never replacing anything.

    Args:
        vault: The vault folder (from Settings).

    Returns:
        Whether the vault was new, and which files were written.

    Raises:
        VaultSetupError: The folder can't be created or used (a file is in the way,
            no permission).
    """
    created = not vault.exists()
    written: list[str] = []
    try:
        ensure_private_dir(vault)
        for folder in FOLDERS:
            (vault / folder).mkdir(exist_ok=True)
        (vault / ".obsidian").mkdir(exist_ok=True)
        if _create(vault / "Home.md", _home(vault.name)):
            written.append("Home.md")
        for base in sorted((TEMPLATES / "bases").glob("*.base")):
            if _create(vault / "Bases" / base.name, base.read_text(encoding="utf-8")):
                written.append(f"Bases/{base.name}")
        if _merge_settings(vault / ".obsidian" / "app.json"):
            written.append(".obsidian/app.json")
    except OSError as exc:
        _log.warning("vault setup failed: %s", Safe(type(exc).__name__))
        raise VaultSetupError from exc
    _log.info("vault bootstrap: new=%s, %s file(s) written", created, len(written))
    return Bootstrap(created, tuple(written))


def _home(name: str) -> str:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=False,  # noqa: S701 - output is Markdown, not HTML
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    # The vault's name is the user's choice of folder; keep it to one plain line.
    title = " ".join(name.replace("%%", "").split()) or "Cyber Vault"
    return environment.get_template("home.md.j2").render(name=title)


def _create(path: Path, text: str) -> bool:
    # Only if missing; an existing file is the user's (or Obsidian's) and stays as it is.
    if path.exists():
        return False
    try:
        atomic_create_text(path, text)
    except FileExistsError:  # appeared meanwhile: still not ours to replace
        return False
    return True


def _merge_settings(path: Path) -> bool:
    current: dict[str, object] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            _log.warning("obsidian app.json unreadable; left as it is")
            return False
        if not isinstance(loaded, dict):
            return False
        current = loaded
    missing = {k: v for k, v in OBSIDIAN_SETTINGS.items() if k not in current}
    if not missing:
        return False
    atomic_write_text(path, json.dumps({**current, **missing}, indent=2) + "\n")
    return True
