import QtQuick
import "../components"
import "../theme"

// Home (task 1.7): one primary action, "Where was I?", recent rooms.
// Bridge: HomeModel. One accent button only (ADHD rule 1).
Item {
    id: home

    objectName: "homeScreen"

    Component.onCompleted: HomeModel.refresh()

    Flickable {
        anchors.fill: parent
        contentHeight: page.implicitHeight + Theme.space12
        clip: true

        Column {
            id: page

            x: Theme.space8
            y: Theme.space8
            width: Math.min(home.width - Theme.space8 * 2, Theme.contentWidth)
            spacing: Theme.space4

            // Nothing yet: a short, friendly start.
            Column {
                objectName: "emptyState"
                width: parent.width
                spacing: Theme.space2
                visible: !HomeModel.hasCurrent && HomeModel.recentRooms.length === 0

                Text {
                    width: parent.width
                    text: qsTr("Ready when you are.")
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeLarge
                    font.weight: Theme.weightSemiBold
                    color: Theme.textPrimary
                }

                Text {
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: qsTr("Start a room and Recon walks you through your notes, one task at a time.")
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeBody
                    color: Theme.textSecondary
                }
            }

            Card {
                objectName: "whereWasI"
                width: parent.width
                title: qsTr("Where was I?")
                visible: HomeModel.hasCurrent

                Column {
                    width: parent.width
                    spacing: Theme.space1

                    Text {
                        text: qsTr("Where was I?")
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.textTertiary
                    }

                    Text {
                        objectName: "currentName"
                        width: parent.width
                        elide: Text.ElideRight
                        text: HomeModel.currentName
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSizeLarge
                        font.weight: Theme.weightMedium
                        color: Theme.textPrimary
                    }

                    Text {
                        objectName: "currentProgress"
                        text: HomeModel.currentTask + " · " + HomeModel.currentWhen
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSizeBody
                        color: Theme.textSecondary
                    }

                    Text {
                        objectName: "lastNote"
                        width: parent.width
                        visible: HomeModel.lastNote !== ""
                        elide: Text.ElideRight
                        text: qsTr("Last note: “%1”").arg(HomeModel.lastNote)
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.textTertiary
                    }
                }
            }

            Row {
                spacing: Theme.space3

                Button {
                    objectName: "primaryAction"
                    variant: "primary"
                    text: HomeModel.primaryText
                    onClicked: HomeModel.primary()
                }

                Button {
                    objectName: "startNew"
                    variant: "quiet"
                    visible: HomeModel.hasCurrent
                    text: qsTr("Start a new room")
                    onClicked: HomeModel.startNew()
                }
            }

            // One-time: Obsidian only opens vaults it knows (task 2.1). Quiet buttons only;
            // the screen's one accent button stays "Start a room" / "Carry on".
            Card {
                objectName: "obsidianStep"
                width: parent.width
                title: qsTr("Open your vault in Obsidian")
                visible: Vault.needsObsidian || Vault.problem !== ""

                Column {
                    width: parent.width
                    spacing: Theme.space2

                    Text {
                        text: Vault.problem !== "" ? qsTr("Your vault") : qsTr("Open your vault in Obsidian, once")
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSizeBody
                        font.weight: Theme.weightMedium
                        color: Theme.textPrimary
                    }

                    Text {
                        objectName: "obsidianStepText"
                        width: parent.width
                        wrapMode: Text.Wrap
                        text: Vault.problem !== ""
                              ? Vault.problem
                              : qsTr("Recon keeps your notes in %1. In Obsidian, choose \"Open folder as vault\" and pick that folder. Then Recon can open notes there for you.").arg(Vault.shown)
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.textSecondary
                    }

                    Row {
                        spacing: Theme.space2
                        visible: Vault.problem === ""

                        Button {
                            objectName: "copyVaultPath"
                            variant: "secondary"
                            text: qsTr("Copy path")
                            onClicked: Vault.copyPath()
                        }

                        Button {
                            objectName: "obsidianDone"
                            variant: "quiet"
                            text: qsTr("I've done that")
                            onClicked: Vault.confirmOpened()
                        }
                    }

                    Button {
                        objectName: "vaultSettings"
                        visible: Vault.problem !== ""
                        variant: "quiet"
                        text: qsTr("Open Settings")
                        onClicked: Navigation.open("settings")
                    }
                }
            }

            Column {
                objectName: "recentRooms"
                width: parent.width
                spacing: Theme.space1
                visible: HomeModel.recentRooms.length > 0

                Text {
                    topPadding: Theme.space4
                    bottomPadding: Theme.space1
                    text: qsTr("Recent rooms")
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeSmall
                    font.weight: Theme.weightMedium
                    color: Theme.textTertiary
                }

                Repeater {
                    model: HomeModel.recentRooms

                    ListRow {
                        required property var modelData
                        objectName: "recent-" + modelData.id
                        width: parent.width
                        title: modelData.name
                        detail: modelData.detail
                        trailing: modelData.when
                        interactive: modelData.canOpen
                        onClicked: HomeModel.resume(modelData.id)
                    }
                }
            }
        }
    }
}
