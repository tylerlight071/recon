"""Opening a folder in the file manager, or a note in Obsidian: local things only."""

from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from recon.services.open_url import obsidian_url, open_folder, open_in_obsidian
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


def test_the_obsidian_link_encodes_every_reserved_character(tmp_path: Path) -> None:
    note = tmp_path / "Cyber Vault" / "DNS & más #1?.md"

    url = obsidian_url(note)

    assert url.startswith("obsidian://open?path=%2F")
    assert "%20Vault%2F" in url
    assert url.endswith("DNS%20%26%20m%C3%A1s%20%231%3F.md")
    assert " " not in url
    assert "#" not in url.removeprefix("obsidian://open?path=")


def test_opens_a_note_in_obsidian(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app()
    seen: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: seen.append(url) is None)
    note = tmp_path / "Room.md"
    note.write_text("# Room")

    assert open_in_obsidian(note) is True
    assert [url.scheme() for url in seen] == ["obsidian"]
    assert seen[0].toString(QUrl.ComponentFormattingOption.FullyEncoded) == obsidian_url(note)


@pytest.mark.parametrize("name", ["missing.md", "note.txt"])
def test_only_existing_markdown_notes_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    app()
    seen: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: seen.append(url) is None)
    (tmp_path / "note.txt").write_text("x")

    assert open_in_obsidian(tmp_path / name) is False
    assert seen == []
