"""FlagGuard: cleans editor text, signals the notice, keeps hex lookalikes on request."""

import logging

import pytest

from recon.bridge.flags import FlagGuard
from tests.ui.qml_harness import app

MD5 = "5d41402abc4b2a76b9719d911017c592"


class Spy:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def __call__(self, block_id: int, text: str) -> None:
        self.calls.append((block_id, text))


@pytest.fixture
def kept_ok() -> list[tuple[int, str]]:
    return []


@pytest.fixture
def guard(kept_ok: list[tuple[int, str]]) -> FlagGuard:
    app()

    def keep(block_id: int, text: str) -> bool:
        kept_ok.append((block_id, text))
        return text == MD5

    return FlagGuard(keep)


def test_clean_text_passes_through_silently(guard: FlagGuard) -> None:
    skipped = Spy()
    guard.flagSkipped.connect(skipped)

    assert guard.clean(3, "TXT records hold text", []) == "TXT records hold text"
    assert skipped.calls == []


def test_braced_flag_is_removed_with_no_keep_option(guard: FlagGuard) -> None:
    skipped = Spy()
    guard.flagSkipped.connect(skipped)

    assert guard.clean(3, "answer THM{x}", []) == "answer "
    assert skipped.calls == [(3, "")]


def test_lone_hex_is_removed_and_offered_for_keeping(guard: FlagGuard) -> None:
    skipped = Spy()
    guard.flagSkipped.connect(skipped)

    assert guard.clean(4, f"md5 {MD5}", []) == "md5 "
    assert skipped.calls == [(4, MD5)]


def test_several_findings_offer_no_keep(guard: FlagGuard) -> None:
    skipped = Spy()
    guard.flagSkipped.connect(skipped)

    guard.clean(4, f"{MD5} THM{{x}}", [])

    assert skipped.calls == [(4, "")]


def test_kept_hex_is_left_in_the_editor(guard: FlagGuard) -> None:
    assert guard.clean(4, f"md5 {MD5}", [MD5]) == f"md5 {MD5}"


def test_keep_restores_only_when_recorded(guard: FlagGuard, kept_ok: list[tuple[int, str]]) -> None:
    restored = Spy()
    guard.keptRestored.connect(restored)

    guard.keep(4, MD5)
    guard.keep(4, "THM{x}")

    assert kept_ok == [(4, MD5), (4, "THM{x}")]
    assert restored.calls == [(4, MD5)]


def test_flag_text_is_never_logged(guard: FlagGuard, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="recon"):
        guard.clean(5, f"THM{{secret}} and {MD5}", [])

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "secret" not in messages
    assert MD5 not in messages
    assert "skipped 2 flag-shaped string(s) in block 5" in messages
