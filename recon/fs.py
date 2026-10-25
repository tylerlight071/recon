"""Crash-safe file writes (CLAUDE.md, Data safety).

Every file Recon writes goes through `atomic_write_text` or
`atomic_write_bytes`: the data goes to a temp file in the same folder, is
fsynced, then replaces the target with `os.replace`, and the folder is
fsynced so the rename itself survives a power cut. A crash leaves either the
old file or the new one, never a half-written mix.
"""

import os
import tempfile
from pathlib import Path

from recon.paths import PRIVATE_FILE_MODE


def atomic_write_bytes(path: Path, data: bytes, mode: int = PRIVATE_FILE_MODE) -> None:
    """Replace `path` with `data` atomically.

    Args:
        path: Target file; its folder must exist.
        data: The new contents.
        mode: Permissions for the new file (0600 by default).

    Raises:
        OSError: The write, fsync or replace failed. The target is unchanged
            and the temp file is removed.
    """
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(mode)
        temp.replace(path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)


def atomic_write_text(path: Path, text: str, mode: int = PRIVATE_FILE_MODE) -> None:
    """Replace `path` with UTF-8 `text` atomically (see `atomic_write_bytes`)."""
    atomic_write_bytes(path, text.encode("utf-8"), mode)


def _fsync_dir(folder: Path) -> None:
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_create_text(path: Path, text: str, mode: int = PRIVATE_FILE_MODE) -> None:
    """Create `path` with UTF-8 `text` atomically, never replacing an existing file.

    The data is written and fsynced to a temp file, then hard-linked into place:
    the link fails if `path` exists, so nothing is ever overwritten, and a
    crash leaves either no file or the whole file.

    Raises:
        FileExistsError: `path` already exists (nothing changed).
        OSError: The write failed (the temp file is removed).
    """
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(mode)
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    _fsync_dir(path.parent)
