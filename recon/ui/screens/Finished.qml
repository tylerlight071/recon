import QtCore
import QtQuick
import QtQuick.Dialogs
import "../components"
import "../theme"

// Finish (task 1.13): a calm completion moment, what was written and how long
// it took, how processing is going (task 2.5), and "Export as Markdown".
// "Back to the room" undoes the finish. Bridges: Finish, Processing. One accent button.
FocusScope {
    id: finish

    objectName: "finishScreen"

    // The completion moment: a tick that settles in when the screen appears.
    onVisibleChanged: if (visible) settle.restart()

    Column {
        anchors.centerIn: parent
        width: parent.width - Theme.space6 * 2
        spacing: Theme.space4

        Rectangle {
            id: badge
            objectName: "completionBadge"
            anchors.horizontalCenter: parent.horizontalCenter
            width: Theme.badgeSize
            height: Theme.badgeSize
            radius: width / 2
            color: Theme.clear
            border.color: Theme.success
            border.width: Theme.focusRingWidth

            Icon {
                anchors.centerIn: parent
                width: Theme.iconSizeLarge
                height: Theme.iconSizeLarge
                name: "check"
                color: Theme.success
            }

            ParallelAnimation {
                id: settle
                NumberAnimation { target: badge; property: "opacity"; from: 0; to: 1; duration: Theme.durationSlow; easing.type: Theme.easing }
                NumberAnimation { target: badge; property: "scale"; from: 0.7; to: 1; duration: Theme.durationSlow; easing.type: Theme.easing }
            }
        }

        Column {
            width: parent.width
            spacing: Theme.space1

            Text {
                objectName: "finishTitle"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: qsTr("%1 is finished.").arg(Finish.roomName)
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeLarge
                font.weight: Theme.weightSemiBold
                color: Theme.textPrimary
            }

            Text {
                objectName: "finishSummary"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: Finish.summary
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeBody
                color: Theme.textSecondary
            }

            Text {
                objectName: "finishTime"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: qsTr("%1 on this room").arg(Finish.timeSpent)
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeBody
                color: Theme.textSecondary
            }
        }

        // Processing, in plain words: the step, waiting, ready, or what went wrong.
        Column {
            objectName: "processingStatus"
            width: parent.width
            spacing: Theme.space2
            visible: processingLine.text !== ""

            Text {
                id: processingLine
                objectName: "processingLine"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: Processing.line !== "" ? Processing.line : Finish.statusLine
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeBody
                color: Processing.failed ? Theme.warning : Theme.textSecondary
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }

            // A thin line filling step by step: progress, never a spinner.
            Rectangle {
                objectName: "processingProgress"
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width / 2
                height: Theme.focusLineHeight
                radius: height / 2
                color: Theme.border
                visible: Processing.busy

                Rectangle {
                    objectName: "processingFill"
                    width: parent.width * Processing.stepNumber / Processing.steps
                    height: parent.height
                    radius: parent.radius
                    color: Theme.accent

                    Behavior on width { NumberAnimation { duration: Theme.durationBase; easing.type: Theme.easing } }
                }
            }

            Button {
                objectName: "openReview"
                anchors.horizontalCenter: parent.horizontalCenter
                visible: Processing.ready || (Finish.inReview && Processing.line === "")
                variant: "secondary"
                text: qsTr("Review notes")
                onClicked: ReviewModel.open(Finish.roomId)
            }

            Button {
                objectName: "retryProcessing"
                anchors.horizontalCenter: parent.horizontalCenter
                visible: Processing.failed
                variant: "secondary"
                text: qsTr("Retry")
                onClicked: Processing.retry()
            }
        }

        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: qsTr("Your notes are safe in Recon. Export makes a Markdown copy you can keep anywhere.")
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.textTertiary
        }

        Button {
            objectName: "exportButton"
            anchors.horizontalCenter: parent.horizontalCenter
            variant: "primary"
            text: Finish.busy ? qsTr("Saving…") : qsTr("Export as Markdown")
            onClicked: if (!Finish.busy) folderDialog.open()
        }

        Column {
            objectName: "exportedArea"
            width: parent.width
            spacing: Theme.space1
            visible: Finish.exportedText !== ""

            Text {
                objectName: "exportedText"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: Finish.exportedText
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.textSecondary
            }

            Button {
                objectName: "openFolder"
                anchors.horizontalCenter: parent.horizontalCenter
                variant: "quiet"
                text: qsTr("Open folder")
                onClicked: Finish.openFolder()
            }
        }

        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Theme.space3

            Button {
                objectName: "backToRoom"
                variant: "quiet"
                text: qsTr("Back to the room")
                onClicked: Finish.backToRoom()
            }

            Button {
                objectName: "finishDone"
                variant: "secondary"
                text: qsTr("Done")
                onClicked: Finish.close()
            }
        }
    }

    FolderDialog {
        id: folderDialog
        objectName: "folderDialog"
        title: qsTr("Choose a folder for the Markdown file")
        currentFolder: Finish.folderUrl !== ""
                       ? Finish.folderUrl
                       : StandardPaths.writableLocation(StandardPaths.DocumentsLocation)
        onAccepted: Finish.export(selectedFolder.toString())
    }
}
