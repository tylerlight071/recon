import QtQuick
import "../components"
import "../theme"

// Review (task 2.6): what processing prepared, before anything reaches the vault.
// Sections, each collapsible with a count: the room note as Obsidian will show it,
// new notes, additions to existing notes (only what changes), and notes left alone.
// A sticky footer keeps Apply (the one accent button) and Discard in reach;
// Discard asks once. Bridge: ReviewModel.
Item {
    id: review

    objectName: "reviewScreen"

    component Markdown: Text {
        width: parent.width - Theme.space6
        wrapMode: Text.Wrap
        textFormat: Text.MarkdownText
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSizeBody
        color: Theme.textPrimary
        linkColor: Theme.accent
    }

    component Note: Text {
        width: parent.width
        wrapMode: Text.Wrap
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.textSecondary
    }

    Flickable {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: footer.top
        contentHeight: page.implicitHeight + Theme.space8
        clip: true

        Column {
            id: page

            x: Theme.space8
            y: Theme.space8
            width: Math.min(review.width - Theme.space8 * 2, Theme.contentWidth)
            spacing: Theme.space4

            Column {
                width: parent.width
                spacing: Theme.space1

                Text {
                    objectName: "reviewTitle"
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: qsTr("Review: %1").arg(ReviewModel.roomName)
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeLarge
                    font.weight: Theme.weightSemiBold
                    color: Theme.textPrimary
                }

                Note {
                    objectName: "reviewIntro"
                    text: ReviewModel.writes === 1
                          ? qsTr("Nothing is in your vault yet. Apply writes 1 note, Discard sends the room back to the panel.")
                          : qsTr("Nothing is in your vault yet. Apply writes %1 notes, Discard sends the room back to the panel.").arg(ReviewModel.writes)
                }
            }

            // What went wrong, and for a conflict, the way on.
            Column {
                objectName: "reviewProblem"
                width: parent.width
                spacing: Theme.space2
                visible: ReviewModel.problem !== ""

                Text {
                    objectName: "reviewProblemText"
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: ReviewModel.problem
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeBody
                    color: Theme.warning
                    Accessible.role: Accessible.AlertMessage
                    Accessible.name: text
                }

                Button {
                    objectName: "recheck"
                    visible: ReviewModel.conflict
                    variant: "secondary"
                    text: qsTr("Re-check")
                    onClicked: ReviewModel.recheck()
                }
            }

            Disclosure {
                objectName: "roomNoteSection"
                width: parent.width
                large: true
                title: qsTr("Room note")
                expanded: true
                visible: ReviewModel.roomNote !== ""

                Markdown {
                    objectName: "roomNoteText"
                    text: ReviewModel.roomNote
                }
            }

            Disclosure {
                objectName: "newNotesSection"
                width: parent.width
                large: true
                title: qsTr("New notes")
                detail: ReviewModel.newNotes.length
                expanded: true
                visible: ReviewModel.newNotes.length > 0

                Repeater {
                    model: ReviewModel.newNotes

                    Disclosure {
                        required property var modelData
                        required property int index
                        objectName: "newNote" + index
                        width: parent.width - Theme.space6
                        title: modelData.title
                        detail: qsTr("%1 · New").arg(modelData.kind)

                        Markdown { text: modelData.markdown }
                    }
                }
            }

            Disclosure {
                objectName: "additionsSection"
                width: parent.width
                large: true
                title: qsTr("Additions")
                detail: ReviewModel.additions.length
                expanded: true
                visible: ReviewModel.additions.length > 0

                Note { text: qsTr("Only the parts Recon adds or updates. Everything else in these notes stays as it is.") }

                Repeater {
                    model: ReviewModel.additions

                    Disclosure {
                        required property var modelData
                        required property int index
                        objectName: "addition" + index
                        width: parent.width - Theme.space6
                        title: modelData.title
                        detail: modelData.kind

                        Markdown { text: modelData.markdown }
                    }
                }
            }

            Disclosure {
                objectName: "skippedSection"
                width: parent.width
                large: true
                title: qsTr("Left alone")
                detail: ReviewModel.skipped.length
                visible: ReviewModel.skipped.length > 0

                Note { text: qsTr("These notes have Recon section markers that were changed or removed, so Recon won't edit them. Your text in them is safe.") }

                Repeater {
                    model: ReviewModel.skipped

                    Text {
                        required property string modelData
                        text: modelData
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSizeBody
                        color: Theme.textPrimary
                    }
                }
            }
        }
    }

    // Sticky footer: Apply and Discard stay in reach however far the page scrolls.
    Rectangle {
        id: footer
        objectName: "reviewFooter"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Theme.controlHeight + Theme.space4 * 2
        color: Theme.surface

        Rectangle {
            width: parent.width
            height: Theme.hairline
            color: Theme.border
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: Theme.space8
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.space3

            Button {
                objectName: "discardReview"
                variant: "secondary"
                enabled: !ReviewModel.busy
                text: qsTr("Discard")
                onClicked: discardDialog.open()
            }

            Button {
                objectName: "applyReview"
                variant: "primary"
                enabled: !ReviewModel.busy && !ReviewModel.conflict
                text: ReviewModel.busy ? qsTr("Working…") : qsTr("Apply")
                onClicked: ReviewModel.apply()
            }
        }
    }

    Dialog {
        id: discardDialog
        objectName: "discardDialog"
        title: qsTr("Discard these notes?")
        body: qsTr("Nothing has been written to your vault. The room goes back to the panel exactly as you left it, so you can add more and finish again.")
        primaryText: qsTr("Discard")
        secondaryText: qsTr("Keep reviewing")
        onAccepted: ReviewModel.discard()
    }
}
