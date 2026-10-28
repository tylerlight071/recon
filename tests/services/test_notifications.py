"""services.notifications: Notify over D-Bus on one thread, actions reported back (faked bus)."""

import logging
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from jeepney import MatchRule, Message, new_method_return, new_signal

from recon.config import APP_ID
from recon.services.notifications import (
    ADDRESS,
    SIGNATURE,
    Notice,
    Notifications,
    notify_message,
)

NOTICE = Notice(7, "DNS in Detail is ready to review", "Check them over.", (("default", "Review"),))


class FakeBus:
    """A session bus that hands out notification IDs and plays back clicks."""

    def __init__(self) -> None:
        self.sent: list[Message] = []
        self.signals: list[Message] = []
        self.fail_send: Exception | None = None
        self.closed = threading.Event()
        self.next_id = 41

    def send_and_get_reply(self, message: Message, *, timeout: float | None = None) -> Message:
        del timeout
        if self.fail_send is not None:
            raise self.fail_send
        self.sent.append(message)
        self.next_id += 1
        return new_method_return(message, "u", (self.next_id,))

    @contextmanager
    def filter(
        self, rule: MatchRule, *, queue: deque[Message] | None = None, bufsize: int = 1
    ) -> Iterator[deque[Message]]:
        del rule, bufsize
        yield queue if queue is not None else deque()

    def recv_until_filtered(
        self, queue: deque[Message], *, timeout: float | None = None
    ) -> Message:
        if self.signals:
            queue.append(self.signals.pop(0))
            return queue[-1]
        time.sleep(min(timeout or 0.01, 0.01))
        raise TimeoutError

    def close(self) -> None:
        self.closed.set()


def _click(notification_id: int, key: str = "default") -> Message:
    return new_signal(ADDRESS, "ActionInvoked", "us", (notification_id, key))


def _until(condition: object, timeout_s: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if callable(condition) and condition():
            return True
        time.sleep(0.01)
    return False


def test_the_notify_call_is_typed_exactly() -> None:
    message = notify_message(NOTICE)

    assert message.header.fields[3] == "Notify"  # member
    assert message.header.fields[8] == SIGNATURE
    app, replaces, icon, summary, body, actions, hints, timeout = message.body
    assert (app, replaces, icon) == ("Recon", 0, APP_ID)
    assert (summary, body, timeout) == (NOTICE.summary, NOTICE.body, -1)
    assert actions == ["default", "Review"]
    assert hints["suppress-sound"] == ("b", True)
    assert hints["desktop-entry"] == ("s", APP_ID)


def test_a_click_comes_back_with_the_callers_token() -> None:
    bus = FakeBus()
    clicks: list[tuple[int, str]] = []
    notifications = Notifications(lambda token, key: clicks.append((token, key)), lambda: bus)
    notifications.start()

    notifications.notify(NOTICE)
    assert _until(lambda: len(bus.sent) == 1)
    bus.signals += [_click(999), _click(42, "default")]  # someone else's, then ours
    assert _until(lambda: clicks == [(7, "default")])

    notifications.close()
    assert bus.closed.wait(2)


def test_without_a_session_bus_nothing_happens(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    def no_bus() -> FakeBus:
        raise OSError

    notifications = Notifications(lambda _t, _k: None, no_bus)
    notifications.start()
    notifications.notify(NOTICE)
    notifications.close()

    assert "no desktop notifications: OSError" in caplog.text


def test_a_failed_send_is_logged_and_the_thread_carries_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = FakeBus()
    bus.fail_send = TimeoutError()
    notifications = Notifications(lambda _t, _k: None, lambda: bus)
    notifications.start()

    notifications.notify(NOTICE)
    assert _until(lambda: "notification not sent: TimeoutError" in caplog.text)
    bus.fail_send = None
    notifications.notify(NOTICE)
    assert _until(lambda: len(bus.sent) == 1)
    notifications.close()


def test_a_broken_bus_stops_quietly(caplog: pytest.LogCaptureFixture) -> None:
    bus = FakeBus()
    bus.signals.append(new_signal(ADDRESS, "ActionInvoked", "s", ("no id",)))
    notifications = Notifications(lambda _t, _k: None, lambda: bus)
    notifications.start()

    assert bus.closed.wait(2)
    assert "desktop notifications stopped: ValueError" in caplog.text
    notifications.close()
