"""Reading structure out of what the user typed or pasted: tables and command comments.

Pure Python, no Qt. The Table block's grid preview uses `parse_table` while the
user types, and the vault templates (Phase 2) will use the same parse, so what the user
sees is what the note gets. `comment_start` finds the `# what it does` part of
a command line so the editor can show it dimmer.
"""

import csv
import re
from dataclasses import dataclass
from typing import Final, Literal

type Delimiter = Literal["\t", "|", ","]

DELIMITERS: Final[tuple[Delimiter, ...]] = ("\t", "|", ",")
"""In order of preference when a line could be read more than one way."""
_RULE: Final = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
"""A Markdown table's header rule, e.g. |---|:---:|. Not a row of data."""
_UNESCAPED_PIPE: Final = re.compile(r"(?<!\\)\|")


@dataclass(frozen=True, slots=True)
class Table:
    """Rows of cells, every row as wide as the widest."""

    rows: tuple[tuple[str, ...], ...]
    delimiter: Delimiter | None
    """How the text was split; None when it isn't a table (one column)."""

    @property
    def columns(self) -> int:
        """Number of columns (0 for no rows)."""
        return len(self.rows[0]) if self.rows else 0

    @property
    def is_grid(self) -> bool:
        """At least one row and two columns: worth showing as a grid."""
        return bool(self.rows) and self.columns >= 2  # noqa: PLR2004 - a grid needs two columns


def parse_table(text: str) -> Table:
    r"""Split pasted or typed rows into cells.

    The delimiter is whichever of tab, pipe and comma appears in the most
    lines (ties go to tab, then pipe). Markdown pipe tables lose their outer
    pipes and header rule; `\|` stays a literal pipe. Commas follow CSV
    quoting, so "a, b" in quotes is one cell. Blank lines are ignored and
    every cell is trimmed.

    Args:
        text: The Table block's text.

    Returns:
        The rows, padded to the same width.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    delimiter = _pick_delimiter(lines)
    if delimiter is None:
        return Table(tuple((line.strip(),) for line in lines), None)
    if delimiter == "|":
        lines = [line for line in lines if not _RULE.match(line)]
    rows = [_split(line, delimiter) for line in lines]
    width = max((len(row) for row in rows), default=0)
    padded = tuple(tuple(row) + ("",) * (width - len(row)) for row in rows)
    return Table(padded, delimiter)


def _pick_delimiter(lines: list[str]) -> Delimiter | None:
    counts = {d: sum(_has(line, d) for line in lines) for d in DELIMITERS}
    best = max(DELIMITERS, key=lambda d: counts[d])  # max keeps the first of equals
    return best if counts[best] else None


def _has(line: str, delimiter: Delimiter) -> bool:
    if delimiter == "|":
        return _UNESCAPED_PIPE.search(line) is not None
    return delimiter in line


def _split(line: str, delimiter: Delimiter) -> list[str]:
    if delimiter == ",":
        cells = next(csv.reader([line], skipinitialspace=True), [])
    elif delimiter == "|":
        cells = _UNESCAPED_PIPE.split(line.strip())
        # Markdown's outer pipes make empty first and last cells; drop just those.
        if len(cells) > 1 and not cells[0].strip():
            cells = cells[1:]
        if len(cells) > 1 and not cells[-1].strip():
            cells = cells[:-1]
        cells = [cell.replace("\\|", "|") for cell in cells]
    else:
        cells = line.split("\t")
    return [cell.strip() for cell in cells]


def comment_start(line: str) -> int | None:
    """Where a command line's `#` comment starts, or None.

    A `#` starts a comment at the start of the line or after whitespace, and
    not inside quotes, as in a shell: `curl http://x/#top` and `echo "# no"`
    have none.

    Args:
        line: One line of a Command block.

    Returns:
        The index of the `#`, or None.
    """
    quote: str | None = None
    previous = " "
    for index, char in enumerate(line):
        if quote is not None:
            if char == quote and previous != "\\":
                quote = None
        elif char in "'\"" and previous != "\\":
            quote = char
        elif char == "#" and previous.isspace():
            return index
        previous = char
    return None
