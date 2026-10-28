"""Pydantic schemas for every model call (CLAUDE.md, Model rules).

Each schema is sent to Ollama as `format` and described in the prompt, and
every reply is validated against it. Lengths are capped so a reply shaped by
prompt injection can't flood a note; names can't carry link or markup
characters. A reply that breaks a rule fails validation and gets one retry.
"""

import re
from typing import Annotated, Final

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

_NAME_FORBIDDEN: Final = re.compile(r"[\[\]|#^%<>`{}\\\r\n\t]")


def _plain_name(value: str) -> str:
    value = " ".join(value.split())
    if not value or _NAME_FORBIDDEN.search(value):
        msg = "a name is plain words: no brackets, |, #, ^, %, <, >, backticks or braces"
        raise ValueError(msg)
    return value


Name = Annotated[str, Field(min_length=1, max_length=80), AfterValidator(_plain_name)]
"""A concept or tool name, e.g. "TCP three-way handshake" or "nmap"."""
Line = Annotated[str, Field(min_length=1, max_length=400)]
"""One point or sentence."""
Paragraph = Annotated[str, Field(min_length=1, max_length=1200)]
"""A short answer or explanation."""
Short = Annotated[str, Field(max_length=60)]
"""A topic or category, e.g. "Networking"."""


class _Schema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Point(_Schema):
    """One of the user's points, tidied, with the block it came from."""

    block: int = Field(description="The number of the block this point comes from.")
    text: Line = Field(description="The point as a short, tidy sentence. Only what he wrote.")


class TaskPoints(_Schema):
    """The user's points for one task, tidied."""

    task: int = Field(ge=1, description="The task number, as in the notes.")
    points: list[Point] = Field(
        max_length=12,
        description="His points for this task, each from one of its blocks.",
    )


class Concept(_Schema):
    """One idea worth its own note."""

    name: Name = Field(description="The usual name for the idea, e.g. 'Hexadecimal'.")
    aliases: list[Name] = Field(
        default_factory=list,
        max_length=6,
        description="Other names for it, including the words he used if they differ.",
    )
    topic: Short = Field(default="", description="A broad area, e.g. 'Networking'.")
    own_words: str = Field(
        default="",
        max_length=400,
        description=(
            "A sentence copied exactly from his notes that says what it is, "
            "or an empty string if he didn't define it."
        ),
    )
    definition: str = Field(
        default="",
        max_length=400,
        description="Only when own_words is empty: one or two plain lines defining it.",
    )
    points: list[Line] = Field(
        default_factory=list,
        max_length=8,
        description="What his notes say about it, as short sentences.",
    )
    gotchas: list[Line] = Field(
        default_factory=list,
        max_length=5,
        description="Things he found confusing or easy to get wrong about it, from his notes.",
    )
    related: list[Name] = Field(
        default_factory=list,
        max_length=6,
        description="Names of other concepts in this list that it connects to.",
    )
    tasks: list[int] = Field(
        default_factory=list, max_length=20, description="Task numbers where it comes up."
    )


class FlagMeaning(_Schema):
    """What one of a tool's flags does."""

    flag: str = Field(min_length=1, max_length=40, description="The flag, e.g. '-sV'.")
    meaning: Line = Field(description="What it does, in a few words.")


class Tool(_Schema):
    """A program or utility he used or read about."""

    name: Name = Field(description="The tool's name as typed on the command line, e.g. 'nmap'.")
    aliases: list[Name] = Field(default_factory=list, max_length=4)
    category: Short = Field(default="", description="e.g. 'Network scanner'.")
    own_words: str = Field(
        default="",
        max_length=400,
        description="A sentence copied exactly from his notes saying what it's for, or ''.",
    )
    purpose: str = Field(
        default="",
        max_length=400,
        description="Only when own_words is empty: one plain line on what it's for.",
    )
    flags: list[FlagMeaning] = Field(
        default_factory=list,
        max_length=20,
        description="Flags used in his commands for this tool, and what each does.",
    )


class Claim(_Schema):
    """A factual statement in his notes, for fact-checking (Phase 3)."""

    block: int = Field(description="The block number it came from.")
    claim: Line = Field(description="The statement, as he made it.")


class Answer(_Schema):
    """A suggested answer to one of his Question blocks."""

    block: int = Field(description="The Question block's number.")
    answer: Paragraph


class Explanation(_Schema):
    """An explanation for one of his "Confused by" blocks."""

    block: int = Field(description="The Confused by block's number.")
    explanation: Paragraph


class CardSuggestion(_Schema):
    """A flashcard he might keep (kept or skipped after Apply, Phase 4)."""

    question: Line
    answer: Line
    concept: Name = Field(description="The concept it belongs to.")


class Process(_Schema):
    """A sequence of steps he described, drawn as a diagram."""

    title: Name
    task: int = Field(ge=1)
    steps: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        min_length=2, max_length=10, description="Each step in a few words, in order."
    )


class RoomExtract(_Schema):
    """Everything the extract step pulls out of one room (pipeline step 3)."""

    summary: list[Line] = Field(
        min_length=3,
        max_length=5,
        description="Three to five short lines on what the room taught.",
    )
    tasks: list[TaskPoints] = Field(
        min_length=1,
        max_length=60,
        description="One entry for every task that has notes, in order.",
    )
    concepts: list[Concept] = Field(default_factory=list, max_length=20)
    tools: list[Tool] = Field(default_factory=list, max_length=10)
    claims: list[Claim] = Field(default_factory=list, max_length=40)
    answers: list[Answer] = Field(default_factory=list, max_length=30)
    explanations: list[Explanation] = Field(default_factory=list, max_length=30)
    cards: list[CardSuggestion] = Field(default_factory=list, max_length=20)
    processes: list[Process] = Field(default_factory=list, max_length=5)
