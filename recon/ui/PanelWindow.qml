import QtQuick
import QtQuick.Window
import "components"
import "screens"
import "theme"

// The slim side panel beside the browser: room session and Finish live here.
// Its title is what the KWin rule matches (with the app ID), so it never changes.
// Bridges: AppSettings (panel width), Navigation (open main-window screens),
// FlagGuard (hard rule 2: the "Flag skipped" notice and "Not a flag, keep it"),
// RoomSession (the open room; task 1.9).
Window {
    id: panel

    objectName: "panelWindow"
    title: "Recon Panel"
    color: Theme.bg
    width: AppSettings.panelWidth
    height: Screen.desktopAvailableHeight
    minimumWidth: Theme.panelWidthMin
    maximumWidth: Theme.panelWidthMax
    minimumHeight: Theme.mainWindowMinHeight
    visible: false

    // Remember the width Tyler drags it to (saved shortly after he stops).
    onWidthChanged: if (visible) AppSettings.panelWidth = width

    function bringForward() {
        const wasHidden = !visible
        if (wasHidden) {
            content.opacity = 0
            show()
            fadeIn.restart()
        }
        raise()
        requestActivate()
    }

    Connections {
        target: Navigation
        function onPanelRequested() { panel.bringForward() }
    }

    // The hex string (and its block) that "Not a flag, keep it" would keep.
    property int skippedBlock: -1
    property string skippedText: ""

    Connections {
        target: FlagGuard
        function onFlagSkipped(blockId, keepable) {
            panel.skippedBlock = blockId
            panel.skippedText = keepable
            if (keepable === "")
                flagToast.show(qsTr("Flag skipped. Recon never saves flags."))
            else
                flagToast.show(qsTr("Skipped something that looks like a flag. If it's an example hash, you can keep it."),
                               qsTr("Not a flag, keep it"))
        }
    }

    NumberAnimation {
        id: fadeIn
        target: content
        property: "opacity"
        from: 0
        to: 1
        duration: Theme.durationBase
        easing.type: Theme.easing
    }

    Connections {
        target: RoomSession
        function onFailed(message) { flagToast.show(message) }
    }

    Item {
        id: content
        anchors.fill: parent

        Session {
            id: sessionView
            anchors.fill: parent
            visible: RoomSession.hasRoom
            focus: visible
        }

        Column {
            objectName: "noRoom"
            visible: !RoomSession.hasRoom
            anchors.centerIn: parent
            width: parent.width - Theme.space6 * 2
            spacing: Theme.space3

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: qsTr("No room open.")
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeLarge
                font.weight: Theme.weightMedium
                color: Theme.textPrimary
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: qsTr("Start a room from Home, and it opens here.")
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeBody
                color: Theme.textSecondary
            }

            Button {
                objectName: "openHome"
                anchors.horizontalCenter: parent.horizontalCenter
                variant: "secondary"
                text: qsTr("Open Home")
                onClicked: Navigation.open("home")
            }
        }
    }

    Toast {
        id: flagToast
        objectName: "flagToast"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        // Above the add bar and footer while a room is open, so it never hides them.
        anchors.bottomMargin: RoomSession.hasRoom ? sessionView.bottomChrome + Theme.space3 : Theme.space6
        width: parent.width - Theme.space4 * 2
        onAction: FlagGuard.keep(panel.skippedBlock, panel.skippedText)
    }
}
