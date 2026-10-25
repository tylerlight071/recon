import QtQuick
import "../components"
import "../theme"

// One block in the room session, with the editor its type needs (task 1.10):
// - Key idea, Question, Confused by: plain text with the type's hint.
// - Command: monospace; `# what it does` shown dimmer.
// - Table: paste or type rows; a grid preview of how the note will read them.
// - Room question: the question, then the answer behind "Show answer".
// Drag the grip (or Alt+Up / Alt+Down) to reorder. Bridges: RoomSession, Editors.
Block {
    id: block

    required property int index
    required property int blockId
    required property string blockType
    required property string text
    required property string typeLabel
    required property string hint
    required property string answer

    // Set by the session while this block is being dragged.
    property bool dragging: false
    readonly property alias editor: editor
    readonly property bool isRoomQuestion: blockType === "room_question"

    signal dragMovedTo(real sceneY)
    signal dragFinished()
    signal focused()

    objectName: "block-" + blockId
    type: blockType
    label: typeLabel
    opacity: dragging ? Theme.draggingOpacity : 1

    // Every keystroke: flags out, autosave queued (hard rules 2 and 7). Returns
    // the text to show, keeping the cursor where it was.
    function apply(area, shown) {
        if (shown === area.text)
            return
        const at = area.cursorPosition
        area.text = shown
        area.cursorPosition = Math.min(at, area.length)
    }

    HoverHandler {
        parent: block.handle
        cursorShape: Qt.OpenHandCursor
    }

    DragHandler {
        id: drag
        parent: block.handle
        target: null
        cursorShape: Qt.ClosedHandCursor
        onActiveChanged: if (!active) block.dragFinished()
        onCentroidChanged: if (active) block.dragMovedTo(centroid.scenePosition.y)
    }

    TextArea {
        id: editor
        objectName: "editor"
        width: parent.width
        hint: block.hint
        accessibleName: block.isRoomQuestion ? qsTr("Room question") : block.typeLabel
        mono: block.blockType === "command"

        property bool ready: false

        Component.onCompleted: {
            text = block.text
            if (block.blockType === "command")
                Editors.dimComments(textDocument, Theme.textTertiary)
            ready = true
        }

        onTextChanged: if (ready) block.apply(editor, RoomSession.edit(block.blockId, text))
        onActiveFocusChanged: if (activeFocus) block.focused()
    }

    // ---- Table: grid preview ---------------------------------------------------
    TablePreview {
        objectName: "tablePreview"
        readonly property var parsed: block.blockType === "table" ? Editors.tablePreview(editor.text) : null

        width: parent.width
        visible: parsed !== null && parsed.grid
        rows: parsed ? parsed.rows : []
        columns: parsed ? parsed.columns : 0
        hiddenRows: parsed ? parsed.hiddenRows : 0
        hiddenColumns: parsed ? parsed.hiddenColumns : 0
    }

    // ---- Room question: the answer, kept out of sight once written -------------
    Column {
        objectName: "answerArea"
        width: parent.width
        spacing: Theme.space2
        visible: block.isRoomQuestion

        // Shown while empty (so it can be written), hidden on return to the task.
        property bool revealed: block.answer === ""

        Button {
            objectName: "answerToggle"
            variant: "quiet"
            visible: answerEditor.length > 0
            text: parent.revealed ? qsTr("Hide answer") : qsTr("Show answer")
            onClicked: {
                parent.revealed = !parent.revealed
                if (parent.revealed)
                    answerEditor.forceActiveFocus()
            }
        }

        TextArea {
            id: answerEditor
            objectName: "answerEditor"
            width: parent.width
            visible: parent.revealed
            hint: qsTr("Your answer. Skip flags.")
            accessibleName: qsTr("Answer")

            property bool ready: false

            Component.onCompleted: {
                text = block.answer
                ready = true
            }

            onTextChanged: if (ready) block.apply(answerEditor, RoomSession.editAnswer(block.blockId, text))
            onActiveFocusChanged: if (activeFocus) block.focused()
        }
    }

    Connections {
        target: RoomSession
        function onFocusBlock(id) {
            if (id === block.blockId)
                editor.forceActiveFocus()
        }
        function onReplaceText(id, field, value) {
            if (id !== block.blockId)
                return
            const area = field === "answer" ? answerEditor : editor
            if (area.text !== value)
                area.text = value
        }
    }
}
