"""Phase 2 acceptance: killing the process mid-Apply leaves the vault before or after, never half.

A child process applies a staged run and SIGKILLs itself just after its Nth
vault write. Start-up's `recover` then finishes the Apply: every note matches
what was staged. Killed before the first write, the vault is exactly as before.
"""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from recon.engine.extract import check
from recon.engine.notes import render_room
from recon.engine.stage import load_journal, load_manifest, recover, stage
from tests.engine.pipeline import capture_of, recorded

REPO = Path(__file__).resolve().parents[2]

CHILD = """
import os, signal, sys
from pathlib import Path
from recon.engine import stage as module

vault, run, backups = (Path(arg) for arg in sys.argv[1:4])
after = int(sys.argv[4])
vault_root = vault.resolve()
writes = 0


def counting(real):
    def write(path, *args, **kwargs):
        global writes
        real(path, *args, **kwargs)
        if vault_root in Path(path).resolve().parents:
            writes += 1
            if writes == after:
                os.kill(os.getpid(), signal.SIGKILL)
    return write


module.atomic_write_text = counting(module.atomic_write_text)
module.atomic_create_text = counting(module.atomic_create_text)
if after == 0:
    def journal_then_die(run_folder, journal):
        os.kill(os.getpid(), signal.SIGKILL)
    module._write_journal = journal_then_die
module.apply(run, vault, backups)
print("finished")
"""


def _staged(tmp_path: Path) -> tuple[Path, Path, Path]:
    vault, run, backups = (
        tmp_path / "vault",
        tmp_path / "runs" / "20261028T120000-ab",
        tmp_path / "b",
    )
    (vault / "02 Concepts").mkdir(parents=True)
    (vault / "02 Concepts" / "Binary.md").write_text(
        "# Binary\n\nMine.\n\n%% recon:start definition %%\nold\n%% recon:end %%\n"
    )
    capture = capture_of("number_systems")
    stage(render_room(capture, check(recorded("number_systems"), capture)), vault, run, room_id=1)
    return vault, run, backups


def _kill_after(vault: Path, run: Path, backups: Path, writes: int) -> None:
    result = subprocess.run(  # noqa: S603 - this interpreter, a fixed script
        [sys.executable, "-c", CHILD, str(vault), str(run), str(backups), str(writes)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == -9, result.stderr
    assert "finished" not in result.stdout


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*.md")}


@pytest.mark.parametrize("writes", [1, 2, 3])
def test_killed_mid_apply_then_recovered_is_fully_applied(tmp_path: Path, writes: int) -> None:
    vault, run, backups = _staged(tmp_path)

    _kill_after(vault, run, backups, writes)
    assert load_journal(run) is not None
    recovered = recover(run, vault)
    assert recovered is not None
    assert recovered.backed_up == 1  # Binary.md, copied before the first write

    for file in load_manifest(run).to_write:
        digest = hashlib.sha256((vault / file.path).read_bytes()).hexdigest()
        assert digest == file.sha256, file.path
    assert (
        (backups / run.name / "02 Concepts" / "Binary.md")
        .read_text()
        .endswith("old\n%% recon:end %%\n")
    )
    assert not list(vault.rglob(".*.tmp"))


def test_killed_before_any_write_leaves_the_vault_as_it_was(tmp_path: Path) -> None:
    vault, run, backups = _staged(tmp_path)
    before = _snapshot(vault)

    _kill_after(vault, run, backups, 0)

    assert _snapshot(vault) == before
    assert recover(run, vault) is None
