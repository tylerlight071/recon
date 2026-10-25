import QtQuick
import QtQuick.Templates as T
import "../theme"

// Single-line input with a hint that shows while it's empty, like TextArea.
// Return and Enter emit `accepted` (a form can start from the keyboard).
T.TextField {
    id: control

    property string hint: ""
    property string accessibleName: hint
    readonly property bool hintShown: length === 0 && preeditText === ""

    implicitWidth: Math.max(contentWidth + leftPadding + rightPadding, Theme.toastWidth)
    implicitHeight: Theme.controlHeight
    leftPadding: Theme.space3
    rightPadding: Theme.space3
    verticalAlignment: TextInput.AlignVCenter
    selectByMouse: true

    font.family: Theme.fontUi
    font.pixelSize: Theme.fontSizeBody
    color: Theme.textPrimary
    selectionColor: Theme.accent
    selectedTextColor: Theme.textOnAccent
    placeholderTextColor: Theme.textTertiary

    Accessible.role: Accessible.EditableText
    Accessible.name: accessibleName
    Accessible.description: hint

    Text {
        objectName: "hint"
        x: control.leftPadding
        width: control.width - control.leftPadding - control.rightPadding
        height: control.height
        verticalAlignment: Text.AlignVCenter
        text: control.hint
        font: control.font
        color: Theme.textTertiary
        elide: Text.ElideRight
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
