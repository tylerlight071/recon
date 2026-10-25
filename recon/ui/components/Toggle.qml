import QtQuick
import QtQuick.Templates as T
import "../theme"

// An on/off switch with its label on the left. Space or Return flips it.
// The track fills with the accent when on; the knob slides (instantly with
// Reduce motion).
T.Switch {
    id: control

    implicitWidth: implicitContentWidth + implicitIndicatorWidth + spacing + leftPadding + rightPadding
    implicitHeight: Math.max(implicitContentHeight, implicitIndicatorHeight) + topPadding + bottomPadding
    padding: Theme.space1
    leftPadding: 0
    rightPadding: 0
    spacing: Theme.space3
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : Theme.disabledOpacity

    font.family: Theme.fontUi
    font.pixelSize: Theme.fontSizeBody

    Accessible.role: Accessible.CheckBox
    Accessible.name: text
    Accessible.checkable: true
    Accessible.checked: checked
    Accessible.onToggleAction: if (enabled) toggle()

    Keys.onReturnPressed: if (enabled) click()
    Keys.onEnterPressed: if (enabled) click()

    indicator: Rectangle {
        objectName: "track"
        implicitWidth: Theme.toggleWidth
        implicitHeight: Theme.toggleHeight
        x: control.width - width - control.rightPadding
        y: (control.height - height) / 2
        radius: height / 2
        color: control.checked ? Theme.accent : Theme.overlay
        border.color: control.checked ? Theme.accent : Theme.border
        border.width: Theme.hairline

        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Theme.easing } }

        Rectangle {
            objectName: "knob"
            width: parent.height - Theme.space1
            height: width
            radius: width / 2
            y: (parent.height - height) / 2
            x: control.checked ? parent.width - width - Theme.space1 / 2 : Theme.space1 / 2
            color: control.checked ? Theme.textOnAccent : Theme.textSecondary

            Behavior on x { NumberAnimation { duration: Theme.durationFast; easing.type: Theme.easing } }
        }

        FocusRing { shown: control.visualFocus; baseRadius: parent.radius }
    }

    contentItem: Text {
        objectName: "label"
        rightPadding: control.indicator.width + control.spacing
        text: control.text
        font: control.font
        color: Theme.textPrimary
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
    }
}
