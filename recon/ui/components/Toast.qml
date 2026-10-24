import QtQuick
import "../theme"

// Brief notice at the bottom of a window, optionally with one action
// (usually "Undo"). Disappears after `timeout` ms; deletions use the 10 s
// default (ADHD rule 4). Call show(message, actionText).
Rectangle {
    id: toast

    property string message: ""
    property string actionText: ""
    property int timeout: Theme.undoToastMs
    readonly property bool shown: state === "shown"

    signal action()
    signal dismissed()

    function show(text, actionLabel) {
        message = text
        actionText = actionLabel === undefined ? "" : actionLabel
        state = "shown"
        timer.restart()
    }

    function hide() {
        if (state !== "shown")
            return
        timer.stop()
        state = ""
        dismissed()
    }

    implicitWidth: Theme.toastWidth
    implicitHeight: Math.max(Theme.controlHeight, content.implicitHeight) + Theme.space2 * 2
    radius: Theme.radiusCard
    color: Theme.overlay
    border.color: Theme.border
    border.width: Theme.hairline
    opacity: 0
    visible: opacity > 0

    Accessible.role: Accessible.AlertMessage
    Accessible.name: message

    states: State {
        name: "shown"
        PropertyChanges { toast.opacity: 1 }
    }
    transitions: Transition {
        NumberAnimation { property: "opacity"; duration: Theme.durationBase; easing.type: Theme.easing }
    }

    Timer {
        id: timer
        interval: toast.timeout
        onTriggered: toast.hide()
    }

    Row {
        id: content
        anchors.verticalCenter: parent.verticalCenter
        x: Theme.space4
        width: parent.width - Theme.space4 - Theme.space2
        spacing: Theme.space3

        Text {
            objectName: "message"
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - (actionButton.visible ? actionButton.width + parent.spacing : 0)
            text: toast.message
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeBody
            color: Theme.textPrimary
            wrapMode: Text.Wrap
        }

        Button {
            id: actionButton
            objectName: "action"
            anchors.verticalCenter: parent.verticalCenter
            variant: "quiet"
            visible: toast.actionText !== ""
            text: toast.actionText
            onClicked: {
                toast.action()
                toast.hide()
            }
        }
    }
}
