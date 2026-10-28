import QtQuick
import "../components"
import "../theme"

// Library (task 2.8, first pass): rooms in the vault, each opening in Obsidian,
// and History, tucked away, with one-click Restore (the toast offers Undo).
// No accent button: nothing here is the one next step. Bridges: LibraryModel, Vault.
Item {
    id: library

    objectName: "libraryScreen"

    Component.onCompleted: LibraryModel.refresh()

    component Heading: Text {
        topPadding: Theme.space4
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSizeSmall
        font.weight: Theme.weightMedium
        color: Theme.textTertiary
    }

    component Note: Text {
        width: parent.width
        wrapMode: Text.Wrap
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.textSecondary
    }

    Flickable {
        anchors.fill: parent
        contentHeight: page.implicitHeight + Theme.space12
        clip: true

        Column {
            id: page

            x: Theme.space8
            y: Theme.space8
            width: Math.min(library.width - Theme.space8 * 2, Theme.contentWidth)
            spacing: Theme.space3

            Text {
                text: qsTr("Library")
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeLarge
                font.weight: Theme.weightSemiBold
                color: Theme.textPrimary
            }

            Note { text: qsTr("Everything Recon has written to your vault. Open a room in Obsidian, or put back an earlier version from History.") }

            Text {
                objectName: "libraryProblem"
                width: parent.width
                wrapMode: Text.Wrap
                visible: LibraryModel.problem !== ""
                text: LibraryModel.problem
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeBody
                color: Theme.warning
            }

            Heading { text: qsTr("Rooms") }

            Note {
                objectName: "noRooms"
                visible: LibraryModel.rooms.length === 0
                text: qsTr("Rooms show up here once you apply them.")
            }

            Note {
                objectName: "openVaultFirst"
                visible: LibraryModel.rooms.length > 0 && !Vault.canOpenInObsidian
                text: qsTr("Open your vault in Obsidian once (Home shows how), and rooms open there from here.")
            }

            Repeater {
                model: LibraryModel.rooms

                Row {
                    required property var modelData
                    width: page.width
                    spacing: Theme.space2

                    ListRow {
                        objectName: "libraryRoom-" + modelData.id
                        width: parent.width - (openRoom.visible ? openRoom.width + parent.spacing : 0)
                        interactive: false
                        title: modelData.name
                        detail: modelData.detail
                        trailing: modelData.date
                    }

                    Button {
                        id: openRoom
                        objectName: "openRoom-" + modelData.id
                        anchors.verticalCenter: parent.verticalCenter
                        visible: Vault.canOpenInObsidian
                        variant: "quiet"
                        text: qsTr("Open in Obsidian")
                        Accessible.name: qsTr("Open %1 in Obsidian").arg(modelData.name)
                        onClicked: LibraryModel.openRoom(modelData.id)
                    }
                }
            }

            Item {
                width: parent.width
                height: Theme.space2
            }

            Disclosure {
                objectName: "historySection"
                width: parent.width
                title: qsTr("History")
                detail: LibraryModel.history.length

                Note {
                    width: parent.width - Theme.space6
                    text: qsTr("Restore puts back the versions a run replaced. What's there now is kept too, so Undo works. Notes a run created stay where they are.")
                }

                Repeater {
                    model: LibraryModel.history

                    Row {
                        required property var modelData
                        width: page.width - Theme.space6
                        spacing: Theme.space2

                        ListRow {
                            objectName: "run-" + modelData.runId
                            width: parent.width - (restoreRun.visible ? restoreRun.width + parent.spacing : 0)
                            interactive: false
                            title: modelData.room
                            detail: modelData.detail
                            trailing: modelData.date
                        }

                        Button {
                            id: restoreRun
                            objectName: "restore-" + modelData.runId
                            anchors.verticalCenter: parent.verticalCenter
                            visible: modelData.canRestore
                            enabled: !LibraryModel.busy
                            variant: "quiet"
                            text: qsTr("Restore")
                            Accessible.name: qsTr("Restore %1 to before this run").arg(modelData.room)
                            onClicked: LibraryModel.restore(modelData.runId)
                        }
                    }
                }
            }
        }
    }
}
