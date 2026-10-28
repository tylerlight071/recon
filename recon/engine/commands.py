"""Reading Tyler's Command blocks: each command, what it does, which tools and flags.

Pure Python and checked in code, never by the model (CLAUDE.md, Model rules):
the room note's Commands table, the tool notes' examples, and which flags a
tool note may describe all come from here.
"""

import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final

from recon.engine.parse import comment_start

_SEPARATORS: Final = re.compile(r"\|\||&&|[|;]")
_PROMPT: Final = re.compile(r"^\s*(?:[$#>]|\w+@[\w.-]+:\S*[$#])\s+")
"""A shell prompt pasted with the command: "$ ", "# ", "user@host:~$ "."""
_ASSIGNMENT: Final = re.compile(r"^[A-Za-z_]\w*=")
_PROGRAM: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,39}$")
_WRAPPERS: Final = frozenset({"sudo", "doas", "time", "nohup", "env", "command", "exec"})
_WRAPPER_VALUES: Final = frozenset({"-u", "-g", "-U", "-C", "-D", "-h", "-p", "-r", "-t", "-T"})
"""Wrapper options that take a value (`sudo -u root`): the value isn't the program."""


@dataclass(frozen=True, slots=True)
class CommandLine:
    """One command and what Tyler said it does ("" if nothing)."""

    command: str
    comment: str


@dataclass(frozen=True, slots=True)
class Invocation:
    """One program run in a command, with the flags it was given."""

    tool: str
    flags: tuple[str, ...]


def command_lines(text: str) -> list[CommandLine]:
    """Each command in a Command block, with its `# what it does`.

    A comment on a line of its own describes the next command, unless that
    command has its own.
    """
    lines: list[CommandLine] = []
    pending = ""
    for raw in text.splitlines():
        start = comment_start(raw)
        command = (raw if start is None else raw[:start]).strip()
        comment = "" if start is None else raw[start + 1 :].strip()
        if not command:
            pending = comment or pending
            continue
        lines.append(CommandLine(_PROMPT.sub("", command), comment or pending))
        pending = ""
    return lines


def invocations(command: str) -> list[Invocation]:
    """Every program a command runs (`a | b && c` runs three), with its flags."""
    found: list[Invocation] = []
    for part in _SEPARATORS.split(command):
        words = _words(part)
        while words and (_ASSIGNMENT.match(words[0]) or words[0] in _WRAPPERS):
            words.pop(0)
            while words and words[0].startswith("-"):  # sudo -u root, env -i
                if words.pop(0) in _WRAPPER_VALUES and words:
                    words.pop(0)
        if not words:
            continue
        program = PurePosixPath(words[0]).name
        if _PROGRAM.match(program):
            found.append(Invocation(program, tuple(_flags(words[1:]))))
    return found


def tool_of(command: str) -> str:
    """The first program a command runs ("" if none can be read)."""
    found = invocations(command)
    return found[0].tool if found else ""


def flags_of(command: str) -> set[str]:
    """Every flag in a command, without values: `--port=80` is `--port`."""
    return {flag for found in invocations(command) for flag in found.flags}


def _flags(words: list[str]) -> list[str]:
    flags: list[str] = []
    for word in words:
        if word == "--":
            break
        if word.startswith("-") and len(word) > 1 and not word[1:2].isdigit():
            flags.append(word.split("=", 1)[0])
    return flags


def _words(text: str) -> list[str]:
    try:
        return shlex.split(text, comments=False, posix=True)
    except ValueError:  # an unclosed quote: still worth reading
        return text.split()
