"""Reading Command blocks in code: commands, comments, tools and flags."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon.engine.commands import (
    CommandLine,
    Invocation,
    command_lines,
    flags_of,
    invocations,
    tool_of,
)


def test_each_line_with_its_comment() -> None:
    text = "pwd  # where am I\n\n# list everything\nls -la\ncd /tmp # go there\n# trailing note"

    assert command_lines(text) == [
        CommandLine("pwd", "where am I"),
        CommandLine("ls -la", "list everything"),
        CommandLine("cd /tmp", "go there"),
    ]


def test_a_command_keeps_its_own_comment_over_one_above() -> None:
    assert command_lines("# above\nls # own") == [CommandLine("ls", "own")]


@pytest.mark.parametrize(
    ("line", "command"),
    [
        ("$ ls -la", "ls -la"),
        ("# whoami", None),
        ("user@host:~$ id", "id"),
        ("root@box:/tmp# id", "id"),
        ("> echo hi", "echo hi"),
    ],
)
def test_pasted_prompts_are_dropped(line: str, command: str | None) -> None:
    lines = command_lines(line)
    assert [c.command for c in lines] == ([command] if command else [])


def test_quoted_hashes_are_not_comments() -> None:
    assert command_lines('echo "# not a comment"  # but this is') == [
        CommandLine('echo "# not a comment"', "but this is")
    ]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("nmap -sV -p 80 10.10.10.10", [Invocation("nmap", ("-sV", "-p"))]),
        ("sudo -u root nmap -sS host", [Invocation("nmap", ("-sS",))]),
        ("LANG=C sort -n file", [Invocation("sort", ("-n",))]),
        ("/usr/bin/curl --header=x http://a", [Invocation("curl", ("--header",))]),
        (
            "cat a.log | grep -i error && wc -l",
            [Invocation("cat", ()), Invocation("grep", ("-i",)), Invocation("wc", ("-l",))],
        ),
        ("find / -name '*.conf' 2>/dev/null", [Invocation("find", ("-name",))]),
        ("ls -- -notaflag", [Invocation("ls", ())]),
        ("head -5 file", [Invocation("head", ())]),
        ("echo 'unclosed", [Invocation("echo", ())]),
        ("./run.sh -v", [Invocation("run.sh", ("-v",))]),
        ("", []),
        ("sudo", []),
        ("$(evil)", []),
    ],
)
def test_invocations(command: str, expected: list[Invocation]) -> None:
    assert invocations(command) == expected


def test_tool_and_flags_helpers() -> None:
    assert tool_of("sudo nmap -sV x") == "nmap"
    assert tool_of("") == ""
    assert flags_of("ls -la | grep -v x") == {"-la", "-v"}


@given(st.text(max_size=200))
def test_never_raises_and_tools_are_plain_names(text: str) -> None:
    for line in command_lines(text):
        for run in invocations(line.command):
            assert run.tool
            assert "/" not in run.tool
            assert all(flag.startswith("-") for flag in run.flags)
