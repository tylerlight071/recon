import QtQuick
import QtQuick.Window
import "components"
import "theme"

// The normal window: Home, Review, Cards, Revise, Ask, Library, Settings.
// Size only; KWin decides where it goes. Closing it never closes the panel.
// Bridges: Navigation (current screen, raise requests).
Window {
    id: main

    objectName: "mainWindow"
    title: "Recon"
    color: Theme.bg
    width: Theme.mainWindowWidth
    height: Theme.mainWindowHeight
    minimumWidth: Theme.mainWindowMinWidth
    minimumHeight: Theme.mainWindowMinHeight
    visible: true

    readonly property var screens: [
        { "key": "home", "label": qsTr("Home"), "icon": "home", "file": "screens/Home.qml" },
        { "key": "settings", "label": qsTr("Settings"), "icon": "sliders", "file": "screens/Settings.qml" }
    ]

    function screenFile(key) {
        const match = screens.find(s => s.key === key)
        return match ? match.file : screens[0].file
    }

    // Raise with a quick fade of the content (Wayland ignores window opacity).
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
        function onMainWindowRequested() { main.bringForward() }
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

        Rectangle {
            id: sidebar
            objectName: "sidebar"
            width: Theme.sidebarWidth
            height: parent.height
            color: Theme.surface

            Rectangle {
                anchors.right: parent.right
                width: Theme.hairline
                height: parent.height
                color: Theme.border
            }

            Column {
                x: Theme.space3
                y: Theme.space4
                width: parent.width - Theme.space3 * 2
                spacing: Theme.space1

                Repeater {
                    model: main.screens

                    SidebarItem {
                        required property var modelData
                        objectName: "nav-" + modelData.key
                        width: parent.width
                        text: modelData.label
                        iconName: modelData.icon
                        selected: Navigation.currentScreen === modelData.key
                        onClicked: Navigation.open(modelData.key)
                    }
                }
            }
        }

        Loader {
            id: screenLoader
            objectName: "screenLoader"
            anchors.left: sidebar.right
            anchors.right: parent.right
            height: parent.height
            source: main.screenFile(Navigation.currentScreen)
        }
    }
}
