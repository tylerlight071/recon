"""The focus chime: generated deterministically, quiet, loaded only when first played."""

import sys
from pathlib import Path

import pytest

from recon.services.chime import CHIME, VOLUME, Chime
from scripts.make_chime import main as make_chime
from tests.ui.qml_harness import app


def test_the_committed_chime_is_what_the_script_makes(tmp_path: Path) -> None:
    out = tmp_path / "chime.wav"

    make_chime(out)

    assert out.read_bytes() == CHIME.read_bytes()


def test_the_chime_loads_on_first_play_and_is_quiet() -> None:
    app()
    chime = Chime()
    assert chime._effect is None  # start-up must not touch audio

    chime.play()
    chime.play()

    effect = chime._effect  # checking what was loaded
    assert effect is not None
    assert effect.source().toLocalFile() == str(CHIME)
    assert effect.volume() == VOLUME


def test_without_audio_libraries_the_chime_stays_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    app()
    monkeypatch.setitem(sys.modules, "PySide6.QtMultimedia", None)  # import now fails
    chime = Chime()

    chime.play()

    assert chime._effect is None
