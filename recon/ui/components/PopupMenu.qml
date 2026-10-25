import QtQuick
import QtQuick.Templates as T
import "../theme"

// A small menu that opens beside its control. `items` is a list of
// { text, key, detail }; picking one emits chosen(key) and closes the menu.
// Up / Down move between items; Escape or a click outside closes it.
T.Popup {
    id: menu

    property string title: ""
    property var items: []

    signal chosen(var key)

    padding: Theme.space1
    implicitWidth: Theme.menuWidth
    implicitHeight: content.implicitHeight + topPadding + bottomPadding
    focus: true
    closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutsideParent

    onOpened: {
        const first = rows.itemAt(0)
        if (first)
            first.forceActiveFocus()
    }

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.durationFast; easing.type: Theme.easing }
    }

    background: Rectangle {
        color: Theme.overlay
        radius: Theme.radiusCard
        border.color: Theme.border
        border.width: Theme.hairline
    }

    contentItem: Column {
        id: content

        // A Popup isn't an Item, so its content carries the menu's role and name.
        Accessible.role: Accessible.PopupMenu
        Accessible.name: menu.title

        Repeater {
            id: rows
            model: menu.items

            ListRow {
                required property var modelData
                required property int index
                objectName: "menuItem-" + modelData.key
                width: content.width
                title: modelData.text
                detail: modelData.detail || ""
                // Close first: choosing can change `items`, which replaces this row.
                onClicked: {
                    const key = modelData.key
                    menu.close()
                    menu.chosen(key)
                }
                Keys.onDownPressed: if (index + 1 < rows.count) rows.itemAt(index + 1).forceActiveFocus()
                Keys.onUpPressed: if (index > 0) rows.itemAt(index - 1).forceActiveFocus()
            }
        }
    }
}
