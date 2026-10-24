"""The pre-push hook that stands in for branch protection on GitHub Free (audit F-02)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "scripts" / "hooks" / "pre-push"
ZERO = "0" * 40
A, B = "a" * 40, "b" * 40
GIT = shutil.which("git") or "/usr/bin/git"


def _hook(stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - the hook under test, by full path
        [str(HOOK), "origin", "https://example.invalid/recon.git"],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


@pytest.mark.parametrize(
    "stdin",
    [
        f"refs/heads/main {A} refs/heads/main {B}\n",
        f"refs/heads/feat/x {A} refs/heads/feat/x {B}\nrefs/heads/main {A} refs/heads/main {B}\n",
        f"refs/heads/main {A} refs/heads/main {B}\nrefs/heads/feat/x {A} refs/heads/feat/x {B}\n",
        f"(delete) {ZERO} refs/heads/main {B}\n",
        f"HEAD {A} refs/heads/main {B}\n",
        f"refs/heads/feat/x {A} refs/heads/main {ZERO}\n",
    ],
    ids=[
        "update",
        "second-of-two",
        "first-of-two",
        "delete",
        "head-colon-main",
        "branch-onto-main",
    ],
)
def test_any_ref_targeting_main_is_refused(stdin: str) -> None:
    done = _hook(stdin)

    assert done.returncode == 1
    assert "Pushing to main is blocked" in done.stderr


@pytest.mark.parametrize(
    "stdin",
    [
        "",
        f"refs/heads/feat/x {A} refs/heads/feat/x {B}\n",
        f"refs/tags/v0.0.0 {A} refs/tags/v0.0.0 {ZERO}\n",
        f"refs/heads/mainline {A} refs/heads/mainline {B}\n",
        f"(delete) {ZERO} refs/heads/feat/old {B}\n",
    ],
    ids=["nothing", "branch", "tag", "similar-name", "delete-branch"],
)
def test_other_refs_are_allowed(stdin: str) -> None:
    assert _hook(stdin).returncode == 0


def test_hook_is_executable() -> None:
    assert os.access(HOOK, os.X_OK)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    return subprocess.run(  # noqa: S603 - git by full path, fixed arguments
        [GIT, *args], cwd=cwd, capture_output=True, text=True, check=False, env=env, timeout=30
    )


def _commit(work: Path, name: str) -> None:
    (work / name).write_text(name)
    _git(work, "add", name)
    _git(work, "commit", "-qm", name)


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    # Let the remote accept a delete of main, so only the hook can stop it.
    _git(remote, "config", "receive.denyDeleteCurrent", "ignore")
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    _commit(work, "first")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "origin", "main")
    _git(work, "switch", "-qc", "feat/x")
    _commit(work, "branch")
    _git(work, "push", "-q", "origin", "feat/x")
    hooks = work / ".git" / "hooks"
    (hooks / "pre-push").symlink_to(HOOK)
    _git(work, "switch", "-q", "main")
    _commit(work, "second")
    _git(work, "switch", "-q", "feat/x")
    _commit(work, "third")
    return work


def _remote_main(work: Path) -> str:
    return _git(work.parent / "remote.git", "rev-parse", "main").stdout.strip()


@pytest.mark.parametrize(
    "args",
    [
        ["origin", "main"],
        ["origin", "feat/x", "main"],
        ["--all", "origin"],
        ["origin", "feat/x:main"],
        ["origin", "--delete", "main"],
    ],
    ids=["main", "multi-ref", "all", "branch-onto-main", "delete"],
)
def test_real_git_push_cannot_change_main(clone: Path, args: list[str]) -> None:
    before = _remote_main(clone)

    done = _git(clone, "push", *args)

    assert done.returncode != 0
    assert "Pushing to main is blocked" in done.stderr
    assert _remote_main(clone) == before


def test_real_git_push_of_a_branch_works(clone: Path) -> None:
    done = _git(clone, "push", "origin", "feat/x")

    assert done.returncode == 0, done.stderr


def test_installer_links_the_hook() -> None:
    text = (REPO / "scripts" / "install-hooks").read_text()

    assert 'ln -sf "$repo/scripts/hooks/pre-push"' in text
    assert "--hook-type pre-commit --hook-type commit-msg" in text
    assert os.access(REPO / "scripts" / "install-hooks", os.X_OK)
    assert "pre-push" not in (REPO / ".pre-commit-config.yaml").read_text().split("repos:")[0]
