"""Writing the export: never overwrites, stays in the folder, private, flag-free."""

import stat
from datetime import date
from pathlib import Path

import pytest

from recon.engine.export import export_room
from recon.engine.render import ExportBlock, ExportRoom, ExportTask
from recon.errors import ExportFailedError, ExportFolderMissingError


def _room(name: str = "DNS in Detail", text: str = "A records point at IPv4") -> ExportRoom:
    return ExportRoom(
        name=name,
        platform="TryHackMe",
        path="",
        module="",
        finished_on=date(2026, 10, 25),
        time_spent_s=600,
        tasks=(
            ExportTask(
                index=1, title="", status="done", blocks=(ExportBlock(type="key_idea", text=text),)
            ),
        ),
    )


def test_writes_one_private_markdown_file(tmp_path: Path) -> None:
    path = export_room(_room(), tmp_path)

    assert path == tmp_path.resolve() / "DNS in Detail.md"
    assert path.read_text(encoding="utf-8").startswith("# DNS in Detail\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["DNS in Detail.md"]  # no temp files left


def test_never_overwrites(tmp_path: Path) -> None:
    (tmp_path / "DNS in Detail.md").write_text("The user's own file")

    second = export_room(_room(), tmp_path)
    third = export_room(_room(), tmp_path)

    assert (second.name, third.name) == ("DNS in Detail (2).md", "DNS in Detail (3).md")
    assert (tmp_path / "DNS in Detail.md").read_text() == "The user's own file"


@pytest.mark.parametrize("name", ["../../escape", "/etc/passwd", "..", "a/../../b", "CON"])
def test_hostile_names_stay_in_the_folder(tmp_path: Path, name: str) -> None:
    folder = tmp_path / "exports"
    folder.mkdir()

    path = export_room(_room(name=name), folder)

    assert path.parent == folder.resolve()
    assert list(tmp_path.iterdir()) == [folder]


def test_flags_never_reach_the_file(tmp_path: Path) -> None:
    path = export_room(_room(text="answer THM{secret_flag}"), tmp_path)

    assert "THM{" not in path.read_text(encoding="utf-8")


def test_a_missing_folder_says_so(tmp_path: Path) -> None:
    with pytest.raises(ExportFolderMissingError):
        export_room(_room(), tmp_path / "gone")


def test_an_unwritable_folder_fails_cleanly(tmp_path: Path) -> None:
    folder = tmp_path / "locked"
    folder.mkdir()
    folder.chmod(0o500)
    try:
        with pytest.raises(ExportFailedError):
            export_room(_room(), folder)
    finally:
        folder.chmod(0o700)
    assert list(folder.iterdir()) == []


def test_gives_up_after_too_many_copies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("recon.engine.export.MAX_COPIES", 2)
    export_room(_room(), tmp_path)
    export_room(_room(), tmp_path)

    with pytest.raises(ExportFailedError):
        export_room(_room(), tmp_path)
