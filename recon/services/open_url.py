"""Opening things outside Recon: the only module allowed `QDesktopServices`.

Only local folders are opened, so nothing here can reach the network.
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
