import QtQuick
import QtQuick.Templates as T
import "../theme"

// Square icon-only button. `tip` is both its tooltip and its accessible name,
// so every icon button says what it does.
T.Button {
    id: control

    property string iconName: ""
    property string tip: ""
    property string shortcutHint: ""

    implicitWidth: Theme.controlHeight
    implicitHeight: Theme.controlHeight
    padding: Theme.space2
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : Theme.disabledOpacity

    Accessible.role: Accessible.Button
    Accessible.name: tip
    Accessible.description: shortcutHint
    Accessible.onPressAction: clicked()

    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    contentItem: Item {
        Icon {
            anchors.centerIn: parent
            name: control.iconName
            color: control.hovered || control.checked ? Theme.textPrimary : Theme.textSecondary
        }
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        opacity: control.down ? Theme.pressedOpacity : 1
        color: control.hovered || control.checked ? Theme.raised : Theme.clear

        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Theme.easing } }

        FocusRing { shown: control.visualFocus }
    }

    Tooltip {
        visible: control.tip !== "" && (control.hovered || control.visualFocus)
        text: control.tip
        shortcut: control.shortcutHint
    }
}
