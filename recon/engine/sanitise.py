"""Making model-derived text safe to put in a vault note (CLAUDE.md, Sanitise).

Every model reply is untrusted: it may be wrong, or shaped by text Tyler
pasted. Before any of it goes into Markdown, `inline` turns it into one line
of plain text that can't:
- link or embed (`[[…]]`, `![[…]]`, `![…](…)`): only the engine makes links;
- open HTML (`<script>`, `<!--`, autolinks);
- start or end a Recon section (`%%` markers) or a frontmatter block (`---`);
- become structure at the start of a line (heading, quote, callout, list,
  fence, table row, rule);
- link anywhere but http(s) (`[x](javascript:…)`).

`cell` does the same for a table cell, `mermaid_label` for a diagram label.
Flags are stripped as well (hard rule 2).
"""

import re
import unicodedata
from typing import Final

from recon.engine.flags_filter import strip_flags

_LINK_TARGET: Final = re.compile(r"\]\((?!https?://)", re.IGNORECASE)
"""A Markdown link or image whose target isn't http(s): `](javascript:…`."""
_LEADING: Final = re.compile(r"^(?:[#>+*=|~_-]|`{3,}|\d+[.)])")
_FENCE_RUN: Final = re.compile(r"`{3,}")


def inline(text: str) -> str:
    """Model text as one safe line of Markdown.

    Args:
        text: Anything the model wrote.

    Returns:
        One line: whitespace collapsed, control characters gone, and nothing
        that Markdown or Obsidian would read as a link, embed, HTML, comment,
        marker or structure.
    """
    text = _one_line(strip_flags(text, unfinished=True).text)
    text = text.replace("\\", "\\\\")
    text = text.replace("[[", "\\[\\[").replace("]]", "\\]\\]")
    text = text.replace("![", "!\\[")
    text = _LINK_TARGET.sub("]\\(", text)
    text = text.replace("<", "&lt;")
    text = text.replace("%%", "%\\%")
    text = _FENCE_RUN.sub(lambda m: "\\`" * len(m.group(0)), text)
    if _LEADING.match(text):
        text = "\\" + text
    return text


def cell(text: str) -> str:
    """Model text for a Markdown table cell: `inline`, with pipes escaped."""
    return inline(text).replace("|", "\\|")


def mermaid_label(text: str) -> str:
    """Text for a quoted Mermaid label: `A["…"]`.

    Quotes, angle brackets, `%` (Mermaid comments and Recon markers) and
    backticks (which could close the code fence) become Mermaid's `#…;`
    entity codes; `#` itself is escaped first so nothing else is decoded.
    """
    text = _one_line(strip_flags(text, unfinished=True).text)
    entities = {"#": "#35;", '"': "#quot;", "<": "#lt;", ">": "#gt;", "%": "#37;", "`": "#96;"}
    return "".join(entities.get(char, char) for char in text)


def _one_line(text: str) -> str:
    # Control and format characters (NUL, ESC, bidi overrides, zero-width) become spaces;
    # str.split already treats line and paragraph separators as whitespace.
    kept = "".join(" " if unicodedata.category(char) in {"Cc", "Cf"} else char for char in text)
    return " ".join(kept.split())
