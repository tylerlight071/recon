"""The soft focus chime (off by default; Settings turns it on).

QtMultimedia is imported on first play, not at start-up: it needs the system's
audio libraries (libpulse), and Recon should still start, silently, without them.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from PySide6.QtCore import QObject, QUrl

from recon.logging_setup import Safe

if TYPE_CHECKING:
    from PySide6.QtMultimedia import QSoundEffect

CHIME: Final = Path(__file__).resolve().parent.parent / "ui" / "sounds" / "chime.wav"
VOLUME: Final = 0.5

_log = logging.getLogger(__name__)


class Chime:
    """Plays the chime. The sound loads on first use, so start-up never touches audio."""

    def __init__(self, source: Path = CHIME, parent: QObject | None = None) -> None:
        """Play `source` (a WAV); `parent` owns the sound effect once it exists."""
        self._source = source
        self._parent = parent
        self._effect: QSoundEffect | None = None

    def play(self) -> None:
        """Play the chime once (quietly); without audio libraries, stay silent."""
        if self._effect is None:
            try:
                from PySide6.QtMultimedia import QSoundEffect  # noqa: PLC0415 - see module docstring
            except ImportError as exc:
                _log.warning("no chime, audio unavailable: %s", Safe(type(exc).__name__))
                return
            self._effect = QSoundEffect(self._parent)
            self._effect.setSource(QUrl.fromLocalFile(str(self._source)))
            self._effect.setVolume(VOLUME)
        self._effect.play()
