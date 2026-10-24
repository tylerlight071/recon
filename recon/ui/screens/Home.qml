import QtQuick
import "../theme"

// Home. Task 1.7 fills it in ("Start a room", "Where was I?", recent rooms).
Item {
    objectName: "homeScreen"

    Column {
        x: Theme.space8
        y: Theme.space8
        width: parent.width - Theme.space8 * 2
        spacing: Theme.space2

        Text {
            text: qsTr("Home")
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeLarge
            font.weight: Theme.weightSemiBold
            color: Theme.textPrimary
        }

        Text {
            width: parent.width
            wrapMode: Text.Wrap
            text: qsTr("Starting a room and \"Where was I?\" come next.")
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeBody
            color: Theme.textSecondary
        }
    }
}
