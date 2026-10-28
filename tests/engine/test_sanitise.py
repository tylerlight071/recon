"""Sanitising model-derived text before it goes into a note (CLAUDE.md, Sanitise)."""

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon.engine.sanitise import cell, inline, mermaid_label

HOSTILE = [
    "![[secret.png]]",
    "[[Home]]",
    "<script>alert(1)</script>",
    "<!-- hide the rest",
    "%% recon:end %%",
    "---",
    "# Heading",
    "> [!warning] fake callout",
    "```",
    "[click](javascript:alert(1))",
    "![img](file:///etc/passwd)",
    "<javascript:alert(1)>",
    "| a | b |",
    "1. numbered",
    "- list",
    "THM{leaked_flag}",
    "line one\nline two\u2028three",
]


@pytest.mark.parametrize("text", HOSTILE)
def test_hostile_text_is_neutralised(text: str) -> None:
    safe = inline(text)

    assert "\n" not in safe
    assert "\u2028" not in safe
    assert not re.search(r"(?<!\\)\[\[", safe)
    assert not re.search(r"(?<!\\)!\[", safe)
    assert "<" not in safe
    assert "%%" not in safe
    assert "THM{" not in safe
    assert not re.search(r"\]\((?!https?://)", safe)
    assert not re.match(r"^(?:[#>+*=|~_-]|`{3}|\d+[.)])", safe)


def test_ordinary_text_reads_the_same() -> None:
    assert inline("Hex uses 0-9 then A-F; one digit is 4 bits.") == (
        "Hex uses 0-9 then A-F; one digit is 4 bits."
    )
    assert inline("Use `ls -la` to see [hidden](https://example.com) files") == (
        "Use `ls -la` to see [hidden](https://example.com) files"
    )


def test_backslashes_stay_literal() -> None:
    assert inline(r"C:\Windows\[[x]]") == r"C:\\Windows\\\[\[x\]\]"


def test_cells_escape_pipes() -> None:
    assert cell("a | b") == "a \\| b"


def test_mermaid_labels_cannot_escape_their_quotes_or_fence() -> None:
    label = mermaid_label('SYN"] --> evil["x` ```%% <b>#')

    assert '"' not in label
    assert "`" not in label
    assert "%" not in label
    assert "<" not in label
    assert ">" not in label
    assert label.startswith("SYN#quot;]")


@given(st.text(max_size=300))
def test_any_text_comes_out_as_one_safe_line(text: str) -> None:
    safe = inline(text)

    assert "\n" not in safe
    assert "\r" not in safe
    assert "<" not in safe
    assert "%%" not in safe
    assert not re.search(r"(?<!\\)\[\[", safe.replace("\\\\", ""))
    assert not re.match(r"^(?:[#>+*=|~_-]|`{3}|\d+[.)])", safe)
    assert re.search(r"(?i)(thm|htb|flag)\{", safe) is None


@given(st.text(max_size=200))
def test_any_label_is_safe_inside_quotes(text: str) -> None:
    label = mermaid_label(text)

    assert not set(label) & set('"`<>%\n')


@pytest.mark.parametrize(
    ("text", "safe"),
    [
        ("see ![x](https://a.b/c.png)", "see !\\[x](https://a.b/c.png)"),
        ("a <b> c", "a &lt;b> c"),
        ("50%% done", "50%\\% done"),
        ("x ``` y", "x \\`\\`\\` y"),
        ("x `` y", "x `` y"),
        ("[[Home]]", "\\[\\[Home\\]\\]"),
        ("[a](ftp://x)", "[a]\\(ftp://x)"),
        ("[a](https://x)", "[a](https://x)"),
        ("- item", "\\- item"),
        ("12) twelve", "\\12) twelve"),
        ("a\x00b\x1bc\u202ed\u200be", "a b c d e"),
        ("tabs\tand\r\nlines\u2028too", "tabs and lines too"),
        ("got THM{not_finished", "got"),
        ("got flag{also", "got"),
    ],
)
def test_exact_replacements(text: str, safe: str) -> None:
    assert inline(text) == safe


def test_mermaid_entities_are_exact() -> None:
    assert mermaid_label('# " < > % `') == "#35; #quot; #lt; #gt; #37; #96;"
    assert mermaid_label("a\x00b\u202ec THM{half") == "a b c"
