import QtQuick
import QtQuick.Templates as T
import "../theme"

// Text button. variant: "primary" (the one accent button on a screen),
// "secondary" (bordered) or "quiet" (text only). Space, Return and Enter click.
T.Button {
    id: control

    property string variant: "secondary"
    property string shortcutHint: ""
    readonly property bool isPrimary: variant === "primary"
    readonly property bool isQuiet: variant === "quiet"

    implicitWidth: Math.max(implicitBackgroundWidth, implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight, implicitContentHeight + topPadding + bottomPadding)
    leftPadding: isQuiet ? Theme.space2 : Theme.space4
    rightPadding: leftPadding
    topPadding: Theme.space1
    bottomPadding: Theme.space1
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : Theme.disabledOpacity

    font.family: Theme.fontUi
    font.pixelSize: Theme.fontSizeBody
    font.weight: isPrimary ? Theme.weightSemiBold : Theme.weightMedium

    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.description: shortcutHint
    Accessible.onPressAction: clicked()

    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.isPrimary ? Theme.textOnAccent
             : control.isQuiet && !control.hovered ? Theme.textSecondary
             : Theme.textPrimary
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        implicitHeight: Theme.controlHeight
        radius: Theme.radiusSmall
        opacity: control.down ? Theme.pressedOpacity : 1
        color: control.isPrimary ? (control.hovered ? Theme.accentHover : Theme.accent)
             : control.isQuiet ? (control.hovered ? Theme.raised : Theme.clear)
             : (control.hovered ? Theme.overlay : Theme.raised)
        border.color: control.isPrimary || control.isQuiet ? Theme.clear : Theme.border
        border.width: Theme.hairline

        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Theme.easing } }

        FocusRing { shown: control.visualFocus }
    }
}
