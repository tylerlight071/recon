import QtQuick
import QtQuick.Templates as T
import "../theme"

// A row in a list: title, a quieter detail line, and a trailing note (e.g. "2 days ago").
// Clickable only when `interactive` is true; otherwise it's plain information.
T.ItemDelegate {
    id: control

    property string title: ""
    property string detail: ""
    property string trailing: ""
    property bool interactive: true

    enabled: interactive
    implicitWidth: Theme.toastWidth
    implicitHeight: content.implicitHeight + topPadding + bottomPadding
    padding: Theme.space3
    leftPadding: Theme.space3
    rightPadding: Theme.space3
    focusPolicy: interactive ? Qt.StrongFocus : Qt.NoFocus

    Accessible.role: interactive ? Accessible.Button : Accessible.StaticText
    Accessible.name: [title, detail, trailing].filter(s => s !== "").join(", ")
    Accessible.onPressAction: if (interactive) clicked()

    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    contentItem: Item {
        id: content
        implicitHeight: Math.max(texts.implicitHeight, trailingText.implicitHeight)

        Column {
            id: texts
            anchors.left: parent.left
            anchors.right: trailingText.left
            anchors.rightMargin: Theme.space3
            spacing: Theme.space1

            Text {
                objectName: "rowTitle"
                width: parent.width
                text: control.title
                elide: Text.ElideRight
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeBody
                font.weight: Theme.weightMedium
                color: Theme.textPrimary
            }

            Text {
                width: parent.width
                visible: control.detail !== ""
                text: control.detail
                elide: Text.ElideRight
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.textSecondary
            }
        }

        Text {
            id: trailingText
            anchors.right: parent.right
            anchors.top: parent.top
            text: control.trailing
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.textTertiary
        }
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: control.interactive && control.hovered ? Theme.raised : Theme.clear

        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Theme.easing } }

        FocusRing { shown: control.visualFocus }
    }
}
