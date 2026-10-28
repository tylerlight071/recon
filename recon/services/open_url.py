"""Opening things outside Recon: the only module allowed `QDesktopServices`.

Only local folders and `obsidian://` links to local notes are opened, so
nothing here can reach the network.
"""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def open_folder(folder: Path) -> bool:
    """Show `folder` in the file manager.

    Returns:
        False if it isn't an existing folder or the desktop couldn't open it.
    """
    if not folder.is_dir():
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def obsidian_url(note: Path) -> str:
    """The `obsidian://open?path=…` link for a note, every reserved character encoded.

    `path` is an absolute path; Obsidian finds the vault that contains it, so
    the vault's name never has to be guessed. Obsidian only follows it for a
    vault it has opened before (task 2.1's one-time step).
    """
    # Everything but A-Z, a-z, 0-9 and -._~ is percent-encoded, slashes included.
    encoded = QUrl.toPercentEncoding(str(note.resolve())).toStdString()
    return f"obsidian://open?path={encoded}"


def open_in_obsidian(note: Path) -> bool:
    """Open a note in Obsidian.

    Returns:
        False if the note isn't there or the desktop couldn't hand the link to Obsidian.
    """
    if not note.is_file() or note.suffix != ".md":
        return False
    return QDesktopServices.openUrl(QUrl(obsidian_url(note), QUrl.ParsingMode.StrictMode))
