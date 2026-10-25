"""Atomic writes: old file or new file after any failure, never a mix (CLAUDE.md, Data safety)."""

import errno
import os
import stat
from pathlib import Path

import pytest

from recon import fs


def test_writes_new_file_privately(tmp_path: Path) -> None:
    target = tmp_path / "settings.toml"

    fs.atomic_write_text(target, "panel_width = 420\n")

    assert target.read_text() == "panel_width = 420\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_replaces_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "f"
    target.write_text("old")

    fs.atomic_write_bytes(target, b"new")

    assert target.read_bytes() == b"new"
    assert [p.name for p in tmp_path.iterdir()] == ["f"]


def test_custom_mode(tmp_path: Path) -> None:
    target = tmp_path / "note.md"

    fs.atomic_write_text(target, "x", mode=0o644)

    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_failed_replace_leaves_old_file_and_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "f"
    target.write_text("old")

    def broken_replace(_self: Path, _target: Path) -> Path:
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(Path, "replace", broken_replace)

    with pytest.raises(OSError, match="No space left"):
        fs.atomic_write_text(target, "new")

    assert target.read_text() == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["f"]


def test_failed_write_leaves_no_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_fsync(_fd: int) -> None:
        raise OSError(errno.EIO, os.strerror(errno.EIO))

    monkeypatch.setattr(os, "fsync", broken_fsync)

    with pytest.raises(OSError, match="Input/output error"):
        fs.atomic_write_text(tmp_path / "f", "new")

    assert list(tmp_path.iterdir()) == []


def test_file_and_folder_are_fsynced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    synced: list[int] = []
    real_fsync = os.fsync

    def recording_fsync(fd: int) -> None:
        synced.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", recording_fsync)

    fs.atomic_write_text(tmp_path / "f", "x")

    assert len(synced) == 2  # the temp file, then the folder after the rename


def test_atomic_create_never_replaces(tmp_path: Path) -> None:
    target = tmp_path / "note.md"
    fs.atomic_create_text(target, "first")

    with pytest.raises(FileExistsError):
        fs.atomic_create_text(target, "second")

    assert target.read_text() == "first"
    assert [p.name for p in tmp_path.iterdir()] == ["note.md"]
