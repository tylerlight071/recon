"""Safe file names built from room and concept names (CLAUDE.md, Path safety).

A name the user typed (or pasted) becomes a file name only through `file_name`:
no path separators, no `..`, no control characters, no names Windows or
Obsidian reserve, nothing hidden (a leading dot), and short enough for any
filesystem. Callers still check the resolved path stays inside its folder.
"""

import re
import unicodedata
from typing import Final

LIMIT_BYTES: Final = 150
"""Room for a suffix like " (12).md" well inside the usual 255-byte limit."""
FALLBACK: Final = "Untitled room"
# Path separators, and characters Obsidian won't allow in note names.
_FORBIDDEN: Final = re.compile(r'[/\\:*?"<>|#^\[\]]')
_SPACES: Final = re.compile(r"\s+")
_RESERVED: Final = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def file_name(name: str, fallback: str = FALLBACK) -> str:
    """A safe file name (without extension) for `name`.

    Args:
        name: A room or concept name, as typed.
        fallback: Used when nothing usable is left.

    Returns:
        The name with forbidden characters replaced by spaces, whitespace
        collapsed, leading dots and spaces dropped, reserved names suffixed,
        and cut to `LIMIT_BYTES` of UTF-8 on a character boundary.
    """
    cleaned = "".join(" " if _unsafe(char) else char for char in unicodedata.normalize("NFC", name))
    cleaned = _SPACES.sub(" ", _FORBIDDEN.sub(" ", cleaned)).strip(" .")
    if cleaned.split(".")[0].lower() in _RESERVED:
        cleaned = f"{cleaned} file"
    cleaned = _cut(cleaned).rstrip(" .")
    return cleaned or fallback


def _unsafe(char: str) -> bool:
    # Control, format (e.g. bidi overrides), lone surrogate, private-use and unassigned
    # characters. Line and paragraph separators are whitespace, so _SPACES handles them.
    return unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co", "Cn"}


def _cut(text: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= LIMIT_BYTES:
        return text
    return encoded[:LIMIT_BYTES].decode("utf-8", errors="ignore")
