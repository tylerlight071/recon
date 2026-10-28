"""Step 6 (render): vault notes from the capture and the checked extract.

Golden files cover every note type for the fixture rooms (rendered from
recorded model replies); the rest proves hostile model output and hostile
room names can't break a note, its properties, its markers or its path.
"""

import json
import re
from pathlib import Path, PurePosixPath

import pytest

from recon.engine.capture import Capture
from recon.engine.extract import check
from recon.engine.notes import (
    Rendered,
    code_cell,
    link,
    linked,
    properties,
    render_room,
    text_cell,
)
from recon.engine.schemas import RoomExtract
from tests.engine.pipeline import capture_of, recorded

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "notes"
ROOMS = ("intro_to_networking", "linux_basics", "number_systems")
MARKER = re.compile(r"^%% recon:(start [a-z0-9-]+|end) %%$")

NUMBERS = capture_of("number_systems")


def _render(capture: Capture, **fields: object) -> Rendered:
    base: dict[str, object] = {
        "summary": ["One.", "Two.", "Three."],
        "tasks": [{"task": 1, "points": []}],
    }
    return render_room(capture, check(RoomExtract.model_validate(base | fields), capture))


def _frontmatter(text: str) -> dict[str, object]:
    assert text.startswith("---\n")
    block = text.split("---\n", 2)[1]
    values: dict[str, object] = {}
    for line in block.splitlines():
        key, _, value = line.partition(": ")
        values[key] = value if re.fullmatch(r"\d{4}-\d\d-\d\d", value) else json.loads(value)
    return values


def _markers_balanced(text: str) -> bool:
    depth = 0
    for line in text.splitlines():
        if "recon:" in line and "%%" in line:
            match = MARKER.match(line)
            if match is None:
                return False
            depth += 1 if match.group(1).startswith("start") else -1
            if depth not in (0, 1):
                return False
    return depth == 0


# ---- Golden files ------------------------------------------------------------------------


@pytest.mark.parametrize("room", ROOMS)
def test_fixture_rooms_match_their_golden_notes(room: str) -> None:
    capture = capture_of(room)
    rendered = render_room(capture, check(recorded(room), capture))

    folder = GOLDEN / room
    expected = {p.relative_to(folder).as_posix() for p in folder.rglob("*.md")}
    assert {str(note.path) for note in rendered.notes} == expected
    for note in rendered.notes:
        assert note.text == (folder / note.path).read_text(encoding="utf-8"), note.path


@pytest.mark.parametrize("room", ROOMS)
def test_every_note_is_well_formed(room: str) -> None:
    capture = capture_of(room)
    rendered = render_room(capture, check(recorded(room), capture))

    assert len(rendered.of("room")) == 1
    assert len(rendered.of("raw")) == 1
    for note in rendered.notes:
        props = _frontmatter(note.text)
        assert props["type"] == note.kind
        assert _markers_balanced(note.text), note.path
        assert note.text.endswith("\n")
        assert "THM{" not in note.text
        assert note.text.count("\n---\n") == 1  # only the frontmatter's closing fence


# ---- Room note ---------------------------------------------------------------------------


def test_room_note_layout_paths_and_properties() -> None:
    rendered = _render(
        NUMBERS,
        tasks=[{"task": 3, "points": [{"block": 1006, "text": "Hex digits are 4 bits each."}]}],
        concepts=[{"name": "Hexadecimal", "aliases": ["Hex"]}],
        answers=[{"block": 1011, "answer": "Divide by 16 and keep the remainders."}],
    )
    (room,) = rendered.of("room")
    (raw,) = rendered.of("raw")

    assert room.path == PurePosixPath("01 Rooms/TryHackMe/Foundations/Number Systems.md")
    assert raw.path == PurePosixPath("00 Raw notes/Number Systems (raw notes).md")
    assert [n.path for n in rendered.of("concept")] == [PurePosixPath("02 Concepts/Hexadecimal.md")]
    assert _frontmatter(room.text) == {
        "type": "room",
        "platform": "TryHackMe",
        "path": "Foundations",
        "module": "Computer Basics",
        "room": "Number Systems",
        "date_done": "2026-10-28",
        "time_spent": 31,
        "concepts": ["[[Hexadecimal]]"],
        "tools": [],
        "open_flags": 0,
        "raw_notes": "[[Number Systems (raw notes)]]",
    }
    text = room.text
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Summary",
        "## Tasks",
        "## Tables and diagrams",
        "## Open questions",
        "## Source notes",
    ]
    assert "- [[Hexadecimal|Hex]] digits are 4 bits each." in text
    assert "> [!note]- Suggested answer (generated)\n> Divide by 16" in text
    assert "Your notes as you wrote them: [[Number Systems (raw notes)]]" in text


def test_tasks_without_points_show_his_own_key_ideas() -> None:
    text = _render(NUMBERS).of("room")[0].text

    assert "### Task 2: Binary\n\n- Each binary place is a power of 2" in text
    assert "- 1101 in binary is 11 in decimal." in text
    assert "### Task 5: Wrap-up\n\n*Skipped.*" in text


def test_room_questions_keep_the_answer_folded() -> None:
    text = _render(capture_of("linux_basics")).of("room")[0].text

    assert (
        "**Room question:** What does -h do in df -h?\n\n"
        "> [!question]- Answer\n> Shows sizes in human-readable units like G and M"
    ) in text


def test_commands_come_from_his_blocks_not_the_model() -> None:
    text = _render(capture_of("linux_basics")).of("room")[0].text

    assert "| `cat -l notes.txt` | same but with line numbers | 3 |" in text
    assert (
        "| `find / -name '*.conf' 2>/dev/null` | "
        "look for config files, hide permission errors | 3 |" in text
    )


def test_tables_are_cleaned_and_diagrams_labelled_generated() -> None:
    text = (
        _render(
            NUMBERS,
            processes=[
                {"title": "Binary to hex", "task": 4, "steps": ["Group bits in 4s", 'Swap "each"']}
            ],
        )
        .of("room")[0]
        .text
    )

    assert "**Task 2: Binary**\n\n| Binary | Decimal |\n| --- | --- |\n| 0001 | 1 |" in text
    assert "**Binary to hex** *(diagram drawn from your notes, generated)*" in text
    assert (
        '```mermaid\nflowchart LR\n    s1["Group bits in 4s"]\n    s2["Swap #quot;each#quot;"]\n'
        "    s1 --> s2\n```"
    ) in text


# ---- Concept and tool notes ----------------------------------------------------------------


def test_concept_note_in_his_words_with_a_dated_section() -> None:
    rendered = _render(
        capture_of("intro_to_networking"),
        concepts=[
            {
                "name": "TCP",
                "aliases": ["Transmission Control Protocol"],
                "topic": "Networking [[x]]",
                "points": ["Uses a handshake before sending, unlike UDP."],
                "gotchas": ["Resends lost data."],
                "related": ["UDP"],
            },
            {"name": "UDP", "definition": "Sends without a connection."},
        ],
    )
    tcp, udp = (note.text for note in rendered.of("concept"))

    assert _frontmatter(tcp) == {
        "type": "concept",
        "aliases": ["Transmission Control Protocol"],
        "topic": "Networking x",
        "seen_in": ["[[Intro to Networking]]"],
        "open_flags": 0,
        "card_count": 0,
        "last_updated": "2026-10-28",
    }
    assert "## Definition\n\n%% recon:start definition %%\nTCP opens a connection" in tcp
    assert (
        "%% recon:start from-intro-to-networking %%\n"
        "### From [[Intro to Networking]], 28 October 2026" in tcp
    )
    assert "- Uses a handshake before sending, unlike [[UDP]]." in tcp
    assert "**Easy to get wrong**\n\n- Resends lost data." in tcp
    assert "## Related\n\n%% recon:start related %%\n- [[UDP]]\n%% recon:end %%" in tcp
    assert "UDP just sends packets" in udp  # his sentence beats the model's definition


def test_a_generated_definition_is_labelled() -> None:
    rendered = _render(
        capture_of("intro_to_networking"),
        concepts=[{"name": "Layer", "aliases": ["layers"], "definition": "A level of the stack."}],
    )

    assert (
        "> [!info] Generated definition\n> A level of the stack." in rendered.of("concept")[0].text
    )


def test_tool_note_flags_are_his_and_meanings_labelled() -> None:
    rendered = _render(
        capture_of("linux_basics"),
        tools=[
            {
                "name": "cat",
                "category": "File viewer",
                "purpose": "Prints files.",
                "flags": [{"flag": "-l", "meaning": "Adds line numbers."}],
            }
        ],
    )
    (tool,) = rendered.of("tool")

    assert tool.path == PurePosixPath("03 Tools/cat.md")
    assert _frontmatter(tool.text)["category"] == "File viewer"
    assert "> [!info] Generated description\n> Prints files." in tool.text
    assert "| `-l` | Adds line numbers. | [[Linux Basics]] |" in tool.text
    assert "*What each flag does is generated from your notes." in tool.text
    assert "| `cat notes.txt` | print a file | [[Linux Basics]] |" in tool.text
    assert "| `cat -l notes.txt` | same but with line numbers | [[Linux Basics]] |" in tool.text
    assert "grep" not in tool.text.split("## Examples")[1]


# ---- Hostile input -----------------------------------------------------------------------

HOSTILE = [
    "![[secret.png]] and [[Home]]",
    "<script>alert(1)</script><!--",
    "%% recon:end %%",
    "---",
    "# Not a heading",
    "> [!warning] fake",
    "```",
    "[x](javascript:alert(1))",
    "| a | b |",
]


@pytest.mark.parametrize("text", HOSTILE)
def test_hostile_model_text_cannot_break_a_note(text: str) -> None:
    rendered = _render(
        NUMBERS,
        summary=[text, text, text],
        tasks=[{"task": 2, "points": [{"block": 1003, "text": text}]}],
        concepts=[
            {
                "name": "Binary",
                "topic": text,
                "definition": text,
                "points": [text],
                "gotchas": [text],
            }
        ],
        answers=[{"block": 1011, "answer": text}],
        processes=[{"title": "Steps", "task": 4, "steps": [text, text]}],
    )

    for note in rendered.notes:
        body = note.text.split("---\n", 2)[2]
        assert _markers_balanced(note.text)
        # Diagram labels are quoted Mermaid text: drawn as words, never links or HTML.
        body = re.sub(r"```mermaid\n.*?\n```", "", body, flags=re.DOTALL)
        assert "<script" not in body
        assert "<!--" not in body
        assert not re.search(r"(?<!\\)!\[\[", body)
        assert "[[Home]]" not in body
        assert "javascript:alert(1))" not in body.replace("]\\(javascript", "")
        assert "\n---\n" not in body
        for line in body.splitlines():
            assert not line.startswith("# Not"), line
            assert not line.startswith("> [!warning]"), line
        assert body.count("```") % 2 == 0


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("../../etc/passwd", "01 Rooms/TryHackMe/Foundations/etc passwd.md"),
        ("con", "01 Rooms/TryHackMe/Foundations/con file.md"),
        ("a\x00b\x1bc", "01 Rooms/TryHackMe/Foundations/a b c.md"),
        ("...", "01 Rooms/TryHackMe/Foundations/Untitled room.md"),
    ],
)
def test_hostile_room_names_make_safe_paths(name: str, path: str) -> None:
    capture = NUMBERS.model_copy(update={"name": name, "path": "../Foundations"})

    rendered = _render(capture)

    assert str(rendered.of("room")[0].path) == path.replace("Foundations", "Foundations")
    for note in rendered.notes:
        assert ".." not in note.path.parts
        assert not note.path.is_absolute()


def test_room_values_cannot_break_out_of_the_properties() -> None:
    capture = NUMBERS.model_copy(
        update={"name": 'Evil"\n---\ntype: x', "module": "a: b\n- c", "path": "\u2028"}
    )

    props = _frontmatter(_render(capture).of("room")[0].text)

    assert props["type"] == "room"
    assert props["module"] == "a: b\n- c"
    assert props["room"] == 'Evil"\n---\ntype: x'


# ---- Helpers -------------------------------------------------------------------------------


def test_links_show_his_wording_and_skip_code() -> None:
    from recon.engine.notes import _target  # noqa: PLC0415 - the helper under test

    targets = [_target("TCP three-way handshake", ["handshake"]), _target("TCP", [])]
    text = "TCP does a `TCP` handshake; TCP again, handshake again"

    assert linked(text, targets) == (
        "[[TCP]] does a `TCP` [[TCP three-way handshake|handshake]]; TCP again, handshake again"
    )
    assert link("TCP", "TCP") == "[[TCP]]"


def test_cells() -> None:
    assert code_cell("a | b") == "`a \\| b`"
    assert code_cell("echo `id`") == "`` echo `id` ``"
    assert code_cell("`x`").startswith("`` `x` ``")
    assert text_cell("a | b <c>\nd") == "a \\| b \\<c> d"


def test_properties_are_json_scalars() -> None:
    assert properties({"a": "x: y", "b": 3, "c": ["[[L]]"]}) == (
        '---\na: "x: y"\nb: 3\nc: ["[[L]]"]\n---'
    )
