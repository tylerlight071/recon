"""Hard rule 2: flags are never stored.

Anything shaped like a CTF flag is removed before it reaches the database,
the vault, cards or backups:

- `THM{…}`, `flag{…}`, `HTB{…}` (any letter case, 1 to 200 characters inside,
  on one line): always removed. These are answers, never study material.
- A *lone* run of 32 or more hex characters (nothing alphanumeric touching
  either end): removed by default, because hashing rooms show example hashes
  that look exactly like flags. Tyler can say "Not a flag, keep it" for one
  such string; it's then listed in `kept` and left alone from then on.

When saving, an *unfinished* braced flag (`THM{` with no closing brace before
the end of its line) is removed too: typed one key at a time, a flag would
otherwise reach the database almost whole before its `}` arrives. Editors
don't do this, so Tyler sees what he types until the flag is complete.

Removing a match can join the text around it into a new flag-shaped string
(two hex halves either side of a `THM{…}`), so stripping repeats until the
text is stable. Pure Python, no Qt: the repository and the UI both call it.
"""

import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Final, Literal

type Kind = Literal["flag", "hex"]

BRACED: Final = re.compile(r"(?:thm|htb|flag)\{[^{}\n]{1,200}\}", re.IGNORECASE)
UNFINISHED: Final = re.compile(r"(?:thm|htb|flag)\{[^{}\n]{0,200}$", re.IGNORECASE | re.MULTILINE)
LONE_HEX: Final = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{32,}(?![0-9A-Za-z])")
_MAX_ROUNDS: Final = 50
"""Each round removes at least one character, so this is never reached in practice."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One flag-shaped string in a text."""

    kind: Kind
    text: str
    start: int
    end: int

    @property
    def keepable(self) -> bool:
        """Whether "Not a flag, keep it" is offered (hex lookalikes only)."""
        return self.kind == "hex"


@dataclass(frozen=True, slots=True)
class Filtered:
    """A text with its flags removed."""

    text: str
    removed: tuple[Finding, ...]
    """What was removed, in the order found (positions refer to the text at that round)."""

    @property
    def changed(self) -> bool:
        """Whether anything was removed."""
        return bool(self.removed)


def find_flags(text: str, kept: Collection[str] = (), *, unfinished: bool = False) -> list[Finding]:
    """Flag-shaped strings in `text`, in order, ignoring hex strings Tyler kept.

    Braced flags are found first and blanked out (same length, so positions
    hold) before looking for the rest, so no finding can overlap another.

    Args:
        text: Any text: typed, pasted, transcribed or read from a screenshot.
        kept: Hex strings marked "Not a flag, keep it". Braced flags can't be kept.
        unfinished: Also find braced flags still being typed (for saving).

    Returns:
        The findings, non-overlapping, sorted by position.
    """
    findings = [Finding("flag", m.group(0), m.start(), m.end()) for m in BRACED.finditer(text)]
    masked = _blank(text, findings)
    if unfinished:
        found = [
            Finding("flag", m.group(0), m.start(), m.end()) for m in UNFINISHED.finditer(masked)
        ]
        findings += found
        masked = _blank(masked, found)
    findings += [
        Finding("hex", m.group(0), m.start(), m.end())
        for m in LONE_HEX.finditer(masked)
        if m.group(0) not in kept
    ]
    return sorted(findings, key=lambda f: f.start)


def strip_flags(text: str, kept: Collection[str] = (), *, unfinished: bool = False) -> Filtered:
    """Remove every flag-shaped string, repeating until none is left.

    Only the matched characters are removed; everything else Tyler wrote is
    left exactly as it was.

    Args:
        text: The text to clean.
        kept: Hex strings marked "Not a flag, keep it".
        unfinished: Also remove braced flags still being typed. The database
            layer always sets this; editors don't, so typing isn't disturbed.

    Returns:
        The cleaned text and what was removed.
    """
    removed: list[Finding] = []
    for _ in range(_MAX_ROUNDS):
        findings = find_flags(text, kept, unfinished=unfinished)
        if not findings:
            break
        removed.extend(findings)
        text = _cut(text, findings)
    return Filtered(text, tuple(removed))


def contains_flag(text: str, kept: Collection[str] = (), *, unfinished: bool = False) -> bool:
    """Whether `text` still has anything flag-shaped in it."""
    return bool(find_flags(text, kept, unfinished=unfinished))


def _cut(text: str, findings: list[Finding]) -> str:
    # Splice from the end so earlier positions stay valid.
    for finding in sorted(findings, key=lambda f: f.start, reverse=True):
        text = text[: finding.start] + text[finding.end :]
    return text


def _blank(text: str, findings: list[Finding]) -> str:
    # NUL is neither a hex digit nor a letter: nothing can match across a blank.
    for finding in findings:
        text = text[: finding.start] + "\0" * (finding.end - finding.start) + text[finding.end :]
    return text
