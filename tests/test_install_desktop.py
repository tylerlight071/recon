"""The app-menu installer: valid entry named by the app ID, careful uninstall."""

import shutil
import stat
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from recon.config import APP_ID
from scripts import install_desktop
from scripts.install_desktop import (
    ICON,
    LAUNCHER,
    data_home,
    exec_quote,
    install,
    main,
    refresh_menu,
    render_entry,
    targets,
    uninstall,
)


def _keys(entry: Path) -> dict[str, str]:
    lines = entry.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "[Desktop Entry]"
    return dict(line.split("=", 1) for line in lines[1:] if line)


def test_data_home_follows_xdg(tmp_path: Path) -> None:
    assert data_home({}, tmp_path) == tmp_path / ".local" / "share"
    assert data_home({"XDG_DATA_HOME": "relative"}, tmp_path) == tmp_path / ".local" / "share"
    assert data_home({"XDG_DATA_HOME": "/x/share"}, tmp_path) == Path("/x/share")


@pytest.mark.parametrize(
    ("path", "quoted"),
    [
        (
            "/data/projects/Recon/packaging/recon-launch",
            "/data/projects/Recon/packaging/recon-launch",
        ),
        ("/home/t/My Projects/recon-launch", '"/home/t/My Projects/recon-launch"'),
        ('/a"b/$x/`c`', '"/a\\\\"b/\\\\$x/\\\\`c\\\\`"'),
        ("/a\\b", '"/a\\\\\\\\b"'),
    ],
)
def test_exec_quoting(path: str, quoted: str) -> None:
    assert exec_quote(Path(path)) == quoted


def test_install_writes_an_entry_named_by_the_app_id(tmp_path: Path) -> None:
    entry, icon = install(tmp_path)

    assert (entry, icon) == targets(tmp_path)
    assert entry.name == f"{APP_ID}.desktop"
    keys = _keys(entry)
    assert keys["Exec"] == str(LAUNCHER)
    assert keys["Icon"] == keys["StartupWMClass"] == APP_ID
    assert keys["Terminal"] == "false"
    assert keys["Name"] == "Recon"
    assert icon.read_bytes() == ICON.read_bytes()
    assert ET.parse(icon).getroot().tag.endswith("svg")  # noqa: S314 - our own committed file
    for path in (entry, icon):
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert LAUNCHER.stat().st_mode & stat.S_IXUSR


@pytest.mark.skipif(shutil.which("desktop-file-validate") is None, reason="desktop-file-utils")
def test_the_entry_passes_desktop_file_validate(tmp_path: Path) -> None:
    entry, _icon = install(tmp_path)

    result = subprocess.run(  # noqa: S603 - fixed validator, temp file
        [shutil.which("desktop-file-validate") or "", str(entry)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == ""  # no hints either


def test_reinstalling_is_fine_and_follows_a_moved_checkout(tmp_path: Path) -> None:
    install(tmp_path)
    entry, _icon = install(tmp_path, launcher=Path("/elsewhere/My Recon/packaging/recon-launch"))

    assert _keys(entry)["Exec"] == '"/elsewhere/My Recon/packaging/recon-launch"'
    assert render_entry(LAUNCHER).count("Exec=") == 1


def test_uninstall_removes_only_what_it_installed(tmp_path: Path) -> None:
    entry, icon = install(tmp_path)

    assert uninstall(tmp_path) == [entry, icon]
    assert not entry.exists()
    assert not icon.exists()
    assert uninstall(tmp_path) == []


def test_uninstall_leaves_someone_elses_file(tmp_path: Path) -> None:
    entry, _icon = targets(tmp_path)
    entry.parent.mkdir(parents=True)
    entry.write_text("[Desktop Entry]\nName=Not ours\n")

    assert uninstall(tmp_path) == []
    assert entry.exists()


def test_refresh_runs_only_tools_that_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sycoca = tmp_path / "kbuildsycoca6"
    sycoca.write_text("")
    calls: list[list[str]] = []
    monkeypatch.setattr(install_desktop, "REFRESH", (str(sycoca), str(tmp_path / "missing")))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **_kw: calls.append(args) or subprocess.CompletedProcess(args, 0),
    )

    refresh_menu(tmp_path)

    assert calls == [[str(sycoca), "--noincremental"]]


def test_main_installs_and_uninstalls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    assert main(["--no-refresh"]) == 0
    assert targets(tmp_path)[0].exists()
    assert main(["--uninstall", "--no-refresh"]) == 0
    assert not targets(tmp_path)[0].exists()
    assert main(["--uninstall", "--no-refresh"]) == 0

    out = capsys.readouterr().out
    assert "Installed:" in out
    assert "Removed:" in out
    assert "Nothing of Recon's to remove." in out
