import QtQuick
import QtQuick.Templates as T
import "../theme"

// One note block: a card with a thin coloured left edge for its type, a type
// label and a drag handle. Put the editor inside. Reordering is task 1.10.
T.Pane {
    id: block

    property string type: "key_idea"
    property string label: ""
    property bool showHandle: true
    readonly property alias handle: grip
    default property alias content: body.data

    padding: Theme.space3
    leftPadding: Theme.space3 + Theme.blockEdgeWidth
    implicitWidth: implicitContentWidth + leftPadding + rightPadding
    implicitHeight: implicitContentHeight + topPadding + bottomPadding

    Accessible.role: Accessible.Grouping
    Accessible.name: label + " block"

    background: Rectangle {
        color: Theme.raised
        radius: Theme.radiusCard
        border.color: Theme.border
        border.width: Theme.hairline
        clip: true

        Rectangle {
            objectName: "edge"
            width: Theme.blockEdgeWidth
            height: parent.height
            color: Theme.blockEdge(block.type)
            opacity: Theme.blockEdgeOpacity
        }
    }

    contentItem: Column {
        spacing: Theme.space2

        Item {
            width: parent.width
            height: Math.max(typeLabel.implicitHeight, grip.implicitHeight)

            Text {
                id: typeLabel
                objectName: "typeLabel"
                anchors.verticalCenter: parent.verticalCenter
                text: block.label
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeSmall
                font.weight: Theme.weightMedium
                color: Theme.textSecondary
            }

            Icon {
                id: grip
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                name: "grip"
                color: Theme.textTertiary
                visible: block.showHandle
            }
        }

        Column {
            id: body
            width: parent.width
            spacing: Theme.space2
        }
    }
}
