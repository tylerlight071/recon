"""Hard rule 2: the flag filter. Exact boundaries, plus properties over arbitrary text."""

import itertools
import string

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from recon.engine.flags_filter import BRACED, LONE_HEX, contains_flag, find_flags, strip_flags

MD5_HELLO = "5d41402abc4b2a76b9719d911017c592"

# Braced flags ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flag",
    [
        "THM{this_is_a_test}",
        "flag{abc}",
        "HTB{x}",
        "thm{lower}",
        "Flag{Mixed_Case}",
        "hTb{1}",
        "THM{with spaces and !@#$%^&*()}",
        "THM{" + "a" * 200 + "}",
    ],
)
def test_braced_flags_are_removed(flag: str) -> None:
    result = strip_flags(f"Answer: {flag} done")

    assert result.text == "Answer:  done"
    assert [f.text for f in result.removed] == [flag]
    assert result.removed[0].kind == "flag"
    assert result.removed[0].keepable is False


@pytest.mark.parametrize(
    "text",
    [
        "THM{}",  # nothing inside
        "THM{" + "a" * 201 + "}",  # longer than a flag
        "THM{line\nbreak}",  # across lines
        "THM{nested{brace}}",
        "THM[square]",
        "TRYHACKME{x}",
        "THM {space}",
    ],
)
def test_things_that_are_not_braced_flags(text: str) -> None:
    assert [f for f in find_flags(text) if f.kind == "flag"] == []


def test_prefix_glued_to_a_word_is_still_caught() -> None:
    assert strip_flags("myflag{secret}").text == "my"


def test_nested_brace_inner_flag_is_removed() -> None:
    assert strip_flags("flag{THM{x}}").text == "flag{}"


# Lone hex ----------------------------------------------------------------------------


@pytest.mark.parametrize("length", [32, 33, 40, 64, 128])
def test_lone_hex_of_32_or_more_is_removed(length: int) -> None:
    value = ("ab12" * 40)[:length]

    result = strip_flags(f"hash {value} end")

    assert result.text == "hash  end"
    assert result.removed[0].kind == "hex"
    assert result.removed[0].keepable is True


def test_31_hex_characters_are_left_alone() -> None:
    value = "a" * 31

    assert strip_flags(value).text == value


@pytest.mark.parametrize(
    "text",
    [
        f"x{MD5_HELLO}",  # letter touching the start
        f"{MD5_HELLO}g",  # letter touching the end
        f"0x{MD5_HELLO}",  # a number literal
        f"9{MD5_HELLO}z",
    ],
)
def test_hex_touching_letters_or_digits_is_not_lone(text: str) -> None:
    assert strip_flags(text).text == text


@pytest.mark.parametrize("edge", [" ", ":", "=", "(", "\n", "\t", "-", "/", ".", ","])
def test_hex_next_to_punctuation_is_lone(edge: str) -> None:
    assert strip_flags(f"md5{edge}{MD5_HELLO}{edge}").text == f"md5{edge}{edge}"


def test_uppercase_hex_counts() -> None:
    assert strip_flags(MD5_HELLO.upper()).text == ""


def test_kept_hex_survives_and_others_do_not() -> None:
    other = "f" * 32

    result = strip_flags(f"{MD5_HELLO} and {other}", kept={MD5_HELLO})

    assert result.text == f"{MD5_HELLO} and "
    assert [f.text for f in result.removed] == [other]


def test_braced_flags_cannot_be_kept() -> None:
    assert strip_flags("THM{x}", kept={"THM{x}"}).text == ""


def test_hex_inside_a_braced_flag_is_one_finding() -> None:
    inner = f"THM{{{MD5_HELLO}}}"

    findings = find_flags(inner)

    assert [(f.kind, f.text) for f in findings] == [("flag", inner)]


# Fixpoint and positions ----------------------------------------------------------------


def test_removal_that_joins_hex_halves_is_caught() -> None:
    joined = "a" * 20 + "THM{x}" + "b" * 20

    result = strip_flags(f"{joined} end")

    assert result.text == " end"
    assert [f.kind for f in result.removed] == ["flag", "hex"]


def test_findings_are_in_order_with_positions() -> None:
    text = f"{MD5_HELLO} then THM{{a}} then flag{{b}}"

    findings = find_flags(text)

    assert [f.text for f in findings] == [MD5_HELLO, "THM{a}", "flag{b}"]
    assert all(text[f.start : f.end] == f.text for f in findings)


def test_clean_text_is_unchanged() -> None:
    text = "TXT records hold text. Port 443 is HTTPS. md5sum prints a hash."

    result = strip_flags(text)

    assert result.text == text
    assert result.removed == ()
    assert result.changed is False
    assert contains_flag(text) is False


def test_contains_flag() -> None:
    assert contains_flag("THM{x}") is True
    assert contains_flag(MD5_HELLO) is True
    assert contains_flag(MD5_HELLO, kept={MD5_HELLO}) is False


def test_fixture_room_flag_and_lookalike() -> None:
    line = "Got the answer for this task: THM{this_is_a_test}"
    hash_line = f"md5sum prints a 32 character hex hash, e.g. {MD5_HELLO} for the word hello"

    assert strip_flags(line).text == "Got the answer for this task: "
    assert strip_flags(hash_line).text == hash_line.replace(MD5_HELLO, "")
    assert strip_flags(hash_line, kept={MD5_HELLO}).text == hash_line


# Properties ------------------------------------------------------------------------------

flags = st.builds(
    lambda prefix, body: f"{prefix}{{{body}}}",
    st.sampled_from(["THM", "flag", "HTB", "thm", "FLAG"]),
    st.text(alphabet=string.ascii_letters + string.digits + "_-!. ", min_size=1, max_size=60),
)
hexes = st.text(alphabet="0123456789abcdefABCDEF", min_size=32, max_size=80)
prose = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="{}"), max_size=200
)


@given(st.text(max_size=400))
def test_output_never_contains_a_flag(text: str) -> None:
    assert not contains_flag(strip_flags(text).text)


@given(st.text(max_size=400))
def test_stripping_is_idempotent(text: str) -> None:
    once = strip_flags(text).text

    assert strip_flags(once).text == once


@given(st.text(max_size=400))
def test_only_characters_are_removed_never_added(text: str) -> None:
    out = strip_flags(text).text

    assert len(out) <= len(text)
    remaining = iter(text)
    assert all(ch in remaining for ch in out)  # out is a subsequence of text


@given(prose, flags, prose)
def test_a_flag_between_texts_goes_and_the_rest_stays(before: str, flag: str, after: str) -> None:
    assume(not contains_flag(before) and not contains_flag(after))
    assume(not contains_flag(before + after))

    result = strip_flags(before + " " + flag + " " + after)

    assert result.text == before + "  " + after
    assert flag in [f.text for f in result.removed]


@given(prose, hexes, prose)
def test_kept_hex_always_survives(before: str, value: str, after: str) -> None:
    assume(not contains_flag(before) and not contains_flag(after))

    text = f"{before} {value} {after}"

    assert value in strip_flags(text, kept={value}).text


@given(hexes)
def test_patterns_agree_with_the_finder(value: str) -> None:
    assert LONE_HEX.fullmatch(value)
    assert find_flags(value)[0].text == value
    assert BRACED.search(value) is None


# Unfinished flags (saving only) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "saved"),
    [
        ("Answer: THM{this_is_a_te", "Answer: "),
        ("flag{", ""),
        ("first line THM{abc\nsecond line", "first line \nsecond line"),
        ("THM{done} and HTB{still typing", " and "),
    ],
)
def test_unfinished_flags_are_removed_when_saving(text: str, saved: str) -> None:
    assert strip_flags(text, unfinished=True).text == saved


def test_editors_leave_unfinished_flags_alone() -> None:
    assert strip_flags("Answer: THM{this_is_a_te").text == "Answer: THM{this_is_a_te"


def test_an_unfinished_brace_mid_line_loses_the_rest_of_that_line_only() -> None:
    text = "use THM{ then the answer\nnext line stays"

    assert strip_flags(text, unfinished=True).text == "use \nnext line stays"


@given(prose)
def test_every_prefix_of_a_typed_flag_saves_without_its_body(before: str) -> None:
    assume(not contains_flag(before, unfinished=True))
    flag = "THM{secret_answer}"

    for end in range(len("THM{") + 1, len(flag) + 1):
        saved = strip_flags(before + flag[:end], unfinished=True).text
        assert "secret" not in saved
        assert saved == before


def test_unfinished_findings_are_reported_as_flags() -> None:
    text = "ok THM{half"

    findings = find_flags(text, unfinished=True)

    assert [(f.kind, f.text, f.start, f.end) for f in findings] == [("flag", "THM{half", 3, 11)]
    assert findings[0].keepable is False


def test_contains_flag_only_counts_unfinished_ones_when_asked() -> None:
    assert contains_flag("THM{half") is False
    assert contains_flag("THM{half", unfinished=True) is True


def test_hex_right_after_a_flag_is_found_in_the_same_pass() -> None:
    text = f"THM{{x}}{MD5_HELLO}"

    assert [f.kind for f in find_flags(text)] == ["flag", "hex"]


def test_findings_never_overlap() -> None:
    text = f"THM{{{MD5_HELLO}}} {MD5_HELLO} flag{{y THM{{z"

    findings = find_flags(text, unfinished=True)

    assert all(a.end <= b.start for a, b in itertools.pairwise(findings))
    assert [f.kind for f in findings] == ["flag", "hex", "flag"]


def test_several_findings_in_one_pass_are_cut_exactly() -> None:
    result = strip_flags(f"a THM{{x}} b flag{{y}} c {MD5_HELLO} d")

    assert result.text == "a  b  c  d"
    assert [f.text for f in result.removed] == ["THM{x}", "flag{y}", MD5_HELLO]


def test_positions_after_a_mid_text_flag_are_exact() -> None:
    text = f"prefix THM{{x}} then {MD5_HELLO} and flag{{y"

    findings = find_flags(text, unfinished=True)

    assert [text[f.start : f.end] for f in findings] == [f.text for f in findings]
    assert [f.text for f in findings] == ["THM{x}", MD5_HELLO, "flag{y"]
