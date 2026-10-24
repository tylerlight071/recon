import QtQuick
import QtQuick.Templates as T
import "../theme"

// Quiet time-on-task chip for the panel header: shows elapsed time, never a
// countdown (ADHD rule 10). Clicking it opens the focus presets (task 1.12).
T.Button {
    id: control

    property int seconds: 0
    property bool running: false
    readonly property string elapsed: format(seconds)

    function format(total) {
        const s = Math.max(0, Math.floor(total))
        const h = Math.floor(s / 3600)
        const m = Math.floor((s % 3600) / 60)
        const rest = s % 60
        const pad = n => (n < 10 ? "0" : "") + n
        return h > 0 ? h + ":" + pad(m) + ":" + pad(rest) : m + ":" + pad(rest)
    }

    function spoken(total) {
        const minutes = Math.floor(Math.max(0, total) / 60)
        return minutes === 1 ? "1 minute" : minutes + " minutes"
    }

    implicitWidth: implicitContentWidth + leftPadding + rightPadding
    implicitHeight: Theme.controlHeightSmall
    leftPadding: Theme.space2
    rightPadding: Theme.space3
    focusPolicy: Qt.StrongFocus

    Accessible.role: Accessible.Button
    Accessible.name: "Time on task, " + spoken(seconds) + (running ? "" : ", paused")
    Accessible.onPressAction: clicked()

    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    contentItem: Row {
        spacing: Theme.space1

        Icon {
            anchors.verticalCenter: parent.verticalCenter
            name: "clock"
            color: control.running ? Theme.textSecondary : Theme.textTertiary
        }

        Text {
            objectName: "elapsed"
            anchors.verticalCenter: parent.verticalCenter
            text: control.elapsed
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeSmall
            font.features: { "tnum": 1 }
            color: control.running ? Theme.textSecondary : Theme.textTertiary
        }
    }

    background: Rectangle {
        radius: height / 2
        color: control.hovered ? Theme.raised : Theme.clear
        border.color: Theme.border
        border.width: Theme.hairline

        FocusRing { shown: control.visualFocus; baseRadius: parent.radius }
    }
}
