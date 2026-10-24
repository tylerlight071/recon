import QtQuick
import QtQuick.Window
import "components"
import "theme"

// The slim side panel beside the browser: room session and Finish live here.
// Its title is what the KWin rule matches (with the app ID), so it never changes.
// Bridges: AppSettings (panel width), Navigation (open main-window screens).
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

    NumberAnimation {
        id: fadeIn
        target: content
        property: "opacity"
        from: 0
        to: 1
        duration: Theme.durationBase
        easing.type: Theme.easing
    }

    Item {
        id: content
        anchors.fill: parent

        Column {
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
}
