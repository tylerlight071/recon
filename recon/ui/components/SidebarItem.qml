import QtQuick
import QtQuick.Templates as T
import "../theme"

// One entry in the main window's sidebar. `selected` marks the current screen.
T.ItemDelegate {
    id: control

    property string iconName: ""
    property bool selected: false

    implicitWidth: implicitContentWidth + leftPadding + rightPadding
    implicitHeight: Theme.sidebarItemHeight
    leftPadding: Theme.space3
    rightPadding: Theme.space3
    spacing: Theme.space3
    focusPolicy: Qt.StrongFocus

    font.family: Theme.fontUi
    font.pixelSize: Theme.fontSizeBody
    font.weight: selected ? Theme.weightMedium : Theme.weightRegular

    Accessible.role: Accessible.PageTab
    Accessible.name: text
    Accessible.selected: selected
    Accessible.onPressAction: clicked()

    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    contentItem: Row {
        spacing: control.spacing

        Icon {
            anchors.verticalCenter: parent.verticalCenter
            name: control.iconName
            visible: control.iconName !== ""
            color: control.selected ? Theme.textPrimary : Theme.textSecondary
        }

        Text {
            objectName: "label"
            anchors.verticalCenter: parent.verticalCenter
            text: control.text
            font: control.font
            color: control.selected || control.hovered ? Theme.textPrimary : Theme.textSecondary
        }
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: control.selected ? Theme.overlay : control.hovered ? Theme.raised : Theme.clear

        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Theme.easing } }

        FocusRing { shown: control.visualFocus }
    }
}
