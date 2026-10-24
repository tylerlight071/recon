"""Smoke test: a KWin rule pins only the panel window, matched by app ID and title.

    uv run python -m scripts.smoke.kwin_rule apply [--width 420]  # write rule, reload KWin
    uv run python -m scripts.smoke.kwin_rule windows [--hold 90]  # open the two windows
    uv run python -m scripts.smoke.kwin_rule geometry             # ask KWin where they are
    uv run python -m scripts.smoke.kwin_rule remove               # delete rule, reload KWin

Recon's panel and main window share one app ID, so the rule must match the
app ID *and* the panel's title. Wayland windows can't report their own
position, so `geometry` loads a tiny KWin script that prints each window's
frame to the journal and reads it back.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from recon.config import APP_ID

PANEL_TITLE = "Recon Panel test"
OTHER_TITLE = "Recon test"
RULE_GROUP = "recon-smoke-panel-test"
"""Fixed group name, so `remove` finds exactly what `apply` wrote."""
RULES_FILE = "kwinrulesrc"
_ALLOWED = frozenset({"kwriteconfig6", "kreadconfig6", "qdbus6", "journalctl", "kscreen-doctor"})
_SEARCH_PATH = "/usr/bin:/bin"
_MARKER = "RECON_SMOKE_GEOMETRY"

# KWin rule values: 1 = exact match; 2 = Force.
_EXACT, _FORCE, _NORMAL_WINDOW = "1", "2", "1"


def _run(args: Sequence[str], *, check: bool = True) -> str:
    name, *rest = args
    if name not in _ALLOWED:
        msg = f"{name} is not an allowlisted command"
        raise ValueError(msg)
    program = shutil.which(name, path=_SEARCH_PATH)
    if program is None:
        msg = f"{name} isn't installed"
        raise FileNotFoundError(msg)
    done = subprocess.run(  # noqa: S603 - allowlisted program by full path, no shell
        [program, *rest], capture_output=True, text=True, timeout=15, check=check
    )
    return done.stdout


def rule_entries(screen_w: int, screen_h: int, width: int) -> dict[str, str]:
    """Keys for a rule that forces the panel to the right edge at full height.

    Args:
        screen_w: Logical screen width.
        screen_h: Logical screen height.
        width: Panel width in logical pixels.

    Returns:
        Key-value pairs for the rule's group in kwinrulesrc.
    """
    return {
        "Description": "Recon panel (Phase 0 smoke test)",
        "wmclass": APP_ID,
        "wmclassmatch": _EXACT,
        "wmclasscomplete": "false",
        "title": PANEL_TITLE,
        "titlematch": _EXACT,
        "types": _NORMAL_WINDOW,
        "position": f"{screen_w - width},0",
        "positionrule": _FORCE,
        "size": f"{width},{screen_h}",
        "sizerule": _FORCE,
    }


def add_to_list(existing: str, item: str) -> str:
    """Add `item` to KWin's comma-separated rules list once."""
    items = [part for part in existing.split(",") if part]
    return ",".join([*items, item] if item not in items else items)


def remove_from_list(existing: str, item: str) -> str:
    """Remove `item` from KWin's comma-separated rules list."""
    return ",".join(part for part in existing.split(",") if part and part != item)


def screen_size() -> tuple[int, int]:
    """Logical size of the first enabled output, from kscreen-doctor."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", _run(["kscreen-doctor", "-o"]))
    match = re.search(r"Geometry: \d+,\d+ (\d+)x(\d+)", text)
    if match is None:
        msg = "couldn't read the screen geometry"
        raise ValueError(msg)
    return int(match.group(1)), int(match.group(2))


def _config(*args: str) -> str:
    return _run(["kreadconfig6", "--file", RULES_FILE, *args]).strip()


def _write(group: str, key: str, value: str) -> None:
    _run(["kwriteconfig6", "--file", RULES_FILE, "--group", group, "--key", key, value])


def reload_kwin() -> None:
    """Ask KWin to re-read its rules."""
    _run(["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"])


def apply(width: int) -> None:
    """Write the test rule and reload KWin."""
    screen_w, screen_h = screen_size()
    for key, value in rule_entries(screen_w, screen_h, width).items():
        _write(RULE_GROUP, key, value)
    rules = add_to_list(_config("--group", "General", "--key", "rules"), RULE_GROUP)
    _write("General", "rules", rules)
    _write("General", "count", str(len(rules.split(","))))
    reload_kwin()
    left = screen_w - width
    print(f"Rule written: {width}x{screen_h} at x={left} on a {screen_w}x{screen_h} screen")


def remove() -> None:
    """Delete the test rule and reload KWin."""
    for key in rule_entries(0, 0, 0):
        _run(
            ["kwriteconfig6", "--file", RULES_FILE, "--group", RULE_GROUP, "--key", key, "--delete"]
        )
    rules = remove_from_list(_config("--group", "General", "--key", "rules"), RULE_GROUP)
    _write("General", "rules", rules)
    # KWin appends applied rules to General/Order on its own; clean that too.
    order = remove_from_list(_config("--group", "General", "--key", "Order"), RULE_GROUP)
    _write("General", "Order", order)
    _write("General", "count", str(len([r for r in rules.split(",") if r])))
    reload_kwin()
    print("Rule removed")


def kwin_script(marker: str = _MARKER) -> str:
    """KWin JavaScript that prints Recon's windows' frames as JSON lines."""
    return (
        "for (const w of workspace.windowList()) {\n"
        f'  if (w.resourceClass.toLowerCase() === "{APP_ID.lower()}") {{\n'
        f'    print("{marker} " + JSON.stringify({{title: w.caption, '
        "x: w.frameGeometry.x, y: w.frameGeometry.y, "
        "w: w.frameGeometry.width, h: w.frameGeometry.height, cls: w.resourceClass}));\n"
        "  }\n"
        "}\n"
    )


def parse_geometry(journal: str, marker: str = _MARKER) -> list[dict[str, object]]:
    """Pull the JSON frames the KWin script printed out of journal text."""
    found: list[dict[str, object]] = []
    for line in journal.splitlines():
        _, sep, payload = line.partition(f"{marker} ")
        if sep:
            found.append(json.loads(payload))
    return found


def geometry() -> list[dict[str, object]]:
    """Load the KWin script once, run it, and read what it printed."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(kwin_script())
        script = Path(handle.name)
    name = f"recon-smoke-{int(time.time())}"
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        number = _run(
            [
                "qdbus6",
                "org.kde.KWin",
                "/Scripting",
                "org.kde.kwin.Scripting.loadScript",
                str(script),
                name,
            ]
        ).strip()
        _run(["qdbus6", "org.kde.KWin", f"/Scripting/Script{number}", "org.kde.kwin.Script.run"])
        time.sleep(0.5)
        _run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", name])
    finally:
        script.unlink()
    journal = _run(
        ["journalctl", "--user", "--since", since, "--no-pager", "-o", "cat"], check=False
    )
    return parse_geometry(journal)


def windows(hold_s: float) -> None:
    """Open the panel and the other window with the same app ID, for `hold_s` seconds."""
    from PySide6.QtCore import QTimer, QUrl  # noqa: PLC0415 - only this subcommand needs Qt
    from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
    from PySide6.QtQml import QQmlApplicationEngine  # noqa: PLC0415

    QGuiApplication.setDesktopFileName(APP_ID)
    app = QGuiApplication(sys.argv[:1])
    qml = Path(__file__).resolve().parent / "qml" / "KWinTestWindow.qml"
    engine = QQmlApplicationEngine()
    for title in (PANEL_TITLE, OTHER_TITLE):
        engine.setInitialProperties({"title": title})
        engine.load(QUrl.fromLocalFile(str(qml)))
    QTimer.singleShot(int(hold_s * 1000), app.quit)
    print(f"Two windows open for {hold_s:.0f} s: '{PANEL_TITLE}' and '{OTHER_TITLE}'")
    app.exec()


def main(argv: list[str]) -> int:
    """Dispatch a subcommand.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        Exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("apply").add_argument("--width", type=int, default=420)
    sub.add_parser("windows").add_argument("--hold", type=float, default=90.0)
    sub.add_parser("geometry")
    sub.add_parser("remove")
    args = parser.parse_args(argv)
    if args.command == "apply":
        apply(args.width)
    elif args.command == "windows":
        windows(args.hold)
    elif args.command == "geometry":
        print(json.dumps(geometry(), indent=2))
    else:
        remove()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
