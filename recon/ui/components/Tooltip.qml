import QtQuick
import QtQuick.Templates as T
import "../theme"

// Small dark tooltip with an optional keyboard shortcut, e.g. "Command  Ctrl+2".
T.ToolTip {
    id: control

    property string shortcut: ""

    // Templates popups don't size themselves; the styled Controls normally do this.
    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset,
                            implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset,
                             implicitContentHeight + topPadding + bottomPadding)
    delay: Theme.tooltipDelay
    padding: Theme.space2
    leftPadding: Theme.space3
    rightPadding: Theme.space3
    font.family: Theme.fontUi
    font.pixelSize: Theme.fontSizeSmall
    x: parent ? (parent.width - implicitWidth) / 2 : 0
    y: parent ? -implicitHeight - Theme.space1 : 0

    // A popup isn't an Item, so its accessible role sits on what it shows.
    contentItem: Row {
        spacing: Theme.space2
        Accessible.role: Accessible.ToolTip
        Accessible.name: control.shortcut === "" ? control.text : control.text + ", " + control.shortcut

        Text {
            text: control.text
            font: control.font
            color: Theme.textPrimary
        }

        Text {
            visible: control.shortcut !== ""
            text: control.shortcut
            font.family: Theme.fontMono
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.textTertiary
        }
    }

    background: Rectangle {
        color: Theme.overlay
        radius: Theme.radiusSmall
        border.color: Theme.border
        border.width: Theme.hairline
    }

    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.durationFast } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.durationFast } }
}
