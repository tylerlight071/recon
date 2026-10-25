import QtQuick
import "../components"
import "../theme"

// The room session (task 1.9), shown in the panel while a room is open.
// Top to bottom: header, task title, blocks, add bar, footer (SPEC.md).
// Bridge: RoomSession. One accent button: "Next task" / "Finish room".
FocusScope {
    id: session

    objectName: "sessionScreen"

    // Height of the add bar and footer (the panel keeps toasts above them).
    readonly property real bottomChrome: addBar.height + footer.height


    // Keep the block with the cursor in view as blocks are added.
    function reveal(item) {
        const top = item.mapToItem(page, 0, 0).y
        const bottom = top + item.height
        if (top < body.contentY)
            body.contentY = top
        else if (bottom > body.contentY + body.height)
            body.contentY = Math.min(bottom - body.height, body.contentHeight - body.height)
    }

    Component.onCompleted: titleField.text = RoomSession.taskTitle

    Connections {
        target: RoomSession
        function onTaskShown() { titleField.text = RoomSession.taskTitle }
        function onTaskCompleted() { tick.play() }
    }

    Shortcut {
        sequences: ["Ctrl+Return", "Ctrl+Enter"]
        enabled: session.visible
        onActivated: RoomSession.next()
    }

    Repeater {
        model: RoomSession.addBar
        Item {
            required property var modelData
            Shortcut {
                sequence: modelData.shortcut
                enabled: session.visible && modelData.available && modelData.shortcut.startsWith("Ctrl")
                onActivated: RoomSession.addBlock(modelData.type)
            }
        }
    }

    // ---- Header: room, "Task n of N", ring, time --------------------------------
    Item {
        id: header
        objectName: "sessionHeader"
        anchors.left: parent.left
        anchors.right: parent.right
        height: headerRow.implicitHeight + Theme.space3 * 2

        Row {
            id: headerRow
            x: Theme.space4
            y: Theme.space3
            width: parent.width - Theme.space4 * 2
            spacing: Theme.space2

            Column {
                width: headerRow.width - tools.width - headerRow.spacing
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.space1

                Text {
                    objectName: "roomName"
                    width: parent.width
                    elide: Text.ElideRight
                    text: RoomSession.roomName
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeLarge
                    font.weight: Theme.weightSemiBold
                    color: Theme.textPrimary
                }

                Text {
                    objectName: "taskLabel"
                    text: RoomSession.taskLabel
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.textSecondary
                }
            }

            Row {
                id: tools
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.space2

                Item {
                    width: Theme.ringSize
                    height: Theme.ringSize
                    anchors.verticalCenter: parent.verticalCenter

                    ProgressRing {
                        objectName: "progressRing"
                        anchors.fill: parent
                        value: RoomSession.progress
                        valueText: RoomSession.taskLabel
                    }

                    // A small win after "Next task": a tick inside the ring, then it fades.
                    Icon {
                        id: tick
                        objectName: "tick"
                        anchors.centerIn: parent
                        name: "check"
                        color: Theme.success
                        opacity: 0
                        scale: 1

                        function play() { tickAnimation.restart() }

                        SequentialAnimation {
                            id: tickAnimation
                            ParallelAnimation {
                                NumberAnimation { target: tick; property: "opacity"; from: 0; to: 1; duration: Theme.durationFast; easing.type: Theme.easing }
                                NumberAnimation { target: tick; property: "scale"; from: 0.6; to: 1; duration: Theme.durationBase; easing.type: Theme.easing }
                            }
                            PauseAnimation { duration: Theme.tickHoldMs }
                            NumberAnimation { target: tick; property: "opacity"; to: 0; duration: Theme.durationBase; easing.type: Theme.easing }
                        }
                    }
                }

                TimerChip {
                    objectName: "timerChip"
                    anchors.verticalCenter: parent.verticalCenter
                    seconds: RoomSession.elapsed
                    running: true
                }

                IconButton {
                    objectName: "sessionHome"
                    anchors.verticalCenter: parent.verticalCenter
                    iconName: "home"
                    tip: qsTr("Open Home")
                    onClicked: Navigation.open("home")
                }
            }
        }

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: Theme.hairline
            color: Theme.border
        }
    }

    // ---- Task title and blocks (scrolls) -------------------------------------------
    Flickable {
        id: body
        objectName: "sessionBody"
        anchors.top: header.bottom
        anchors.bottom: addBar.top
        anchors.left: parent.left
        anchors.right: parent.right
        contentHeight: page.implicitHeight + Theme.space4 * 2
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: page
            x: Theme.space4
            y: Theme.space4
            width: body.width - Theme.space4 * 2
            spacing: Theme.space3

            TextField {
                id: titleField
                objectName: "taskTitle"
                width: parent.width
                hint: RoomSession.titleHint
                accessibleName: qsTr("Task title")
                onTextEdited: RoomSession.setTitle(text)
            }

            Text {
                objectName: "ownWords"
                width: parent.width
                wrapMode: Text.Wrap
                text: qsTr("Notes in your own words. A pasted snippet is fine; a whole task isn't.")
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.textTertiary
            }

            Repeater {
                id: blockList
                objectName: "blockList"
                model: RoomSession.blocks

                Block {
                    id: block

                    required property int blockId
                    required property string blockType
                    required property string text
                    required property string typeLabel
                    required property string hint

                    objectName: "block-" + blockId
                    width: page.width
                    type: blockType
                    label: typeLabel
                    showHandle: false

                    TextArea {
                        id: editor
                        objectName: "editor"
                        width: parent.width
                        hint: block.hint
                        accessibleName: block.typeLabel
                        mono: block.blockType === "command"

                        property bool ready: false

                        Component.onCompleted: {
                            text = block.text
                            ready = true
                        }

                        // Every keystroke: flags out, autosave queued (hard rules 2 and 7).
                        onTextChanged: {
                            if (!ready)
                                return
                            const shown = RoomSession.edit(block.blockId, text)
                            if (shown !== text) {
                                const at = cursorPosition
                                text = shown
                                cursorPosition = Math.min(at, length)
                            }
                        }

                        onActiveFocusChanged: if (activeFocus) session.reveal(block)
                    }

                    Connections {
                        target: RoomSession
                        function onFocusBlock(id) {
                            if (id === block.blockId)
                                editor.forceActiveFocus()
                        }
                        function onReplaceText(id, value) {
                            if (id === block.blockId && editor.text !== value)
                                editor.text = value
                        }
                    }
                }
            }
        }
    }

    // ---- Add bar: one button per block type, always in the same place ------------------
    Item {
        id: addBar
        objectName: "addBar"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: footer.top
        height: addRow.implicitHeight + Theme.space2 * 2

        Rectangle {
            width: parent.width
            height: Theme.hairline
            color: Theme.border
        }

        Row {
            id: addRow
            anchors.centerIn: parent
            spacing: Theme.space1

            Repeater {
                model: RoomSession.addBar

                IconButton {
                    required property var modelData
                    objectName: "add-" + modelData.type
                    iconName: modelData.icon
                    enabled: modelData.available
                    tip: modelData.available ? modelData.label : qsTr("%1 · Coming soon").arg(modelData.label)
                    shortcutHint: modelData.shortcut
                    onClicked: RoomSession.addBlock(modelData.type)
                }
            }
        }
    }

    // ---- Footer: Skip, and the one primary button ----------------------------------
    Item {
        id: footer
        objectName: "sessionFooter"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Theme.controlHeight + Theme.space3 * 2

        Rectangle {
            width: parent.width
            height: Theme.hairline
            color: Theme.border
        }

        Button {
            objectName: "skipTask"
            anchors.left: parent.left
            anchors.leftMargin: Theme.space2
            anchors.verticalCenter: parent.verticalCenter
            variant: "quiet"
            text: qsTr("Skip this task")
            onClicked: RoomSession.skip()
        }

        Button {
            objectName: "nextTask"
            anchors.right: parent.right
            anchors.rightMargin: Theme.space4
            anchors.verticalCenter: parent.verticalCenter
            variant: "primary"
            text: RoomSession.primaryText
            shortcutHint: qsTr("Ctrl+Return")
            onClicked: RoomSession.next()
        }
    }
}
