"""Phase 1 acceptance: a fresh profile is private, and older files are fixed at launch.

Data and config folders are 0700 and their files 0600 (audit F-09, F-22).

Runs the real `python -m recon` start-up in a subprocess against throwaway XDG
folders, with the event loop replaced by an immediate return.
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Start Recon for real, but return from the event loop at once instead of waiting.
LAUNCH = (
    "import sys\n"
    "from PySide6.QtGui import QGuiApplication\n"
    "QGuiApplication.exec = lambda self: 0\n"
    "from recon.__main__ import main\n"
    "sys.exit(main([]))\n"
)


def _launch(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "QT_QPA_PLATFORM": "offscreen",
        "QT_QUICK_BACKEND": "software",
    }
    env.pop("QML_DISK_CACHE_PATH", None)
    return subprocess.run(  # noqa: S603 - this interpreter, a fixed script
        [sys.executable, "-c", LAUNCH],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _modes(root: Path) -> dict[str, int]:
    return {
        str(path.relative_to(root)): stat.S_IMODE(path.lstat().st_mode)
        for path in [root, *root.rglob("*")]
    }


def test_fresh_profile_is_private(tmp_path: Path) -> None:
    result = _launch(tmp_path)

    assert result.returncode == 0, result.stderr
    for root in (tmp_path / "data" / "recon", tmp_path / "config" / "recon"):
        modes = _modes(root)
        assert modes, root
        wrong = {
            name: oct(mode)
            for name, mode in modes.items()
            if mode != (0o700 if (root / name).is_dir() or name == "." else 0o600)
        }
        assert wrong == {}, root
    # Folders created on the way are private too (backups/ used to be 0755).
    assert stat.S_IMODE((tmp_path / "data" / "recon" / "backups").stat().st_mode) == 0o700
    # Qt's QML cache lives in Recon's private cache, not ~/.cache/Recon.
    assert not (tmp_path / "cache" / "Recon").exists()
    qmlcache = tmp_path / "cache" / "recon" / "qmlcache"
    assert list(qmlcache.glob("*.qmlc"))
    assert stat.S_IMODE(qmlcache.stat().st_mode) == 0o700


def test_older_files_are_locked_down_at_launch(tmp_path: Path) -> None:
    config = tmp_path / "config" / "recon"
    snapshots = tmp_path / "data" / "recon" / "backups" / "db"
    config.mkdir(parents=True)
    snapshots.mkdir(parents=True)
    (config / "settings.toml").write_text("panel_width = 420\n")
    (config / "settings.toml").chmod(0o644)
    old = snapshots / "app-2026-10-20.db"
    old.write_bytes(b"")
    old.chmod(0o644)
    (tmp_path / "data" / "recon" / "backups").chmod(0o755)

    result = _launch(tmp_path)

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE((config / "settings.toml").stat().st_mode) == 0o600
    assert stat.S_IMODE(old.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "data" / "recon" / "backups").stat().st_mode) == 0o700
