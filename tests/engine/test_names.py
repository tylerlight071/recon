"""Safe file names from room names: hostile examples and properties."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon.engine.names import FALLBACK, LIMIT_BYTES, file_name


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("DNS in Detail", "DNS in Detail"),
        ("../../etc/passwd", "etc passwd"),
        ("..", FALLBACK),
        ("", FALLBACK),
        ("   ", FALLBACK),
        (".hidden", "hidden"),
        ("a/b\\c", "a b c"),
        ('What? Why: "this" <now> | [[link]] #tag ^block', "What Why this now link tag block"),
        ("tab\there\nnewline", "tab here newline"),
        ("bidi" + chr(0x202E) + "evil", "bidi evil"),  # a right-to-left override
        ("CON", "CON file"),
        ("nul.txt", "nul.txt file"),
        ("com1", "com1 file"),
        ("console", "console"),
        ("trailing dot.", "trailing dot"),
        ("Cafe" + chr(0x301), "Caf" + chr(0xE9)),  # normalised to one character
    ],
)
def test_file_names(name: str, safe: str) -> None:
    assert file_name(name) == safe


def test_long_names_are_cut_on_a_character_boundary() -> None:
    name = "é" * 200

    safe = file_name(name)

    assert len(safe.encode("utf-8")) <= LIMIT_BYTES
    assert set(safe) == {"é"}


@given(st.text(max_size=400))
def test_file_names_are_always_safe(name: str) -> None:
    safe = file_name(name)

    assert safe
    assert "/" not in safe
    assert "\\" not in safe
    assert "\x00" not in safe
    assert not safe.startswith((".", " "))
    assert not safe.endswith((".", " "))
    assert safe not in {".", ".."}
    assert len(safe.encode("utf-8")) <= LIMIT_BYTES
    assert all(char.isprintable() for char in safe)
    assert file_name(safe) == safe
