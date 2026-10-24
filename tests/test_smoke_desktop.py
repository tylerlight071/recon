"""Global shortcut portal and KWin rule smoke tests: the pure parts."""

import stat
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any

import pytest

from recon.config import APP_ID
from scripts.smoke import kwin_rule, shortcut
from scripts.smoke.shortcut import Events, PortalError, PortalSession

# Shortcut portal ----------------------------------------------------------------


def test_request_path_follows_the_portal_spec() -> None:
    assert shortcut.request_path(":1.361", "recon42") == (
        "/org/freedesktop/portal/desktop/request/1_361/recon42"
    )


def test_shortcut_spec_asks_for_f9() -> None:
    [(shortcut_id, options)] = shortcut.shortcut_spec()

    assert shortcut_id == "voice"
    assert options["preferred_trigger"] == ("s", "F9")
    assert options["description"] == ("s", "Hold to talk (Recon)")


@pytest.mark.parametrize(
    ("code", "words"), [(0, "accepted"), (1, "cancelled"), (2, "failed"), (9, "unknown (9)")]
)
def test_describe_response(code: int, words: str) -> None:
    assert shortcut.describe_response(code) == words


def test_events_pair_presses_with_releases() -> None:
    events = Events(
        [
            ("released", 0.5),
            ("pressed", 1.0),
            ("pressed", 1.2),
            ("released", 2.0),
            ("released", 2.5),
        ]
    )

    assert events.pairs() == pytest.approx([0.8])


def test_evaluate_needs_enough_pairs() -> None:
    events = Events([("pressed", 1.0), ("released", 1.7)])

    assert shortcut.evaluate(events, 1).passed
    assert not shortcut.evaluate(events, 2).passed
    assert shortcut.evaluate(events, 1).detail == "1 press/release pair(s); holds 700 ms"
    assert shortcut.evaluate(Events(), 1).detail.endswith("holds none")


def test_log_is_private(tmp_path: Path) -> None:
    path = shortcut.log_path({"XDG_CACHE_HOME": str(tmp_path)}, Path("/unused"))

    shortcut.write_log(path, ["one", "two"])

    assert path == tmp_path / "recon/smoke/shortcut.log"
    assert path.read_text() == "one\ntwo\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


class _Header:
    def __init__(self, message_type: object, member: str = "") -> None:
        self.message_type = message_type
        self.fields = {shortcut.HeaderFields.member: member}


class _Message:
    def __init__(
        self, body: tuple[Any, ...], message_type: object = None, member: str = ""
    ) -> None:
        self.body = body
        self.header = _Header(message_type or shortcut.MessageType.method_return, member)


class _FakeConnection:
    """Answers portal calls from a script of replies and Response bodies."""

    unique_name = ":1.7"

    def __init__(self, replies: list[_Message], responses: list[_Message]) -> None:
        self.replies = replies
        self.responses = responses
        self.sent: list[object] = []

    def send_and_get_reply(self, message: object, timeout: float) -> _Message:  # noqa: ARG002
        self.sent.append(message)
        if self.replies:
            return self.replies.pop(0)
        return _Message(())

    def filter(self, _rule: object, bufsize: int = 1) -> AbstractContextManager[list[object]]:  # noqa: ARG002
        return nullcontext([])

    def recv_until_filtered(self, _queue: object, timeout: float) -> _Message:  # noqa: ARG002
        if not self.responses:
            raise TimeoutError
        return self.responses.pop(0)


def test_register_error_is_reported() -> None:
    error = _Message(("App info not found",), shortcut.MessageType.error)
    session = PortalSession(_FakeConnection([error], []), [])  # type: ignore[arg-type]

    with pytest.raises(PortalError, match=r"Registry\.Register refused"):
        session.register()


def test_cancelled_request_is_reported() -> None:
    session = PortalSession(_FakeConnection([], [_Message((1, {}))]), [])  # type: ignore[arg-type]

    with pytest.raises(PortalError, match="CreateSession was cancelled"):
        session.create_session()


def test_bind_reports_an_empty_trigger(capsys: pytest.CaptureFixture[str]) -> None:
    bound = ("a(sa{sv})", [("voice", {"trigger_description": ("s", "")})])
    session = PortalSession(_FakeConnection([], [_Message((0, {"shortcuts": bound}))]), [])  # type: ignore[arg-type]

    assert session.bind() == ""
    assert "assigned no key" in capsys.readouterr().out


def test_full_sequence_with_presses() -> None:
    session_handle = "/org/freedesktop/portal/desktop/session/1_7/t"
    responses = [
        _Message((0, {"session_handle": ("s", session_handle)})),
        _Message(
            (0, {"shortcuts": ("a(sa{sv})", [("voice", {"trigger_description": ("s", "F9")})])})
        ),
        _Message((session_handle, "voice", 1, {}), member="Activated"),
        _Message((session_handle, "other", 2, {}), member="Activated"),
        _Message((session_handle, "voice", 3, {}), member="Deactivated"),
    ]
    log: list[str] = []
    session = PortalSession(_FakeConnection([], responses), log)  # type: ignore[arg-type]
    events = Events()

    session.register()
    session.create_session()
    assert session.bind() == "F9"
    session.listen(events, presses=1, timeout=5)

    assert [kind for kind, _ in events.seen] == ["pressed", "released"]
    assert f"Registered app ID {APP_ID} with the portal" in log


# KWin rule ---------------------------------------------------------------------


def test_rule_pins_the_panel_by_app_id_and_title() -> None:
    entries = kwin_rule.rule_entries(1280, 720, 420)

    assert entries["wmclass"] == APP_ID
    assert entries["title"] == "Recon Panel test"
    assert (entries["wmclassmatch"], entries["titlematch"]) == ("1", "1")
    assert entries["position"] == "860,0"
    assert entries["size"] == "420,720"
    assert (entries["positionrule"], entries["sizerule"]) == ("2", "2")


@pytest.mark.parametrize(
    ("existing", "added", "removed"),
    [
        ("", "r", ""),
        ("steam", "steam,r", "steam"),
        ("steam,r", "steam,r", "steam"),
        ("r,steam", "r,steam", "steam"),
    ],
)
def test_rule_list_editing(existing: str, added: str, removed: str) -> None:
    assert kwin_rule.add_to_list(existing, "r") == added
    assert kwin_rule.remove_from_list(added, "r") == removed


def test_kwin_script_filters_on_the_app_id() -> None:
    script = kwin_rule.kwin_script("M")

    assert f'"{APP_ID.lower()}"' in script
    assert 'print("M " + JSON.stringify(' in script


def test_parse_geometry_reads_only_marked_lines() -> None:
    journal = 'noise\nkwin: M {"title": "Recon Panel test", "x": 860}\nM not-this\n'

    assert kwin_rule.parse_geometry(journal.replace("M not-this", "other"), "M") == [
        {"title": "Recon Panel test", "x": 860}
    ]


def test_run_refuses_unlisted_commands() -> None:
    with pytest.raises(ValueError, match="not an allowlisted command"):
        kwin_rule._run(["rm", "-rf", "/"])
