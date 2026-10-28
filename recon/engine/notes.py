"""Pipeline step 6, render: the checked extract and the user's notes as vault notes.

Python decides what every value looks like, already escaped; Jinja2 templates
in `templates/notes/` lay the notes out (the model never writes Markdown).

- The user's own text (raw notes, questions, commands, tables) is escaped only
  where it could break the note's structure (`render.escape_lines` and friends).
- Model-derived text goes through `sanitise` first, then the engine adds the
  only links: to the concepts and tools found in this room.
- Generated content is labelled (hard rule 5): definitions, descriptions,
  suggested answers, flag meanings, diagrams.
- Generated sections sit between `%% recon:start <section> %%` markers.
- Properties are written as JSON scalars and lists, which YAML reads exactly,
  so nothing typed can break out of the frontmatter.

Nothing is written here: the notes go to staging (task 2.4), never the vault.
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Final, Literal

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel, ConfigDict

from recon.engine.capture import Capture, CaptureBlock, CaptureTask
from recon.engine.commands import command_lines, invocations
from recon.engine.names import file_name
from recon.engine.render import (
    ExportBlock,
    escape_lines,
    markdown_table,
    one_line,
    render_block,
)
from recon.engine.sanitise import cell, inline, mermaid_label
from recon.engine.schemas import Concept, RoomExtract, Tool

TEMPLATES: Final = Path(__file__).resolve().parent / "templates"
RAW_FOLDER: Final = "00 Raw notes"
ROOMS_FOLDER: Final = "01 Rooms"
CONCEPTS_FOLDER: Final = "02 Concepts"
TOOLS_FOLDER: Final = "03 Tools"
RAW_SUFFIX: Final = " (raw notes)"
"""Raw notes are named apart from the room note, so `[[Room]]` is never ambiguous."""
_SECTION: Final = re.compile(r"[^a-z0-9]+")
_PROPERTY_TEXT: Final = re.compile(r"[\[\]<>%|#^`{}]")
_CODE_SPAN: Final = re.compile(r"(`+)(?:(?!\1).)+?\1")
_BACKTICKS: Final = re.compile(r"`+")

type NoteKind = Literal["room", "raw", "concept", "tool"]
type Property = str | int | date | Sequence[str]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RenderedNote(_Model):
    """One note, ready for staging."""

    path: PurePosixPath
    """Relative to the vault, e.g. `02 Concepts/Hexadecimal.md`."""
    kind: NoteKind
    text: str


class Rendered(_Model):
    """Every note one room produces."""

    notes: tuple[RenderedNote, ...]

    def of(self, kind: NoteKind) -> tuple[RenderedNote, ...]:
        """The notes of one kind."""
        return tuple(note for note in self.notes if note.kind == kind)


@dataclass(frozen=True, slots=True)
class _Target:
    """A note the engine may link to, and the words that mean it."""

    stem: str
    words: tuple[str, ...]


def render_room(capture: Capture, extract: RoomExtract) -> Rendered:
    """Render the room note, raw notes, and a note per concept and tool.

    Args:
        capture: The user's notes, flags removed (step 1).
        extract: The checked extract (step 3).

    Returns:
        The notes, with paths relative to the vault.
    """
    names = _Names(capture)
    concepts = {c.name: _target(c.name, c.aliases) for c in extract.concepts}
    tools = {t.name: _target(t.name, t.aliases) for t in extract.tools}
    environment = _environment()
    notes = [
        RenderedNote(
            path=names.room_path,
            kind="room",
            text=_room(environment, capture, extract, names, [*concepts.values(), *tools.values()]),
        ),
        RenderedNote(path=names.raw_path, kind="raw", text=_raw(environment, capture)),
    ]
    for concept in extract.concepts:
        others = [t for n, t in concepts.items() if n != concept.name]
        notes.append(
            RenderedNote(
                path=PurePosixPath(CONCEPTS_FOLDER, f"{concepts[concept.name].stem}.md"),
                kind="concept",
                text=_concept(environment, concept, concepts, others, names),
            )
        )
    for tool in extract.tools:
        notes.append(
            RenderedNote(
                path=PurePosixPath(TOOLS_FOLDER, f"{tools[tool.name].stem}.md"),
                kind="tool",
                text=_tool(environment, tool, capture, names),
            )
        )
    return Rendered(notes=_unique_paths(notes))


# ---- Names and paths -----------------------------------------------------------------------


class _Names:
    """The room's file names, links and folders, worked out once."""

    def __init__(self, capture: Capture) -> None:
        self.stem = file_name(capture.name)
        self.raw_stem = f"{self.stem}{RAW_SUFFIX}"
        self.room_path = room_note_path(capture.platform, capture.path, capture.name)
        self.raw_path = PurePosixPath(RAW_FOLDER, f"{self.raw_stem}.md")
        self.room_link = link(self.stem)
        self.raw_link = link(self.raw_stem)
        self.finished_on = capture.finished_on
        self.day = f"{capture.finished_on.day} {capture.finished_on:%B %Y}"
        self.section = f"from-{_SECTION.sub('-', self.stem.casefold()).strip('-') or 'room'}"


def room_note_path(platform: str, path: str, name: str) -> PurePosixPath:
    """Where a room's note lives in the vault: `01 Rooms/<platform>/<path>/<room>.md`."""
    folders = [ROOMS_FOLDER, file_name(platform, "Other")]
    if path.strip():
        folders.append(file_name(path, "Other"))
    return PurePosixPath(*folders, f"{file_name(name)}.md")


def link(stem: str, shown: str = "") -> str:
    """A wikilink to a note by its file name, showing `shown` if it differs."""
    return f"[[{stem}|{shown}]]" if shown and shown != stem else f"[[{stem}]]"


def _target(name: str, aliases: Iterable[str]) -> _Target:
    words = sorted({name, *aliases}, key=lambda word: (-len(word), word.casefold(), word))
    return _Target(file_name(name, "Untitled"), tuple(words))


def _unique_paths(notes: list[RenderedNote]) -> tuple[RenderedNote, ...]:
    # Two names that make the same file name ("TCP/IP" and "TCP IP"): the first wins.
    seen: dict[str, RenderedNote] = {}
    for note in notes:
        seen.setdefault(str(note.path).casefold(), note)
    return tuple(seen.values())


# ---- Linking -------------------------------------------------------------------------------


def linked(text: str, targets: Sequence[_Target]) -> str:
    """Sanitised model text with the first mention of each target linked.

    Mentions inside inline code aren't linked; longer names win over shorter
    ones they contain ("TCP handshake" before "TCP").
    """
    spans = [m.span() for m in _CODE_SPAN.finditer(text)]
    taken: list[tuple[int, int, str]] = []
    for target in targets:
        for word in target.words:
            found = _find(text, word, spans, taken)
            if found is not None:
                start, end = found
                taken.append((start, end, link(target.stem, text[start:end])))
                break
    for start, end, replacement in sorted(taken, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def _find(
    text: str, word: str, code: list[tuple[int, int]], taken: list[tuple[int, int, str]]
) -> tuple[int, int] | None:
    pattern = re.compile(rf"(?<![\w\\]){re.escape(word)}(?!\w)", re.IGNORECASE)
    for match in pattern.finditer(text):
        start, end = match.span()
        busy = [*code, *((s, e) for s, e, _ in taken)]
        if not any(start < e and s < end for s, e in busy):
            return start, end
    return None


# ---- Properties ----------------------------------------------------------------------------


def properties(values: Mapping[str, Property]) -> str:
    """A frontmatter block. Strings and lists are JSON, which YAML reads as written."""
    lines = ["---"]
    for key, value in values.items():
        if isinstance(value, date):
            shown = value.isoformat()
        elif isinstance(value, int):
            shown = str(value)
        elif isinstance(value, str):
            shown = json.dumps(value)
        else:
            shown = json.dumps(list(value))
        lines.append(f"{key}: {shown}")
    lines.append("---")
    return "\n".join(lines)


def _plain(text: str) -> str:
    """Model text for a property: one line, no link, markup or marker characters."""
    return " ".join(_PROPERTY_TEXT.sub("", text).split())


# ---- Room note -----------------------------------------------------------------------------


def _room(
    environment: Environment,
    capture: Capture,
    extract: RoomExtract,
    names: _Names,
    targets: Sequence[_Target],
) -> str:
    points = {task.task: [p.text for p in task.points] for task in extract.tasks}
    answers = {a.block: a.answer for a in extract.answers}
    values = {
        "properties": properties(
            {
                "type": "room",
                "platform": capture.platform,
                "path": capture.path,
                "module": capture.module,
                "room": capture.name,
                "date_done": capture.finished_on,
                "time_spent": capture.time_spent_s // 60,
                "concepts": [link(file_name(c.name, "Untitled")) for c in extract.concepts],
                "tools": [link(file_name(t.name, "Untitled")) for t in extract.tools],
                "open_flags": 0,
                "raw_notes": names.raw_link,
            }
        ),
        "title": one_line(capture.name),
        "summary": [linked(inline(line), targets) for line in extract.summary],
        "tasks": [_task(task, points.get(task.index, []), targets) for task in capture.tasks],
        "commands": _command_rows(capture),
        "tables": [
            {"label": _task_label(task), "body": markdown_table(block.text)}
            for task in capture.tasks
            for block in task.blocks
            if block.type == "table"
        ],
        "diagrams": [
            {"title": inline(process.title), "lines": _flowchart(process.steps)}
            for process in extract.processes
        ],
        "questions": [
            {
                "text": one_line(escape_lines(block.text)),
                "answer": inline(answers.get(block.id, "")),
            }
            for block in capture.blocks()
            if block.type == "question"
        ],
        "raw_link": names.raw_link,
    }
    return _render(environment, "notes/room.md.j2", values)


def _task(
    task: CaptureTask, points: Sequence[str], targets: Sequence[_Target]
) -> dict[str, object]:
    if points:
        shown = [linked(inline(point), targets) for point in points]
    else:
        # No points from the model: the user's own key ideas, as written, so nothing goes missing.
        shown = [
            one_line(escape_lines(b.text)) for b in task.blocks if b.type in {"key_idea", "voice"}
        ]
    return {
        "heading": _task_label(task),
        "skipped": task.status == "skipped",
        "points": shown,
        "room_questions": [
            {"text": one_line(escape_lines(block.text)), "answer": _quote(block.answer)}
            for block in task.blocks
            if block.type == "room_question"
        ],
    }


def _task_label(task: CaptureTask) -> str:
    title = one_line(escape_lines(task.title))
    return f"Task {task.index}: {title}" if title else f"Task {task.index}"


def _quote(text: str) -> str:
    """The user's text inside a callout, every line prefixed with `> `."""
    if not text.strip():
        return ""
    return "\n".join(f"> {line}".rstrip() for line in escape_lines(text).splitlines())


def _command_rows(capture: Capture) -> list[dict[str, object]]:
    return [
        {"command": code_cell(line.command), "comment": text_cell(line.comment), "task": task.index}
        for task in capture.tasks
        for block in task.blocks
        if block.type == "command"
        for line in command_lines(block.text)
    ]


def code_cell(text: str) -> str:
    """A command as inline code in a table cell: no backtick or pipe can end it early."""
    longest = max((len(run) for run in _BACKTICKS.findall(text)), default=0)
    ticks = "`" * (longest + 1)
    padded = f" {text} " if text.startswith("`") or text.endswith("`") else text
    return f"{ticks}{padded.replace('|', '\\|')}{ticks}"


def text_cell(text: str) -> str:
    """The user's text in a table cell: one line, pipes and markup that could escape escaped."""
    return one_line(text).replace("\\", "\\\\").replace("|", "\\|").replace("<", "\\<")


def _flowchart(steps: Sequence[str]) -> list[str]:
    """Each step once as a labelled node, then the arrows between them."""
    ids = [f"s{i}" for i in range(1, len(steps) + 1)]
    nodes = [f'{node}["{mermaid_label(step)}"]' for node, step in zip(ids, steps, strict=True)]
    return [*nodes, *(f"{a} --> {b}" for a, b in pairwise(ids))]


# ---- Raw notes -----------------------------------------------------------------------------


def _raw(environment: Environment, capture: Capture) -> str:
    values = {
        "properties": properties(
            {
                "type": "raw",
                "platform": capture.platform,
                "path": capture.path,
                "module": capture.module,
                "room": capture.name,
                "captured_on": capture.finished_on,
                "time_spent": capture.time_spent_s // 60,
            }
        ),
        "title": f"{one_line(capture.name)}{RAW_SUFFIX}",
        "tasks": [
            {
                "heading": _task_label(task),
                "skipped": task.status == "skipped",
                "blocks": [render_block(_export_block(block)) for block in task.blocks],
            }
            for task in capture.tasks
        ],
    }
    return _render(environment, "notes/raw.md.j2", values)


def _export_block(block: CaptureBlock) -> ExportBlock:
    return ExportBlock(type=block.type, text=block.text, answer=block.answer or None)


# ---- Concept and tool notes ----------------------------------------------------------------


def _concept(
    environment: Environment,
    concept: Concept,
    targets: Mapping[str, _Target],
    others: Sequence[_Target],
    names: _Names,
) -> str:
    values = {
        "properties": properties(
            {
                "type": "concept",
                "aliases": list(concept.aliases),
                "topic": _plain(concept.topic),
                "seen_in": [names.room_link],
                "open_flags": 0,
                "card_count": 0,
                "last_updated": names.finished_on,
            }
        ),
        "title": one_line(concept.name),
        "own_words": one_line(escape_lines(concept.own_words)),
        "definition": inline(concept.definition or "Not defined in your notes yet."),
        "from_section": names.section,
        "room_link": names.room_link,
        "day": names.day,
        "points": [linked(inline(p), others) for p in concept.points],
        "gotchas": [linked(inline(g), others) for g in concept.gotchas],
        "related": [link(targets[r].stem) for r in concept.related if r in targets],
    }
    return _render(environment, "notes/concept.md.j2", values)


def _tool(environment: Environment, tool: Tool, capture: Capture, names: _Names) -> str:
    words = {w.casefold() for w in (tool.name, *tool.aliases)}
    examples = [
        {
            "command": code_cell(line.command),
            "comment": text_cell(line.comment),
            "room": names.room_link,
        }
        for block in capture.blocks()
        if block.type == "command"
        for line in command_lines(block.text)
        if any(run.tool.casefold() in words for run in invocations(line.command))
    ]
    values = {
        "properties": properties(
            {
                "type": "tool",
                "aliases": list(tool.aliases),
                "category": _plain(tool.category),
                "seen_in": [names.room_link],
                "last_updated": capture.finished_on,
            }
        ),
        "title": one_line(tool.name),
        "own_words": one_line(escape_lines(tool.own_words)),
        "purpose": inline(tool.purpose or "Not described in your notes yet."),
        "flags": [
            {"flag": code_cell(f.flag), "meaning": cell(f.meaning), "room": names.room_link}
            for f in tool.flags
        ],
        "examples": examples,
    }
    return _render(environment, "notes/tool.md.j2", values)


# ---- Templates -----------------------------------------------------------------------------


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES),
        # Markdown, not HTML: every value is escaped for its context before it gets here.
        autoescape=False,  # noqa: S701 - output is Markdown; HTML escaping would mangle it
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _render(environment: Environment, template: str, values: Mapping[str, object]) -> str:
    text = environment.get_template(template).render(**values)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
