import QtQuick
import "../components"
import "../editors"
import "../theme"

// The room session (task 1.9), shown in the panel while a room is open.
// Top to bottom: header, task title, blocks, add bar, footer (SPEC.md).
// Footer: Previous task (Alt+Left), Skip this task, and Next task (Ctrl+Return).
// Blocks reorder by dragging the grip, or Alt+Up / Alt+Down in a block.
// Bridge: RoomSession. One accent button: "Next task" / "Finish room".
FocusScope {
    id: session

    objectName: "sessionScreen"

    // Height of the add bar and footer (the panel keeps toasts above them).
    readonly property real bottomChrome: addBar.height + footer.height


    // The block with the cursor (for Alt+Up / Alt+Down), and a drag's landing slot.
    property int focusedIndex: -1
    property int dropSlot: -1

    function blockAt(i) { return blockList.itemAt(i) }

    // Move the focused block up or down one place from the keyboard.
    function nudge(step) {
        const item = blockAt(focusedIndex)
        if (!item)
            return
        const target = Math.max(0, Math.min(focusedIndex + step, blockList.count - 1))
        RoomSession.moveBlock(item.blockId, target)
        // The editor keeps the cursor, so it won't report focus again.
        focusedIndex = target
    }

    // While dragging: the slot is how many blocks' middles are above the pointer.
    function dragTo(from, sceneY) {
        const y = page.mapFromItem(null, 0, sceneY).y
        let slot = 0
        for (let i = 0; i < blockList.count; ++i) {
            const item = blockAt(i)
            if (item.y + item.height / 2 < y)
                slot = i + 1
        }
        dropSlot = slot
        blockAt(from).dragging = true
        const gap = page.spacing / 2
        const below = slot < blockList.count ? blockAt(slot) : null
        const last = blockAt(blockList.count - 1)
        dropLine.y = page.y + (below ? below.y - gap : last.y + last.height + gap) - dropLine.height / 2
    }

    function drop(from) {
        const item = blockAt(from)
        const slot = dropSlot
        dropSlot = -1
        if (!item)
            return
        item.dragging = false
        if (slot < 0)
            return
        const target = slot > from ? slot - 1 : slot
        if (target !== from)
            RoomSession.moveBlock(item.blockId, target)
    }

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

    // Undo and redo when the cursor isn't in a block (blocks handle their own keys;
    // the task title keeps its own text undo).
    Shortcut {
        sequences: [StandardKey.Undo]
        enabled: session.visible
        onActivated: RoomSession.undo()
    }

    Shortcut {
        sequences: [StandardKey.Redo, "Ctrl+Shift+Z"]
        enabled: session.visible
        onActivated: RoomSession.redo()
    }

    Shortcut {
        sequence: "Ctrl+Shift+Backspace"
        enabled: session.visible && session.focusedIndex >= 0 && blockList.count > 1
        onActivated: {
            const item = session.blockAt(session.focusedIndex)
            if (item)
                RoomSession.deleteBlock(item.blockId)
        }
    }

    Shortcut {
        sequence: "Alt+Up"
        enabled: session.visible && session.focusedIndex > 0
        onActivated: session.nudge(-1)
    }

    Shortcut {
        sequence: "Alt+Down"
        enabled: session.visible && session.focusedIndex >= 0 && session.focusedIndex < blockList.count - 1
        onActivated: session.nudge(1)
    }

    Shortcut {
        sequence: "Alt+Left"
        enabled: session.visible && RoomSession.canGoBack
        onActivated: RoomSession.previous()
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
                    id: timerChip
                    objectName: "timerChip"
                    anchors.verticalCenter: parent.verticalCenter
                    seconds: Focus.seconds
                    running: Focus.running
                    progress: Focus.focusing ? Focus.focusProgress : -1
                    focusText: Focus.focusing ? qsTr("in a %1 minute focus block").arg(Focus.focusMinutes) : ""
                    onClicked: focusMenu.open()

                    PopupMenu {
                        id: focusMenu
                        objectName: "focusMenu"
                        y: timerChip.height + Theme.space1
                        x: timerChip.width - width
                        title: qsTr("Focus")
                        items: (Focus.focusing
                                ? [{ "text": qsTr("Stop focusing"), "key": 0,
                                     "detail": qsTr("%1 minute block").arg(Focus.focusMinutes) }]
                                : []).concat(Focus.presets.map(m => ({ "text": qsTr("Focus for %1 minutes").arg(m), "key": m })))
                        onChosen: key => key === 0 ? Focus.stopFocus() : Focus.startFocus(key)
                    }
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

                BlockEditor {
                    width: page.width
                    deletable: blockList.count > 1
                    onFocused: session.focusedIndex = index
                    onDragMovedTo: sceneY => session.dragTo(index, sceneY)
                    onDragFinished: session.drop(index)
                }
            }
        }

        // Where a dragged block will land.
        Rectangle {
            id: dropLine
            objectName: "dropLine"
            x: page.x
            width: page.width
            height: Theme.focusRingWidth
            radius: height / 2
            color: Theme.accent
            visible: session.dropSlot >= 0
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

        // Disabled (not hidden) on task 1, so Skip never shifts (ADHD rule 5).
        IconButton {
            id: previousTask
            objectName: "previousTask"
            anchors.left: parent.left
            anchors.leftMargin: Theme.space2
            anchors.verticalCenter: parent.verticalCenter
            iconName: "chevronLeft"
            tip: qsTr("Previous task")
            shortcutHint: qsTr("Alt+Left")
            enabled: RoomSession.canGoBack
            onClicked: RoomSession.previous()
        }

        Button {
            objectName: "skipTask"
            anchors.left: previousTask.right
            anchors.leftMargin: Theme.space1
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
