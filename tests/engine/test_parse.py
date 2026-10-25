"""Table parsing and command comments: examples plus properties (hypothesis)."""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from recon.engine.parse import DELIMITERS, comment_start, parse_table

# Tables ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "rows", "delimiter"),
    [
        ("80, HTTP, web\n443, HTTPS, web", [["80", "HTTP", "web"], ["443", "HTTPS", "web"]], ","),
        ("Port\tService\n22\tSSH", [["Port", "Service"], ["22", "SSH"]], "\t"),
        (
            "| Port | Service |\n|------|:-------:|\n| 53 | DNS |",
            [["Port", "Service"], ["53", "DNS"]],
            "|",
        ),
        ("a | b\nc | d", [["a", "b"], ["c", "d"]], "|"),
        ('"x, y", z\n1, 2', [["x, y", "z"], ["1", "2"]], ","),
        ("a\\|b | c", [["a|b", "c"]], "|"),
        ("a, b, c\nd", [["a", "b", "c"], ["d", "", ""]], ","),
        ("\n\n80, HTTP\n\n\n", [["80", "HTTP"]], ","),
        ("a,,c", [["a", "", "c"]], ","),
        ("a || c", [["a", "", "c"]], "|"),
        # Tab beats comma when both appear on every line.
        ("Name\tNotes\nnmap\tscans, maps", [["Name", "Notes"], ["nmap", "scans, maps"]], "\t"),
        # The delimiter on the most lines wins.
        ("a, b\nc | d\ne | f", [["a, b", ""], ["c", "d"], ["e", "f"]], "|"),
    ],
)
def test_tables(text: str, rows: list[list[str]], delimiter: str) -> None:
    table = parse_table(text)

    assert [list(row) for row in table.rows] == rows
    assert table.delimiter == delimiter


def test_plain_lines_are_not_a_grid() -> None:
    table = parse_table("just a note\nand another")

    assert table.delimiter is None
    assert table.rows == (("just a note",), ("and another",))
    assert table.columns == 1
    assert table.is_grid is False


def test_empty_text_is_an_empty_table() -> None:
    table = parse_table("   \n")

    assert (table.rows, table.columns, table.is_grid) == ((), 0, False)


def test_a_grid_needs_two_columns() -> None:
    assert parse_table("a, b").is_grid is True


_CELL = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs", "Cc", "Zl", "Zp"),
        blacklist_characters='\t|,"\\\n\r\x0b\x0c\x1c\x1d\x1e\x85',
    ),
    max_size=12,
).map(str.strip)


@given(
    st.lists(st.lists(_CELL, min_size=2, max_size=6), min_size=1, max_size=8).filter(
        lambda rows: all(any(cell for cell in row) for row in rows)
    ),
    st.sampled_from(DELIMITERS),
)
def test_rows_joined_with_a_delimiter_parse_back(rows: list[list[str]], delimiter: str) -> None:
    width = max(len(row) for row in rows)
    joiner = {"\t": "\t", "|": " | ", ",": ", "}[delimiter]
    text = "\n".join(joiner.join(row) for row in rows)

    if delimiter == "|":
        # Empty outer cells would read as Markdown's outer pipes, which are dropped.
        assume(all(row[0] and row[-1] for row in rows))

    table = parse_table(text)

    assert table.delimiter == delimiter
    assert [list(row) for row in table.rows] == [row + [""] * (width - len(row)) for row in rows]


@given(st.text(max_size=300))
def test_any_text_parses_to_a_rectangle(text: str) -> None:
    table = parse_table(text)

    assert all(len(row) == table.columns for row in table.rows)
    assert all(cell == cell.strip() for row in table.rows for cell in row)


# Command comments ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "start"),
    [
        ("dig example.com MX  # who handles mail", 20),
        ("# a whole-line comment", 0),
        ("  # indented", 2),
        ("curl http://x/#top", None),
        ('echo "# not a comment"', None),
        ("echo '# nor this' # but this", 18),
        ('echo "say \\"#hi\\"" # yes', 19),
        ("grep -c a#b file", None),
        ("nmap -sV 10.10.0.5", None),
        ("", None),
    ],
)
def test_comment_start(line: str, start: int | None) -> None:
    assert comment_start(line) == start


@given(st.text(max_size=200))
def test_comment_start_points_at_a_hash(line: str) -> None:
    start = comment_start(line)

    assert start is None or (line[start] == "#" and (start == 0 or line[start - 1].isspace()))
