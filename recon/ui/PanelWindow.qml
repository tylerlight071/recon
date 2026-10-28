import QtQuick
import QtQuick.Window
import "components"
import "screens"
import "theme"

// The slim side panel beside the browser: room session and Finish live here.
// Its title is what the KWin rule matches (with the app ID), so it never changes.
// Bridges: AppSettings (panel width), Navigation (open main-window screens),
// FlagGuard (hard rule 2: the "Flag skipped" notice and "Not a flag, keep it"),
// RoomSession (the open room; task 1.9), Focus (the timer), Finish (task 1.13).
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

    // Remember the width the user drags it to (saved shortly after the drag stops).
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

    // What the toast's button does ("Not a flag, keep it", or Undo a delete).
    property var toastAction: null

    // A notice without a button waits for an open Undo (or keep) toast to go, rather
    // than taking its button away early (audit F-21).
    property string waiting: ""

    function notify(message, actionText, action) {
        if (action === undefined && toast.shown && toastAction !== null) {
            waiting = message
            return
        }
        toastAction = action === undefined ? null : action
        toast.show(message, actionText)
    }

    Connections {
        target: FlagGuard
        function onFlagSkipped(blockId, keepable) {
            if (keepable === "")
                panel.notify(qsTr("Flag skipped. Recon never saves flags."))
            else
                panel.notify(qsTr("Skipped something that looks like a flag. If it's an example hash, you can keep it."),
                             qsTr("Not a flag, keep it"), () => FlagGuard.keep(blockId, keepable))
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
        function onFailed(message) { panel.notify(message) }
        function onSaveRecovered() { panel.notify(qsTr("Saved again.")) }
        // Deletions get a 10 s Undo (ADHD rule 4).
        function onBlockDeleted(blockId) {
            panel.notify(qsTr("Block deleted."), qsTr("Undo"), () => RoomSession.undoDelete(blockId))
        }
    }

    Connections {
        target: FlagGuard
        function onFieldFlagSkipped(window) {
            if (window === "panel")
                panel.notify(qsTr("Flag skipped. Recon never saves flags."))
        }
    }

    Connections {
        target: Finish
        function onFailed(message) { panel.notify(message) }
    }

    Connections {
        target: Focus
        function onFocusDone(minutes) {
            panel.notify(qsTr("That's %1 minutes of focus. Keep going, or take a short break.").arg(minutes))
        }
        function onBreakSuggested() {
            panel.notify(qsTr("You've been at this for an hour and a half. Time for a short break?"))
        }
    }

    Item {
        id: content
        anchors.fill: parent

        Session {
            id: sessionView
            anchors.fill: parent
            visible: RoomSession.hasRoom && !Finish.shown
            focus: visible
        }

        Finished {
            anchors.fill: parent
            visible: Finish.shown
            focus: visible
        }

        Column {
            objectName: "noRoom"
            visible: !RoomSession.hasRoom && !Finish.shown
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
        id: toast
        objectName: "panelToast"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        // Above the add bar and footer while a room is open, so it never hides them.
        anchors.bottomMargin: RoomSession.hasRoom ? sessionView.bottomChrome + Theme.space3 : Theme.space6
        width: parent.width - Theme.space4 * 2
        onDismissed: {
            panel.toastAction = null
            if (panel.waiting !== "") {
                const message = panel.waiting
                panel.waiting = ""
                panel.notify(message)
            }
        }
        onAction: {
            const action = panel.toastAction
            panel.toastAction = null
            if (action)
                action()
        }
    }
}
