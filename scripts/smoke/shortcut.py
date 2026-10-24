"""Smoke test: register F9 through the GlobalShortcuts portal and see press and release.

    RECON_MODULE=scripts.smoke.shortcut packaging/recon-launch [--presses 2] [--timeout 60]

Uses one jeepney D-Bus connection for everything, in the order Recon will:
host `Registry.Register` with the app ID first (needed when not sandboxed),
then `CreateSession`, `BindShortcuts`, and the `Activated`/`Deactivated`
signals. KDE asks once whether to allow the shortcut. Needs a .desktop file
named after the app ID in ~/.local/share/applications, or Register fails with
"App info not found".

Results go to stdout and to `$XDG_CACHE_HOME/recon/smoke/shortcut.log`, so a
run started from the app menu can be checked afterwards.
"""

import argparse
import os
import secrets
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jeepney import DBusAddress, MatchRule, MessageType, new_method_call
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import DBusConnection, open_dbus_connection
from jeepney.low_level import HeaderFields

from recon.config import APP_ID
from scripts.smoke._common import Outcome

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
REGISTRY = DBusAddress(PORTAL_PATH, PORTAL_BUS, "org.freedesktop.host.portal.Registry")
SHORTCUTS_IFACE = "org.freedesktop.portal.GlobalShortcuts"
SHORTCUTS = DBusAddress(PORTAL_PATH, PORTAL_BUS, SHORTCUTS_IFACE)
SHORTCUT_ID = "voice"
SHORTCUT_DESCRIPTION = "Hold to talk (Recon)"
PREFERRED_TRIGGER = "F9"
_REPLY_TIMEOUT_S = 10.0
_DIALOG_TIMEOUT_S = 120.0
"""BindShortcuts waits for Tyler to answer KDE's permission dialog."""

type Variant = tuple[str, Any]
"""A D-Bus variant as jeepney writes it: (signature, value)."""


class PortalError(Exception):
    """A portal call failed; the message says which step."""


@dataclass(slots=True)
class Events:
    """Shortcut events seen, as (kind, monotonic time) pairs."""

    seen: list[tuple[str, float]] = field(default_factory=list)

    def pairs(self) -> list[float]:
        """Hold durations in seconds for each press followed by a release."""
        durations: list[float] = []
        pressed_at: float | None = None
        for kind, at in self.seen:
            if kind == "pressed":
                pressed_at = at
            elif kind == "released" and pressed_at is not None:
                durations.append(at - pressed_at)
                pressed_at = None
        return durations


def request_path(unique_name: str, token: str) -> str:
    """Object path the portal will use for a Request, per the portal spec.

    Args:
        unique_name: This connection's unique bus name, e.g. ":1.42".
        token: The `handle_token` sent with the call.

    Returns:
        `/org/freedesktop/portal/desktop/request/<sender>/<token>`.
    """
    sender = unique_name.removeprefix(":").replace(".", "_")
    return f"{PORTAL_PATH}/request/{sender}/{token}"


def shortcut_spec() -> list[tuple[str, dict[str, Variant]]]:
    """The `a(sa{sv})` list BindShortcuts takes."""
    return [
        (
            SHORTCUT_ID,
            {
                "description": ("s", SHORTCUT_DESCRIPTION),
                "preferred_trigger": ("s", PREFERRED_TRIGGER),
            },
        )
    ]


def describe_response(code: int) -> str:
    """Plain words for a portal Response code."""
    return {0: "accepted", 1: "cancelled", 2: "failed"}.get(code, f"unknown ({code})")


def evaluate(events: Events, wanted: int) -> Outcome:
    """Pass when at least `wanted` press-then-release pairs were seen.

    Args:
        events: What arrived.
        wanted: How many presses to ask for.

    Returns:
        The outcome, with hold durations.
    """
    holds = events.pairs()
    detail = f"{len(holds)} press/release pair(s); holds " + (
        ", ".join(f"{hold * 1000:.0f} ms" for hold in holds) or "none"
    )
    return Outcome(len(holds) >= wanted, detail)


class PortalSession:
    """One D-Bus connection that owns a GlobalShortcuts session."""

    def __init__(self, conn: DBusConnection, log: list[str]) -> None:
        """Wrap an open session-bus connection.

        Args:
            conn: Connection from `open_dbus_connection`.
            log: Lines are appended here as steps happen.
        """
        self.conn = conn
        self.log = log
        self.session_handle = ""

    def _say(self, line: str) -> None:
        self.log.append(line)
        print(line, flush=True)

    def register(self) -> None:
        """Host Registry.Register with the app ID; must be the first portal call."""
        reply = self.conn.send_and_get_reply(
            new_method_call(REGISTRY, "Register", "sa{sv}", (APP_ID, {})), timeout=_REPLY_TIMEOUT_S
        )
        if reply.header.message_type == MessageType.error:
            msg = f"Registry.Register refused {APP_ID}: {reply.body}"
            raise PortalError(msg)
        self._say(f"Registered app ID {APP_ID} with the portal")

    def _request(
        self,
        method: str,
        signature: str,
        args: tuple[Any, ...],
        timeout: float,
        extra_options: dict[str, Variant] | None = None,
    ) -> dict[str, Variant]:
        """Call a portal method that answers through a Request object's Response signal."""
        token = f"recon{secrets.token_hex(4)}"
        path = request_path(self.conn.unique_name, token)
        rule = MatchRule(
            type="signal", interface="org.freedesktop.portal.Request", member="Response", path=path
        )
        # Subscribe before calling, so a fast Response can't be missed.
        self.conn.send_and_get_reply(message_bus.AddMatch(rule), timeout=_REPLY_TIMEOUT_S)
        options: dict[str, Variant] = {"handle_token": ("s", token), **(extra_options or {})}
        with self.conn.filter(rule) as queue:
            reply = self.conn.send_and_get_reply(
                new_method_call(SHORTCUTS, method, signature, (*args, options)),
                timeout=_REPLY_TIMEOUT_S,
            )
            if reply.header.message_type == MessageType.error:
                msg = f"{method} failed: {reply.body}"
                raise PortalError(msg)
            response = self.conn.recv_until_filtered(queue, timeout=timeout)
        code, results = response.body
        if code != 0:
            msg = f"{method} was {describe_response(code)}"
            raise PortalError(msg)
        return dict(results)

    def create_session(self) -> None:
        """CreateSession and remember the session handle."""
        session_token: Variant = ("s", f"recon{secrets.token_hex(4)}")
        results = self._request(
            "CreateSession", "a{sv}", (), _REPLY_TIMEOUT_S, {"session_handle_token": session_token}
        )
        self.session_handle = str(results["session_handle"][1])
        self._say(f"Created portal session {self.session_handle}")

    def bind(self) -> str:
        """BindShortcuts for F9; KDE may show its permission dialog.

        Returns:
            The trigger KDE assigned, in KDE's words (e.g. "F9").
        """
        self._say("Binding F9. If KDE asks whether to allow Recon's shortcut, allow it.")
        results = self._request(
            "BindShortcuts",
            "oa(sa{sv})sa{sv}",
            (self.session_handle, shortcut_spec(), ""),
            _DIALOG_TIMEOUT_S,
        )
        bound = results.get("shortcuts", ("", []))[1]
        triggers = [str(opts.get("trigger_description", ("s", "?"))[1]) for _sid, opts in bound]
        trigger = next((t for t in triggers if t), "")
        if trigger:
            self._say(f"KDE bound the shortcut to: {trigger}")
        else:
            self._say(
                "KDE accepted the shortcut but assigned no key. Set one in System Settings > "
                "Keyboard > Shortcuts, or clear the stale entry and run this again."
            )
        return trigger

    def listen(self, events: Events, presses: int, timeout: float) -> None:
        """Record Activated/Deactivated signals until enough presses or the timeout.

        Args:
            events: Where to record what arrives.
            presses: Stop after this many press/release pairs.
            timeout: Give up after this many seconds.
        """
        rule = MatchRule(type="signal", interface=SHORTCUTS_IFACE, path=PORTAL_PATH)
        self.conn.send_and_get_reply(message_bus.AddMatch(rule), timeout=_REPLY_TIMEOUT_S)
        self._say(f"Now press and release F9 {presses} times (hold it briefly each time).")
        deadline = time.monotonic() + timeout
        with self.conn.filter(rule, bufsize=64) as queue:
            while len(events.pairs()) < presses and time.monotonic() < deadline:
                try:
                    signal = self.conn.recv_until_filtered(
                        queue, timeout=deadline - time.monotonic()
                    )
                except TimeoutError:
                    break
                handle, shortcut_id, *_rest = signal.body
                if handle != self.session_handle or shortcut_id != SHORTCUT_ID:
                    continue
                member = str(signal.header.fields.get(HeaderFields.member, ""))
                kind = {"Activated": "pressed", "Deactivated": "released"}.get(member, "")
                if kind:
                    events.seen.append((kind, time.monotonic()))
                    self._say(f"  F9 {kind}")


def log_path(env: Mapping[str, str], home: Path) -> Path:
    """Where the run's log is written: `$XDG_CACHE_HOME/recon/smoke/shortcut.log`."""
    base = env.get("XDG_CACHE_HOME", "")
    root = Path(base) if base and Path(base).is_absolute() else home / ".cache"
    return root / "recon" / "smoke" / "shortcut.log"


def write_log(path: Path, lines: Sequence[str]) -> None:
    """Write the log privately (folder 0700, file 0600)."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def run_portal(presses: int, timeout: float, log: list[str]) -> Outcome:
    """Do the whole portal sequence on one connection.

    Args:
        presses: Press/release pairs to wait for.
        timeout: Seconds to wait for them.
        log: Progress lines are appended here.

    Returns:
        The outcome.
    """
    events = Events()
    try:
        with open_dbus_connection(bus="SESSION") as conn:
            session = PortalSession(conn, log)
            session.register()
            session.create_session()
            if not session.bind():
                return Outcome(False, "KDE assigned no key to the shortcut, so F9 can't fire")
            session.listen(events, presses, timeout)
    except (PortalError, TimeoutError) as exc:
        return Outcome(False, str(exc) or type(exc).__name__)
    return evaluate(events, presses)


def main(argv: list[str]) -> int:
    """Parse arguments, run the sequence, print and log the result.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        0 on pass, 1 on fail.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--presses", type=int, default=2, help="press/release pairs to wait for")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for them")
    args = parser.parse_args(argv)
    log = [f"Shortcut smoke test started {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    outcome = run_portal(args.presses, args.timeout, log)
    verdict = "PASS" if outcome.passed else "FAIL"
    line = f"{verdict}  Global shortcut via portal ({APP_ID})\n      {outcome.detail}"
    print(line)
    log.append(line)
    write_log(log_path(dict(os.environ), Path.home()), log)
    return 0 if outcome.passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
