"""Staging, Apply, Discard and backups: hard rules 3, 4, 6, 8 and 9 (task 2.4)."""

import hashlib
import stat
from pathlib import Path, PurePosixPath

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon.engine.extract import check
from recon.engine.notes import Rendered, RenderedNote, render_room
from recon.engine.stage import (
    JOURNAL,
    MANIFEST,
    STAGED,
    Journal,
    apply,
    discard,
    inside,
    load_journal,
    load_manifest,
    merge,
    prune_backups,
    recover,
    sections,
    stage,
)
from recon.errors import ApplyConflict, StagingDamagedError, UnsafePathError
from tests.engine.pipeline import capture_of, recorded

RUN = "20261028T120000-abcd"
ROOM = "01 Rooms/TryHackMe/Foundations/Number Systems.md"
RAW = "00 Raw notes/Number Systems (raw notes).md"
CONCEPT = "02 Concepts/Binary.md"


@pytest.fixture
def places(tmp_path: Path) -> tuple[Path, Path, Path]:
    vault, runs, backups = tmp_path / "vault", tmp_path / "runs", tmp_path / "backups"
    vault.mkdir()
    return vault, runs / RUN, backups


def _rendered() -> Rendered:
    capture = capture_of("number_systems")
    return render_room(capture, check(recorded("number_systems"), capture))


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def _note(path: str, text: str, kind: str = "concept") -> RenderedNote:
    return RenderedNote.model_validate({"path": PurePosixPath(path), "kind": kind, "text": text})


# ---- Hard rule 3: nothing reaches the vault without Apply --------------------------------


def test_staging_never_touches_the_vault(places: tuple[Path, Path, Path]) -> None:
    vault, run, _backups = places
    (vault / "Home.md").write_text("mine")
    before = _snapshot(vault)

    manifest = stage(_rendered(), vault, run, room_id=1)

    assert _snapshot(vault) == before
    assert manifest.run_id == RUN
    assert {f.action for f in manifest.files} == {"create"}
    assert (run / STAGED / ROOM).read_text() == _rendered().of("room")[0].text
    assert stat.S_IMODE((run / STAGED / ROOM).stat().st_mode) == 0o600
    assert load_manifest(run) == manifest


def test_apply_writes_every_staged_note(places: tuple[Path, Path, Path]) -> None:
    vault, run, backups = places
    rendered = _rendered()
    stage(rendered, vault, run, room_id=1)

    applied = apply(run, vault, backups)

    assert applied.written == len(rendered.notes)
    assert applied.backed_up == 0
    for note in rendered.notes:
        assert (vault / note.path).read_text() == note.text
        assert stat.S_IMODE((vault / note.path).stat().st_mode) == 0o600
    assert load_journal(run) == Journal(state="applied", written=len(rendered.notes))


# ---- Hard rule 9: stop on conflict --------------------------------------------------------


@pytest.mark.parametrize("change", ["edited", "created", "deleted"])
def test_a_note_changed_since_staging_stops_apply_whole(
    places: tuple[Path, Path, Path], change: str
) -> None:
    vault, run, backups = places
    stage(_rendered(), vault, run, room_id=1)
    (vault / "Home.md").write_text("mine")  # unrelated files don't matter
    target = vault / CONCEPT
    target.parent.mkdir(parents=True, exist_ok=True)
    if change in {"edited", "deleted"}:
        # Stage over an existing note, then change it.
        target.write_text("%% recon:start definition %%\nold\n%% recon:end %%\n")
        stage(_rendered(), vault, run, room_id=1)
        if change == "edited":
            target.write_text(target.read_text() + "The user's own line\n")
        else:
            target.unlink()
    else:
        target.write_text("The user made this note in Obsidian meanwhile\n")
    before = _snapshot(vault)

    with pytest.raises(ApplyConflict):
        apply(run, vault, backups)

    assert _snapshot(vault) == before
    assert not backups.exists() or _snapshot(backups) == {}
    assert load_journal(run) is None


# ---- Hard rule 6: back up before overwriting ---------------------------------------------


def test_every_overwritten_file_is_backed_up_first(places: tuple[Path, Path, Path]) -> None:
    vault, run, backups = places
    old = (
        "---\ntype: concept\n---\n# Binary\n\nMy intro.\n\n"
        "%% recon:start definition %%\nold\n%% recon:end %%\n"
    )
    (vault / "02 Concepts").mkdir()
    (vault / CONCEPT).write_text(old)

    manifest = stage(_rendered(), vault, run, room_id=1)
    applied = apply(run, vault, backups)

    (binary,) = [f for f in manifest.files if f.path == CONCEPT]
    assert binary.action == "update"
    assert applied.backed_up == 1
    assert (backups / RUN / CONCEPT).read_text() == old
    assert stat.S_IMODE((backups / RUN / CONCEPT).stat().st_mode) == 0o600
    new = (vault / CONCEPT).read_text()
    assert new.startswith(
        "---\ntype: concept\n---\n# Binary\n\nMy intro.\n\n%% recon:start definition %%\n"
    )
    assert "\nold\n" not in new


def test_only_the_newest_twenty_backups_are_kept(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    for day in range(1, 26):
        (backups / f"202610{day:02d}T090000-ab").mkdir(parents=True)
    (backups / "db").mkdir()
    (backups / "notes").mkdir()

    assert prune_backups(backups) == 5

    left = sorted(p.name for p in backups.iterdir())
    assert left[0] == "20261006T090000-ab"
    assert "db" in left
    assert "notes" in left
    assert prune_backups(tmp_path / "none") == 0


# ---- Hard rule 8: only inside markers ------------------------------------------------------


def test_merge_changes_only_marker_insides_and_adds_missing_sections() -> None:
    existing = (
        '---\ntype: concept\naliases: ["mine"]\n---\n# Binary\n\n'
        "## Definition\n\nTyler's own intro.\n\n"
        "%% recon:start definition %%\nold definition\n%% recon:end %%\n\n"
        "The user's note after the section.\n"
    )
    new = (
        "---\ntype: concept\n---\n# Binary\n\n## Definition\n\n"
        "%% recon:start definition %%\nnew definition\n%% recon:end %%\n\n"
        "## Notes\n\n%% recon:start from-dns %%\n### From [[DNS]]\n- point\n%% recon:end %%\n"
    )

    merged = merge(existing, new)

    assert merged == (
        '---\ntype: concept\naliases: ["mine"]\n---\n# Binary\n\n'
        "## Definition\n\nTyler's own intro.\n\n"
        "%% recon:start definition %%\nnew definition\n%% recon:end %%\n\n"
        "The user's note after the section.\n\n"
        "## Notes\n\n%% recon:start from-dns %%\n### From [[DNS]]\n- point\n%% recon:end %%\n"
    )


def test_merge_keeps_sections_the_new_note_lacks_and_reuses_headings() -> None:
    existing = "## Notes\n\n%% recon:start from-a %%\nA\n%% recon:end %%\n"
    new = "## Notes\n\n%% recon:start from-b %%\nB\n%% recon:end %%\n"

    assert merge(existing, new) == (
        "## Notes\n\n%% recon:start from-a %%\nA\n%% recon:end %%\n\n"
        "%% recon:start from-b %%\nB\n%% recon:end %%\n"
    )


@pytest.mark.parametrize(
    "damaged",
    [
        "%% recon:start a %%\nno end\n",
        "%% recon:end %%\n",
        "%% recon:start a %%\n%% recon:start b %%\nx\n%% recon:end %%\n%% recon:end %%\n",
        "%% recon:start a %%\nx\n%% recon:end %%\n%% recon:start a %%\ny\n%% recon:end %%\n",
    ],
)
def test_damaged_markers_are_never_edited(places: tuple[Path, Path, Path], damaged: str) -> None:
    vault, run, backups = places
    assert sections(damaged) is None
    assert merge(damaged, "%% recon:start a %%\nnew\n%% recon:end %%\n") is None
    (vault / "02 Concepts").mkdir()
    (vault / CONCEPT).write_text(damaged)

    manifest = stage(_rendered(), vault, run, room_id=1)
    apply(run, vault, backups)

    assert [f.path for f in manifest.skipped] == [CONCEPT]
    assert (vault / CONCEPT).read_text() == damaged


def test_an_unchanged_note_is_left_alone(places: tuple[Path, Path, Path]) -> None:
    vault, run, backups = places
    stage(_rendered(), vault, run, room_id=1)
    apply(run, vault, backups)
    second = vault.parent / "runs" / "20261028T130000-ef"

    manifest = stage(_rendered(), vault, second, room_id=1)
    applied = apply(second, vault, backups)

    assert {f.action for f in manifest.files} == {"same"}
    assert applied.written == 0
    assert applied.backed_up == 0


_TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=40).filter(
    lambda s: "%%" not in s
)


@given(outside=st.lists(_TEXT, min_size=3, max_size=3), old=_TEXT, new=_TEXT)
def test_merge_never_changes_text_outside_markers(outside: list[str], old: str, new: str) -> None:
    before, middle, after = (f"{part}\n" for part in outside)
    existing = f"{before}%% recon:start s %%\n{old}\n%% recon:end %%\n{middle}{after}"

    merged = merge(existing, f"%% recon:start s %%\n{new}\n%% recon:end %%\n")

    assert merged == f"{before}%% recon:start s %%\n{new}\n%% recon:end %%\n{middle}{after}"


# ---- Hard rule 4: raw notes are never changed ----------------------------------------------


def test_a_rerun_gets_new_raw_notes_and_the_room_links_to_them(
    places: tuple[Path, Path, Path],
) -> None:
    vault, run, backups = places
    (vault / "00 Raw notes").mkdir()
    original = "first capture, never to change\n"
    (vault / RAW).write_text(original)

    manifest = stage(_rendered(), vault, run, room_id=1)
    apply(run, vault, backups)

    assert (vault / RAW).read_text() == original
    second = vault / "00 Raw notes/Number Systems (raw notes 2).md"
    assert "# Number Systems (raw notes 2)\n" in second.read_text()
    room = (vault / ROOM).read_text()
    assert "[[Number Systems (raw notes 2)]]" in room
    assert "[[Number Systems (raw notes)]]" not in room
    assert RAW not in {f.path for f in manifest.files}


def test_identical_raw_notes_are_not_written_twice(places: tuple[Path, Path, Path]) -> None:
    vault, run, backups = places
    stage(_rendered(), vault, run, room_id=1)
    apply(run, vault, backups)
    later = vault.parent / "runs" / "20261028T130000-ef"

    stage(_rendered(), vault, later, room_id=1)

    assert not (vault / "00 Raw notes/Number Systems (raw notes 2).md").exists()
    assert (later / STAGED / RAW).exists()


def test_the_ninety_ninth_raw_copy_is_the_last(places: tuple[Path, Path, Path]) -> None:
    vault, run, _backups = places
    (vault / "00 Raw notes").mkdir()
    (vault / RAW).write_text("x")
    for copy in range(2, 99):
        (vault / f"00 Raw notes/Number Systems (raw notes {copy}).md").write_text("x")

    manifest = stage(_rendered(), vault, run, room_id=1)
    assert "00 Raw notes/Number Systems (raw notes 99).md" in {f.path for f in manifest.files}

    (vault / "00 Raw notes/Number Systems (raw notes 99).md").write_text("x")
    with pytest.raises(StagingDamagedError):
        stage(_rendered(), vault, run, room_id=1)


# ---- Damaged staging, Discard, paths -------------------------------------------------------


def test_altered_or_missing_staging_writes_nothing(places: tuple[Path, Path, Path]) -> None:
    vault, run, backups = places
    stage(_rendered(), vault, run, room_id=1)
    (run / STAGED / ROOM).write_text("tampered")

    with pytest.raises(StagingDamagedError):
        apply(run, vault, backups)
    assert _snapshot(vault) == {}

    (run / STAGED / ROOM).unlink()
    with pytest.raises(StagingDamagedError):
        apply(run, vault, backups)
    (run / STAGED / MANIFEST).write_text("{not json")
    with pytest.raises(StagingDamagedError):
        apply(run, vault, backups)


def test_discard_removes_the_staged_notes_only(places: tuple[Path, Path, Path]) -> None:
    vault, run, backups = places
    stage(_rendered(), vault, run, room_id=1)
    (run / "extract-1.json").write_text("{}")

    discard(run)
    discard(run)  # twice is fine

    assert not (run / STAGED).exists()
    assert (run / "extract-1.json").exists()
    assert _snapshot(vault) == {}
    with pytest.raises(StagingDamagedError):
        apply(run, vault, backups)


def test_discard_never_follows_a_symlink(tmp_path: Path) -> None:
    precious = tmp_path / "precious"
    precious.mkdir()
    (precious / "keep.md").write_text("mine")
    run = tmp_path / "run"
    run.mkdir()
    (run / STAGED).symlink_to(precious)

    discard(run)

    assert (precious / "keep.md").read_text() == "mine"
    assert not (run / STAGED).exists()


@pytest.mark.parametrize("path", ["../outside.md", "/etc/passwd", "a/../../b.md", ""])
def test_paths_outside_the_vault_are_refused(tmp_path: Path, path: str) -> None:
    with pytest.raises(UnsafePathError):
        inside(tmp_path, PurePosixPath(path))


def test_a_symlinked_folder_leading_out_is_refused(places: tuple[Path, Path, Path]) -> None:
    vault, run, _backups = places
    outside = vault.parent / "elsewhere"
    outside.mkdir()
    (vault / "02 Concepts").symlink_to(outside)

    with pytest.raises(UnsafePathError):
        stage(_rendered(), vault, run, room_id=1)
    assert list(outside.iterdir()) == []


# ---- Crash recovery -------------------------------------------------------------------------


def test_recover_finishes_an_interrupted_apply(places: tuple[Path, Path, Path]) -> None:
    vault, run, _backups = places
    rendered = _rendered()
    manifest = stage(rendered, vault, run, room_id=1)
    # As if Apply crashed after writing two files.
    (run / JOURNAL).write_text(Journal(state="applying").model_dump_json())
    for file in manifest.files[:2]:
        target = vault / file.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((run / STAGED / file.path).read_bytes())
    # And the user edited one not yet written: it must be left alone.
    hand = vault / manifest.files[-1].path
    hand.parent.mkdir(parents=True, exist_ok=True)
    hand.write_text("The user's own")

    result = recover(run, vault)

    assert result is not None
    assert result.written == len(manifest.files) - 3
    assert hand.read_text() == "The user's own"
    for file in manifest.files[:-1]:
        assert hashlib.sha256((vault / file.path).read_bytes()).hexdigest() == file.sha256
    assert load_journal(run) == Journal(state="applied", written=result.written)
    assert recover(run, vault) is None  # nothing left to finish


def test_recover_without_a_journal_does_nothing(places: tuple[Path, Path, Path]) -> None:
    vault, run, _backups = places
    stage(_rendered(), vault, run, room_id=1)
    assert recover(run, vault) is None
    (run / JOURNAL).write_text("garbage")
    assert recover(run, vault) is None
    assert _snapshot(vault) == {}


def test_files_are_written_atomically() -> None:
    # Every vault write goes through recon.fs (temp file, fsync, os.replace / link).
    import inspect  # noqa: PLC0415

    from recon.engine import stage as module  # noqa: PLC0415

    source = inspect.getsource(module)
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source
    assert "open(" not in source


# ---- Edge cases (each found by mutation testing) ----------------------------------------------


def test_only_the_raw_title_is_renumbered(places: tuple[Path, Path, Path]) -> None:
    vault, run, _backups = places
    raw = _note(
        "00 Raw notes/R (raw notes).md",
        "# R (raw notes)\n\n**Key idea**\nSee the (raw notes)\n",
        "raw",
    )
    (vault / "00 Raw notes").mkdir()
    (vault / raw.path).write_text("older")

    stage(Rendered(notes=(raw,)), vault, run, room_id=1)

    staged = (run / STAGED / "00 Raw notes/R (raw notes 2).md").read_text()
    assert staged == "# R (raw notes 2)\n\n**Key idea**\nSee the (raw notes)\n"


def test_runs_without_raw_notes_stage_fine(places: tuple[Path, Path, Path]) -> None:
    vault, run, _backups = places

    manifest = stage(Rendered(notes=(_note(CONCEPT, "# Binary\n"),)), vault, run, room_id=1)

    assert [f.path for f in manifest.files] == [CONCEPT]


def test_a_note_that_is_not_utf8_is_left_alone(places: tuple[Path, Path, Path]) -> None:
    vault, run, backups = places
    (vault / "02 Concepts").mkdir()
    odd = b"The user's note \xff\xfe in another encoding\n"
    (vault / CONCEPT).write_bytes(odd)

    manifest = stage(_rendered(), vault, run, room_id=1)
    apply(run, vault, backups)

    assert CONCEPT in {f.path for f in manifest.skipped}
    assert (vault / CONCEPT).read_bytes() == odd


def test_new_sections_share_one_new_heading_and_keep_trailing_spaces() -> None:
    existing = "# Binary\n\nA line break here  \n"
    new = (
        "## Notes\n\n%% recon:start a %%\nA\n%% recon:end %%\n\n"
        "%% recon:start b %%\nB\n%% recon:end %%\n"
    )

    assert merge(existing, new) == (
        "# Binary\n\nA line break here  \n\n## Notes\n\n"
        "%% recon:start a %%\nA\n%% recon:end %%\n\n"
        "%% recon:start b %%\nB\n%% recon:end %%\n"
    )


def test_a_new_section_without_a_heading_is_added_as_it_is() -> None:
    assert merge("Mine.\n", "%% recon:start a %%\nA\n%% recon:end %%\n") == (
        "Mine.\n\n%% recon:start a %%\nA\n%% recon:end %%\n"
    )


def test_journal_and_result_count_every_backup(places: tuple[Path, Path, Path]) -> None:
    vault, run, backups = places
    (vault / "02 Concepts").mkdir()
    for name in ("Binary", "Decimal"):
        (vault / f"02 Concepts/{name}.md").write_text(
            "%% recon:start definition %%\nold\n%% recon:end %%\n"
        )
    stage(_rendered(), vault, run, room_id=1)

    applied = apply(run, vault, backups)

    assert applied.backed_up == 2
    journal = load_journal(run)
    assert journal is not None
    assert (journal.state, journal.backed_up, journal.written) == ("applied", 2, applied.written)


def test_recover_keeps_the_backup_count_and_skips_hand_edits_anywhere(
    places: tuple[Path, Path, Path],
) -> None:
    vault, run, _backups = places
    manifest = stage(_rendered(), vault, run, room_id=1)
    (run / JOURNAL).write_text(Journal(state="applying", backed_up=3).model_dump_json())
    first = vault / manifest.files[0].path
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_text("The user's own, made after Apply began")

    result = recover(run, vault)

    assert result is not None
    assert (result.written, result.backed_up) == (len(manifest.files) - 1, 3)
    assert first.read_text() == "The user's own, made after Apply began"
    assert (vault / manifest.files[1].path).exists()
    journal = load_journal(run)
    assert journal is not None
    assert journal.backed_up == 3


def test_new_notes_are_created_never_overwritten(
    places: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from recon.engine import stage as module  # noqa: PLC0415 - patching its writers

    vault, run, backups = places
    stage(_rendered(), vault, run, room_id=1)
    created: list[str] = []
    real = module.atomic_create_text

    def spy(path: Path, text: str) -> None:
        created.append(path.relative_to(vault).as_posix())
        real(path, text)

    monkeypatch.setattr(module, "atomic_create_text", spy)
    monkeypatch.setattr(module, "atomic_write_text", _refuse)

    apply(run, vault, backups)

    assert sorted(created) == sorted(f.path for f in load_manifest(run).files)


def _refuse(path: Path, text: str) -> None:
    if "vault" in path.parts:
        pytest.fail(f"overwrote {path}")
    from recon.fs import atomic_write_text  # noqa: PLC0415

    atomic_write_text(path, text)


def test_few_backups_are_all_kept(tmp_path: Path) -> None:
    for day in range(1, 4):
        (tmp_path / f"202610{day:02d}T090000-ab").mkdir()

    assert prune_backups(tmp_path) == 0
    assert len(list(tmp_path.iterdir())) == 3


class _CrashError(Exception):
    """Stands in for the process dying mid-write."""


def test_the_journal_records_backups_before_the_first_vault_write(
    places: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from recon.engine import stage as module  # noqa: PLC0415 - patching its writers

    vault, run, backups = places
    (vault / "02 Concepts").mkdir()
    (vault / CONCEPT).write_text("%% recon:start definition %%\nold\n%% recon:end %%\n")
    stage(_rendered(), vault, run, room_id=1)

    def crash(path: Path, _text: str) -> None:
        raise _CrashError(path)

    monkeypatch.setattr(module, "atomic_create_text", crash)
    with pytest.raises(_CrashError):
        apply(run, vault, backups)

    journal = load_journal(run)
    assert journal is not None
    assert (journal.state, journal.backed_up) == ("applying", 1)


def test_flags_never_reach_the_vault(places: tuple[Path, Path, Path]) -> None:
    # Hard rule 2, end to end: linux_basics holds a flag and a lone hex hash.
    from recon.engine.flags_filter import find_flags  # noqa: PLC0415

    vault, run, backups = places
    capture = capture_of("linux_basics")
    stage(render_room(capture, check(recorded("linux_basics"), capture)), vault, run, room_id=3)

    apply(run, vault, backups)

    for path, data in _snapshot(vault).items():
        assert find_flags(data.decode(), unfinished=True) == [], path


# ---- Restore from History (task 2.8) ----------------------------------------------------------


def test_restore_puts_back_what_a_run_replaced_and_can_be_undone(
    places: tuple[Path, Path, Path],
) -> None:
    from recon.engine.stage import restore  # noqa: PLC0415

    vault, run, backups = places
    (vault / "02 Concepts").mkdir()
    old = "%% recon:start definition %%\nmine before\n%% recon:end %%\n"
    (vault / CONCEPT).write_text(old)
    stage(_rendered(), vault, run, room_id=1)
    apply(run, vault, backups)
    applied = (vault / CONCEPT).read_text()
    created = vault / "02 Concepts/Decimal.md"
    assert created.exists()

    assert restore(backups / RUN, vault, backups / "20261028T130000-ef") == 1

    assert (vault / CONCEPT).read_text() == old
    assert (backups / "20261028T130000-ef" / CONCEPT).read_text() == applied
    assert created.exists()  # notes the run created stay
    assert restore(backups / "20261028T130000-ef", vault, backups / "20261028T140000-01") == 1
    assert (vault / CONCEPT).read_text() == applied  # undone


def test_restore_never_touches_raw_notes_or_follows_links(
    places: tuple[Path, Path, Path],
) -> None:
    from recon.engine.stage import restore  # noqa: PLC0415

    vault, _run, backups = places
    backup = backups / RUN
    (backup / "00 Raw notes").mkdir(parents=True)
    (backup / RAW).write_text("not mine to put back")
    outside = vault.parent / "outside.md"
    outside.write_text("secret")
    (backup / "link.md").symlink_to(outside)
    (vault / "00 Raw notes").mkdir()
    (vault / RAW).write_text("as typed")
    # Real backups after the skipped ones: skipping must carry on, and count each.
    (backup / "02 Concepts").mkdir()
    (backup / CONCEPT).write_text("binary before")
    (backup / "02 Concepts" / "Hex.md").write_text("hex before")

    assert restore(backup, vault, backups / "new") == 2
    assert (vault / RAW).read_text() == "as typed"
    assert not (vault / "link.md").exists()
    assert (vault / CONCEPT).read_text() == "binary before"
    assert (vault / "02 Concepts" / "Hex.md").read_text() == "hex before"


def test_restore_without_a_backup_changes_nothing(places: tuple[Path, Path, Path]) -> None:
    from recon.engine.stage import restore  # noqa: PLC0415
    from recon.errors import BackupMissingError  # noqa: PLC0415

    vault, _run, backups = places

    with pytest.raises(BackupMissingError):
        restore(backups / "gone", vault, backups / "new")
    assert _snapshot(vault) == {}
