"""Desktop notifications over D-Bus (freedesktop Notifications), task 2.5.

One private thread owns one session-bus connection: it sends each `Notify`
call and listens for `ActionInvoked` on that same connection, because some
servers (Plasma among them) only send the click back to the connection that
created the notification. jeepney writes the call's signature explicitly
(`susssasa{sv}i`, with an unsigned `replaces_id`), which QtDBus can't do from
Python (ADR 0009).

Calm by default (ADHD rule 11): no sound, the server's normal timeout, and
nothing at all if the session bus isn't there (CI, a bare TTY). The app works
the same either way.
"""

import logging
import queue
import threading
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Final, Protocol

from jeepney import DBusAddress, MatchRule, Message, new_method_call
from jeepney.io.blocking import open_dbus_connection

from recon.config import APP_ID, APP_NAME
from recon.logging_setup import Safe

ADDRESS: Final = DBusAddress(
    "/org/freedesktop/Notifications",
    bus_name="org.freedesktop.Notifications",
    interface="org.freedesktop.Notifications",
)
SIGNATURE: Final = "susssasa{sv}i"
CALL_TIMEOUT_S: Final = 5.0
POLL_S: Final = 0.5
"""How often the thread looks for new notifications to send while it listens."""

type OnAction = Callable[[int, str], None]
"""Called with the caller's token and the action key ("default" for a click)."""

_log = logging.getLogger(__name__)


class Connection(Protocol):
    """The parts of jeepney's blocking `DBusConnection` used here (tests pass a fake)."""

    def send_and_get_reply(self, message: Message, *, timeout: float | None = None) -> Message:
        """Call a method and wait for its reply."""

    def filter(
        self, rule: MatchRule, *, queue: deque[Message] | None = None, bufsize: int = 1
    ) -> AbstractContextManager[deque[Message]]:
        """Collect messages matching `rule` while the context is open."""

    def recv_until_filtered(
        self, queue: deque[Message], *, timeout: float | None = None
    ) -> Message:
        """Receive until a message lands in `queue` (TimeoutError if none in time)."""

    def close(self) -> None:
        """Close the connection."""


@dataclass(frozen=True, slots=True)
class Notice:
    """One notification to send."""

    token: int
    """The caller's own ID for it (a room ID), passed back with any action."""
    summary: str
    body: str
    actions: Sequence[tuple[str, str]] = ()
    """(key, label) pairs; "default" is a click on the notification itself."""


def session_connection() -> Connection:
    """A blocking connection to the session bus (raises OSError if there isn't one)."""
    connection: Connection = open_dbus_connection(bus="SESSION")
    return connection


def notify_message(notice: Notice) -> Message:
    """The `Notify` call for `notice`."""
    actions = [part for pair in notice.actions for part in pair]
    hints = {
        "desktop-entry": ("s", APP_ID),
        "suppress-sound": ("b", True),
        "category": ("s", "transfer.complete"),
    }
    body = (APP_NAME, 0, APP_ID, notice.summary, notice.body, actions, hints, -1)
    return new_method_call(ADDRESS, "Notify", SIGNATURE, body)


class Notifications:
    """Sends notifications and reports their actions, on one private thread."""

    def __init__(
        self, on_action: OnAction, connect: Callable[[], Connection] = session_connection
    ) -> None:
        """Set up (nothing runs until `start`).

        Args:
            on_action: Called on the notification thread when an action is chosen.
            connect: Opens the session-bus connection (tests pass a fake).
        """
        self._on_action = on_action
        self._connect = connect
        self._outbox: queue.SimpleQueue[Notice] = queue.SimpleQueue()
        self._tokens: dict[int, int] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="recon-notifications", daemon=True)

    def start(self) -> None:
        """Start the notification thread."""
        self._thread.start()

    def notify(self, notice: Notice) -> None:
        """Queue a notification (sent within half a second; never blocks)."""
        self._outbox.put(notice)

    def close(self, timeout_s: float = 1.0) -> None:
        """Stop the thread (it's a daemon, so a stuck bus never holds up quitting)."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout_s)

    def _run(self) -> None:
        # Thread boundary: no bus, or a bus that goes away, is logged once and ends quietly.
        try:
            connection = self._connect()
        except (OSError, ValueError) as exc:
            _log.info("no desktop notifications: %s", Safe(type(exc).__name__))
            return
        try:
            self._serve(connection)
        except Exception as exc:  # thread boundary: notifications are a nicety
            _log.warning("desktop notifications stopped: %s", Safe(type(exc).__name__))
        finally:
            connection.close()

    def _serve(self, connection: Connection) -> None:
        rule = MatchRule(type="signal", interface=ADDRESS.interface, member="ActionInvoked")
        with connection.filter(rule, bufsize=64) as actions:
            while not self._stop.is_set():
                for notice in self._drain():
                    self._send(connection, notice)
                for message in self._wait(connection, actions):
                    self._act(message)

    def _drain(self) -> Iterator[Notice]:
        while True:
            try:
                yield self._outbox.get_nowait()
            except queue.Empty:
                return

    def _send(self, connection: Connection, notice: Notice) -> None:
        try:
            reply = connection.send_and_get_reply(notify_message(notice), timeout=CALL_TIMEOUT_S)
        except (OSError, TimeoutError) as exc:
            _log.warning("notification not sent: %s", Safe(type(exc).__name__))
            return
        (notification_id,) = reply.body or (0,)
        if isinstance(notification_id, int) and notification_id:
            self._tokens[notification_id] = notice.token

    def _wait(self, connection: Connection, actions: deque[Message]) -> list[Message]:
        if not actions:
            try:
                connection.recv_until_filtered(actions, timeout=POLL_S)
            except TimeoutError:
                return []
        found = list(actions)
        actions.clear()
        return found

    def _act(self, message: Message) -> None:
        notification_id, key = message.body
        token = self._tokens.get(notification_id)
        if token is not None and isinstance(key, str):
            self._on_action(token, key)
