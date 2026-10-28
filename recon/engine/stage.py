"""Staging, Apply, Discard and backups: the only way room output reaches the vault.

Hard rules this module keeps (CLAUDE.md):

- **3. Nothing reaches the vault without Apply.** `stage` writes only under the
  run's folder (`runs/<run id>/staged/`). Only `apply` writes into the vault.
- **4. Raw notes are never changed.** A raw note that already exists is never
  updated: a re-run's raw notes get a new file ("… (raw notes 2).md"), and the
  room note links to that one.
- **6. Back up before overwriting.** Apply copies every file it will replace to
  `backups/<run id>/` first. `prune_backups` keeps the newest 20 runs.
- **8. Only edit inside markers.** Updating an existing note replaces the
  inside of its `%% recon:start <name> %%` … `%% recon:end %%` sections and
  adds sections it lacks at the end. Nothing outside the markers changes,
  frontmatter included. A note whose markers are damaged is skipped and listed.
- **9. Stop on conflict.** Staging records each target's SHA-256 (or that it
  didn't exist). Apply re-hashes every target first and writes nothing if any
  changed.

Crash safety: every write is atomic (`fs`). Apply records its plan in
`apply.json` before the first vault write and marks it done after the last, so
`recover` can finish an Apply a crash interrupted: the vault ends up fully
applied, never half. A file changed by hand since then is left alone.
"""

import hashlib
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from recon.engine.notes import RAW_SUFFIX, NoteKind, Rendered, RenderedNote
from recon.errors import ApplyConflict, StagingDamagedError, UnsafePathError
from recon.fs import atomic_create_text, atomic_write_bytes, atomic_write_text
from recon.paths import ensure_private_dir

STAGED: Final = "staged"
MANIFEST: Final = "manifest.json"
JOURNAL: Final = "apply.json"
KEEP_BACKUPS: Final = 20
MAX_RAW_COPIES: Final = 99

type Action = Literal["create", "update", "same", "skip"]

_SECTION: Final = re.compile(
    r"^%% recon:start (?P<name>[a-z0-9-]+) %%\n(?P<body>.*?)^%% recon:end %%$",
    re.MULTILINE | re.DOTALL,
)
_MARKER_LINE: Final = re.compile(r"^%% recon:(?:start [a-z0-9-]+|end) %%$", re.MULTILINE)
_HEADING: Final = re.compile(r"^#{1,6} .*$", re.MULTILINE)
_RUN_ID: Final = re.compile(r"^\d{8}T\d{6}-[0-9a-f]{1,32}$")
"""A run folder's name (`services.runs`): UTC time, then a random hex ID."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StagedFile(_Model):
    """One vault file a run will create or change."""

    path: str
    """Relative to the vault, with forward slashes."""
    kind: NoteKind
    action: Action
    base_sha256: str | None
    """The vault file's hash when staged (None: it didn't exist)."""
    sha256: str
    """The staged content's hash."""


class Manifest(_Model):
    """Everything Apply needs, written beside the staged files."""

    run_id: str = Field(min_length=1, max_length=64)
    room_id: int
    files: tuple[StagedFile, ...]

    @property
    def to_write(self) -> tuple[StagedFile, ...]:
        """Files Apply writes (new or changed)."""
        return tuple(f for f in self.files if f.action in {"create", "update"})

    @property
    def skipped(self) -> tuple[StagedFile, ...]:
        """Notes left alone because their markers are damaged (shown on the review screen)."""
        return tuple(f for f in self.files if f.action == "skip")


class Journal(_Model):
    """`apply.json`: Apply's progress, for finishing it after a crash."""

    state: Literal["applying", "applied"]
    written: int = 0
    backed_up: int = 0


@dataclass(frozen=True, slots=True)
class Applied:
    """What Apply did."""

    written: int
    backed_up: int


# ---- Stage -------------------------------------------------------------------------------------


def stage(rendered: Rendered, vault: Path, run_folder: Path, *, room_id: int) -> Manifest:
    """Write the run's notes to `run_folder/staged/`, never the vault.

    Args:
        rendered: The notes from the render step.
        vault: The vault folder (only read here).
        run_folder: `runs/<run id>/`; its name is the run ID.
        room_id: The room the run is for.

    Returns:
        The manifest, also saved as `staged/manifest.json`.

    Raises:
        UnsafePathError: A note's path would land outside the vault.
    """
    staged = run_folder / STAGED
    ensure_private_dir(staged)
    notes = _with_raw_name(rendered.notes, vault)
    files = [_stage_note(note, vault, staged) for note in notes]
    manifest = Manifest(run_id=run_folder.name, room_id=room_id, files=tuple(files))
    atomic_write_text(staged / MANIFEST, manifest.model_dump_json() + "\n")
    return manifest


def _stage_note(note: RenderedNote, vault: Path, staged: Path) -> StagedFile:
    relative = _relative(note.path)
    target = inside(vault, relative)
    existing = target.read_bytes() if target.is_file() else None
    text = note.text
    action: Action = "create"
    if existing is not None:
        merged = _merge_bytes(existing, note.text)
        if merged is None:
            action = "skip"
        else:
            text = merged
            action = "same" if merged.encode() == existing else "update"
    destination = inside(staged, relative)
    ensure_private_dir(destination.parent)
    atomic_write_text(destination, text)
    return StagedFile(
        path=relative.as_posix(),
        kind=note.kind,
        action=action,
        base_sha256=None if existing is None else _sha256(existing),
        sha256=_sha256(text.encode()),
    )


def _merge_bytes(existing: bytes, new: str) -> str | None:
    """`merge` for a file on disk; None (leave it alone) if it isn't valid UTF-8.

    Decoding with replacement characters and writing back would change the user's
    text outside the markers, so such a note is skipped instead.
    """
    try:
        return merge(existing.decode(), new)
    except UnicodeDecodeError:
        return None


def _with_raw_name(notes: Iterable[RenderedNote], vault: Path) -> list[RenderedNote]:
    """Raw notes are never changed: a re-run's raw notes get the next free name.

    The same raw notes again (nothing new written) stage as unchanged. Otherwise
    "… (raw notes).md" becomes "… (raw notes 2).md", and the room note's links
    to it follow.
    """
    notes = list(notes)
    raw = next((n for n in notes if n.kind == "raw"), None)
    if raw is None:
        return notes
    copy = _free_raw_copy(raw, vault)
    if copy == 1:
        return notes
    numbered = f"{RAW_SUFFIX[:-1]} {copy})"
    old_stem = raw.path.stem
    new_stem = old_stem.removesuffix(RAW_SUFFIX) + numbered
    renamed = raw.model_copy(
        update={
            "path": raw.path.with_name(f"{new_stem}.md"),
            "text": raw.text.replace(f"{RAW_SUFFIX}\n", f"{numbered}\n", 1),
        }
    )
    return [
        renamed
        if note is raw
        else note.model_copy(
            update={"text": note.text.replace(f"[[{old_stem}]]", f"[[{new_stem}]]")}
        )
        for note in notes
    ]


def _free_raw_copy(raw: RenderedNote, vault: Path) -> int:
    """1 for the plain name, n for "(raw notes n)": the first that's free or identical."""
    stem = raw.path.stem.removesuffix(RAW_SUFFIX)
    for copy in range(1, MAX_RAW_COPIES + 1):
        name = raw.path.stem if copy == 1 else f"{stem}{RAW_SUFFIX[:-1]} {copy})"
        target = inside(vault, raw.path.with_name(f"{name}.md"))
        if not target.exists():
            return copy
        if target.read_bytes() == raw.text.encode():
            return copy
    raise StagingDamagedError  # 99 sets of raw notes for one room: something is wrong


# ---- Merge inside markers ----------------------------------------------------------------------


def merge(existing: str, new: str) -> str | None:
    """`existing` with its Recon sections refreshed from `new`; None if its markers are damaged.

    Each section in both is replaced by the new one's inside. Sections only in
    `new` are added at the end, under their heading from `new` unless `existing`
    already has that heading. Everything outside the markers stays exactly as it is.
    """
    old_sections = sections(existing)
    new_sections = sections(new)
    if old_sections is None or new_sections is None:
        return None
    result = _SECTION.sub(
        lambda m: _section(m.group("name"), new_sections.get(m.group("name"), m.group("body"))),
        existing,
    )
    headings = set(_HEADING.findall(existing))
    for match in _SECTION.finditer(new):
        name, body = match.group("name"), match.group("body")
        if name in old_sections:
            continue
        before = _HEADING.findall(new[: match.start()])
        heading = before[-1] if before else ""
        block = _section(name, body)
        if heading and heading not in headings:
            block = f"{heading}\n\n{block}"
            headings.add(heading)
        result = f"{result.rstrip(chr(10))}\n\n{block}\n"
    return result


def sections(text: str) -> dict[str, str] | None:
    """Each Recon section's name and inside, or None if the markers aren't well formed.

    Well formed: every start has an end, none nests, and no name repeats.
    """
    found: dict[str, str] = {}
    matched_lines = 0
    for match in _SECTION.finditer(text):
        body = match.group("body")
        if _MARKER_LINE.search(body) or match.group("name") in found:
            return None
        found[match.group("name")] = body
        matched_lines += 2
    if len(_MARKER_LINE.findall(text)) != matched_lines:
        return None
    return found


def _section(name: str, body: str) -> str:
    return f"%% recon:start {name} %%\n{body}%% recon:end %%"


# ---- Apply -------------------------------------------------------------------------------------


def apply(run_folder: Path, vault: Path, backups: Path) -> Applied:
    """Write a staged run into the vault: check, back up, journal, write.

    Args:
        run_folder: `runs/<run id>/`, staged by `stage`.
        vault: The vault folder.
        backups: `backups/`; this run's go in `backups/<run id>/`.

    Returns:
        How many files were written and backed up.

    Raises:
        ApplyConflict: A vault file changed since staging. Nothing was written.
        StagingDamagedError: The staged files are missing or don't match the manifest.
        UnsafePathError: A path would land outside the vault.
    """
    manifest = load_manifest(run_folder)
    staged = _read_staged(manifest, run_folder)
    for file in manifest.to_write:
        if current_sha256(inside(vault, _relative(file.path))) != file.base_sha256:
            raise ApplyConflict
    backed_up = _back_up(manifest, vault, backups / manifest.run_id)
    _write_journal(run_folder, Journal(state="applying", backed_up=backed_up))
    written = _write(manifest, staged, vault)
    _write_journal(run_folder, Journal(state="applied", written=written, backed_up=backed_up))
    return Applied(written=written, backed_up=backed_up)


def recover(run_folder: Path, vault: Path) -> Applied | None:
    """Finish an Apply a crash interrupted; None if there was nothing to finish.

    Each file still as it was when staged is written; each already written is
    left; one changed by hand since is left alone (and not counted).
    """
    journal = load_journal(run_folder)
    if journal is None or journal.state != "applying":
        return None
    manifest = load_manifest(run_folder)
    staged = _read_staged(manifest, run_folder)
    written = _write(manifest, staged, vault)
    _write_journal(
        run_folder, Journal(state="applied", written=written, backed_up=journal.backed_up)
    )
    return Applied(written=written, backed_up=journal.backed_up)


def _back_up(manifest: Manifest, vault: Path, folder: Path) -> int:
    count = 0
    for file in manifest.to_write:
        if file.action != "update":
            continue
        copy = inside(folder, _relative(file.path))
        ensure_private_dir(copy.parent)
        atomic_write_bytes(copy, inside(vault, _relative(file.path)).read_bytes())
        count += 1
    return count


def _write(manifest: Manifest, staged: dict[str, str], vault: Path) -> int:
    """Write each file whose target is still as staged; returns how many were written now."""
    written = 0
    for file in manifest.to_write:
        target = inside(vault, _relative(file.path))
        current = current_sha256(target)
        if current == file.sha256:
            continue  # already written (a recovered Apply)
        if current != file.base_sha256:
            continue  # changed by hand after Apply started: never overwrite it
        ensure_private_dir(target.parent)
        if file.action == "create":
            atomic_create_text(target, staged[file.path])
        else:
            atomic_write_text(target, staged[file.path])
        written += 1
    return written


# ---- Discard and backups -----------------------------------------------------------------------


def discard(run_folder: Path) -> None:
    """Throw away the staged notes (the run's model logs stay until runs expire)."""
    staged = run_folder / STAGED
    if staged.is_symlink():
        staged.unlink()
    elif staged.exists():
        shutil.rmtree(staged)


def prune_backups(backups: Path, keep: int = KEEP_BACKUPS) -> int:
    """Delete all but the newest `keep` runs' backups; returns how many went.

    Run IDs start with their UTC time, so sorting them sorts by age. Only
    folders named like run IDs are touched, and symlinks never.
    """
    if not backups.is_dir():
        return 0
    runs = sorted(
        p for p in backups.iterdir() if p.is_dir() and not p.is_symlink() and _RUN_ID.match(p.name)
    )
    old = runs[: max(0, len(runs) - keep)]
    for folder in old:
        shutil.rmtree(folder)
    return len(old)


# ---- Files and paths ---------------------------------------------------------------------------


def load_manifest(run_folder: Path) -> Manifest:
    """The run's manifest.

    Raises:
        StagingDamagedError: It's missing or unreadable (e.g. after Discard).
    """
    try:
        return Manifest.model_validate_json((run_folder / STAGED / MANIFEST).read_bytes())
    except (OSError, ValidationError) as exc:
        raise StagingDamagedError from exc


def load_journal(run_folder: Path) -> Journal | None:
    """Apply's journal, or None if Apply never started (or it's unreadable)."""
    try:
        return Journal.model_validate_json((run_folder / JOURNAL).read_bytes())
    except (OSError, ValidationError):
        return None


def current_sha256(path: Path) -> str | None:
    """A file's SHA-256 now, or None if it doesn't exist."""
    try:
        return _sha256(path.read_bytes())
    except FileNotFoundError:
        return None


def inside(root: Path, relative: PurePosixPath) -> Path:
    """`root / relative`, refusing anything that would resolve outside `root`.

    Raises:
        UnsafePathError: An absolute path, a `..`, or a symlink leading out.
    """
    # Resolving catches every way out: an absolute path, `..`, or a symlinked folder.
    path = root.joinpath(*relative.parts)
    base = root.resolve()
    resolved = path.resolve()
    if base not in resolved.parents:
        raise UnsafePathError
    return path


def _read_staged(manifest: Manifest, run_folder: Path) -> dict[str, str]:
    staged: dict[str, str] = {}
    for file in manifest.to_write:
        try:
            data = inside(run_folder / STAGED, _relative(file.path)).read_bytes()
        except OSError as exc:
            raise StagingDamagedError from exc
        if _sha256(data) != file.sha256:
            raise StagingDamagedError
        staged[file.path] = data.decode()
    return staged


def _write_journal(run_folder: Path, journal: Journal) -> None:
    atomic_write_text(run_folder / JOURNAL, journal.model_dump_json() + "\n")


def _relative(path: str | PurePosixPath) -> PurePosixPath:
    return PurePosixPath(path)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
