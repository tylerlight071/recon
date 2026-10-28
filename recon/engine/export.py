"""Write a finished room to a Markdown file in a folder the user chose (task 1.13).

Never overwrites: if "DNS in Detail.md" exists, the next is "DNS in Detail (2).md".
The file name comes from `names.file_name`, and the final path is checked to
be directly inside the chosen folder before anything is written.
"""

from pathlib import Path
from typing import Final

from recon.engine.names import file_name
from recon.engine.render import ExportRoom, render_export
from recon.errors import ExportFailedError, ExportFolderMissingError, UnsafePathError
from recon.fs import atomic_create_text

MAX_COPIES: Final = 999


def export_room(room: ExportRoom, folder: Path) -> Path:
    """Write `room` as Markdown into `folder` and return the new file's path.

    Raises:
        ExportFolderMissingError: `folder` isn't an existing folder.
        UnsafePathError: The file would land outside `folder` (never expected).
        ExportFailedError: The write failed; nothing was left behind.
    """
    if not folder.is_dir():
        raise ExportFolderMissingError
    base = folder.resolve()
    text = render_export(room)
    stem = file_name(room.name)
    for copy in range(1, MAX_COPIES + 1):
        name = f"{stem}.md" if copy == 1 else f"{stem} ({copy}).md"
        path = base / name
        if path.resolve().parent != base:
            raise UnsafePathError
        try:
            atomic_create_text(path, text)
        except FileExistsError:
            continue
        except OSError as exc:
            raise ExportFailedError from exc
        return path
    raise ExportFailedError
