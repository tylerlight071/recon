"""What the review screen shows for a staged run (task 2.6). Pure Python.

`build_review` reads the manifest and splits the run into the spec's sections:
the room note, new notes, additions to existing notes (only the parts that
change), and notes left alone because their markers are damaged. Links and
flags join in Phase 3.

`for_display` turns Obsidian Markdown into Markdown Qt's `Text` renders: no
frontmatter or `%%` markers, wikilinks shown as their text, callouts as quotes
with a bold title, Mermaid shown as its source, and headings two levels
smaller. The preview is display-only, so images and HTML are neutralised as
well: nothing in a note can make the review screen load or run anything.
"""

import re
from collections.abc import Callable
from typing import Final

from pydantic import BaseModel, ConfigDict

from recon.engine.notes import NoteKind
from recon.engine.stage import Manifest, StagedFile, sections

_FRONTMATTER: Final = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_MARKER: Final = re.compile(r"^%% recon:(?:start [a-z0-9-]+|end) %%\n?", re.MULTILINE)
_WIKILINK: Final = re.compile(r"(?<!\\)!?\[\[([^\[\]|]+)(?:\|([^\[\]]+))?\]\]")
_CALLOUT: Final = re.compile(r"^> \[!(\w+)\][-+]? ?(.*)$", re.MULTILINE)
_FENCE: Final = re.compile(r"^(`{3,}|~{3,})")
_CODE_SPAN: Final = re.compile(r"((?<!`)`+(?!`).*?(?<!`)`+(?!`))")
_HEADING: Final = re.compile(r"^#{1,6} .*$", re.MULTILINE)
_DISPLAY_HEADING: Final = re.compile(r"^(#{1,6}) ")
_SECTION_BLOCK: Final = re.compile(
    r"^%% recon:start (?P<name>[a-z0-9-]+) %%\n(?P<body>.*?)^%% recon:end %%$",
    re.MULTILINE | re.DOTALL,
)
_CALLOUT_TITLES: Final = {
    "question": "Answer",
    "note": "Note",
    "info": "Info",
    "warning": "Check this",
}


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReviewNote(_Model):
    """One note in the review."""

    path: str
    kind: NoteKind
    title: str
    markdown: str
    """Ready for display: the whole note, or for an addition only what changes."""


class Review(_Model):
    """A staged run, split into the review screen's sections."""

    run_id: str
    room_id: int
    room: ReviewNote | None
    new: tuple[ReviewNote, ...]
    additions: tuple[ReviewNote, ...]
    skipped: tuple[ReviewNote, ...]

    @property
    def writes(self) -> int:
        """How many vault files Apply would write."""
        return (1 if self.room else 0) + len(self.new) + len(self.additions)


def build_review(
    manifest: Manifest,
    staged: Callable[[str], str],
    existing: Callable[[str], str | None],
) -> Review:
    """Split a staged run into the review's sections.

    Args:
        manifest: The run's manifest.
        staged: A staged note's text, by vault path.
        existing: The vault note's text now (None if it doesn't exist).

    Returns:
        The review. Raw notes aren't listed: they're the user's own words, as typed.
    """
    room: ReviewNote | None = None
    new: list[ReviewNote] = []
    additions: list[ReviewNote] = []
    skipped: list[ReviewNote] = []
    for file in manifest.files:
        if file.kind == "raw" or file.action == "same":
            continue
        if file.action == "skip":
            skipped.append(_note(file, ""))
        elif file.kind == "room":
            room = _note(file, for_display(staged(file.path)))
        elif file.action == "create":
            new.append(_note(file, for_display(staged(file.path))))
        else:
            added = added_parts(existing(file.path) or "", staged(file.path))
            additions.append(_note(file, for_display(added)))
    return Review(
        run_id=manifest.run_id,
        room_id=manifest.room_id,
        room=room,
        new=tuple(new),
        additions=tuple(additions),
        skipped=tuple(skipped),
    )


def _note(file: StagedFile, markdown: str) -> ReviewNote:
    title = file.path.rsplit("/", 1)[-1].removesuffix(".md")
    return ReviewNote(path=file.path, kind=file.kind, title=title, markdown=markdown)


def added_parts(old: str, new: str) -> str:
    """Only the Recon sections of `new` that differ from `old`, each under its heading."""
    before = sections(old) or {}
    parts: list[str] = []
    for match in _SECTION_BLOCK.finditer(new):
        name, body = match.group("name"), match.group("body")
        if before.get(name) == body:
            continue
        headings = _HEADING.findall(new[: match.start()])
        heading = f"{headings[-1]}\n\n" if headings else ""
        parts.append(f"{heading}{body.strip()}")
    return "\n\n".join(parts) + ("\n" if parts else "")


def for_display(markdown: str) -> str:
    """Obsidian Markdown as Qt's Markdown renderer should show it (display only)."""
    text = _FRONTMATTER.sub("", markdown)
    text = _MARKER.sub("", text)
    lines: list[str] = []
    fence = ""
    for line in text.splitlines():
        opened = _FENCE.match(line)
        if fence:
            lines.append(line)
            if opened and opened.group(1).startswith(fence):
                fence = ""
            continue
        if opened:
            fence = opened.group(1)
            lines.append(line)
            continue
        lines.append(_display_line(line))
    return "\n".join(lines).strip() + "\n"


def _display_line(line: str) -> str:
    # Qt draws headings large: two levels smaller keeps the review calm (`#` shows as `###`).
    line = _DISPLAY_HEADING.sub(lambda m: "#" * min(6, len(m.group(1)) + 2) + " ", line)
    line = _CALLOUT.sub(
        lambda m: f"> **{m.group(2) or _CALLOUT_TITLES.get(m.group(1), '')}**", line
    )
    parts = _CODE_SPAN.split(line)
    # Odd parts are code spans, shown as written; the rest is display text.
    return "".join(part if index % 2 else _display_text(part) for index, part in enumerate(parts))


def _display_text(text: str) -> str:
    text = _WIKILINK.sub(lambda m: m.group(2) or m.group(1), text)
    # Display only: no images to fetch and no HTML to interpret.
    return text.replace("![", "!\\[").replace("<", "&lt;")
