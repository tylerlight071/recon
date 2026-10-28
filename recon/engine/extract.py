"""Pipeline step 3, extract: the model reads the room and fills `RoomExtract`.

The room goes into the prompt between `<room>` delimiters and is described to
the model as data (CLAUDE.md, Prompt injection). That isn't relied on: the
schema, its length limits and the checks below are the defence.

Anything checkable in code is checked here, and code wins:
- task points only for tasks the room has;
- answers and explanations only for Question and Confused by blocks;
- concepts and tools only if Tyler's notes mention them (no invented notes);
- `own_words` only if it really is his sentence, otherwise it's generated;
- a tool's flags only if they appear in his commands for that tool;
- `related` only to other concepts from this room; duplicates merged;
- flags stripped from everything the model wrote (hard rule 2).
"""

import logging
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Final, Protocol

from pydantic import BaseModel, ValidationError

from recon.engine.capture import Capture, CaptureBlock
from recon.engine.commands import command_lines, invocations
from recon.engine.flags_filter import strip_flags
from recon.engine.schemas import Concept, FlagMeaning, Point, RoomExtract, TaskPoints, Tool
from recon.errors import ModelResponseInvalidError
from recon.services.runs import RunLog

PROMPT: Final = Path(__file__).resolve().parent / "prompts" / "extract.RoomExtract.md"
STEP: Final = "extract"
POINT_SOURCES: Final = frozenset({"key_idea", "command", "table", "voice"})
"""Block types a task point may come from: his own statements."""
LABELS: Final = {
    "key_idea": "key idea",
    "command": "command",
    "table": "table",
    "question": "question",
    "confused": "confused by",
    "room_question": "room question",
    "voice": "voice note",
}
_DELIMITER: Final = re.compile(r"<(/?)(room|task)\b", re.IGNORECASE)
_SENTENCE_END: Final = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_OPENING_WORDS: Final = 4
"""A sentence defines a concept if it names it within its first four words."""
_OWN_WORDS_MAX: Final = 400
_ALIAS_WORDS: Final = 4
_GUARD: Final = "\u2039"
"""Single left-pointing angle quotation mark: reads like "<", delimits nothing."""

_log = logging.getLogger(__name__)


class Model(Protocol):
    """The Ollama service's structured call (`services.ollama.OllamaService`)."""

    def structured[T: BaseModel](  # noqa: PLR0913 - mirrors OllamaService.structured
        self,
        *,
        model: str,
        schema: type[T],
        system: str,
        prompt: str,
        run: RunLog | None = None,
        step: str = "call",
        think: bool = False,
        context: int = ...,
    ) -> T:
        """One validated call."""


def extract(
    capture: Capture, model: Model, model_name: str, run: RunLog | None, *, think: bool = False
) -> RoomExtract:
    """Ask the model for the room's structure, then check it in code.

    Args:
        capture: The room, flags already removed (step 1).
        model: Makes the structured call.
        model_name: The text model, from Settings.
        run: Where the raw replies are kept.
        think: Let the model reason first (slower, often better; Settings).

    Returns:
        The checked extract.

    Raises:
        OllamaUnavailable, ModelMissing, ModelCallFailedError, ModelResponseInvalidError:
            From the call; the step fails cleanly and the review screen says so.
    """
    raw = ask(capture, model, model_name, run, think=think)
    checked = check(raw, capture)
    _log.info(
        "extract kept %s of %s concepts and %s of %s tools",
        len(checked.concepts),
        len(raw.concepts),
        len(checked.tools),
        len(raw.tools),
    )
    return checked


def ask(
    capture: Capture, model: Model, model_name: str, run: RunLog | None, *, think: bool = False
) -> RoomExtract:
    """The model's reply, validated against the schema but not yet checked in code."""
    return model.structured(
        model=model_name,
        schema=RoomExtract,
        system=PROMPT.read_text(encoding="utf-8"),
        prompt=room_prompt(capture),
        run=run,
        step=STEP,
        think=think,
    )


def room_prompt(capture: Capture) -> str:
    """The room as the model reads it: numbered, typed blocks inside `<room>`."""
    place = " · ".join(p for p in (capture.platform, capture.path, capture.module) if p)
    lines = ["<room>", f"Room: {_data(capture.name)}"]
    if place:
        lines.append(f"Where: {_data(place)}")
    for task in capture.tasks:
        title = f" · {_data(task.title)}" if task.title else ""
        lines.append(f'<task number="{task.index}">Task {task.index}{title}')
        if task.status == "skipped" and not task.blocks:
            lines.append("(skipped)")
        lines.extend(_block_lines(block) for block in task.blocks)
        lines.append("</task>")
    lines.append("</room>")
    return "\n".join(lines)


def _block_lines(block: CaptureBlock) -> str:
    text = f"[block {block.id} · {LABELS[block.type]}]\n{_data(block.text)}"
    if block.answer:
        text += f"\nAnswer: {_data(block.answer)}"
    return text


def _data(text: str) -> str:
    # Tyler's text can't open or close the delimiters: "</room>" gets a look-alike "<".
    return _DELIMITER.sub(lambda m: f"{_GUARD}{m.group(1)}{m.group(2)}", text)


# ---- Checks in code ------------------------------------------------------------------------


def check(raw: RoomExtract, capture: Capture) -> RoomExtract:
    """`raw` with everything code can rule out removed, and flags stripped."""
    stripped, _emptied = _strip(raw.model_dump())
    try:
        clean = RoomExtract.model_validate(stripped)
    except ValidationError as exc:  # only if removing flags emptied the whole summary
        raise ModelResponseInvalidError from exc
    notes = _normalise(
        "\n".join(f"{b.text}\n{b.answer}" for b in capture.blocks())
        + "\n".join(f"\n{t.title}" for t in capture.tasks)
    )
    task_numbers = {task.index for task in capture.tasks if task.blocks}
    sentences = _sentences(capture)
    concepts = [
        c if c.own_words else _with_own_words(c, sentences)
        for c in _concepts(clean.concepts, notes, task_numbers)
    ]
    names = {c.name.casefold() for c in concepts}
    concepts = [
        c.model_copy(update={"related": [r for r in c.related if r.casefold() in names]})
        for c in concepts
    ]
    kinds = {b.id: b.type for b in capture.blocks()}
    tools = _tools(clean.tools, notes, capture)
    concepts = _without_tool_names(concepts, tools)
    names = {c.name.casefold() for c in concepts}
    return clean.model_copy(
        update={
            "tasks": _tasks(clean.tasks, capture),
            "concepts": concepts,
            "tools": tools,
            "claims": [c for c in clean.claims if c.block in kinds],
            "answers": [a for a in clean.answers if kinds.get(a.block) == "question"],
            "explanations": [e for e in clean.explanations if kinds.get(e.block) == "confused"],
            "cards": [c for c in clean.cards if c.concept.casefold() in names],
            "processes": [p for p in clean.processes if p.task in task_numbers],
        }
    )


def _tasks(tasks: Iterable[TaskPoints], capture: Capture) -> list[TaskPoints]:
    """Points only from his own statements, in the task they belong to.

    A point must name a Key idea, Command, Table or Voice block of its task:
    questions and confusions are answered elsewhere, never restated as facts.
    """
    sources = {
        block.id: task.index
        for task in capture.tasks
        for block in task.blocks
        if block.type in POINT_SOURCES
    }
    merged: dict[int, list[Point]] = {}
    for task in tasks:
        merged.setdefault(task.task, []).extend(
            p for p in task.points if sources.get(p.block) == task.task
        )
    return [TaskPoints(task=n, points=merged[n][:12]) for n in sorted(merged) if merged[n]]


def _concepts(concepts: Iterable[Concept], notes: str, tasks: set[int]) -> list[Concept]:
    kept: dict[str, Concept] = {}
    for found in concepts:
        if not any(_mentions(notes, n) for n in (found.name, *found.aliases)):
            continue
        own, definition = _own_words(found.own_words, found.definition, notes)
        concept = found.model_copy(
            update={
                "aliases": _unique(
                    a for a in found.aliases if a.casefold() != found.name.casefold()
                ),
                "own_words": own,
                "definition": definition,
                "tasks": sorted({t for t in found.tasks if t in tasks}),
            }
        )
        key = concept.name.casefold()
        if key in kept:
            kept[key] = _merge(kept[key], concept)
        else:
            kept[key] = concept
    return list(kept.values())


def _tools(tools: Iterable[Tool], notes: str, capture: Capture) -> list[Tool]:
    used: dict[str, set[str]] = {}
    for block in capture.blocks():
        if block.type == "command":
            for line in command_lines(block.text):
                for run in invocations(line.command):
                    used.setdefault(run.tool.casefold(), set()).update(run.flags)
    kept: dict[str, Tool] = {}
    for tool in tools:
        names = [tool.name, *tool.aliases]
        if tool.name.casefold() in kept or not any(_mentions(notes, n) for n in names):
            continue
        flags = set().union(*(used.get(n.casefold(), set()) for n in names))
        own, purpose = _own_words(tool.own_words, tool.purpose, notes)
        kept[tool.name.casefold()] = tool.model_copy(
            update={
                "aliases": _unique(a for a in tool.aliases if a.casefold() != tool.name.casefold()),
                "own_words": own,
                "purpose": purpose,
                "flags": _unique_flags(f for f in tool.flags if f.flag in flags),
            }
        )
    return list(kept.values())


def _own_words(own: str, generated: str, notes: str) -> tuple[str, str]:
    """His sentence only if it's really in his notes; otherwise it counts as generated."""
    own = " ".join(own.split())
    if own and _normalise(own) in notes:
        return own, ""
    return "", generated or own


def _without_tool_names(concepts: list[Concept], tools: list[Tool]) -> list[Concept]:
    """A tool's name means its tool note: no concept may be named or aliased by one."""
    taken = {n.casefold() for tool in tools for n in (tool.name, *tool.aliases)}
    return [
        c.model_copy(
            update={
                "aliases": [a for a in c.aliases if a.casefold() not in taken],
                "related": [r for r in c.related if r.casefold() not in taken],
            }
        )
        for c in concepts
        if c.name.casefold() not in taken
    ]


def _sentences(capture: Capture) -> list[str]:
    """His Key idea and Voice sentences, in order: where his own definitions live."""
    found: list[str] = []
    for block in capture.blocks():
        if block.type in {"key_idea", "voice"}:
            for line in block.text.splitlines():
                found.extend(s.strip() for s in _SENTENCE_END.split(line) if s.strip())
    return found


def _with_own_words(concept: Concept, sentences: Iterable[str]) -> Concept:
    """His first sentence that starts by naming the concept, as its definition.

    "TCP opens a connection with…" defines TCP in his words; the model often
    misses these, and his words beat a generated definition (SPEC.md, Concept note).
    """
    names = [_normalise(n) for n in (concept.name, *concept.aliases)]
    for sentence in sentences:
        opening = " ".join(_normalise(sentence).split()[:_OPENING_WORDS])
        if len(sentence) <= _OWN_WORDS_MAX and any(_mentions(opening, n) for n in names):
            return concept.model_copy(update={"own_words": sentence, "definition": ""})
    return concept


def _merge(first: Concept, second: Concept) -> Concept:
    return first.model_copy(
        update={
            "aliases": _unique([*first.aliases, *second.aliases]),
            "points": [*first.points, *second.points][:8],
            "gotchas": [*first.gotchas, *second.gotchas][:5],
            "related": _unique([*first.related, *second.related]),
            "tasks": sorted({*first.tasks, *second.tasks}),
            "own_words": first.own_words or second.own_words,
            "definition": "" if (first.own_words or second.own_words) else first.definition,
        }
    )


def _mentions(notes: str, name: str) -> bool:
    words = _normalise(name)
    return bool(words) and re.search(rf"(?<!\w){re.escape(words)}(?!\w)", notes) is not None


def _normalise(text: str) -> str:
    return " ".join(text.casefold().split())


def _unique(items: Iterable[str]) -> list[str]:
    """Names once each (ignoring case), and only name-sized: an alias isn't a definition."""
    seen: dict[str, str] = {}
    for item in items:
        if len(item.split()) <= _ALIAS_WORDS:
            seen.setdefault(item.casefold(), item)
    return list(seen.values())


def _unique_flags(items: Iterable[FlagMeaning]) -> list[FlagMeaning]:
    seen: dict[str, FlagMeaning] = {}
    for item in items:
        seen.setdefault(item.flag, item)
    return list(seen.values())


def _strip(value: object) -> tuple[object, bool]:
    """Flag-shaped text removed from every string (hard rule 2).

    Returns the cleaned value, and whether removing a flag left a string empty.
    A list item emptied that way (a point, or a claim whose text was only a
    flag) is dropped rather than failing validation.
    """
    if isinstance(value, str):
        cleaned = strip_flags(value, unfinished=True).text
        return cleaned, bool(value.strip()) and not cleaned.strip()
    if isinstance(value, list):
        kept = [item for item, emptied in map(_strip, value) if not emptied]
        return kept, False
    if isinstance(value, dict):
        pairs = {key: _strip(item) for key, item in value.items()}
        return {k: v for k, (v, _e) in pairs.items()}, any(e for _v, e in pairs.values())
    return value, False
