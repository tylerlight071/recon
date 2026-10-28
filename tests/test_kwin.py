"""The KWin pinning service, against a fake KDE that behaves like kreadconfig6/kwriteconfig6."""

import copy
import stat
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon.config import APP_ID
from recon.services import kwin
from recon.services.kwin import (
    RULE_GROUP,
    KWinPinning,
    Method,
    PanelGeometry,
    Result,
    add_to_list,
    panel_script,
    remove_from_list,
    rule_entries,
)

GEOMETRY = PanelGeometry.right_edge((0, 0, 1280, 720), 420)
# The user's real kwinrulesrc before Recon (Phase 0): one unrelated Order entry, no rules.
TYLERS_CONFIG: dict[str, dict[str, str]] = {"General": {"Order": "steam", "rules": ""}}


class FakeKde:
    """kreadconfig6/kwriteconfig6 on an in-memory kwinrulesrc, plus scripted qdbus6 answers."""

    def __init__(self, config: dict[str, dict[str, str]] | None = None) -> None:
        self.config = copy.deepcopy(TYLERS_CONFIG if config is None else config)
        self.calls: list[tuple[str, ...]] = []
        self.fail: set[str] = set()
        """Command names (or 'reconfigure', 'loadScript', 'run') that should fail."""
        self.script_number = "0"

    def __call__(self, args: Sequence[str]) -> Result:
        self.calls.append(tuple(args))
        name = args[0]
        if name in self.fail:
            return Result(1)
        if name in {"kreadconfig6", "kwriteconfig6"}:
            return self._config_tool(args)
        return self._qdbus(args)

    def _config_tool(self, args: Sequence[str]) -> Result:
        opts = dict(zip(args[1::2], args[2::2], strict=False))
        group = self.config.setdefault(opts["--group"], {})
        key = opts["--key"]
        if args[0] == "kreadconfig6":
            return Result(0, group.get(key, "") + "\n")
        if "--delete" in args:
            group.pop(key, None)
        else:
            group[key] = args[-1]
        return Result(0)

    def _qdbus(self, args: Sequence[str]) -> Result:
        method = args[-1] if "loadScript" not in " ".join(args) else "loadScript"
        if method.endswith("reconfigure") and "reconfigure" in self.fail:
            return Result(1)
        if method == "loadScript":
            return Result(1) if "loadScript" in self.fail else Result(0, self.script_number + "\n")
        if method.endswith("Script.run") and "run" in self.fail:
            return Result(1)
        return Result(0, "true\n")

    def made(self, fragment: str) -> bool:
        return any(fragment in " ".join(call) for call in self.calls)


@pytest.fixture
def kde() -> FakeKde:
    return FakeKde()


@pytest.fixture
def pinning(kde: FakeKde, tmp_path: Path) -> KWinPinning:
    return KWinPinning(kde, tmp_path / "kwin-panel.js")


# Geometry and rule contents -------------------------------------------------------


def test_right_edge_geometry() -> None:
    assert PanelGeometry(x=860, y=0, width=420) == GEOMETRY
    offset = PanelGeometry.right_edge((100, 30, 1280, 720), 360)
    assert (offset.x, offset.y, offset.width) == (1020, 30, 360)


def test_rule_matches_app_id_and_panel_title_exactly_and_forces_geometry() -> None:
    entries = rule_entries(GEOMETRY)

    assert (entries["wmclass"], entries["wmclassmatch"]) == (APP_ID, "1")
    assert (entries["title"], entries["titlematch"]) == ("Recon Panel", "1")
    assert (entries["position"], entries["positionrule"]) == ("860,0", "2")
    # Width fixed by min = max; height from vertical maximise (respects the taskbar).
    assert (entries["minsize"], entries["minsizerule"]) == ("420,1", "2")
    assert (entries["maxsize"], entries["maxsizerule"]) == ("420,32767", "2")
    assert (entries["maximizevert"], entries["maximizevertrule"]) == ("true", "2")
    assert "size" not in entries


def test_fallback_script_pins_the_same_window() -> None:
    script = panel_script(GEOMETRY)

    assert f'const APP = "{APP_ID.lower()}";' in script
    assert 'const TITLE = "Recon Panel";' in script
    assert "const WIDTH = 420;" in script
    assert "workspace.clientArea(KWin.MaximizeArea, w)" in script
    assert "workspace.windowAdded.connect(pin);" in script


@given(st.lists(st.sampled_from(["steam", "a", "b", RULE_GROUP]), max_size=6))
def test_list_editing_is_exact(items: list[str]) -> None:
    existing = ",".join(items)

    added = add_to_list(existing, RULE_GROUP)
    removed = remove_from_list(added, RULE_GROUP)

    assert added.split(",").count(RULE_GROUP) == 1
    assert RULE_GROUP not in removed.split(",")
    assert [i for i in removed.split(",") if i] == [i for i in items if i != RULE_GROUP]


# Pinning ----------------------------------------------------------------------------


def test_pin_writes_the_rule_and_reloads_kwin(pinning: KWinPinning, kde: FakeKde) -> None:
    assert pinning.pin(GEOMETRY) is Method.RULE

    assert kde.config[RULE_GROUP] == rule_entries(GEOMETRY)
    assert kde.config["General"]["rules"] == RULE_GROUP
    assert kde.config["General"]["count"] == "1"
    assert kde.made("/KWin reconfigure")


def test_pin_leaves_tylers_other_settings_alone(pinning: KWinPinning, kde: FakeKde) -> None:
    pinning.pin(GEOMETRY)

    assert kde.config["General"]["Order"] == "steam"
    assert set(kde.config) == {"General", RULE_GROUP}


def test_pin_keeps_other_rules(tmp_path: Path) -> None:
    kde = FakeKde({"General": {"rules": "abc", "count": "1"}, "abc": {"title": "x"}})

    KWinPinning(kde, tmp_path / "s.js").pin(GEOMETRY)

    assert kde.config["General"]["rules"] == f"abc,{RULE_GROUP}"
    assert kde.config["General"]["count"] == "2"
    assert kde.config["abc"] == {"title": "x"}


def test_pinning_again_with_a_new_width_rewrites_one_rule(
    pinning: KWinPinning, kde: FakeKde
) -> None:
    pinning.pin(GEOMETRY)
    wider = PanelGeometry.right_edge((0, 0, 1280, 720), 500)

    assert pinning.pin(wider) is Method.RULE

    assert kde.config[RULE_GROUP]["minsize"] == "500,1"
    assert kde.config[RULE_GROUP]["position"] == "780,0"
    assert kde.config["General"]["rules"] == RULE_GROUP


@pytest.mark.parametrize("broken", ["kwriteconfig6", "reconfigure"])
def test_rule_failure_falls_back_to_the_script(
    pinning: KWinPinning, kde: FakeKde, tmp_path: Path, broken: str
) -> None:
    kde.fail.add(broken)
    kde.script_number = "7"

    assert pinning.pin(GEOMETRY) is Method.SCRIPT

    script = tmp_path / "kwin-panel.js"
    assert script.read_text() == panel_script(GEOMETRY)
    assert stat.S_IMODE(script.stat().st_mode) == 0o600
    assert kde.made(f"loadScript {script} recon-panel")
    assert kde.made("/Scripting/Script7 org.kde.kwin.Script.run")


@pytest.mark.parametrize(
    ("fail", "number"),
    [
        ({"kwriteconfig6", "loadScript"}, "0"),
        ({"kwriteconfig6", "run"}, "0"),
        ({"kwriteconfig6"}, "-1"),
    ],
)
def test_neither_way_working_returns_none(
    pinning: KWinPinning, kde: FakeKde, fail: set[str], number: str
) -> None:
    kde.fail |= fail
    kde.script_number = number

    assert pinning.pin(GEOMETRY) is None


def test_script_that_cannot_be_written_returns_none(kde: FakeKde, tmp_path: Path) -> None:
    kde.fail.add("kwriteconfig6")
    pinning = KWinPinning(kde, tmp_path / "missing-folder" / "s.js")

    assert pinning.pin(GEOMETRY) is None


# Unpinning --------------------------------------------------------------------------


def test_unpin_restores_tylers_config_exactly(pinning: KWinPinning, kde: FakeKde) -> None:
    pinning.pin(GEOMETRY)
    # KWin appends applied rules to Order on its own (Phase 0 finding).
    kde.config["General"]["Order"] = f"steam,{RULE_GROUP}"

    assert pinning.unpin() is True

    # No "count=0" left behind: the existing file had no count key (seen on a real desktop).
    assert kde.config["General"] == {"Order": "steam", "rules": ""}
    assert kde.config.get(RULE_GROUP, {}) == {}
    assert kde.made("/KWin reconfigure")


def test_unpin_removes_the_script_too(pinning: KWinPinning, kde: FakeKde, tmp_path: Path) -> None:
    kde.fail.add("kwriteconfig6")
    pinning.pin(GEOMETRY)
    kde.fail.clear()

    pinning.unpin()

    assert not (tmp_path / "kwin-panel.js").exists()
    assert kde.made("unloadScript recon-panel")


def test_unpin_reports_failure(pinning: KWinPinning, kde: FakeKde) -> None:
    pinning.pin(GEOMETRY)
    kde.fail.add("kwriteconfig6")

    assert pinning.unpin() is False


# Runner -------------------------------------------------------------------------------


def test_runner_refuses_unlisted_programs() -> None:
    with pytest.raises(ValueError, match="not an allowlisted command"):
        kwin.run_command(["rm", "-rf", "/"])


def test_runner_reports_missing_program(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kwin.shutil, "which", lambda *_a, **_k: None)

    assert kwin.run_command(["qdbus6", "org.kde.KWin"]) == Result(127)


def test_runner_runs_by_full_path_without_a_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "qdbus6"
    fake.write_text('#!/bin/sh\necho "args:$*"\n')
    fake.chmod(0o755)
    monkeypatch.setattr(kwin.shutil, "which", lambda *_a, **_k: str(fake))

    assert kwin.run_command(["qdbus6", "a; rm -rf /"]) == Result(0, "args:a; rm -rf /\n")


def test_runner_timeout_and_os_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kwin.shutil, "which", lambda *_a, **_k: "/usr/bin/qdbus6")

    def slow(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired("qdbus6", 10)

    monkeypatch.setattr(kwin.subprocess, "run", slow)
    assert kwin.run_command(["qdbus6"]).code == 124

    def broken(*_a: object, **_k: object) -> None:
        raise PermissionError

    monkeypatch.setattr(kwin.subprocess, "run", broken)
    assert kwin.run_command(["qdbus6"]).code == 127


def test_unpin_keeps_count_when_other_rules_remain(tmp_path: Path) -> None:
    kde = FakeKde({"General": {"rules": "abc", "count": "1"}, "abc": {"title": "x"}})
    pinning = KWinPinning(kde, tmp_path / "s.js")
    pinning.pin(GEOMETRY)

    pinning.unpin()

    assert kde.config["General"]["rules"] == "abc"
    assert kde.config["General"]["count"] == "1"


def test_unpin_also_removes_keys_from_the_older_rule_shape(tmp_path: Path) -> None:
    kde = FakeKde(
        {
            "General": {"rules": RULE_GROUP, "count": "1"},
            RULE_GROUP: {"size": "420,720", "sizerule": "2"},
        }
    )

    KWinPinning(kde, tmp_path / "s.js").unpin()

    assert kde.config[RULE_GROUP] == {}
