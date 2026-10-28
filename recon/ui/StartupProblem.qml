import QtQuick
import QtQuick.Window
import "components"
import "theme"

// Shown instead of Recon when it can't start (or is already open), so a launch
// from the app menu never fails silently (audit F-10, F-12). Bridge: Problem.
Window {
    id: problem

    objectName: "startupProblem"
    title: "Recon"
    color: Theme.bg
    width: Theme.dialogWidth + Theme.space8 * 2
    height: content.implicitHeight + Theme.space8 * 2
    minimumWidth: width
    minimumHeight: height
    visible: true

    Column {
        id: content
        x: Theme.space8
        y: Theme.space8
        width: problem.width - Theme.space8 * 2
        spacing: Theme.space3

        Text {
            objectName: "problemTitle"
            width: parent.width
            wrapMode: Text.Wrap
            text: Problem.title
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeLarge
            font.weight: Theme.weightSemiBold
            color: Theme.textPrimary
        }

        Text {
            objectName: "problemMessage"
            width: parent.width
            wrapMode: Text.Wrap
            text: Problem.message
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeBody
            color: Theme.textSecondary
        }

        Item {
            width: parent.width
            height: Theme.space2
        }

        Button {
            objectName: "problemClose"
            variant: "primary"
            text: qsTr("Close")
            focus: true
            onClicked: Qt.quit()
        }
    }
}
