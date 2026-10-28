import QtQuick
import QtQuick.Templates as T
import "../theme"

// A collapsible section: a header row (chevron, title, quieter detail or count)
// that shows or hides what's inside. Space, Return or a click toggles it.
Column {
    id: control

    property string title: ""
    property string detail: ""
    property bool expanded: false
    property bool large: false
    default property alias content: body.data

    spacing: Theme.space2

    T.AbstractButton {
        id: header
        objectName: control.objectName + "Header"
        width: parent.width
        implicitHeight: Math.max(Theme.controlHeight, row.implicitHeight + Theme.space2 * 2)
        focusPolicy: Qt.StrongFocus
        onClicked: control.expanded = !control.expanded

        Accessible.role: Accessible.Button
        Accessible.name: control.detail !== "" ? control.title + ", " + control.detail : control.title
        Accessible.description: control.expanded ? qsTr("Expanded") : qsTr("Collapsed")
        Accessible.onPressAction: clicked()
        Keys.onReturnPressed: clicked()
        Keys.onEnterPressed: clicked()

        background: Rectangle {
            radius: Theme.radiusSmall
            color: header.hovered ? Theme.raised : Theme.clear

            Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Theme.easing } }

            FocusRing { shown: header.visualFocus }
        }

        contentItem: Row {
            id: row
            leftPadding: Theme.space2
            spacing: Theme.space2

            Icon {
                anchors.verticalCenter: parent.verticalCenter
                width: Theme.iconSize
                height: Theme.iconSize
                name: "chevron"
                color: Theme.textSecondary
                rotation: control.expanded ? 90 : 0

                Behavior on rotation { NumberAnimation { duration: Theme.durationFast; easing.type: Theme.easing } }
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: control.title
                font.family: Theme.fontUi
                font.pixelSize: control.large ? Theme.fontSizeLarge : Theme.fontSizeBody
                font.weight: control.large ? Theme.weightSemiBold : Theme.weightMedium
                color: Theme.textPrimary
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: control.detail !== ""
                text: control.detail
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.textSecondary
            }
        }
    }

    Column {
        id: body
        objectName: control.objectName + "Body"
        width: parent.width
        leftPadding: Theme.space6
        spacing: Theme.space3
        visible: control.expanded
    }
}
