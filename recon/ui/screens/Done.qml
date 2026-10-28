import QtQuick
import "../components"
import "../theme"

// Done (task 2.7): the room is in the vault. A short completion moment, what was
// written, the room's place in its path, and "Open in Obsidian" (the one accent
// button). Until the vault has been opened in Obsidian once, its one-time step
// shows instead, because Obsidian ignores links to vaults it doesn't know.
// Bridges: DoneModel, Vault, Navigation.
Item {
    id: done

    objectName: "doneScreen"

    Component.onCompleted: settle.restart()

    Column {
        anchors.centerIn: parent
        width: Math.min(done.width - Theme.space8 * 2, Theme.contentWidth)
        spacing: Theme.space4

        Rectangle {
            id: badge
            objectName: "doneBadge"
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
                objectName: "doneTitle"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: qsTr("%1 is in your vault.").arg(DoneModel.roomName)
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeLarge
                font.weight: Theme.weightSemiBold
                color: Theme.textPrimary
            }

            Text {
                objectName: "doneWritten"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                visible: DoneModel.written > 0
                text: DoneModel.written === 1 ? qsTr("1 note written.") : qsTr("%1 notes written.").arg(DoneModel.written)
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeBody
                color: Theme.textSecondary
            }

            Text {
                objectName: "doneProgress"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: DoneModel.progress
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeBody
                color: Theme.textSecondary
            }
        }

        Button {
            objectName: "openInObsidian"
            anchors.horizontalCenter: parent.horizontalCenter
            visible: Vault.canOpenInObsidian
            variant: "primary"
            text: qsTr("Open in Obsidian")
            onClicked: DoneModel.openInObsidian()
        }

        Text {
            objectName: "doneProblem"
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            visible: DoneModel.problem !== ""
            text: DoneModel.problem
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.warning
        }

        Button {
            objectName: "notOpened"
            anchors.horizontalCenter: parent.horizontalCenter
            visible: Vault.canOpenInObsidian && DoneModel.tried
            variant: "quiet"
            text: qsTr("Didn't open?")
            onClicked: DoneModel.notOpened()
        }

        // Obsidian only follows links to vaults it has opened: the one-time step first.
        Card {
            objectName: "doneOpenVault"
            width: parent.width
            visible: Vault.needsObsidian
            title: qsTr("Open your vault in Obsidian, once")

            Column {
                width: parent.width
                spacing: Theme.space3

                Text {
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: qsTr("Open your vault in Obsidian, once")
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeBody
                    font.weight: Theme.weightSemiBold
                    color: Theme.textPrimary
                }

                Text {
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: qsTr("In Obsidian, choose \"Open folder as vault\" and pick %1. After that, Recon can open your notes there.").arg(Vault.shown)
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeBody
                    color: Theme.textSecondary
                }

                Row {
                    spacing: Theme.space3

                    Button {
                        objectName: "doneCopyPath"
                        variant: "secondary"
                        text: qsTr("Copy path")
                        onClicked: Vault.copyPath()
                    }

                    Button {
                        objectName: "doneConfirmOpened"
                        variant: "primary"
                        text: qsTr("I've done that")
                        onClicked: Vault.confirmOpened()
                    }
                }
            }
        }

        Button {
            objectName: "doneHome"
            anchors.horizontalCenter: parent.horizontalCenter
            variant: "quiet"
            text: qsTr("Back to Home")
            onClicked: Navigation.open("home")
        }
    }
}
