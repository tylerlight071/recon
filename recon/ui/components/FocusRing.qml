import QtQuick
import "../theme"

// Visible keyboard-focus outline, drawn just outside its parent.
// Shown only for keyboard focus (visualFocus), never on mouse clicks.
Rectangle {
    objectName: "focusRing"
    property bool shown: false
    property real baseRadius: Theme.radiusSmall

    anchors.fill: parent
    anchors.margins: -Theme.focusRingGap
    radius: baseRadius + Theme.focusRingGap
    color: Theme.clear
    border.color: Theme.focusRing
    border.width: Theme.focusRingWidth
    visible: shown
}
