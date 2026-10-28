"""XDG path resolution and private permissions."""

import stat
from pathlib import Path

import pytest

from recon import errors
from recon.paths import (
    AppPaths,
    ensure_private_dir,
    ensure_private_file,
    private_opener,
    secure_tree,
)


def test_xdg_defaults_when_unset(tmp_path: Path) -> None:
    paths = AppPaths.from_environ({}, tmp_path)

    assert paths.data == tmp_path / ".local/share/recon"
    assert paths.config == tmp_path / ".config/recon"
    assert paths.cache == tmp_path / ".cache/recon"
    assert paths.log_file == tmp_path / ".local/share/recon/app.log"
    assert paths.runs == tmp_path / ".local/share/recon/runs"


def test_xdg_variables_respected(tmp_path: Path) -> None:
    env = {
        "XDG_DATA_HOME": str(tmp_path / "d"),
        "XDG_CONFIG_HOME": str(tmp_path / "c"),
        "XDG_CACHE_HOME": str(tmp_path / "k"),
    }
    paths = AppPaths.from_environ(env, tmp_path)

    assert paths.data == tmp_path / "d/recon"
    assert paths.config == tmp_path / "c/recon"
    assert paths.cache == tmp_path / "k/recon"


@pytest.mark.parametrize("value", ["", "relative/dir"])
def test_empty_or_relative_xdg_values_ignored(tmp_path: Path, value: str) -> None:
    paths = AppPaths.from_environ({"XDG_DATA_HOME": value}, tmp_path)

    assert paths.data == tmp_path / ".local/share/recon"


def test_fresh_profile_folders_are_0700(tmp_path: Path) -> None:
    paths = AppPaths.from_environ({}, tmp_path)
    paths.ensure()

    for folder in (paths.data, paths.config, paths.cache):
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700


def test_too_open_folder_is_locked_down(tmp_path: Path) -> None:
    folder = tmp_path / "open"
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)

    ensure_private_dir(folder)

    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


def test_unfixable_folder_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "open"
    folder.mkdir()
    folder.chmod(0o755)

    def refuse(_self: Path, _mode: int) -> None:
        raise PermissionError

    monkeypatch.setattr(Path, "chmod", refuse)

    with pytest.raises(errors.InsecurePermissionsError):
        ensure_private_dir(folder)


def test_private_opener_creates_0600(tmp_path: Path) -> None:
    target = tmp_path / "f"
    # Builtin open() because Path.open() has no `opener` parameter.
    with open(target, "w", opener=private_opener) as handle:
        handle.write("x")

    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_chmod_that_has_no_effect_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "open"
    folder.mkdir()
    folder.chmod(0o755)
    # Some filesystems accept chmod and ignore it.
    monkeypatch.setattr(Path, "chmod", lambda _self, _mode: None)

    with pytest.raises(errors.InsecurePermissionsError):
        ensure_private_dir(folder)


def test_ensure_private_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "f"
    ensure_private_file(path)  # missing: nothing to do
    assert not path.exists()

    path.write_text("x")
    path.chmod(0o644)
    ensure_private_file(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    path.chmod(0o644)
    monkeypatch.setattr(Path, "chmod", lambda _self, _mode: None)
    with pytest.raises(errors.InsecurePermissionsError):
        ensure_private_file(path)


def test_every_missing_level_is_created_private(tmp_path: Path) -> None:
    # Audit F-09: mkdir(parents=True) left the levels above the last at 0755.
    tmp_path.chmod(0o755)

    ensure_private_dir(tmp_path / "a" / "b" / "c")

    for level in (tmp_path / "a", tmp_path / "a" / "b", tmp_path / "a" / "b" / "c"):
        assert stat.S_IMODE(level.stat().st_mode) == 0o700
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o755  # existing parents aren't touched


def test_secure_tree_fixes_what_is_too_open_and_skips_symlinks(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir(mode=0o755)
    loose = tmp_path / "sub" / "notes.db"
    loose.write_text("x")
    loose.chmod(0o644)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("not Recon's")
    outside.chmod(0o644)
    (tmp_path / "link").symlink_to(outside)

    fixed = secure_tree(tmp_path)

    assert fixed == 2
    assert stat.S_IMODE((tmp_path / "sub").stat().st_mode) == 0o700
    assert stat.S_IMODE(loose.stat().st_mode) == 0o600
    assert stat.S_IMODE(outside.stat().st_mode) == 0o644  # never followed
    assert secure_tree(tmp_path) == 0


def test_a_file_where_the_folder_should_be_is_refused(tmp_path: Path) -> None:
    (tmp_path / "recon").write_text("not a folder")

    with pytest.raises(NotADirectoryError):
        ensure_private_dir(tmp_path / "recon")
