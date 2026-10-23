"""XDG path resolution and private permissions."""

import stat
from pathlib import Path

import pytest

from recon import errors
from recon.paths import AppPaths, ensure_private_dir, private_opener


def test_xdg_defaults_when_unset(tmp_path: Path) -> None:
    paths = AppPaths.from_environ({}, tmp_path)

    assert paths.data == tmp_path / ".local/share/recon"
    assert paths.config == tmp_path / ".config/recon"
    assert paths.cache == tmp_path / ".cache/recon"
    assert paths.log_file == tmp_path / ".local/share/recon/app.log"


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
