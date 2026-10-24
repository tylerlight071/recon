import QtQuick
import QtQuick.Templates as T
import "../theme"

// Modal question with one primary action and an optional quieter one.
// Escape or the secondary button rejects; the primary button accepts.
T.Dialog {
    id: control

    property string body: ""
    property string primaryText: "OK"
    property string secondaryText: "Cancel"

    modal: true
    focus: true
    closePolicy: T.Popup.CloseOnEscape
    padding: Theme.space6
    topPadding: Theme.space5
    width: Theme.dialogWidth
    // Templates popups don't size themselves; the styled Controls normally do this.
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset,
                             implicitContentHeight + topPadding + bottomPadding
                             + (implicitHeaderHeight > 0 ? implicitHeaderHeight + spacing : 0)
                             + (implicitFooterHeight > 0 ? implicitFooterHeight + spacing : 0))
    anchors.centerIn: parent

    T.Overlay.modal: Rectangle { color: Theme.scrim }

    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.durationBase; easing.type: Theme.easing } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.durationFast; easing.type: Theme.easing } }

    // A popup isn't an Item, so its accessible role sits on what it shows.
    background: Rectangle {
        Accessible.role: Accessible.Dialog
        Accessible.name: control.title
        Accessible.description: control.body
        color: Theme.overlay
        radius: Theme.radiusDialog
        border.color: Theme.border
        border.width: Theme.hairline
    }

    header: Text {
        visible: control.title !== ""
        text: control.title
        topPadding: Theme.space5
        leftPadding: Theme.space6
        rightPadding: Theme.space6
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Theme.weightSemiBold
        color: Theme.textPrimary
        wrapMode: Text.Wrap
    }

    contentItem: Text {
        text: control.body
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSizeBody
        color: Theme.textSecondary
        wrapMode: Text.Wrap
    }

    footer: Row {
        layoutDirection: Qt.RightToLeft
        spacing: Theme.space2
        rightPadding: Theme.space6
        bottomPadding: Theme.space5

        Button {
            objectName: "primary"
            variant: "primary"
            text: control.primaryText
            onClicked: control.accept()
        }

        Button {
            objectName: "secondary"
            variant: "quiet"
            visible: control.secondaryText !== ""
            text: control.secondaryText
            onClicked: control.reject()
        }
    }
}
