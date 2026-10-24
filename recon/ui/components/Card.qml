import QtQuick
import QtQuick.Templates as T
import "../theme"

// Raised surface with a hairline border. Put content inside; it's padded.
T.Pane {
    id: control

    property string title: ""

    padding: Theme.space4
    implicitWidth: implicitContentWidth + leftPadding + rightPadding
    implicitHeight: implicitContentHeight + topPadding + bottomPadding

    Accessible.role: Accessible.Grouping
    Accessible.name: title

    background: Rectangle {
        color: Theme.raised
        radius: Theme.radiusCard
        border.color: Theme.border
        border.width: Theme.hairline
    }
}
