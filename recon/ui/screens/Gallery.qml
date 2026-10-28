import QtQuick
import QtQuick.Window
import "../components"
import "../theme"

// Developer-only component gallery: `uv run python -m recon --gallery`.
// It shows every variant side by side, so it breaks the one-accent-button
// rule on purpose; it's never shown to the user as part of the app.
Window {
    id: gallery

    width: Theme.galleryWidth
    height: Theme.galleryHeight
    visible: true
    title: "Recon component gallery"
    color: Theme.bg

    component Heading: Text {
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Theme.weightSemiBold
        color: Theme.textPrimary
        topPadding: Theme.space4
    }

    component Note: Text {
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.textTertiary
    }

    Flickable {
        anchors.fill: parent
        contentHeight: page.implicitHeight + Theme.space12
        clip: true

        Column {
            id: page
            x: Theme.space8
            y: Theme.space6
            width: gallery.width - Theme.space8 * 2
            spacing: Theme.space3

            Heading { text: "Buttons"; topPadding: 0 }
            Row {
                spacing: Theme.space3
                Button { objectName: "galleryPrimary"; variant: "primary"; text: "Next task" }
                Button { variant: "secondary"; text: "Export as Markdown" }
                Button { variant: "quiet"; text: "Skip this task" }
                Button { variant: "primary"; text: "Disabled"; enabled: false }
            }

            Heading { text: "Icon buttons and tooltips" }
            Row {
                spacing: Theme.space2
                IconButton { iconName: "plus"; tip: "Add block"; shortcutHint: "Ctrl+1" }
                IconButton { iconName: "mic"; tip: "Hold to talk"; shortcutHint: "F9" }
                IconButton { iconName: "undo"; tip: "Undo"; shortcutHint: "Ctrl+Z" }
                IconButton { iconName: "close"; tip: "Close" }
                IconButton { iconName: "check"; tip: "Done" }
                IconButton { iconName: "chevron"; tip: "Open" }
            }
            Item {
                width: parent.width
                height: Theme.controlHeight + Theme.space6
                Item {
                    y: Theme.space6
                    width: Theme.controlHeight
                    height: Theme.controlHeight
                    Tooltip { visible: true; text: "Command"; shortcut: "Ctrl+2"; delay: 0 }
                }
            }

            Heading { text: "Card" }
            Card {
                title: "Where was I?"
                width: Theme.toastWidth
                Column {
                    spacing: Theme.space1
                    Text { text: "DNS in Detail"; color: Theme.textPrimary; font.family: Theme.fontUi; font.pixelSize: Theme.fontSizeBody; font.weight: Theme.weightMedium }
                    Text { text: "Task 4 of 7, 2 days ago"; color: Theme.textSecondary; font.family: Theme.fontUi; font.pixelSize: Theme.fontSizeSmall }
                    Text { text: "Last note: 'TXT records hold text'"; color: Theme.textTertiary; font.family: Theme.fontUi; font.pixelSize: Theme.fontSizeSmall }
                }
            }

            Heading { text: "Text areas" }
            Row {
                spacing: Theme.space3
                TextArea { width: Theme.toastWidth; hint: "What's the one thing this task is teaching? Your words, one line is fine." }
                TextArea { width: Theme.toastWidth; mono: true; hint: "Paste or type the command. Add what it does after a #."; text: "nmap -sV 10.10.0.5  # versions of open services" }
            }

            Heading { text: "Text fields" }
            Row {
                spacing: Theme.space3
                TextField { width: Theme.toastWidth; hint: "e.g. DNS in Detail"; accessibleName: "Room name" }
                TextField { width: Theme.numberFieldWidth; hint: "e.g. 7"; accessibleName: "Number of tasks" }
            }

            Heading { text: "Choices and list rows" }
            Column {
                width: Theme.toastWidth
                Choice { width: parent.width; text: "New room"; detail: "Take notes as you go, one task at a time."; checked: true }
                Choice { width: parent.width; text: "From memory"; detail: "For a room you've already done. Coming soon."; enabled: false }
                ListRow { width: parent.width; title: "Linux Basics"; detail: "Pre Security · Linux · Done"; trailing: "9 days ago"; interactive: false }
                ListRow { width: parent.width; title: "DNS in Detail"; detail: "Task 4 of 7"; trailing: "2 days ago" }
            }

            Heading { text: "Blocks" }
            Note { text: "Each type has its own muted edge colour. Reordering arrives in task 1.10." }
            Repeater {
                model: [
                    ["key_idea", "Key idea"], ["command", "Command"], ["table", "Table"],
                    ["screenshot", "Screenshot"], ["question", "Question"], ["confused", "Confused by"],
                    ["room_question", "Room question"], ["voice", "Voice"]
                ]
                Block {
                    required property var modelData
                    width: Theme.panelWidthDefault
                    type: modelData[0]
                    label: modelData[1]
                    TextArea { width: parent.width; hint: "Type here"; accessibleName: modelData[1] }
                }
            }

            Heading { text: "Progress ring, timer chip, sidebar" }
            Row {
                spacing: Theme.space4
                ProgressRing { id: ring; value: 3 / 7; valueText: "Task 3 of 7"; anchors.verticalCenter: parent.verticalCenter }
                Button { text: "Back"; variant: "quiet"; onClicked: ring.value = Math.max(0, ring.value - 1 / 7) }
                Button { text: "Forward"; variant: "quiet"; onClicked: ring.value = Math.min(1, ring.value + 1 / 7) }
                TimerChip {
                    id: chip
                    anchors.verticalCenter: parent.verticalCenter
                    seconds: 754
                    running: true
                    Timer { interval: 1000; repeat: true; running: chip.running; onTriggered: chip.seconds += 1 }
                    onClicked: chip.running = !chip.running
                }
            }
            Column {
                width: Theme.toastWidth / 1.5
                spacing: Theme.space1
                SidebarItem { width: parent.width; text: "Home"; iconName: "chevron"; selected: true }
                SidebarItem { width: parent.width; text: "Revise"; iconName: "check" }
                SidebarItem { width: parent.width; text: "Library"; iconName: "clock" }
            }

            Heading { text: "Toast and dialog" }
            Row {
                spacing: Theme.space3
                Button { text: "Delete a block"; onClicked: toast.show("Block deleted.", "Undo") }
                Button { text: "Flag skipped"; onClicked: toast.show("Flag skipped. It won't be saved.", "Not a flag, keep it") }
                Button { text: "Discard review"; onClicked: dialog.open() }
            }
            Note { id: result; text: "" }
        }
    }

    Toast {
        id: toast
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.space6
        onAction: result.text = "Undo pressed"
    }

    Dialog {
        id: dialog
        title: "Discard these changes?"
        body: "Your notes stay in the room. Only this review is thrown away."
        primaryText: "Discard"
        secondaryText: "Keep reviewing"
        onAccepted: result.text = "Discarded"
        onRejected: result.text = "Kept"
    }
}
