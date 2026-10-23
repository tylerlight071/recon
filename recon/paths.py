"""XDG locations for Recon's data, config and cache, created with private permissions."""

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from recon.errors import InsecurePermissionsError

PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
_APP_DIR = "recon"


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Recon's own folders. Built from the environment once and passed around."""

    data: Path
    config: Path
    cache: Path

    @property
    def log_file(self) -> Path:
        """Path of the rotating application log."""
        return self.data / "app.log"

    @classmethod
    def from_environ(cls, environ: dict[str, str], home: Path) -> Self:
        """Resolve folders from XDG variables, falling back to the XDG defaults.

        Args:
            environ: Environment mapping, usually `dict(os.environ)`.
            home: The user's home folder.

        Returns:
            The resolved paths. Nothing is created on disk.
        """

        def base(var: str, default: str) -> Path:
            value = environ.get(var, "")
            # The XDG spec says relative values are invalid and must be ignored.
            return Path(value) if value and Path(value).is_absolute() else home / default

        return cls(
            data=base("XDG_DATA_HOME", ".local/share") / _APP_DIR,
            config=base("XDG_CONFIG_HOME", ".config") / _APP_DIR,
            cache=base("XDG_CACHE_HOME", ".cache") / _APP_DIR,
        )

    def ensure(self) -> None:
        """Create every folder as 0700 and lock down any that are too open.

        Raises:
            InsecurePermissionsError: A folder is too open and can't be fixed.
        """
        for folder in (self.data, self.config, self.cache):
            ensure_private_dir(folder)


def ensure_private_dir(folder: Path) -> None:
    """Create `folder` (and parents) and make sure it is mode 0700.

    Args:
        folder: Folder to create or check.

    Raises:
        InsecurePermissionsError: The folder is too open and chmod failed.
    """
    folder.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    if stat.S_IMODE(folder.stat().st_mode) != PRIVATE_DIR_MODE:
        try:
            folder.chmod(PRIVATE_DIR_MODE)
        except OSError as exc:
            raise InsecurePermissionsError(str(folder)) from exc


def private_opener(path: str, flags: int) -> int:
    """`open()` opener that creates new files as 0600.

    Args:
        path: File path passed by `open()`.
        flags: Flags passed by `open()`.

    Returns:
        The open file descriptor.
    """
    return os.open(path, flags, PRIVATE_FILE_MODE)
