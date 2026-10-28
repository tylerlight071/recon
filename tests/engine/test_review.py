"""engine.review: a staged run split into the review screen's sections, shown safely."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon.engine.extract import check
from recon.engine.notes import render_room
from recon.engine.review import Review, added_parts, build_review, for_display
from recon.engine.stage import STAGED, load_manifest, stage
from tests.engine.pipeline import capture_of, recorded

CONCEPT = "02 Concepts/Binary.md"


def _staged(tmp_path: Path, existing: dict[str, str] | None = None) -> Path:
    vault, run = tmp_path / "vault", tmp_path / "runs" / "20261028T120000-ab"
    for path, text in (existing or {}).items():
        (vault / path).parent.mkdir(parents=True, exist_ok=True)
        (vault / path).write_text(text)
    vault.mkdir(exist_ok=True)
    capture = capture_of("number_systems")
    stage(render_room(capture, check(recorded("number_systems"), capture)), vault, run, room_id=1)
    return run


def _review(tmp_path: Path, run: Path) -> Review:
    vault = tmp_path / "vault"
    return build_review(
        load_manifest(run),
        lambda path: (run / STAGED / path).read_text(),
        lambda path: (vault / path).read_text() if (vault / path).exists() else None,
    )


def test_a_first_run_is_a_room_note_and_new_notes(tmp_path: Path) -> None:
    review = _review(tmp_path, _staged(tmp_path))

    assert review.run_id == "20261028T120000-ab"
    assert review.room_id == 1
    assert review.room is not None
    assert review.room.title == "Number Systems"
    assert review.room.markdown.startswith("### Number Systems\n\n#### Summary\n")
    assert "Binary" in [n.title for n in review.new]
    assert {n.kind for n in review.new} == {"concept"}
    assert all(n.markdown.startswith(f"### {n.title}\n") for n in review.new)
    assert review.additions == ()
    assert review.skipped == ()
    assert review.writes == 1 + len(review.new)  # raw notes aren't listed


def test_an_existing_note_shows_only_what_changes(tmp_path: Path) -> None:
    old = (
        "# Binary\n\nMy own intro.\n\n## Definition\n\n"
        "%% recon:start definition %%\nold\n%% recon:end %%\n"
    )
    review = _review(tmp_path, _staged(tmp_path, {CONCEPT: old}))

    (binary,) = review.additions
    assert binary.title == "Binary"
    assert binary.markdown.startswith("#### Definition\n\n")
    assert "#### Notes" in binary.markdown
    assert "My own intro" not in binary.markdown
    assert "Binary" not in [n.title for n in review.new]


def test_damaged_notes_are_listed_as_left_alone(tmp_path: Path) -> None:
    review = _review(tmp_path, _staged(tmp_path, {CONCEPT: "%% recon:start a %%\nno end\n"}))

    assert [n.title for n in review.skipped] == ["Binary"]
    assert review.skipped[0].markdown == ""


def test_unchanged_notes_are_not_listed(tmp_path: Path) -> None:
    first = _staged(tmp_path)
    vault = tmp_path / "vault"
    for file in load_manifest(first).files:
        (vault / file.path).parent.mkdir(parents=True, exist_ok=True)
        (vault / file.path).write_text((first / STAGED / file.path).read_text())
    run = tmp_path / "runs" / "20261028T130000-cd"
    capture = capture_of("number_systems")
    stage(render_room(capture, check(recorded("number_systems"), capture)), vault, run, room_id=1)

    review = _review(tmp_path, run)

    assert (review.room, review.new, review.additions) == (None, (), ())
    assert review.writes == 0


def test_added_parts_skips_unchanged_sections() -> None:
    old = "## A\n\n%% recon:start a %%\nsame\n%% recon:end %%\n"
    new = (
        "## A\n\n%% recon:start a %%\nsame\n%% recon:end %%\n\n"
        "%% recon:start b %%\nnew bit\n%% recon:end %%\n"
    )

    assert added_parts(old, new) == "## A\n\nnew bit\n"
    assert added_parts(new, new) == ""
    assert added_parts("", "%% recon:start c %%\nx\n%% recon:end %%\n") == "x\n"


# ---- Display ------------------------------------------------------------------------------


def test_obsidian_markdown_is_shown_as_qt_can_render_it() -> None:
    note = (
        '---\ntype: "room"\n---\n# DNS\n\n%% recon:start summary %%\n'
        "- See [[TCP three-way handshake|the handshake]] and [[UDP]].\n"
        "%% recon:end %%\n\n"
        "> [!question]- Answer\n> 443\n\n"
        "> [!info] Generated definition\n> A thing.\n\n"
        "> [!note]-\n> untitled\n"
    )

    assert for_display(note) == (
        "### DNS\n\n- See the handshake and UDP.\n\n"
        "> **Answer**\n> 443\n\n"
        "> **Generated definition**\n> A thing.\n\n"
        "> **Note**\n> untitled\n"
    )


def test_code_is_shown_as_written() -> None:
    note = "Run `cat < notes.txt` then:\n```sh\necho <b> [[x]]\n```\n~~~\n<i>\n~~~\nafter <x>\n"

    assert for_display(note) == (
        "Run `cat < notes.txt` then:\n```sh\necho <b> [[x]]\n```\n~~~\n<i>\n~~~\nafter &lt;x>\n"
    )


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("![[secret.png]]", "secret.png\n"),
        ("![remote](https://example.com/x.png)", "!\\[remote](https://example.com/x.png)\n"),
        ("<img src=x onerror=alert(1)>", "&lt;img src=x onerror=alert(1)>\n"),
        ("<!-- hidden -->", "&lt;!-- hidden -->\n"),
    ],
)
def test_nothing_can_load_or_run_in_the_preview(text: str, shown: str) -> None:
    assert for_display(text) == shown


@given(st.text(max_size=200))
def test_any_text_previews_without_html_or_images(text: str) -> None:
    shown = for_display(text)
    outside_code = "".join(part for index, part in enumerate(shown.split("`")) if index % 2 == 0)
    if "```" not in text and "~~~" not in text:
        assert "<" not in outside_code
        assert "![" not in outside_code


def test_headings_are_two_levels_smaller_but_code_is_untouched() -> None:
    assert for_display("# A\n## B\n##### E\n```\n# comment\n```\n#tag\n") == (
        "### A\n#### B\n###### E\n```\n# comment\n```\n#tag\n"
    )
