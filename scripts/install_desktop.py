"""Install Recon in the app menu: the desktop entry and its icon (task 1.15).

Writes two files, both named after the app ID (the GlobalShortcuts portal and
the KWin rule match on it, ADR 0003):

- `$XDG_DATA_HOME/applications/io.github.tylerlight071.Recon.desktop`, whose
  Exec is this checkout's `packaging/recon-launch` (it sets up the CUDA
  libraries, then starts Recon; no terminal window);
- `$XDG_DATA_HOME/icons/hicolor/scalable/apps/io.github.tylerlight071.Recon.svg`.

Then asks KDE to refresh its menu. `--uninstall` removes exactly those two
files, and only if this script wrote them. Nothing else is touched.

Run: `uv run python -m scripts.install_desktop` (or `--uninstall`).
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Final

from recon.config import APP_ID
from recon.fs import atomic_write_bytes, atomic_write_text

REPO: Final = Path(__file__).resolve().parent.parent
TEMPLATE: Final = REPO / "packaging" / f"{APP_ID}.desktop"
ICON: Final = REPO / "packaging" / "icons" / f"{APP_ID}.svg"
LAUNCHER: Final = REPO / "packaging" / "recon-launch"
MARKER: Final = "X-Recon-Installed-By=scripts/install_desktop.py"
PUBLIC_FILE: Final = 0o644
"""Menus and icon themes are read by other processes, so these two aren't private."""
REFRESH: Final = ("/usr/bin/kbuildsycoca6", "/usr/bin/update-desktop-database")


def data_home(environ: dict[str, str], home: Path) -> Path:
    """`$XDG_DATA_HOME`, or ~/.local/share when it's unset or not absolute (XDG spec)."""
    value = environ.get("XDG_DATA_HOME", "")
    return Path(value) if value and Path(value).is_absolute() else home / ".local" / "share"


def targets(data: Path) -> tuple[Path, Path]:
    """Where the desktop entry and the icon go."""
    return (
        data / "applications" / f"{APP_ID}.desktop",
        data / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg",
    )


def exec_quote(path: Path) -> str:
    """A path quoted for a desktop entry's Exec key (Desktop Entry Specification 1.5).

    Arguments with spaces or reserved characters go in double quotes, with `"`,
    backtick, `$` and backslash escaped by a backslash; then, as Exec is a
    string value, every backslash is doubled once more.
    """
    text = str(path)
    if any(char in text for char in " \t\n\"'\\><~|&;$*?#()`"):
        escaped = "".join(f"\\{char}" if char in '"`$\\' else char for char in text)
        text = f'"{escaped}"'
    # A literal % would be read as a field code (%d, %f…); the spec writes it %%.
    return text.replace("\\", "\\\\").replace("%", "%%")


def render_entry(launcher: Path) -> str:
    """The desktop entry, with Exec pointing at this checkout's launcher."""
    return TEMPLATE.read_text(encoding="utf-8").replace("@RECON_LAUNCH@", exec_quote(launcher))


class NotOursError(FileExistsError):
    """A desktop entry with Recon's name exists that this script didn't write."""


def install(data: Path, launcher: Path = LAUNCHER, *, force: bool = False) -> tuple[Path, Path]:
    """Write the desktop entry and icon under `data`; returns their paths.

    Raises:
        NotOursError: An entry with Recon's name is there that this script didn't
            write (audit F-23); `force` replaces it anyway.
    """
    entry, icon = targets(data)
    if entry.exists() and not force and MARKER not in entry.read_text(encoding="utf-8"):
        raise NotOursError(entry)
    for folder in (entry.parent, icon.parent):
        folder.mkdir(parents=True, exist_ok=True)
    atomic_write_text(entry, render_entry(launcher), mode=PUBLIC_FILE)
    atomic_write_bytes(icon, ICON.read_bytes(), mode=PUBLIC_FILE)
    return entry, icon


def uninstall(data: Path) -> list[Path]:
    """Remove the two files, only if this script wrote them; returns what was removed."""
    entry, icon = targets(data)
    if not entry.exists():
        return []
    if MARKER not in entry.read_text(encoding="utf-8"):
        return []  # someone else's file of the same name: leave it alone
    removed = [entry]
    entry.unlink()
    if icon.exists():
        icon.unlink()
        removed.append(icon)
    return removed


def refresh_menu(data: Path) -> None:
    """Ask KDE (and other desktops) to pick up the change; menus also notice on their own."""
    for tool in REFRESH:
        if not Path(tool).exists():
            continue
        args = (
            [tool, "--noincremental"]
            if tool.endswith("kbuildsycoca6")
            else [tool, str(data / "applications")]
        )
        subprocess.run(args, check=False, capture_output=True, timeout=60)  # noqa: S603 - fixed tool, full path, no shell


def main(argv: list[str] | None = None) -> int:
    """Install (or with --uninstall, remove) Recon's menu entry."""
    parser = argparse.ArgumentParser(description="Add Recon to the app menu.")
    parser.add_argument("--uninstall", action="store_true", help="remove the menu entry and icon")
    parser.add_argument(
        "--no-refresh", action="store_true", help="don't ask KDE to rebuild its menu"
    )
    parser.add_argument(
        "--force", action="store_true", help="replace an entry this script didn't write"
    )
    args = parser.parse_args(argv)
    data = data_home(dict(os.environ), Path.home())
    if args.uninstall:
        removed = uninstall(data)
        print("Removed:" if removed else "Nothing of Recon's to remove.", *removed, sep="\n  ")
    else:
        try:
            entry, icon = install(data, force=args.force)
        except NotOursError as exc:
            print(
                f"Not installed: {exc} wasn't written by this script. "
                "Look at it first; run again with --force to replace it."
            )
            return 1
        print(f"Installed:\n  {entry}\n  {icon}")
    if not args.no_refresh:
        refresh_menu(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
