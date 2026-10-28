import QtQuick
import QtQuick.Window
import "components"
import "theme"

// The normal window: Home, Review, Cards, Revise, Ask, Library, Settings.
// Size only; KWin decides where it goes. Closing it never closes the panel.
// Bridges: Navigation (current screen, raise requests), Pinning (KWin rule, task 1.4).
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

    // `under`: a screen reached from another one, with no sidebar entry of its own.
    readonly property var screens: [
        { "key": "home", "label": qsTr("Home"), "icon": "home", "file": "screens/Home.qml" },
        { "key": "start", "under": "home", "file": "screens/Start.qml" },
        { "key": "review", "under": "home", "file": "screens/Review.qml" },
        { "key": "done", "under": "home", "file": "screens/Done.qml" },
        { "key": "library", "label": qsTr("Library"), "icon": "library", "file": "screens/Library.qml" },
        { "key": "settings", "label": qsTr("Settings"), "icon": "sliders", "file": "screens/Settings.qml" }
    ]

    // The sidebar entry that lights up for a screen (Start lights up Home).
    function sidebarKey(key) {
        const match = screens.find(s => s.key === key)
        return match && match.under ? match.under : key
    }

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

    Connections {
        target: FlagGuard
        function onFieldFlagSkipped(window) {
            if (window === "main")
                toast.show(qsTr("Flag skipped. Recon never saves flags."))
        }
    }

    // A restore from History can be undone: Undo restores the restore's own backup.
    property string undoRun: ""

    Connections {
        target: LibraryModel
        function onRestored(message, newRunId) {
            main.undoRun = newRunId
            toast.show(message, qsTr("Undo"))
        }
    }

    Connections {
        target: toast
        function onAction() {
            if (main.undoRun !== "")
                LibraryModel.restore(main.undoRun)
            main.undoRun = ""
        }
        function onDismissed() { main.undoRun = "" }
    }

    Connections {
        target: Pinning
        function onPinFailed() {
            toast.show(qsTr("Couldn't pin the panel. It opens as a normal window for now. You can try again in Settings."))
        }
        function onUnpinFailed() {
            toast.show(qsTr("Couldn't remove the panel's KDE rule. Turn pinning on and off again to retry."))
        }
    }

    // The theme follows Settings (one engine, so this covers the panel too).
    // Asked once, at first launch, before any room starts (ADR 0004).
    Component.onCompleted: {
        Theme.accentName = Qt.binding(() => AppSettings.accent)
        Theme.reduceMotion = Qt.binding(() => AppSettings.reduceMotion)
        if (Pinning.askNeeded)
            pinQuestion.open()
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
                    model: main.screens.filter(s => !s.under)

                    SidebarItem {
                        required property var modelData
                        objectName: "nav-" + modelData.key
                        width: parent.width
                        text: modelData.label
                        iconName: modelData.icon
                        selected: main.sidebarKey(Navigation.currentScreen) === modelData.key
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

    Dialog {
        id: pinQuestion
        objectName: "pinQuestion"
        title: qsTr("Pin the Recon panel to the right edge of your screen while you work?")
        body: qsTr("Recon adds a KDE window rule for its panel only, so it always sits beside your browser at full height. You can turn this off in Settings.")
        primaryText: qsTr("Pin the panel")
        secondaryText: qsTr("Not now")
        onAccepted: Pinning.pin()
        onRejected: Pinning.decline()
    }

    Toast {
        id: toast
        objectName: "toast"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.space6
    }
}
