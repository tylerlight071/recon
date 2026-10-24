import QtQuick
import "../theme"

// Settings. Task 1.14 fills it in (vault, accent, reduce motion, panel width, chime, pinning).
Item {
    objectName: "settingsScreen"

    Column {
        x: Theme.space8
        y: Theme.space8
        width: parent.width - Theme.space8 * 2
        spacing: Theme.space2

        Text {
            text: qsTr("Settings")
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeLarge
            font.weight: Theme.weightSemiBold
            color: Theme.textPrimary
        }

        Text {
            width: parent.width
            wrapMode: Text.Wrap
            text: qsTr("Panel width is remembered when you resize the panel. More settings come later.")
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeBody
            color: Theme.textSecondary
        }
    }
}
