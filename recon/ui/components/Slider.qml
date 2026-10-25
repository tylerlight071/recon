import QtQuick
import QtQuick.Templates as T
import "../theme"

// A horizontal slider. Arrow keys step by `stepSize`; Page Up / Page Down by ten
// steps. `accessibleName` and `valueText` are what a screen reader says.
T.Slider {
    id: control

    property string accessibleName: ""
    property string valueText: String(Math.round(value))

    implicitWidth: Theme.toastWidth
    implicitHeight: Theme.controlHeight
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : Theme.disabledOpacity

    Accessible.role: Accessible.Slider
    Accessible.name: accessibleName
    Accessible.description: valueText

    Keys.onPressed: event => {
        if (event.key === Qt.Key_PageUp) {
            value = Math.min(to, value + stepSize * 10)
            moved()
            event.accepted = true
        } else if (event.key === Qt.Key_PageDown) {
            value = Math.max(from, value - stepSize * 10)
            moved()
            event.accepted = true
        }
    }

    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.availableWidth
        height: Theme.sliderTrack
        radius: height / 2
        color: Theme.overlay

        Rectangle {
            objectName: "fill"
            width: control.visualPosition * parent.width
            height: parent.height
            radius: parent.radius
            color: Theme.accent
        }
    }

    handle: Rectangle {
        objectName: "handle"
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: Theme.sliderHandle
        height: Theme.sliderHandle
        radius: width / 2
        color: control.pressed ? Theme.accentHover : Theme.textPrimary
        border.color: Theme.border
        border.width: Theme.hairline

        FocusRing { shown: control.visualFocus; baseRadius: parent.radius }
    }
}
