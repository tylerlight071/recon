"""ReviewBridge: open a staged run, then Apply, Discard or Re-check, with calm problems."""

from collections.abc import Callable, Iterator

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject

from recon.bridge.review import ReviewBridge
from recon.engine.review import Review, ReviewNote
from recon.engine.stage import Applied
from recon.errors import ApplyConflict, StagingDamagedError
from tests.ui.qml_harness import SignalCounter, app

REVIEW = Review(
    run_id="20261028T120000-ab",
    room_id=4,
    room=ReviewNote(path="01 Rooms/DNS.md", kind="room", title="DNS", markdown="# DNS\n"),
    new=(ReviewNote(path="02 Concepts/TCP.md", kind="concept", title="TCP", markdown="# TCP\n"),),
    additions=(ReviewNote(path="03 Tools/dig.md", kind="tool", title="dig", markdown="new bit\n"),),
    skipped=(ReviewNote(path="02 Concepts/UDP.md", kind="concept", title="UDP", markdown=""),),
)
_OWNERS: list[QObject] = []


@pytest.fixture(autouse=True)
def _delete_on_the_main_thread() -> Iterator[None]:
    yield
    while _OWNERS:
        _OWNERS.pop().deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class Fakes:
    """Processing, scripted."""

    def __init__(self) -> None:
        self.loaded: tuple[Review, str] | None = (REVIEW, "DNS in Detail")
        self.error: Exception | None = None
        self.calls: list[tuple[str, str]] = []

    def load(self, room_id: int) -> tuple[Review, str] | None:
        self.calls.append(("load", str(room_id)))
        return self.loaded

    def apply(self, run_id: str) -> Applied:
        self.calls.append(("apply", run_id))
        if self.error is not None:
            raise self.error
        return Applied(written=3, backed_up=1)

    def discard(self, run_id: str) -> None:
        self.calls.append(("discard", run_id))

    def requeue(self, run_id: str) -> int:
        self.calls.append(("requeue", run_id))
        return self.loaded[0].room_id if self.loaded else 4


def _bridge(
    fakes: Fakes, submit: Callable[[Callable[[], None]], None] = lambda job: job()
) -> ReviewBridge:
    app()
    owner = QObject()
    _OWNERS.append(owner)
    return ReviewBridge(
        fakes.load, fakes.apply, fakes.discard, fakes.requeue, submit=submit, parent=owner
    )


def test_opening_shows_every_section() -> None:
    review = _bridge(Fakes())
    opened = SignalCounter(review, "opened()")
    assert review.property("shown") is False

    review.open(4)

    assert opened.count == 1
    assert review.property("shown") is True
    assert review.property("roomName") == "DNS in Detail"
    assert review.property("roomNote") == "# DNS\n"
    assert review.property("newNotes") == [
        {"title": "TCP", "kind": "Concept", "markdown": "# TCP\n"}
    ]
    assert review.property("additions") == [
        {"title": "dig", "kind": "Tool", "markdown": "new bit\n"}
    ]
    assert review.property("skipped") == ["UDP"]
    assert review.property("writes") == 3


def test_nothing_staged_says_so() -> None:
    fakes = Fakes()
    fakes.loaded = None
    review = _bridge(fakes)
    nothing: list[int] = []
    review.nothingToReview.connect(nothing.append)

    review.open(4)

    assert nothing == [4]
    assert review.property("shown") is False
    assert (review.property("roomNote"), review.property("writes")) == ("", 0)
    assert review.property("newNotes") == review.property("additions") == []


def test_apply_writes_then_clears() -> None:
    fakes = Fakes()
    review = _bridge(fakes)
    review.open(4)
    applied: list[tuple[int, int]] = []
    review.applied.connect(lambda room, written: applied.append((room, written)))

    review.apply()

    assert ("apply", REVIEW.run_id) in fakes.calls
    assert applied == [(4, 3)]
    assert review.property("shown") is False
    assert review.property("busy") is False


def test_a_conflict_writes_nothing_and_offers_recheck() -> None:
    fakes = Fakes()
    fakes.error = ApplyConflict()
    review = _bridge(fakes)
    review.open(4)
    rechecked: list[int] = []
    review.recheckRequested.connect(rechecked.append)

    review.apply()

    assert review.property("conflict") is True
    assert review.property("problem") == ApplyConflict.user_message
    assert review.property("shown") is True

    review.recheck()

    assert ("requeue", REVIEW.run_id) in fakes.calls
    assert rechecked == [4]
    assert review.property("conflict") is False


@pytest.mark.parametrize(
    ("error", "message"),
    [(StagingDamagedError(), StagingDamagedError.user_message), (RuntimeError("x"), None)],
)
def test_other_problems_are_calm(error: Exception, message: str | None) -> None:
    fakes = Fakes()
    fakes.error = error
    review = _bridge(fakes)
    review.open(4)

    review.apply()

    assert review.property("conflict") is False
    assert review.property("problem")
    assert "RuntimeError" not in review.property("problem")
    if message:
        assert review.property("problem") == message


def test_discard_reopens_the_room() -> None:
    fakes = Fakes()
    review = _bridge(fakes)
    review.open(4)
    discarded: list[int] = []
    review.discarded.connect(discarded.append)

    review.discard()

    assert ("discard", REVIEW.run_id) in fakes.calls
    assert discarded == [4]
    assert review.property("shown") is False


def test_nothing_happens_without_a_review_or_while_busy() -> None:
    held: list[Callable[[], None]] = []
    fakes = Fakes()
    review = _bridge(fakes, held.append)

    review.apply()
    review.discard()
    review.recheck()
    assert held == []

    review.open(4)
    held.pop()()
    review.apply()
    review.apply()  # busy: ignored
    review.discard()
    assert len(held) == 1
