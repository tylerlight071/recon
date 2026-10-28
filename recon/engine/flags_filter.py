"""Hard rule 2: flags are never stored.

Anything shaped like a CTF flag is removed before it reaches the database,
the vault, cards or backups:

- `THM{…}`, `flag{…}`, `HTB{…}` (any letter case, 1 to 200 characters inside,
  on one line): always removed. These are answers, never study material.
- A *lone* run of 32 or more hex characters (nothing alphanumeric touching
  either end): removed by default, because hashing rooms show example hashes
  that look exactly like flags. The user can say "Not a flag, keep it" for one
  such string; it's then listed in `kept` and left alone from then on.

When saving, an *unfinished* braced flag is removed too: typed one key at a
time, a flag would otherwise reach the database almost whole before its `}`
arrives. Only something that looks like a flag mid-typing counts: the prefix,
then no whitespace, quotes or pipes, up to the end of the line. So commands
and prose that mention `flag{` keep every word (audit F-03). While typing (timed
autosaves, undo snapshots), a 20-31 character hex run ending a line is held
back too, so a hash typed key by key never reaches the database (audit F-07);
a final save stores it, so a real ID ending a line isn't lost. Editors don't
do either, so the user sees what they type until a flag is complete.

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
# A flag still being typed: the prefix, then only characters a flag body has (no
# whitespace, quotes or pipes), running to the end of the line. Narrow on purpose
# (audit F-03): `grep -ri "flag{" /home` or prose about the THM{ prefix isn't a flag.
UNFINISHED: Final = re.compile(
    r"(?:thm|htb|flag)\{[^{}\s\"'`|]{0,200}$", re.IGNORECASE | re.MULTILINE
)
# A hash still being typed: 20 to 31 hex characters ending a line (audit F-07). Held
# back from timed autosaves only, never from a final save, so a real ID ending a line
# is stored once the user moves on.
TYPING_HEX: Final = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{20,31}$", re.MULTILINE)
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


def find_flags(
    text: str, kept: Collection[str] = (), *, unfinished: bool = False, typing: bool = False
) -> list[Finding]:
    """Flag-shaped strings in `text`, in order, ignoring hex strings the user kept.

    Braced flags are found first and blanked out (same length, so positions
    hold) before looking for the rest, so no finding can overlap another.

    Args:
        text: Any text: typed, pasted, transcribed or read from a screenshot.
        kept: Hex strings marked "Not a flag, keep it". Braced flags can't be kept.
        unfinished: Also find braced flags still being typed (for saving).
        typing: Also find a hash still being typed at a line's end (timed autosaves).

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
    hexes = [
        Finding("hex", m.group(0), m.start(), m.end())
        for m in LONE_HEX.finditer(masked)
        if m.group(0) not in kept
    ]
    findings += hexes
    if typing:
        masked = _blank(masked, hexes)
        findings += [
            Finding("hex", m.group(0), m.start(), m.end()) for m in TYPING_HEX.finditer(masked)
        ]
    return sorted(findings, key=lambda f: f.start)


def strip_flags(
    text: str, kept: Collection[str] = (), *, unfinished: bool = False, typing: bool = False
) -> Filtered:
    """Remove every flag-shaped string, repeating until none is left.

    Only the matched characters are removed; everything else the user wrote is
    left exactly as it was.

    Args:
        text: The text to clean.
        kept: Hex strings marked "Not a flag, keep it".
        unfinished: Also remove braced flags still being typed. The database
            layer always sets this; editors don't, so typing isn't disturbed.
        typing: Also hold back a hash still being typed at a line's end. Timed
            autosaves and undo snapshots set this; final saves don't.

    Returns:
        The cleaned text and what was removed.
    """
    removed: list[Finding] = []
    for _ in range(_MAX_ROUNDS):
        findings = find_flags(text, kept, unfinished=unfinished, typing=typing)
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
