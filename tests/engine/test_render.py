"""The Markdown export: golden file, escaping, and structure that Tyler's text can't break."""

import os
import re
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon.engine.render import (
    ExportBlock,
    ExportRoom,
    ExportTask,
    duration,
    escape_lines,
    fenced,
    markdown_table,
    render_export,
)

GOLDEN = Path(__file__).resolve().parent.parent / "golden" / "export_dns_in_detail.md"
MD5 = "5d41402abc4b2a76b9719d911017c592"


def _room(*tasks: ExportTask, name: str = "DNS in Detail") -> ExportRoom:
    return ExportRoom(
        name=name,
        platform="TryHackMe",
        path="Pre Security",
        module="Network Fundamentals",
        finished_on=date(2026, 10, 25),
        time_spent_s=4320,
        tasks=tasks,
    )


SAMPLE = _room(
    ExportTask(
        index=1,
        title="Record types",
        status="done",
        blocks=(
            ExportBlock(type="key_idea", text="Each record type answers a different question."),
            ExportBlock(type="command", text="dig example.com MX  # who handles mail"),
            ExportBlock(type="table", text="Type, Holds\nA, IPv4 address\nTXT, free text | notes"),
            ExportBlock(type="question", text="Why can't CNAME share a name?"),
            ExportBlock(type="confused", text=""),
            ExportBlock(
                type="room_question",
                text="Which record holds a mail server?",
                answer="MX",
            ),
        ),
    ),
    ExportTask(
        index=2, title="", status="skipped", blocks=(ExportBlock(type="key_idea", text=""),)
    ),
    ExportTask(
        index=3,
        title="Hashes",
        status="done",
        blocks=(
            ExportBlock(type="key_idea", text=f"md5 of hello: {MD5} (kept)", kept=(MD5,)),
            ExportBlock(
                type="key_idea", text="# not a heading\n> not a quote\n---\n%% not hidden %%"
            ),
        ),
    ),
)


def test_golden_export() -> None:
    text = render_export(SAMPLE)

    if os.environ.get("RECON_UPDATE_GOLDEN"):
        GOLDEN.write_text(text, encoding="utf-8")
    assert text == GOLDEN.read_text(encoding="utf-8")


def test_flags_are_stripped_on_the_way_out_except_kept_hashes() -> None:
    room = _room(
        ExportTask(
            index=1,
            title="Answers THM{title}",
            status="done",
            blocks=(
                ExportBlock(type="key_idea", text="got THM{abc} and flag{def"),
                ExportBlock(type="room_question", text="q", answer="HTB{x}"),
                ExportBlock(type="key_idea", text=f"{MD5} and {'a' * 32}", kept=(MD5,)),
            ),
        )
    )

    text = render_export(room)

    assert "THM{abc}" not in text
    assert "flag{def" not in text
    assert "HTB{" not in text
    assert MD5 in text
    assert "a" * 32 not in text


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("# heading", "\\# heading"),
        ("   ## indented", "   \\## indented"),
        ("    # code-indented stays", "    # code-indented stays"),
        ("> quote", "\\> quote"),
        ("```", "\\```"),
        ("~~~python", "\\~~~python"),
        ("---", "\\---"),
        ("===", "\\==="),
        ("***", "\\***"),
        ("a %% b %%", "a \\%\\% b \\%\\%"),
        ("plain - text # inside", "plain - text # inside"),
        ("- a list item", "- a list item"),
    ],
)
def test_escape_lines(text: str, escaped: str) -> None:
    assert escape_lines(text) == escaped


def test_fence_outlasts_backticks_inside() -> None:
    assert fenced("a ```` b", "sh") == "`````sh\na ```` b\n`````"
    assert fenced("plain") == "```\nplain\n```"


def test_tables() -> None:
    assert markdown_table("a, b\nc, d|e") == "| a | b |\n| --- | --- |\n| c | d\\|e |"
    assert markdown_table("just text\n# heading") == "just text\n\\# heading"


@pytest.mark.parametrize(
    ("seconds", "words"),
    [
        (0, "under a minute"),
        (59, "under a minute"),
        (60, "1 minute"),
        (125, "2 minutes"),
        (3600, "1 hour"),
        (3660, "1 hour 1 minute"),
        (4320, "1 hour 12 minutes"),
        (7200 + 300, "2 hours 5 minutes"),
    ],
)
def test_duration(seconds: int, words: str) -> None:
    assert duration(seconds) == words


def _structure(markdown: str) -> tuple[list[str], list[str]]:
    """Headings outside code fences, and quote lines that aren't Recon's answer callout."""
    headings: list[str] = []
    stray: list[str] = []
    fence, in_callout = "", False
    for line in markdown.splitlines():
        match = re.match(r"^(`{3,}|~{3,})", line)
        if fence:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
                fence = ""
            continue
        if line == "> [!question]- Answer":
            in_callout = True
            continue
        if line.startswith(">") and in_callout:
            continue
        in_callout = False
        if match:
            fence = match.group(1)
        elif re.match(r"^ {0,3}#{1,6}(\s|$)", line):
            headings.append(line.split(" ")[0])
        elif re.match(r"^ {0,3}(>|-{3,}\s*$|={3,}\s*$|%%)", line):
            stray.append(line)
    return headings, stray


_TEXT = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters="\r\x0b\x0c\x1c\x1d\x1e\x85" + chr(0x2028) + chr(0x2029),
    ),
    max_size=120,
)


@given(
    st.lists(
        st.tuples(
            _TEXT,
            st.sampled_from(
                ["key_idea", "command", "table", "question", "confused", "room_question"]
            ),
            _TEXT,
            _TEXT,
        ),
        min_size=1,
        max_size=4,
    ),
    _TEXT,
)
def test_tylers_text_never_changes_the_notes_structure(
    blocks: list[tuple[str, str, str, str]], name: str
) -> None:
    tasks = tuple(
        ExportTask(
            index=i + 1,
            title=title,
            status="done",
            blocks=(ExportBlock(type=kind, text=text, answer=answer),),
        )
        for i, (text, kind, answer, title) in enumerate(blocks)
    )

    headings, stray = _structure(render_export(_room(*tasks, name=name)))

    # One title and one heading per task; no quotes, rules or comments of Tyler's own.
    assert headings == ["#"] + ["##"] * len(tasks)
    assert stray == []


def _one(block: ExportBlock, title: str = "") -> str:
    return render_export(_room(ExportTask(index=1, title=title, status="done", blocks=(block,))))


def test_an_unknown_block_type_is_labelled_note() -> None:
    assert "**Note**\nsomething" in _one(ExportBlock(type="mystery", text="something"))


def test_room_question_answers() -> None:
    no_answer = _one(ExportBlock(type="room_question", text="Which port?", answer=None))
    kept = _one(ExportBlock(type="room_question", text="Hash?", answer=f"md5 {MD5}", kept=(MD5,)))
    lines = _one(ExportBlock(type="room_question", text="Steps?", answer="first\nsecond"))

    assert "[!question]" not in no_answer
    assert f"> md5 {MD5}" in kept
    assert "> [!question]- Answer\n> first\n> second" in lines


def test_titles_and_cells_are_defused() -> None:
    title = _one(ExportBlock(type="key_idea", text="x"), title="A %% hidden %% title")
    cells = _one(ExportBlock(type="table", text="path, note\nC:\\Temp, a %% b"))

    assert "## Task 1: A \\%\\% hidden \\%\\% title" in title
    assert "| C:\\\\Temp | a \\%\\% b |" in cells


def test_tylers_spacing_is_kept_but_blank_runs_collapse() -> None:
    text = _one(ExportBlock(type="key_idea", text="    indented on purpose\n\n\n\nlater"))

    assert "**Key idea**\n    indented on purpose\n\nlater" in text
