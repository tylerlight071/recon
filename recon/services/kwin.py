"""Pin the panel to the right edge of the screen with a KWin window rule (task 1.4).

Opt-in only: nothing here runs until Tyler says yes. The rule matches Recon's
app ID *and* the panel's title, so the main window (same app ID) stays free,
and it forces the panel to the right edge at the width from Settings (Tyler
chose "width from Settings only" while pinned). The height isn't a number:
the rule forces vertical maximise, so KWin fills exactly the area above the
taskbar. On Wayland, Qt reports the whole screen as "available", so a numeric
height ran under the taskbar on Tyler's desktop.

If writing the rule or reloading KWin fails, a small KWin script does the same
for this session instead. Removing the pin deletes Recon's rule group and its
entries in `General/rules` and `General/Order` (KWin appends rules to Order
itself), and unloads the script. Nothing outside Recon's own group is touched.

This is the only module allowed to run programs (tests/test_network_imports.py).
"""

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field

from recon.config import APP_ID
from recon.fs import atomic_write_text

RULES_FILE: Final = "kwinrulesrc"
RULE_GROUP: Final = "recon-panel"
SCRIPT_NAME: Final = "recon-panel"
PANEL_TITLE: Final = "Recon Panel"
ALLOWED_COMMANDS: Final = frozenset({"kreadconfig6", "kwriteconfig6", "qdbus6"})
_SEARCH_PATH: Final = "/usr/bin:/bin"
_TIMEOUT_S: Final = 10
_NOT_INSTALLED: Final = 127
_TIMED_OUT: Final = 124
# KWin rule values: 1 = exact match; 2 = Force; window type 1 = normal window.
_EXACT, _FORCE, _NORMAL_WINDOW = "1", "2", "1"
_MAX_HEIGHT: Final = 32767
# Keys earlier versions of the rule used; removed on unpin too.
_OLD_KEYS: Final = ("size", "sizerule")


class PanelGeometry(BaseModel):
    """Where the pinned panel goes, in logical pixels. KWin decides the height."""

    model_config = ConfigDict(frozen=True)

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)

    @classmethod
    def right_edge(cls, screen: tuple[int, int, int, int], width: int) -> Self:
        """The panel against the right edge of the screen.

        Args:
            screen: The screen's area (x, y, width, height).
            width: Panel width.

        Returns:
            The geometry.
        """
        x, y, screen_width, _height = screen
        return cls(x=x + screen_width - width, y=y, width=width)


class Method(StrEnum):
    """How the panel ended up pinned."""

    RULE = "rule"
    SCRIPT = "script"


@dataclass(frozen=True, slots=True)
class Result:
    """What a command returned."""

    code: int
    stdout: str = ""


type Runner = Callable[[Sequence[str]], Result]


def run_command(args: Sequence[str]) -> Result:
    """Run an allowlisted KDE tool by full path, without a shell, with a timeout.

    Args:
        args: Program name and arguments.

    Returns:
        Exit code and output; 127 when the program isn't installed, 124 on timeout.

    Raises:
        ValueError: The program isn't on the allowlist.
    """
    name, *rest = args
    if name not in ALLOWED_COMMANDS:
        msg = f"{name} is not an allowlisted command"
        raise ValueError(msg)
    program = shutil.which(name, path=_SEARCH_PATH)
    if program is None:
        return Result(_NOT_INSTALLED)
    keep = ("HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
    env = {"PATH": _SEARCH_PATH, "LC_ALL": "C"} | {
        k: os.environ[k] for k in keep if k in os.environ
    }
    try:
        done = subprocess.run(  # noqa: S603 - allowlisted program by full path, no shell
            [program, *rest],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Result(_TIMED_OUT)
    except OSError:
        return Result(_NOT_INSTALLED)
    return Result(done.returncode, done.stdout)


def rule_entries(geometry: PanelGeometry) -> dict[str, str]:
    """The keys of Recon's rule group in kwinrulesrc."""
    return {
        "Description": "Recon panel (added by Recon; remove it in Recon's Settings)",
        "wmclass": APP_ID,
        "wmclassmatch": _EXACT,
        "wmclasscomplete": "false",
        "title": PANEL_TITLE,
        "titlematch": _EXACT,
        "types": _NORMAL_WINDOW,
        "position": f"{geometry.x},{geometry.y}",
        "positionrule": _FORCE,
        # Width fixed (min = max); the height is left to vertical maximise below.
        "minsize": f"{geometry.width},1",
        "minsizerule": _FORCE,
        "maxsize": f"{geometry.width},{_MAX_HEIGHT}",
        "maxsizerule": _FORCE,
        "maximizevert": "true",
        "maximizevertrule": _FORCE,
    }


def add_to_list(existing: str, item: str) -> str:
    """Make `item` appear exactly once in a comma-separated KWin list.

    Other entries keep their order; an existing `item` keeps its first place
    (duplicates, e.g. from a hand edit, are dropped).
    """
    items = [part for part in existing.split(",") if part]
    if item not in items:
        return ",".join([*items, item])
    first = items.index(item)
    return ",".join(p for i, p in enumerate(items) if p != item or i == first)


def remove_from_list(existing: str, item: str) -> str:
    """Remove `item` from a comma-separated KWin list."""
    return ",".join(part for part in existing.split(",") if part and part != item)


def panel_script(geometry: PanelGeometry) -> str:
    """KWin JavaScript that pins the panel the way the rule would (the fallback)."""
    return (
        f'const APP = "{APP_ID.lower()}";\n'
        f'const TITLE = "{PANEL_TITLE}";\n'
        f"const WIDTH = {geometry.width};\n"
        "function pin(w) {\n"
        "  if (w.resourceClass.toLowerCase() === APP && w.caption === TITLE) {\n"
        "    // The work area: the screen minus panels such as the taskbar.\n"
        "    const area = workspace.clientArea(KWin.MaximizeArea, w);\n"
        "    w.frameGeometry = {\n"
        "      x: area.x + area.width - WIDTH, y: area.y, width: WIDTH, height: area.height\n"
        "    };\n"
        "  }\n"
        "}\n"
        "workspace.windowList().forEach(pin);\n"
        "workspace.windowAdded.connect(pin);\n"
    )


class KWinPinning:
    """Adds and removes the panel pin. Every step checks its exit code."""

    def __init__(self, run: Runner, script_path: Path) -> None:
        """Use `run` for every command; keep the fallback script at `script_path`.

        Args:
            run: Runs one allowlisted command (injected so tests can fake KDE).
            script_path: Where the fallback KWin script is written.
        """
        self._run = run
        self._script_path = script_path

    def pin(self, geometry: PanelGeometry) -> Method | None:
        """Pin the panel: the rule if possible, otherwise the session script.

        Safe to call again (e.g. with a new width): it rewrites Recon's group.

        Returns:
            How it was pinned, or None when neither way worked.
        """
        if self._write_rule(geometry) and self._reconfigure():
            self._unload_script()
            return Method.RULE
        if self._load_script(geometry):
            return Method.SCRIPT
        return None

    def unpin(self) -> bool:
        """Remove Recon's rule and script; leave every other rule alone.

        Returns:
            True when the rule is gone and KWin has reloaded.
        """
        keys = [*rule_entries(PanelGeometry(x=0, y=0, width=1)), *_OLD_KEYS]
        removed = all(self._delete(RULE_GROUP, key) for key in keys)
        rules = remove_from_list(self._read("rules"), RULE_GROUP)
        order = remove_from_list(self._read("Order"), RULE_GROUP)
        # With no rules left, drop `count` rather than leave "count=0" behind.
        if rules:
            counted = self._write_general("count", str(_count(rules)))
        else:
            counted = self._delete("General", "count")
        removed = (
            removed
            and self._write_general("rules", rules)
            and counted
            and self._write_general("Order", order)
            and self._reconfigure()
        )
        self._unload_script()
        self._script_path.unlink(missing_ok=True)
        return removed

    def _ok(self, args: Sequence[str]) -> bool:
        return self._run(args).code == 0

    def _delete(self, group: str, key: str) -> bool:
        return self._ok(
            ["kwriteconfig6", "--file", RULES_FILE, "--group", group, "--key", key, "--delete"]
        )

    def _read(self, key: str) -> str:
        result = self._run(
            ["kreadconfig6", "--file", RULES_FILE, "--group", "General", "--key", key]
        )
        return result.stdout.strip() if result.code == 0 else ""

    def _write_general(self, key: str, value: str) -> bool:
        return self._ok(
            ["kwriteconfig6", "--file", RULES_FILE, "--group", "General", "--key", key, value]
        )

    def _write_rule(self, geometry: PanelGeometry) -> bool:
        for key, value in rule_entries(geometry).items():
            if not self._ok(
                ["kwriteconfig6", "--file", RULES_FILE, "--group", RULE_GROUP, "--key", key, value]
            ):
                return False
        rules = add_to_list(self._read("rules"), RULE_GROUP)
        return self._write_general("rules", rules) and self._write_general(
            "count", str(_count(rules))
        )

    def _reconfigure(self) -> bool:
        return self._ok(["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"])

    def _load_script(self, geometry: PanelGeometry) -> bool:
        try:
            atomic_write_text(self._script_path, panel_script(geometry))
        except OSError:
            return False
        self._unload_script()
        loaded = self._run(
            [
                "qdbus6",
                "org.kde.KWin",
                "/Scripting",
                "org.kde.kwin.Scripting.loadScript",
                str(self._script_path),
                SCRIPT_NAME,
            ]
        )
        number = loaded.stdout.strip()
        if loaded.code != 0 or not re.fullmatch(r"\d+", number) or int(number) < 0:
            return False
        return self._ok(
            ["qdbus6", "org.kde.KWin", f"/Scripting/Script{number}", "org.kde.kwin.Script.run"]
        )

    def _unload_script(self) -> None:
        # Fine if nothing was loaded; KWin just answers false.
        self._run(
            [
                "qdbus6",
                "org.kde.KWin",
                "/Scripting",
                "org.kde.kwin.Scripting.unloadScript",
                SCRIPT_NAME,
            ]
        )


def _count(rules: str) -> int:
    return len([part for part in rules.split(",") if part])
