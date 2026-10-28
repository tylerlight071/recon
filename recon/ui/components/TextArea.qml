import QtQuick
import QtQuick.Templates as T
import "../theme"

// Multi-line input with a hint that fades out on typing and comes back when
// the text is cleared (SPEC.md, Room session). `mono` for commands.
// Tab and Shift+Tab move to the next or previous control. With `tabTypes`, Tab
// types a tab character instead (tables) and Ctrl+Tab / Ctrl+Shift+Tab leave.
T.TextArea {
    id: control

    property string hint: ""
    property string accessibleName: hint
    property bool mono: false
    property bool tabTypes: false

    function moveFocus(forward) {
        const next = nextItemInFocusChain(forward)
        if (next)
            next.forceActiveFocus(forward ? Qt.TabFocusReason : Qt.BacktabFocusReason)
    }

    // Audit F-13: Tab used to type a tab, so the keyboard could never leave a block.
    // Keys handlers accept by default: hand the key back to type a tab.
    Keys.onTabPressed: event => {
        if (tabTypes && !(event.modifiers & Qt.ControlModifier)) {
            event.accepted = false
            return
        }
        moveFocus(true)
        event.accepted = true
    }
    Keys.onBacktabPressed: event => {
        if (tabTypes && !(event.modifiers & Qt.ControlModifier)) {
            event.accepted = false
            return
        }
        moveFocus(false)
        event.accepted = true
    }
    readonly property bool hintShown: length === 0 && preeditText === ""

    implicitWidth: Math.max(contentWidth + leftPadding + rightPadding, Theme.toastWidth)
    implicitHeight: Math.max(contentHeight + topPadding + bottomPadding, Theme.textAreaMinHeight)
    padding: Theme.space3
    wrapMode: TextEdit.Wrap
    selectByMouse: true
    persistentSelection: true

    font.family: mono ? Theme.fontMono : Theme.fontUi
    font.pixelSize: mono ? Theme.fontSizeMono : Theme.fontSizeBody
    color: Theme.textPrimary
    selectionColor: Theme.accent
    selectedTextColor: Theme.textOnAccent
    placeholderTextColor: Theme.textTertiary

    Accessible.role: Accessible.EditableText
    Accessible.name: accessibleName
    Accessible.description: hint

    Text {
        id: hintText
        objectName: "hint"
        x: control.leftPadding
        y: control.topPadding
        width: control.width - control.leftPadding - control.rightPadding
        text: control.hint
        font: control.font
        color: Theme.textTertiary
        wrapMode: Text.Wrap
        opacity: control.hintShown ? 1 : 0
        Accessible.ignored: true

        Behavior on opacity { NumberAnimation { duration: Theme.durationFast; easing.type: Theme.easing } }
    }

    background: Rectangle {
        color: Theme.surface
        radius: Theme.radiusSmall
        border.color: control.activeFocus ? Theme.focusRing : Theme.border
        border.width: control.activeFocus ? Theme.focusRingWidth : Theme.hairline
    }
}
