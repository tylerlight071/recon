"""Enforce per-package branch coverage gates from a coverage JSON report.

CLAUDE.md requires at least 90% for engine/, db/, revision/ and services/, and
80% overall (the overall gate is `fail_under` in pyproject.toml). coverage.py
has no per-package threshold, so CI runs `coverage json` and then this script.

It prints one line per gated package, so a pass always says what was checked,
and it fails if a package has Python files on disk that the report never
measured (a wrong `source`, a path mismatch, a file no test imports).

Usage:
    uv run python scripts/coverage_gates.py coverage.json
"""

import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
GATES: dict[str, float] = {
    "recon/engine/": 90.0,
    "recon/db/": 90.0,
    "recon/revision/": 90.0,
    "recon/services/": 90.0,
}

type Summary = Mapping[str, int]


@dataclass(frozen=True, slots=True)
class GateResult:
    """Outcome for one gated package."""

    prefix: str
    gate: float
    percent: float | None
    """None when the package has nothing measurable yet."""
    unmeasured: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """True when nothing is unmeasured and the gate holds (or there's no code yet)."""
        return not self.unmeasured and (self.percent is None or self.percent >= self.gate)

    def line(self) -> str:
        """One human-readable line for the CI log."""
        if self.unmeasured:
            return f"{self.prefix}: not measured: {', '.join(self.unmeasured)}"
        if self.percent is None:
            return f"{self.prefix}: no code yet (gate {self.gate:.0f}%)"
        verdict = "OK" if self.passed else "BELOW GATE"
        return f"{self.prefix}: {self.percent:.1f}% (gate {self.gate:.0f}%) {verdict}"


def normalise(name: str, root: Path = REPO_ROOT) -> str:
    """Report key as a POSIX path relative to the repo root.

    Args:
        name: A key from the report's `files` mapping (relative, `./`-prefixed or absolute).
        root: Repository root that absolute keys are made relative to.

    Returns:
        e.g. "recon/engine/link.py".
    """
    path = Path(name)
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            return PurePosixPath(path).as_posix()
    return PurePosixPath(*path.parts).as_posix().removeprefix("./")


def package_percent(summaries: Mapping[str, Summary], prefix: str) -> float | None:
    """Combined line-plus-branch coverage for every file under `prefix`.

    Args:
        summaries: Normalised file name -> coverage summary.
        prefix: Package folder, relative to the repo root, with a trailing slash.

    Returns:
        The percentage, or None when the package has nothing measurable yet.
    """
    covered = total = 0
    for name, summary in summaries.items():
        if name.startswith(prefix):
            covered += summary["covered_lines"] + summary.get("covered_branches", 0)
            total += summary["num_statements"] + summary.get("num_branches", 0)
    return None if total == 0 else 100.0 * covered / total


def python_files(root: Path, prefix: str) -> list[str]:
    """Repo-relative paths of the .py files under a package folder on disk."""
    folder = root / prefix
    if not folder.is_dir():
        return []
    return sorted(path.relative_to(root).as_posix() for path in folder.rglob("*.py"))


def check(
    report: Mapping[str, object], on_disk: Mapping[str, Iterable[str]] | None = None
) -> list[GateResult]:
    """Evaluate every gate.

    Args:
        report: A parsed coverage JSON report.
        on_disk: Gated prefix -> .py files that exist; defaults to scanning the repo.

    Returns:
        One result per gated package, in GATES order.

    Raises:
        ValueError: The report has no `files` mapping.
    """
    files = report.get("files")
    if not isinstance(files, dict):
        msg = "coverage report has no 'files' mapping"
        raise ValueError(msg)  # noqa: TRY004 - a malformed report is bad input, not a type error
    summaries = {normalise(name): data["summary"] for name, data in files.items()}
    results = []
    for prefix, gate in GATES.items():
        expected = on_disk[prefix] if on_disk is not None else python_files(REPO_ROOT, prefix)
        unmeasured = tuple(name for name in expected if name not in summaries)
        results.append(GateResult(prefix, gate, package_percent(summaries, prefix), unmeasured))
    return results


def main(argv: list[str]) -> int:
    """Read the report named in `argv` and print one line per gate.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        Process exit code: 0 when all gates hold, 1 when any fails, 2 on bad input.
    """
    if len(argv) != 1:
        print(__doc__)
        return 2
    try:
        results = check(json.loads(Path(argv[0]).read_text(encoding="utf-8")))
    except ValueError as exc:
        print(f"coverage gates: {exc}")
        return 2
    for result in results:
        print(result.line())
    failed = [result for result in results if not result.passed]
    print("per-package coverage gates: " + ("FAILED" if failed else "OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
