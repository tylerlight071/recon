"""Render a finished room as one Markdown note (the Phase 1 export, task 1.13).

Pydantic in, Markdown out, through a Jinja2 template (`templates/export.md.j2`):
Python decides what each block looks like; the template lays out the note.
Tyler's text is escaped only where it could break the note's structure: a
line that would become a heading, quote, code fence, rule, HTML block or
Obsidian comment.
Commands go in a fence longer than any backtick run inside them; tables
become Markdown tables. Flags are stripped once more on the way out (hard
rule 2), keeping only the hex strings Tyler marked "Not a flag, keep it".
"""

import re
from datetime import date
from pathlib import Path
from typing import Final, Literal

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel, ConfigDict

from recon.engine.flags_filter import strip_flags
from recon.engine.parse import parse_table

TEMPLATES: Final = Path(__file__).resolve().parent / "templates"
LABELS: Final = {
    "key_idea": "Key idea",
    "command": "Command",
    "table": "Table",
    "screenshot": "Screenshot",
    "question": "Question",
    "confused": "Confused by",
    "room_question": "Room question",
    "voice": "Voice note",
}
# A line that Markdown (or Obsidian) would read as structure, not text. A leading
# `<` can open an HTML block (`<script`, `<!--`) that hides the rest of the note
# (audit F-08), so it's escaped too; `\<` shows as a plain `<`.
_STRUCTURE: Final = re.compile(
    r"^(\s{0,3})(#|>|<|```|~~~|-{3,}\s*$|={3,}\s*$|\*{3,}\s*$|_{3,}\s*$)"
)
_BACKTICKS: Final = re.compile(r"`+")


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExportBlock(_Model):
    """One block, as written."""

    type: str
    text: str
    answer: str | None = None
    kept: tuple[str, ...] = ()


class ExportTask(_Model):
    """One task with its blocks."""

    index: int
    title: str
    status: Literal["open", "done", "skipped"]
    blocks: tuple[ExportBlock, ...]


class ExportRoom(_Model):
    """A finished room."""

    name: str
    platform: str
    path: str
    module: str
    finished_on: date
    time_spent_s: int
    tasks: tuple[ExportTask, ...]


def render_export(room: ExportRoom) -> str:
    """The room as one Markdown note."""
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES),
        # Markdown, not HTML: escaping is done by the filters below, per context.
        autoescape=False,  # noqa: S701 - output is Markdown; HTML escaping would mangle it
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["oneline"] = one_line
    environment.filters["block"] = render_block
    environment.filters["duration"] = duration
    environment.filters["day"] = lambda d: f"{d.day} {d:%B %Y}"
    environment.globals["has_content"] = has_content
    place = " · ".join(part for part in (room.platform, room.path, room.module) if part)
    text = environment.get_template("export.md.j2").render(room=room, place=place)
    return re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"


def render_block(block: ExportBlock) -> str:
    """One block's Markdown, under its bold label."""
    text = _clean(block.text, block.kept)
    label = f"**{LABELS.get(block.type, 'Note')}**"
    if block.type == "command":
        body = fenced(text, "sh")
    elif block.type == "table":
        body = markdown_table(text)
    else:
        body = escape_lines(text)
    if block.type == "room_question":
        answer = _clean(block.answer or "", block.kept)
        if answer.strip():
            callout = "\n".join(f"> {line}" for line in escape_lines(answer).splitlines())
            body = f"{body}\n\n> [!question]- Answer\n{callout}"
    return f"{label}\n{body}"


def has_content(block: ExportBlock) -> bool:
    """Whether a block has anything written (empty blocks are left out)."""
    return bool(block.text.strip() or (block.answer or "").strip())


def escape_lines(text: str) -> str:
    """Text with any structure-making line start escaped, and `%%` defused."""
    lines = text.replace("%%", "\\%\\%").splitlines()
    return "\n".join(_STRUCTURE.sub(r"\1\\\2", line) for line in lines)


def one_line(text: str) -> str:
    """Text for a heading: one line, whitespace collapsed, `%%` defused."""
    return " ".join(text.replace("%%", "\\%\\%").split())


def fenced(text: str, language: str = "") -> str:
    """A code fence that nothing inside can close early."""
    longest = max((len(run) for run in _BACKTICKS.findall(text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def markdown_table(text: str) -> str:
    """Rows as a Markdown table (first row as header); plain text if it isn't a grid."""
    table = parse_table(text)
    if not table.is_grid:
        return escape_lines(text)

    def row(cells: tuple[str, ...]) -> str:
        return "| " + " | ".join(_cell(cell) for cell in cells) + " |"

    header, *rest = table.rows
    rule = "| " + " | ".join("---" for _ in header) + " |"
    return "\n".join([row(header), rule, *(row(r) for r in rest)])


def duration(seconds: int) -> str:
    """Plain time: "under a minute", "12 minutes", "1 hour 5 minutes"."""
    minutes = seconds // 60
    if minutes < 1:
        return "under a minute"
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minutes:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
    return " ".join(parts)


def _cell(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("%%", "\\%\\%")
        .replace("<", "\\<")  # no HTML from a cell either (audit F-08)
    )


def _clean(text: str, kept: tuple[str, ...]) -> str:
    return strip_flags(text, kept, unfinished=True).text.strip("\n")
