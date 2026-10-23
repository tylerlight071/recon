"""The per-package coverage gate script."""

import json
from pathlib import Path

from scripts.coverage_gates import check, main


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


def test_passes_when_every_package_meets_its_gate() -> None:
    report = {"files": {"recon/engine/a.py": _file(10, 10, 4, 3), "recon/ui.py": _file(10, 0)}}

    assert check(report) == []


def test_fails_a_package_below_90() -> None:
    report = {"files": {"recon/db/x.py": _file(10, 8, 0, 0), "recon/engine/y.py": _file(5, 5)}}

    assert check(report) == ["recon/db/: 80.0% < 90%"]


def test_branches_count_towards_the_gate() -> None:
    report = {"files": {"recon/services/s.py": _file(10, 10, 10, 7)}}

    assert check(report) == ["recon/services/: 85.0% < 90%"]


def test_empty_packages_are_skipped() -> None:
    assert check({"files": {"recon/revision/__init__.py": _file(0, 0)}}) == []


def test_malformed_report() -> None:
    assert check({"files": []}) == ["coverage report has no 'files' mapping"]


def test_main_exit_codes(tmp_path: Path) -> None:
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps({"files": {}}))
    bad.write_text(json.dumps({"files": {"recon/db/x.py": _file(10, 1)}}))

    assert main([str(good)]) == 0
    assert main([str(bad)]) == 1
    assert main([]) == 2
