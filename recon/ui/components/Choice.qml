import QtQuick
import QtQuick.Templates as T
import "../theme"

// One option in a set of choices (a radio button): a label and a quieter detail
// line. Options in the same parent are exclusive. Space or Return picks it.
T.RadioButton {
    id: control

    property string detail: ""
    property color swatch: Theme.clear

    implicitWidth: implicitContentWidth + leftPadding + rightPadding
    implicitHeight: implicitContentHeight + topPadding + bottomPadding
    padding: Theme.space2
    spacing: Theme.space3
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : Theme.disabledOpacity

    font.family: Theme.fontUi
    font.pixelSize: Theme.fontSizeBody
    font.weight: Theme.weightMedium

    Accessible.role: Accessible.RadioButton
    Accessible.name: text
    Accessible.description: detail
    Accessible.checked: checked
    Accessible.onPressAction: if (enabled) click()

    Keys.onReturnPressed: if (enabled) click()
    Keys.onEnterPressed: if (enabled) click()

    indicator: Rectangle {
        objectName: "indicator"
        x: control.leftPadding
        y: control.topPadding + Theme.hairline
        width: Theme.iconSize
        height: Theme.iconSize
        radius: width / 2
        color: Theme.surface
        border.width: Theme.hairline
        border.color: control.checked ? Theme.accent : Theme.textTertiary

        Rectangle {
            objectName: "dot"
            anchors.centerIn: parent
            width: Theme.space2
            height: Theme.space2
            radius: width / 2
            color: Theme.accent
            visible: control.checked
        }
    }

    contentItem: Column {
        leftPadding: Theme.iconSize + control.spacing
        spacing: Theme.space1

        Row {
            spacing: Theme.space2

            // Optional colour swatch (e.g. the accent choices in Settings).
            Rectangle {
                objectName: "swatch"
                anchors.verticalCenter: parent.verticalCenter
                width: Theme.swatchSize
                height: Theme.swatchSize
                radius: width / 2
                color: control.swatch
                visible: control.swatch.a > 0
            }

            Text {
                objectName: "label"
                text: control.text
                font: control.font
                color: Theme.textPrimary
            }
        }

        Text {
            objectName: "detail"
            visible: control.detail !== ""
            text: control.detail
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.textSecondary
        }
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: control.enabled && control.hovered ? Theme.raised : Theme.clear

        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Theme.easing } }

        FocusRing { shown: control.visualFocus }
    }
}
