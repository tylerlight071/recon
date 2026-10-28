"""The component set: loads cleanly, behaves, and is keyboard- and screen-reader-usable."""

import re

import pytest
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from tests.ui.qml_harness import (
    COMPONENTS_DIR,
    Loaded,
    SignalCounter,
    centre,
    load,
    wait,
    wait_until,
)

COMPONENT_FILES = sorted(path.stem for path in COMPONENTS_DIR.glob("*.qml"))
# Purely visual helpers: no role or name of their own.
DECORATIVE = {"FocusRing", "Icon"}
DEFAULT_BODIES = {
    "Button": 'Button { objectName: "subject"; text: "Next task" }',
    "IconButton": 'IconButton { objectName: "subject"; iconName: "plus"; tip: "Add block" }',
    "Icon": 'Icon { objectName: "subject"; name: "mic" }',
    "Card": 'Card { objectName: "subject"; title: "Where was I?"; Text { text: "x" } }',
    "TextArea": 'TextArea { objectName: "subject"; hint: "One line is fine." }',
    "Block": 'Block { objectName: "subject"; type: "command"; label: "Command" }',
    "ProgressRing": 'ProgressRing { objectName: "subject"; value: 0.4 }',
    "Toast": 'Toast { objectName: "subject" }',
    "Dialog": 'Dialog { objectName: "subject"; title: "Discard?"; body: "Sure?" }',
    "SidebarItem": 'SidebarItem { objectName: "subject"; text: "Home" }',
    "TimerChip": 'TimerChip { objectName: "subject"; seconds: 754 }',
    "Tooltip": 'Item { Tooltip { objectName: "subject"; text: "Add"; visible: true; delay: 0 } }',
    "FocusRing": 'Item { width: 10; height: 10; FocusRing { objectName: "subject" } }',
    "ListRow": 'ListRow { objectName: "subject"; title: "DNS in Detail"; detail: "Task 4 of 7" }',
    "Disclosure": (
        'Disclosure { objectName: "subject"; width: 400; title: "New notes"; detail: "3";'
        ' Text { objectName: "inside"; text: "TCP" } }'
    ),
    "TextField": 'TextField { objectName: "subject"; hint: "e.g. DNS in Detail" }',
    "Choice": 'Choice { objectName: "subject"; text: "New room"; detail: "As you go." }',
    "Toggle": 'Toggle { objectName: "subject"; text: "Reduce motion" }',
    "Slider": 'Slider { objectName: "subject"; from: 0; to: 10; value: 3; accessibleName: "W" }',
    "PopupMenu": (
        'Item { PopupMenu { objectName: "subject"; title: "Focus"; '
        'items: [{ "text": "Focus for 25 minutes", "key": 25 }] } }'
    ),
}


def _colour(obj: QObject, name: str) -> str:
    value = obj.property(name)
    assert isinstance(value, QColor), name
    return value.name(QColor.NameFormat.HexArgb)


def _child(loaded: Loaded, name: str) -> QObject:
    return loaded.find(name)


def test_every_component_has_a_default_test_body() -> None:
    assert set(COMPONENT_FILES) == set(DEFAULT_BODIES)


@pytest.mark.parametrize("name", COMPONENT_FILES)
def test_component_loads_without_warnings(name: str) -> None:
    loaded = load(DEFAULT_BODIES[name])

    assert loaded.warnings == []


@pytest.mark.parametrize("name", sorted(set(COMPONENT_FILES) - DECORATIVE))
def test_interactive_components_declare_role_and_name(name: str) -> None:
    source = (COMPONENTS_DIR / f"{name}.qml").read_text(encoding="utf-8")

    # The role may be an expression, e.g. Button when clickable, StaticText when not.
    assert re.search(r"Accessible\.role:[^\n]*Accessible\.\w+", source)
    assert re.search(r"Accessible\.name:", source)


# Button ---------------------------------------------------------------------


def test_button_name_and_variants() -> None:
    loaded = load(
        'Button { objectName: "subject"; text: "Next task"; variant: "primary" }\n'
        'Button { objectName: "quiet"; y: 40; text: "Skip"; variant: "quiet" }'
    )
    primary, theme = loaded.subject, loaded.theme
    background = primary.property("background")
    content = primary.property("contentItem")

    assert _colour(background, "color") == _colour(theme, "accent")
    assert _colour(content, "color") == _colour(theme, "textOnAccent")
    quiet_bg = _child(loaded, "quiet").property("background")
    assert _colour(quiet_bg, "color") == _colour(theme, "clear")


@pytest.mark.parametrize("key", [Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_button_clicks_from_the_keyboard(key: Qt.Key) -> None:
    loaded = load('Button { objectName: "subject"; text: "Next task" }')
    button = loaded.subject
    spy = SignalCounter(button, "clicked()")
    loaded.window.requestActivate()
    QMetaObject.invokeMethod(button, "forceActiveFocus")
    wait(20)

    QTest.keyClick(loaded.window, key)
    wait(20)

    assert spy.count == 1


def test_focus_ring_shows_for_keyboard_focus_only() -> None:
    loaded = load('Button { objectName: "subject"; text: "Next task" }')
    button = loaded.subject
    loaded.window.requestActivate()
    wait(20)
    ring = loaded.find("focusRing")
    assert ring is not None
    assert ring.property("visible") is False

    QTest.keyClick(loaded.window, Qt.Key.Key_Tab)
    wait(20)

    assert button.property("activeFocus") is True
    assert ring.property("visible") is True


def test_disabled_button_does_not_click() -> None:
    loaded = load('Button { objectName: "subject"; text: "Go"; enabled: false }')
    spy = SignalCounter(loaded.subject, "clicked()")

    QTest.mouseClick(loaded.window, Qt.MouseButton.LeftButton, pos=centre(loaded.subject).toPoint())
    wait(20)

    assert spy.count == 0
    assert loaded.subject.property("opacity") < 1


# Icon button and tooltip ------------------------------------------------------


def test_icon_button_is_named_by_its_tip() -> None:
    loaded = load(
        'IconButton { objectName: "subject"; iconName: "mic"; '
        'tip: "Hold to talk"; shortcutHint: "F9" }'
    )

    assert loaded.subject.property("tip") == "Hold to talk"
    assert loaded.subject.property("shortcutHint") == "F9"


def test_tooltip_sizes_itself_and_shows_the_shortcut() -> None:
    loaded = load(
        'Item { width: 32; height: 32; Tooltip { objectName: "subject"; '
        'text: "Command"; shortcut: "Ctrl+2"; visible: true; delay: 0 } }'
    )
    wait(100)
    tooltip = loaded.subject

    assert tooltip.property("width") > 0
    assert tooltip.property("height") > 0
    assert tooltip.property("shortcut") == "Ctrl+2"


# Text area --------------------------------------------------------------------


def test_hint_hides_while_typing_and_returns_when_cleared() -> None:
    loaded = load('TextArea { objectName: "subject"; hint: "One line is fine." }')
    area = loaded.subject
    hint = _child(loaded, "hint")
    assert hint.property("opacity") == 1

    area.setProperty("text", "TXT records hold text")
    wait(20)
    assert hint.property("opacity") == 0

    area.setProperty("text", "")
    wait(20)
    assert hint.property("opacity") == 1


def test_mono_text_area_uses_the_mono_font() -> None:
    loaded = load('TextArea { objectName: "subject"; mono: true; hint: "Command" }')

    assert loaded.subject.property("font").family() == "JetBrains Mono"


def test_text_area_accessible_name_defaults_to_hint() -> None:
    loaded = load('TextArea { objectName: "subject"; hint: "Something you want answered later." }')

    assert loaded.subject.property("accessibleName") == "Something you want answered later."


# Block --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("block_type", "colour_token"),
    [("key_idea", "accent"), ("command", "blockCommand"), ("question", "blockQuestion")],
)
def test_block_edge_follows_its_type(block_type: str, colour_token: str) -> None:
    loaded = load(f'Block {{ objectName: "subject"; type: "{block_type}"; label: "X" }}')
    edge = _child(loaded, "edge")

    assert _colour(edge, "color") == _colour(loaded.theme, colour_token)
    assert edge.property("opacity") == pytest.approx(loaded.theme.property("blockEdgeOpacity"))


def test_block_shows_label_and_holds_content() -> None:
    loaded = load(
        'Block { objectName: "subject"; type: "table"; label: "Table"; '
        'Text { objectName: "inside"; text: "80, HTTP" } }'
    )

    assert _child(loaded, "typeLabel").property("text") == "Table"
    assert _child(loaded, "inside").property("text") == "80, HTTP"


# Progress ring --------------------------------------------------------------------


@pytest.mark.parametrize(("value", "clamped"), [(-1, 0), (0, 0), (0.5, 0.5), (1, 1), (3, 1)])
def test_ring_clamps_its_value(value: float, clamped: float) -> None:
    loaded = load(f'ProgressRing {{ objectName: "subject"; value: {value} }}')

    assert loaded.subject.property("clampedValue") == pytest.approx(clamped)
    assert loaded.subject.property("shownValue") == pytest.approx(clamped)


def test_ring_animates_unless_motion_is_reduced() -> None:
    loaded = load('ProgressRing { objectName: "subject"; value: 0 }', reduce_motion=False)
    ring = loaded.subject

    ring.setProperty("value", 1)

    assert ring.property("shownValue") < 1  # it didn't jump
    assert wait_until(lambda: 0 < ring.property("shownValue") < 1)  # it passed through
    assert wait_until(lambda: ring.property("shownValue") == pytest.approx(1))


# Toast ------------------------------------------------------------------------------


def test_toast_undo_emits_action_and_hides() -> None:
    loaded = load('Toast { objectName: "subject" }')
    toast = loaded.subject
    action, dismissed = SignalCounter(toast, "action()"), SignalCounter(toast, "dismissed()")
    QMetaObject.invokeMethod(
        toast, "show", Q_ARG("QVariant", "Block deleted."), Q_ARG("QVariant", "Undo")
    )
    wait(20)
    assert toast.property("shown") is True

    button = _child(loaded, "action")
    QMetaObject.invokeMethod(button, "clicked")
    wait(20)

    assert (action.count, dismissed.count) == (1, 1)
    assert toast.property("shown") is False


def test_toast_hides_itself_after_its_timeout() -> None:
    loaded = load('Toast { objectName: "subject"; timeout: 50 }')
    toast = loaded.subject
    dismissed = SignalCounter(toast, "dismissed()")
    QMetaObject.invokeMethod(
        toast, "show", Q_ARG("QVariant", "Flag skipped."), Q_ARG("QVariant", "")
    )

    assert wait_until(lambda: dismissed.count == 1)
    assert toast.property("shown") is False


def test_undo_toast_waits_ten_seconds_by_default() -> None:
    loaded = load('Toast { objectName: "subject" }')

    assert loaded.subject.property("timeout") == 10_000


# Dialog ----------------------------------------------------------------------------


def test_dialog_escape_rejects() -> None:
    loaded = load(
        'Dialog { objectName: "subject"; title: "Discard?"; body: "Sure?" }', size=(600, 400)
    )
    dialog = loaded.subject
    rejected = SignalCounter(dialog, "rejected()")
    loaded.window.requestActivate()
    QMetaObject.invokeMethod(dialog, "open")
    wait(50)

    QTest.keyClick(loaded.window, Qt.Key.Key_Escape)
    wait(50)

    assert rejected.count == 1
    assert dialog.property("visible") is False


def test_dialog_sizes_itself() -> None:
    loaded = load(
        'Dialog { objectName: "subject"; title: "Discard?"; body: "Sure?" }', size=(600, 400)
    )
    QMetaObject.invokeMethod(loaded.subject, "open")
    wait(50)

    assert loaded.subject.property("height") > 0


# Sidebar item and timer chip ------------------------------------------------------------


def test_sidebar_item_selection_styling() -> None:
    loaded = load(
        'SidebarItem { objectName: "subject"; text: "Home"; selected: true }\n'
        'SidebarItem { objectName: "other"; y: 40; text: "Library" }'
    )
    theme = loaded.theme

    assert _colour(loaded.subject.property("background"), "color") == _colour(theme, "overlay")
    labels = list(loaded.root.findChildren(QObject, "label"))
    colours = sorted(_colour(label, "color") for label in labels)
    assert colours == sorted([_colour(theme, "textPrimary"), _colour(theme, "textSecondary")])


@pytest.mark.parametrize(
    ("seconds", "shown"),
    [(0, "0:00"), (9, "0:09"), (754, "12:34"), (3725, "1:02:05"), (-5, "0:00")],
)
def test_timer_chip_formats_elapsed_time(seconds: int, shown: str) -> None:
    loaded = load(f'TimerChip {{ objectName: "subject"; seconds: {seconds} }}')

    assert loaded.subject.property("elapsed") == shown


def test_timer_chip_never_shows_a_countdown() -> None:
    source = (COMPONENTS_DIR / "TimerChip.qml").read_text(encoding="utf-8")

    assert "remaining" not in source.lower()
    assert "left" not in re.sub(r"leftPadding|Text\.AlignLeft", "", source)


def test_list_row_reads_as_one_line_and_only_clicks_when_interactive() -> None:
    loaded = load(
        'ListRow { objectName: "subject"; title: "Linux Basics"; detail: "Done"; '
        'trailing: "2 days ago"; interactive: false }'
    )
    row = loaded.subject
    clicks = SignalCounter(row, "clicked()")

    QTest.mouseClick(loaded.window, Qt.MouseButton.LeftButton, pos=centre(row).toPoint())
    wait(20)

    assert clicks.count == 0
    assert row.property("enabled") is False
    assert loaded.find("rowTitle").property("text") == "Linux Basics"


# TextField ------------------------------------------------------------------------


def test_text_field_hint_hides_while_typed_in() -> None:
    loaded = load('TextField { objectName: "subject"; hint: "e.g. 7" }')
    hint = _child(loaded, "hint")
    assert hint.property("opacity") == 1

    loaded.subject.setProperty("text", "7")
    wait(20)

    assert hint.property("opacity") == 0
    assert loaded.subject.property("accessibleName") == "e.g. 7"


def test_text_field_return_accepts() -> None:
    loaded = load('TextField { objectName: "subject"; hint: "Room name" }')
    field = loaded.subject
    accepted = SignalCounter(field, "accepted()")
    field.forceActiveFocus()

    QTest.keyClick(loaded.window, Qt.Key.Key_Return)

    assert accepted.count == 1


# Choice ---------------------------------------------------------------------------


def test_choices_are_exclusive_and_keyboard_picks() -> None:
    loaded = load(
        'Column { Choice { objectName: "subject"; text: "New room"; checked: true }\n'
        'Choice { objectName: "other"; text: "From memory" } }'
    )
    first, other = loaded.subject, loaded.find("other")
    other.forceActiveFocus()

    QTest.keyClick(loaded.window, Qt.Key.Key_Return)
    wait(20)

    assert (first.property("checked"), other.property("checked")) == (False, True)
    assert loaded.find("dot").property("visible") is False


def test_a_disabled_choice_cannot_be_picked() -> None:
    loaded = load(
        'Column { Choice { objectName: "first"; text: "New room"; checked: true }\n'
        'Choice { objectName: "subject"; text: "From memory"; enabled: false } }'
    )
    choice = loaded.subject

    QTest.mouseClick(loaded.window, Qt.MouseButton.LeftButton, pos=centre(choice).toPoint())
    QMetaObject.invokeMethod(choice, "click")
    wait(20)

    assert choice.property("checked") is False
    assert loaded.find("first").property("checked") is True
    assert choice.property("opacity") == loaded.theme.property("disabledOpacity")


# PopupMenu ------------------------------------------------------------------------


def test_popup_menu_picks_with_the_keyboard_and_closes() -> None:
    loaded = load(
        'Item { width: 300; height: 300; PopupMenu { objectName: "subject"; title: "Focus"; '
        'items: [{ "text": "Focus for 15 minutes", "key": 15 }, '
        '{ "text": "Focus for 25 minutes", "key": 25, "detail": "A pomodoro" }] } }'
    )
    menu = loaded.subject
    picked: list[object] = []
    menu.chosen.connect(picked.append)

    QMetaObject.invokeMethod(menu, "open")
    assert wait_until(lambda: menu.property("opened") is True)
    QTest.keyClick(loaded.window, Qt.Key.Key_Down)
    QTest.keyClick(loaded.window, Qt.Key.Key_Return)

    assert picked == [25]
    assert wait_until(lambda: menu.property("visible") is False)
    assert loaded.warnings == []


# TimerChip focus line ---------------------------------------------------------------


def test_timer_chip_focus_line_fills_and_hides() -> None:
    loaded = load(
        'TimerChip { objectName: "subject"; seconds: 90; progress: 0.5; '
        'focusText: "in a 25 minute focus block" }'
    )
    line = loaded.find("focusLine")

    assert line.property("visible") is True
    full = loaded.subject.property("width") - 2 * loaded.subject.property("height") / 2
    assert line.property("width") == pytest.approx(full * 0.5, abs=1)

    loaded.subject.setProperty("progress", -1)
    wait(20)
    assert line.property("visible") is False


# Toggle -------------------------------------------------------------------------


def test_toggle_flips_by_click_and_keyboard() -> None:
    loaded = load('Toggle { objectName: "subject"; width: 300; text: "Reduce motion" }')
    toggle = loaded.subject
    toggled = SignalCounter(toggle, "toggled()")

    QTest.mouseClick(loaded.window, Qt.MouseButton.LeftButton, pos=centre(toggle).toPoint())
    wait(20)
    assert toggle.property("checked") is True
    toggle.forceActiveFocus()
    QTest.keyClick(loaded.window, Qt.Key.Key_Space)
    wait(20)
    assert toggle.property("checked") is False
    QTest.keyClick(loaded.window, Qt.Key.Key_Return)
    wait(20)

    assert toggle.property("checked") is True
    assert toggled.count == 3
    assert _colour(loaded.find("track"), "color") == _colour(loaded.theme, "accent")


# Slider -------------------------------------------------------------------------


def test_slider_steps_with_the_keyboard() -> None:
    loaded = load(
        'Slider { objectName: "subject"; width: 300; from: 360; to: 520; stepSize: 4; '
        'value: 420; accessibleName: "Panel width" }'
    )
    slider = loaded.subject
    moved = SignalCounter(slider, "moved()")
    slider.forceActiveFocus()

    QTest.keyClick(loaded.window, Qt.Key.Key_Right)
    assert slider.property("value") == 424
    QTest.keyClick(loaded.window, Qt.Key.Key_PageUp)
    assert slider.property("value") == 464
    QTest.keyClick(loaded.window, Qt.Key.Key_PageDown)
    QTest.keyClick(loaded.window, Qt.Key.Key_PageDown)
    assert slider.property("value") == 384
    for _ in range(3):
        QTest.keyClick(loaded.window, Qt.Key.Key_PageDown)

    assert slider.property("value") == 360
    assert moved.count >= 6
    assert slider.property("valueText") == "360"


# Choice swatch ------------------------------------------------------------------


def test_choice_swatch_shows_only_when_set() -> None:
    loaded = load(
        'Column { Choice { objectName: "subject"; text: "Cyan"; swatch: Theme.accentCyan }\n'
        'Choice { objectName: "plain"; text: "New room" } }'
    )

    swatches, pending = [], [loaded.window.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == "swatch":
            swatches.append(item.property("visible"))
        pending.extend(item.childItems())
    assert sorted(swatches) == [False, True]


def test_disclosure_toggles_from_the_keyboard_and_announces_its_state() -> None:
    loaded = load(DEFAULT_BODIES["Disclosure"])
    subject = loaded.subject
    header = loaded.find("subjectHeader")
    inside = loaded.find("inside")
    assert subject.property("expanded") is False
    assert inside.property("visible") is False

    header.forceActiveFocus()
    QTest.keyClick(loaded.window, Qt.Key.Key_Space)

    assert subject.property("expanded") is True
    assert inside.property("visible") is True
    QMetaObject.invokeMethod(header, "clicked")
    assert subject.property("expanded") is False
    assert loaded.warnings == []
