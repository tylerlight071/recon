"""Enforce per-package branch coverage gates from a coverage JSON report.

CLAUDE.md requires at least 90% for engine/, db/, revision/ and services/, and
80% overall (the overall gate is `fail_under` in pyproject.toml). coverage.py
has no per-package threshold, so CI runs `coverage json` and then this script.

Usage:
    uv run python scripts/coverage_gates.py coverage.json
"""

import json
import sys
from pathlib import Path

GATES: dict[str, float] = {
    "recon/engine/": 90.0,
    "recon/db/": 90.0,
    "recon/revision/": 90.0,
    "recon/services/": 90.0,
}


def package_percent(files: dict[str, dict[str, dict[str, int]]], prefix: str) -> float | None:
    """Combined line-plus-branch coverage for every file under `prefix`.

    Args:
        files: The `files` mapping from a coverage JSON report.
        prefix: Package folder, relative to the repo root, with a trailing slash.

    Returns:
        The percentage, or None when the package has nothing measurable yet.
    """
    covered = total = 0
    for name, data in files.items():
        if name.startswith(prefix):
            summary = data["summary"]
            covered += summary["covered_lines"] + summary.get("covered_branches", 0)
            total += summary["num_statements"] + summary.get("num_branches", 0)
    return None if total == 0 else 100.0 * covered / total


def check(report: dict[str, object]) -> list[str]:
    """Return one failure line per package below its gate.

    Args:
        report: A parsed coverage JSON report.

    Returns:
        Failure messages; empty when every gate holds.
    """
    files = report["files"]
    if not isinstance(files, dict):
        return ["coverage report has no 'files' mapping"]
    failures: list[str] = []
    for prefix, gate in GATES.items():
        percent = package_percent(files, prefix)
        if percent is not None and percent < gate:
            failures.append(f"{prefix}: {percent:.1f}% < {gate:.0f}%")
    return failures


def main(argv: list[str]) -> int:
    """Read the report named in `argv` and print the result.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        Process exit code: 0 when all gates hold.
    """
    if len(argv) != 1:
        print(__doc__)
        return 2
    report = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    failures = check(report)
    for line in failures:
        print(f"coverage gate failed: {line}")
    if not failures:
        print("per-package coverage gates: OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
