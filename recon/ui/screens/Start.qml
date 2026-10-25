import QtQuick
import "../components"
import "../theme"

// Start a room (task 1.8): two fields, path and module behind "More".
// Bridge: StartRoom. Return in any field starts; Escape goes back to Home.
FocusScope {
    id: start

    objectName: "startScreen"

    property bool more: false

    function submit() {
        StartRoom.start(roomName.text, taskCount.text, pathField.text, moduleField.text)
    }

    Component.onCompleted: {
        StartRoom.refresh()
        pathField.text = StartRoom.lastPath
        moduleField.text = StartRoom.lastModule
        roomName.forceActiveFocus()
    }

    Keys.onEscapePressed: Navigation.open("home")

    // Moves focus to the field that needs fixing, so Tyler can just type.
    Connections {
        target: StartRoom
        function onChanged() {
            if (StartRoom.problem === "")
                return
            if (roomName.text.trim() === "")
                roomName.forceActiveFocus()
            else
                taskCount.forceActiveFocus()
        }
    }

    component FieldLabel: Text {
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSizeSmall
        font.weight: Theme.weightMedium
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
            width: Math.min(start.width - Theme.space8 * 2, Theme.contentWidth)
            spacing: Theme.space5

            Text {
                text: qsTr("Start a room")
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeLarge
                font.weight: Theme.weightSemiBold
                color: Theme.textPrimary
            }

            Column {
                width: parent.width
                spacing: Theme.space2

                FieldLabel { text: qsTr("Room name") }

                TextField {
                    id: roomName
                    objectName: "roomName"
                    width: parent.width
                    hint: qsTr("e.g. DNS in Detail")
                    accessibleName: qsTr("Room name")
                    maximumLength: StartRoom.nameLimit
                    onAccepted: start.submit()
                }
            }

            Column {
                spacing: Theme.space2

                FieldLabel { text: qsTr("Number of tasks") }

                TextField {
                    id: taskCount
                    objectName: "taskCount"
                    width: Theme.numberFieldWidth
                    implicitWidth: Theme.numberFieldWidth
                    hint: qsTr("e.g. 7")
                    accessibleName: qsTr("Number of tasks")
                    maximumLength: String(StartRoom.maxTasks).length
                    inputMethodHints: Qt.ImhDigitsOnly
                    onAccepted: start.submit()
                }
            }

            // Path and module are remembered from the last room; most rooms keep them.
            Column {
                width: parent.width
                spacing: Theme.space3

                Row {
                    spacing: Theme.space2

                    Button {
                        objectName: "moreToggle"
                        variant: "quiet"
                        text: start.more ? qsTr("Less") : qsTr("More")
                        Accessible.description: qsTr("Path and module")
                        onClicked: start.more = !start.more
                    }

                    Text {
                        objectName: "placeSummary"
                        anchors.verticalCenter: parent.verticalCenter
                        visible: !start.more && text !== ""
                        text: [pathField.text.trim(), moduleField.text.trim()].filter(s => s !== "").join(" · ")
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.textTertiary
                    }
                }

                Column {
                    objectName: "moreFields"
                    width: parent.width
                    spacing: Theme.space5
                    visible: start.more

                    Column {
                        width: parent.width
                        spacing: Theme.space2

                        FieldLabel { text: qsTr("Path") }

                        TextField {
                            id: pathField
                            objectName: "pathField"
                            width: parent.width
                            hint: qsTr("e.g. Pre Security")
                            accessibleName: qsTr("Path")
                            maximumLength: StartRoom.placeLimit
                            onAccepted: start.submit()
                        }
                    }

                    Column {
                        width: parent.width
                        spacing: Theme.space2

                        FieldLabel { text: qsTr("Module") }

                        TextField {
                            id: moduleField
                            objectName: "moduleField"
                            width: parent.width
                            hint: qsTr("e.g. Network Fundamentals")
                            accessibleName: qsTr("Module")
                            maximumLength: StartRoom.placeLimit
                            onAccepted: start.submit()
                        }
                    }
                }
            }

            Column {
                width: parent.width
                spacing: Theme.space1

                FieldLabel { text: qsTr("Mode") }

                Choice {
                    objectName: "modeNew"
                    width: parent.width
                    text: qsTr("New room")
                    detail: qsTr("Take notes as you go, one task at a time.")
                    checked: true
                }

                // From memory arrives in Phase 4; shown now so the choice never moves.
                Choice {
                    objectName: "modeMemory"
                    width: parent.width
                    enabled: false
                    text: qsTr("From memory")
                    detail: qsTr("For a room you've already done. Coming soon.")
                }
            }

            Text {
                objectName: "problem"
                width: parent.width
                visible: StartRoom.problem !== ""
                wrapMode: Text.Wrap
                text: StartRoom.problem
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeBody
                color: Theme.warning
                Accessible.role: Accessible.AlertMessage
                Accessible.name: text
            }

            Row {
                spacing: Theme.space3

                Button {
                    objectName: "startButton"
                    variant: "primary"
                    enabled: !StartRoom.busy
                    text: StartRoom.busy ? qsTr("Starting…") : qsTr("Start")
                    shortcutHint: qsTr("Return")
                    onClicked: start.submit()
                }

                Button {
                    objectName: "backButton"
                    variant: "quiet"
                    text: qsTr("Back")
                    shortcutHint: qsTr("Escape")
                    onClicked: Navigation.open("home")
                }
            }
        }
    }
}
