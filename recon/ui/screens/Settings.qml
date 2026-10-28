import QtCore
import QtQuick
import QtQuick.Dialogs
import "../components"
import "../theme"

// Settings (task 1.14, first pass): vault folder, Ollama's models (task 2.2),
// accent colour, reduce motion, panel pinning and width, and the focus chime.
// Every change saves on its own (shortly after it settles); "Done" goes back to
// Home. Bridges: AppSettings, Models, Pinning, Focus, Navigation.
Item {
    id: settings

    objectName: "settingsScreen"

    // Fresh news each time Settings opens (a check takes a few seconds at most).
    Component.onCompleted: Models.check()

    component SectionTitle: Text {
        topPadding: Theme.space4
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSizeSmall
        font.weight: Theme.weightMedium
        color: Theme.textTertiary
    }

    component Note: Text {
        width: parent.width
        wrapMode: Text.Wrap
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.textSecondary
    }

    Flickable {
        anchors.fill: parent
        contentHeight: page.implicitHeight + Theme.space12
        clip: true

        Column {
            id: page

            x: Theme.space8
            y: Theme.space8
            width: Math.min(settings.width - Theme.space8 * 2, Theme.contentWidth)
            spacing: Theme.space3

            Text {
                text: qsTr("Settings")
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSizeLarge
                font.weight: Theme.weightSemiBold
                color: Theme.textPrimary
            }

            Note { text: qsTr("Changes save as you make them.") }

            // ---- Vault ---------------------------------------------------------------
            SectionTitle { text: qsTr("Vault") }

            Row {
                width: parent.width
                spacing: Theme.space3

                Column {
                    width: parent.width - changeVault.width - parent.spacing
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Theme.space1

                    Text {
                        objectName: "vaultShown"
                        width: parent.width
                        elide: Text.ElideMiddle
                        text: AppSettings.vaultShown
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSizeBody
                        color: Theme.textPrimary
                    }

                    Note { text: qsTr("Recon writes your notes here once it processes rooms. Open it in Obsidian as a vault.") }
                }

                Button {
                    id: changeVault
                    objectName: "changeVault"
                    anchors.verticalCenter: parent.verticalCenter
                    variant: "secondary"
                    text: qsTr("Change…")
                    onClicked: vaultDialog.open()
                }
            }

            // ---- Models --------------------------------------------------------------
            SectionTitle { text: qsTr("Models") }

            Repeater {
                model: Models.roles

                Row {
                    required property var modelData
                    width: page.width
                    spacing: Theme.space3

                    Text {
                        width: Theme.settingsLabelWidth
                        text: modelData.role
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSizeBody
                        color: Theme.textSecondary
                    }

                    Text {
                        objectName: "model-" + modelData.name
                        width: parent.width - Theme.settingsLabelWidth - parent.spacing
                        elide: Text.ElideRight
                        text: modelData.name
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSizeMono
                        color: Theme.textPrimary
                    }
                }
            }

            Row {
                width: parent.width
                spacing: Theme.space3

                Row {
                    width: parent.width - checkModels.width - parent.spacing
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Theme.space2

                    // Green when ready, amber when something needs doing: never red.
                    Rectangle {
                        objectName: "modelsDot"
                        anchors.verticalCenter: parent.verticalCenter
                        width: Theme.space2
                        height: Theme.space2
                        radius: width / 2
                        color: Models.state === "ready" ? Theme.success
                             : Models.state === "checking" ? Theme.textTertiary
                             : Theme.warning
                    }

                    Text {
                        objectName: "modelsMessage"
                        width: parent.width - Theme.space2 - parent.spacing
                        anchors.verticalCenter: parent.verticalCenter
                        wrapMode: Text.Wrap
                        text: Models.message
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSizeBody
                        color: Theme.textPrimary
                        Accessible.role: Accessible.StaticText
                        Accessible.name: text
                    }
                }

                Button {
                    id: checkModels
                    objectName: "checkModels"
                    anchors.verticalCenter: parent.verticalCenter
                    variant: "secondary"
                    enabled: !Models.checking
                    text: qsTr("Check again")
                    onClicked: Models.check()
                }
            }

            // The exact command for each missing model: Recon never downloads one itself.
            Row {
                objectName: "pullCommands"
                visible: Models.commands !== ""
                width: parent.width
                spacing: Theme.space3

                Rectangle {
                    width: parent.width - copyCommands.width - parent.spacing
                    height: commandText.implicitHeight + Theme.space2 * 2
                    radius: Theme.radiusSmall
                    color: Theme.raised
                    border.width: Theme.hairline
                    border.color: Theme.border

                    Text {
                        id: commandText
                        x: Theme.space3
                        y: Theme.space2
                        width: parent.width - Theme.space3 * 2
                        wrapMode: Text.WrapAnywhere
                        text: Models.commands
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSizeMono
                        color: Theme.textPrimary
                    }
                }

                Button {
                    id: copyCommands
                    objectName: "copyCommands"
                    anchors.verticalCenter: parent.verticalCenter
                    variant: "quiet"
                    text: qsTr("Copy")
                    onClicked: Models.copyCommands()
                }
            }

            Note { text: qsTr("Everything runs on this computer through Ollama. To use other models, change their names in settings.toml.") }

            // ---- Look ----------------------------------------------------------------
            SectionTitle { text: qsTr("Look") }

            Column {
                objectName: "accentChoices"
                width: parent.width

                Repeater {
                    model: AppSettings.accents

                    Choice {
                        required property string modelData
                        objectName: "accent-" + modelData
                        width: parent.width
                        text: modelData.charAt(0).toUpperCase() + modelData.slice(1)
                        swatch: Theme.accentFor(modelData)
                        checked: AppSettings.accent === modelData
                        onToggled: if (checked) AppSettings.accent = modelData
                    }
                }
            }

            Toggle {
                objectName: "reduceMotion"
                width: parent.width
                text: qsTr("Reduce motion")
                checked: AppSettings.reduceMotion
                onToggled: AppSettings.reduceMotion = checked
            }

            Note { text: qsTr("Makes fades, slides and the progress ring instant.") }

            // ---- Panel ---------------------------------------------------------------
            SectionTitle { text: qsTr("Panel") }

            Toggle {
                objectName: "pinPanel"
                width: parent.width
                text: qsTr("Pin the panel to the right edge")
                checked: AppSettings.pinning === "on"
                onToggled: checked ? Pinning.pin() : Pinning.unpin()
            }

            Note { text: qsTr("Adds a KDE window rule for Recon's panel only. Turning it off removes the rule and leaves your other rules alone.") }

            Item {
                width: parent.width
                height: Theme.space2
            }

            Row {
                width: parent.width
                spacing: Theme.space3

                Text {
                    id: widthLabel
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("Panel width")
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeBody
                    color: Theme.textPrimary
                }

                Slider {
                    id: widthSlider
                    objectName: "panelWidth"
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - widthLabel.width - widthValue.width - parent.spacing * 2
                    from: Theme.panelWidthMin
                    to: Theme.panelWidthMax
                    stepSize: Theme.space1
                    value: AppSettings.panelWidth
                    accessibleName: qsTr("Panel width")
                    valueText: qsTr("%1 pixels").arg(Math.round(value))
                    onMoved: AppSettings.panelWidth = value
                }

                Text {
                    id: widthValue
                    objectName: "panelWidthValue"
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("%1 px").arg(AppSettings.panelWidth)
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeBody
                    font.features: { "tnum": 1 }
                    color: Theme.textSecondary
                }
            }

            // ---- Focus ---------------------------------------------------------------
            SectionTitle { text: qsTr("Focus") }

            Row {
                width: parent.width
                spacing: Theme.space3

                Toggle {
                    objectName: "chime"
                    width: parent.width - playChime.width - parent.spacing
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("Chime when a focus block ends")
                    checked: AppSettings.chime
                    onToggled: AppSettings.chime = checked
                }

                Button {
                    id: playChime
                    objectName: "playChime"
                    anchors.verticalCenter: parent.verticalCenter
                    variant: "quiet"
                    text: qsTr("Play")
                    onClicked: Focus.previewChime()
                }
            }

            Note { text: qsTr("A soft two-note chime. Off unless you turn it on.") }

            Item {
                width: parent.width
                height: Theme.space4
            }

            Button {
                objectName: "settingsDone"
                variant: "primary"
                text: qsTr("Done")
                onClicked: Navigation.open("home")
            }
        }
    }

    FolderDialog {
        id: vaultDialog
        objectName: "vaultDialog"
        title: qsTr("Choose the folder for your vault")
        currentFolder: AppSettings.vaultUrl
        onAccepted: AppSettings.chooseVault(selectedFolder.toString())
    }
}
