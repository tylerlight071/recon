"""services.runs: run folders for raw model replies, private and kept 30 days."""

import json
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from recon.services.runs import KEEP_DAYS, RunLog, RunStore

NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)


def _store(root: Path, now: datetime = NOW) -> RunStore:
    ids = iter(["aaaa", "bbbb", "cccc"])
    return RunStore(root, lambda: now, lambda: next(ids))


def test_run_ids_start_with_the_time_so_they_sort_by_age(tmp_path: Path) -> None:
    store = _store(tmp_path / "runs")

    first, second = store.start(), store.start()

    assert first.run_id == "20261028T120000-aaaa"
    assert second.run_id == "20261028T120000-bbbb"
    assert first.folder == tmp_path / "runs" / first.run_id
    assert not first.folder.exists()  # nothing on disk until something is recorded


def test_record_writes_private_json(tmp_path: Path) -> None:
    run = _store(tmp_path / "runs").start()

    path = run.record("extract", 1, {"reply": "{}", "seconds": 1.5})

    assert path == run.folder / "extract-1.json"
    assert json.loads(path.read_text()) == {"reply": "{}", "seconds": 1.5}
    assert stat.S_IMODE(run.folder.stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "runs").stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("step", ["../escape", "a/b", "", "a b", ".hidden", "x\n"])
def test_step_names_cannot_leave_the_run_folder(tmp_path: Path, step: str) -> None:
    run = RunLog(tmp_path / "run")

    with pytest.raises(ValueError, match="step names"):
        run.record(step, 1, {})
    assert not (tmp_path / "escape-1.json").exists()


def test_prune_deletes_runs_older_than_thirty_days(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    old = _store(root, NOW - timedelta(days=KEEP_DAYS, seconds=1)).start()
    edge = _store(root, NOW - timedelta(days=KEEP_DAYS - 1)).start()
    for run in (old, edge):
        run.record("extract", 1, {})
    (root / "notes.txt").write_text("not a run")
    (root / "not-a-run").mkdir()

    removed = _store(root).prune()

    assert removed == 1
    assert not old.folder.exists()
    assert edge.folder.exists()
    assert (root / "notes.txt").exists()
    assert (root / "not-a-run").exists()


def test_prune_never_follows_a_symlink(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    root.mkdir()
    precious = tmp_path / "precious"
    precious.mkdir()
    (precious / "keep.md").write_text("mine")
    (root / "20200101T000000-link").symlink_to(precious)

    assert _store(root).prune() == 0
    assert (precious / "keep.md").read_text() == "mine"


def test_prune_without_a_runs_folder_does_nothing(tmp_path: Path) -> None:
    assert _store(tmp_path / "runs").prune() == 0
    assert not (tmp_path / "runs").exists()


def test_start_up_prunes_old_runs(tmp_path: Path) -> None:
    from recon.__main__ import prune_runs  # noqa: PLC0415 - start-up's own helper
    from recon.paths import AppPaths  # noqa: PLC0415

    paths = AppPaths.from_environ({}, tmp_path)
    old = paths.runs / "20200101T000000-abcd"
    old.mkdir(parents=True)

    prune_runs(paths)

    assert not old.exists()


def test_start_up_carries_on_when_a_run_will_not_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from recon.__main__ import prune_runs  # noqa: PLC0415 - start-up's own helper
    from recon.paths import AppPaths  # noqa: PLC0415

    def refuse(_self: RunStore, keep_days: int = KEEP_DAYS) -> int:
        raise PermissionError(keep_days)

    monkeypatch.setattr(RunStore, "prune", refuse)

    prune_runs(AppPaths.from_environ({}, tmp_path))

    assert "old runs not deleted: PermissionError" in caplog.text
