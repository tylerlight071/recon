"""The per-package coverage gate script (audit F-05)."""

import json
from pathlib import Path

import pytest

from scripts.coverage_gates import GATES, GateResult, check, main, normalise, python_files

NOTHING_ON_DISK: dict[str, tuple[str, ...]] = dict.fromkeys(GATES, ())


def _file(
    lines: int, covered: int, branches: int = 0, covered_branches: int = 0
) -> dict[str, object]:
    return {
        "summary": {
            "num_statements": lines,
            "covered_lines": covered,
            "num_branches": branches,
            "covered_branches": covered_branches,
        }
    }


def _by_prefix(results: list[GateResult]) -> dict[str, GateResult]:
    return {result.prefix: result for result in results}


def test_passes_when_every_package_meets_its_gate() -> None:
    report = {"files": {"recon/engine/a.py": _file(10, 10, 4, 3), "recon/ui.py": _file(10, 0)}}

    results = _by_prefix(check(report, NOTHING_ON_DISK))

    assert all(result.passed for result in results.values())
    assert results["recon/engine/"].line() == "recon/engine/: 92.9% (gate 90%) OK"
    assert results["recon/db/"].line() == "recon/db/: no code yet (gate 90%)"


def test_fails_a_package_below_90() -> None:
    report = {"files": {"recon/db/x.py": _file(10, 8), "recon/engine/y.py": _file(5, 5)}}

    db = _by_prefix(check(report, NOTHING_ON_DISK))["recon/db/"]

    assert not db.passed
    assert db.line() == "recon/db/: 80.0% (gate 90%) BELOW GATE"


def test_branches_count_towards_the_gate() -> None:
    report = {"files": {"recon/services/s.py": _file(10, 10, 10, 7)}}

    assert not _by_prefix(check(report, NOTHING_ON_DISK))["recon/services/"].passed


@pytest.mark.parametrize(
    "key",
    [
        "./recon/db/x.py",
        "/home/runner/work/recon/recon/recon/db/x.py",
        "recon/db/x.py",
    ],
)
def test_keys_are_normalised_so_gates_cannot_be_skipped(key: str) -> None:
    root = Path("/home/runner/work/recon/recon")
    assert normalise(key, root) == "recon/db/x.py"


def test_absolute_key_outside_the_repo_is_kept_as_is() -> None:
    assert normalise("/elsewhere/recon/db/x.py", Path("/repo")) == "/elsewhere/recon/db/x.py"


def test_absolute_keys_from_this_repo_are_gated() -> None:
    from scripts.coverage_gates import REPO_ROOT  # noqa: PLC0415 - the real root for this case

    report = {"files": {str(REPO_ROOT / "recon/db/x.py"): _file(100, 0)}}

    assert not _by_prefix(check(report, NOTHING_ON_DISK))["recon/db/"].passed


def test_code_on_disk_missing_from_the_report_fails() -> None:
    on_disk = {**NOTHING_ON_DISK, "recon/engine/": ("recon/engine/link.py",)}

    engine = _by_prefix(check({"files": {}}, on_disk))["recon/engine/"]

    assert not engine.passed
    assert engine.line() == "recon/engine/: not measured: recon/engine/link.py"


def test_python_files_lists_a_package(tmp_path: Path) -> None:
    (tmp_path / "recon/engine/factcheck").mkdir(parents=True)
    (tmp_path / "recon/engine/a.py").touch()
    (tmp_path / "recon/engine/factcheck/b.py").touch()
    (tmp_path / "recon/engine/notes.md").touch()

    assert python_files(tmp_path, "recon/engine/") == [
        "recon/engine/a.py",
        "recon/engine/factcheck/b.py",
    ]
    assert python_files(tmp_path, "recon/missing/") == []


def test_malformed_report() -> None:
    with pytest.raises(ValueError, match="no 'files' mapping"):
        check({"files": []}, NOTHING_ON_DISK)


def test_real_repo_packages_are_all_in_the_report(tmp_path: Path) -> None:
    # Every gated .py file in this repo must appear in a report built from it.
    from scripts.coverage_gates import REPO_ROOT  # noqa: PLC0415

    files = {name: _file(0, 0) for prefix in GATES for name in python_files(REPO_ROOT, prefix)}
    report_path = tmp_path / "c.json"
    report_path.write_text(json.dumps({"files": files}))

    assert main([str(report_path)]) == 0


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad, broken = tmp_path / "bad.json", tmp_path / "broken.json"
    bad.write_text(json.dumps({"files": {"recon/db/x.py": _file(10, 1)}}))
    broken.write_text(json.dumps({"nope": 1}))

    assert main([str(bad)]) == 1
    assert "per-package coverage gates: FAILED" in capsys.readouterr().out
    assert main([str(broken)]) == 2
    assert main([]) == 2
