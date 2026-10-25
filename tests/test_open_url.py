"""Opening a folder in the file manager: local folders only."""

from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from recon.services.open_url import open_folder
from tests.ui.qml_harness import app


def test_opens_an_existing_folder_as_a_local_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app()
    seen: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: seen.append(url) is None)

    assert open_folder(tmp_path) is True
    assert [url.toLocalFile() for url in seen] == [str(tmp_path)]
    assert seen[0].scheme() == "file"


def test_refuses_anything_but_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app()
    seen: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: seen.append(url) is None)
    file = tmp_path / "note.md"
    file.write_text("x")

    assert open_folder(file) is False
    assert open_folder(tmp_path / "missing") is False
    assert seen == []
