"""Whisper smoke test helpers and packaging/recon-launch."""

import hashlib
import io
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Self

import pytest

from scripts.smoke import whisper

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "packaging" / "recon-launch"


# Helpers ----------------------------------------------------------------------


def test_cache_dir_follows_xdg(tmp_path: Path) -> None:
    assert whisper.cache_dir({}, tmp_path) == tmp_path / ".cache/recon/smoke"
    assert whisper.cache_dir({"XDG_CACHE_HOME": "/c"}, tmp_path) == Path("/c/recon/smoke")
    assert whisper.cache_dir({"XDG_CACHE_HOME": "rel"}, tmp_path) == tmp_path / ".cache/recon/smoke"


@pytest.mark.parametrize(
    ("text", "passed"),
    [
        (" And so, my fellow Americans, ask not.", True),
        ("AND SO MY FELLOW-AMERICANS", False),
        ("and so my   fellow  americans", True),
        ("And so, my yellow American", False),
        ("", False),
    ],
)
def test_check_transcript(text: str, *, passed: bool) -> None:
    assert whisper.check_transcript(text).passed is passed


def test_cublas_on_path() -> None:
    lib = "/r/.venv/lib/python3.13/site-packages/nvidia/cublas/lib"
    assert whisper.cublas_on_path({"LD_LIBRARY_PATH": f"/x:{lib}"})
    assert not whisper.cublas_on_path({"LD_LIBRARY_PATH": "/usr/lib"})
    assert not whisper.cublas_on_path({})


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _serve(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> list[str]:
    calls: list[str] = []

    def urlopen(url: str, timeout: float) -> _FakeResponse:
        calls.append(f"{url} {timeout}")
        return _FakeResponse(payload)

    monkeypatch.setattr(whisper.urllib.request, "urlopen", urlopen)
    return calls


def test_fetch_clip_verifies_and_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"fake flac"
    monkeypatch.setattr(whisper, "CLIP_SHA256", hashlib.sha256(payload).hexdigest())
    calls = _serve(monkeypatch, payload)

    first = whisper.fetch_clip(tmp_path / "smoke")
    second = whisper.fetch_clip(tmp_path / "smoke")

    assert first == second == tmp_path / "smoke/jfk.flac"
    assert first.read_bytes() == payload
    assert len(calls) == 1
    assert stat.S_IMODE((tmp_path / "smoke").stat().st_mode) == 0o700


def test_fetch_clip_rejects_a_bad_checksum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, b"tampered")

    with pytest.raises(ValueError, match="checksum mismatch"):
        whisper.fetch_clip(tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_clip_url_is_pinned_https() -> None:
    assert whisper.CLIP_URL.startswith("https://raw.githubusercontent.com/SYSTRAN/faster-whisper/")
    assert "/master/" not in whisper.CLIP_URL


# Launcher ---------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "packaging").mkdir(parents=True)
    shutil.copy2(LAUNCHER, repo / "packaging" / "recon-launch")
    for name in ("cublas", "cuda_nvrtc"):
        (repo / f".venv/lib/python3.13/site-packages/nvidia/{name}/lib").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_uv = bin_dir / "uv"
    fake_uv.write_text(
        "#!/bin/sh\n"
        # `uv sync` installs the voice wheels: create their lib folders, as uv would.
        'if [ "$1" = sync ]; then\n'
        '  echo "sync=$*"\n'
        '  mkdir -p "$PWD/.venv/lib/python3.13/site-packages/nvidia/cublas/lib"\n'
        "  exit 0\n"
        "fi\n"
        'echo "cwd=$(pwd)"\n'
        'echo "args=$*"\n'
        'echo "ld=$LD_LIBRARY_PATH"\n'
        'echo "cache=$CUDA_CACHE_MAXSIZE"\n'
        'echo "malware=$UV_MALWARE_CHECK"\n'
    )
    fake_uv.chmod(0o755)
    return repo


def _launch(repo: Path, *args: str, **env: str) -> dict[str, str]:
    environ = {
        "PATH": f"{repo.parent / 'bin'}:/usr/bin:/bin",
        "HOME": str(repo.parent),
        **env,
    }
    done = subprocess.run(  # noqa: S603 - the launcher under test, by full path
        [str(repo / "packaging" / "recon-launch"), *args],
        capture_output=True,
        text=True,
        env=environ,
        check=True,
        timeout=10,
    )
    return dict(line.split("=", 1) for line in done.stdout.splitlines())


def test_launcher_sets_cuda_paths_and_runs_recon(fake_repo: Path) -> None:
    out = _launch(fake_repo, "--screen", "revise")

    site = fake_repo / ".venv/lib/python3.13/site-packages/nvidia"
    assert out["ld"].split(":") == [str(site / "cublas/lib"), str(site / "cuda_nvrtc/lib")]
    assert out["args"] == "run --frozen --extra voice --no-sync python -m recon --screen revise"
    assert out["sync"] == "sync --frozen --extra voice --inexact --quiet"
    assert out["cwd"] == str(fake_repo)
    assert out["cache"] == "4294967296"
    assert out["malware"] == "1"


def test_launcher_keeps_existing_library_path_and_runs_another_module(fake_repo: Path) -> None:
    out = _launch(fake_repo, LD_LIBRARY_PATH="/opt/lib", RECON_MODULE="scripts.smoke.whisper")

    assert out["ld"].endswith(":/opt/lib")
    assert out["args"] == "run --frozen --extra voice --no-sync python -m scripts.smoke.whisper"


def test_first_launch_after_plain_sync_still_finds_cuda(fake_repo: Path) -> None:
    # A plain `uv sync` removed the voice wheels; the launcher must install them
    # before it builds LD_LIBRARY_PATH (audit F-06).
    shutil.rmtree(fake_repo / ".venv")

    out = _launch(fake_repo)

    cublas = fake_repo / ".venv/lib/python3.13/site-packages/nvidia/cublas/lib"
    assert out["ld"].split(":") == [str(cublas)]


def test_launcher_works_through_a_symlink(fake_repo: Path, tmp_path: Path) -> None:
    link = tmp_path / "bin" / "recon"
    link.symlink_to(fake_repo / "packaging" / "recon-launch")

    done = subprocess.run(  # noqa: S603 - the launcher under test, by full path
        [str(link)],
        capture_output=True,
        text=True,
        env={"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin", "HOME": str(tmp_path)},
        check=True,
        timeout=10,
    )

    assert f"cwd={fake_repo}" in done.stdout


def test_launcher_explains_a_missing_uv(fake_repo: Path, tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("dirname", "readlink"):
        found = shutil.which(name)
        assert found is not None
        (tools / name).symlink_to(found)
    done = subprocess.run(  # noqa: S603 - the launcher under test, by full path
        ["/bin/sh", str(fake_repo / "packaging" / "recon-launch")],
        capture_output=True,
        text=True,
        env={"PATH": str(tools), "HOME": str(tmp_path)},
        check=False,
        timeout=10,
    )

    assert done.returncode == 127
    assert "couldn't find uv" in done.stderr


def test_launcher_is_executable() -> None:
    assert os.access(LAUNCHER, os.X_OK)


# Real GPU (local only) ----------------------------------------------------------


@pytest.mark.gpu
@pytest.mark.slow
def test_real_whisper_on_cuda_through_the_launcher() -> None:
    done = subprocess.run(  # noqa: S603 - the launcher under test, by full path
        [str(LAUNCHER)],
        capture_output=True,
        text=True,
        env={**os.environ, "RECON_MODULE": "scripts.smoke.whisper"},
        check=False,
        timeout=600,
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert "PASS" in done.stdout
