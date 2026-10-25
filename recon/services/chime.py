"""The soft focus chime (off by default; Settings turns it on)."""

from pathlib import Path
from typing import Final

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QSoundEffect

CHIME: Final = Path(__file__).resolve().parent.parent / "ui" / "sounds" / "chime.wav"
VOLUME: Final = 0.5


class Chime:
    """Plays the chime. The sound loads on first use, so start-up never touches audio."""

    def __init__(self, source: Path = CHIME, parent: QObject | None = None) -> None:
        """Play `source` (a WAV); `parent` owns the sound effect once it exists."""
        self._source = source
        self._parent = parent
        self._effect: QSoundEffect | None = None

    def play(self) -> None:
        """Play the chime once (quietly)."""
        if self._effect is None:
            self._effect = QSoundEffect(self._parent)
            self._effect.setSource(QUrl.fromLocalFile(str(self._source)))
            self._effect.setVolume(VOLUME)
        self._effect.play()
