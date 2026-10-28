import QtQuick
import "../theme"

// The Table block's grid preview: the parsed cells under the text, so the user
// sees how the note will read the table. Shows a capped slice; the note keeps all.
Rectangle {
    id: preview

    property var rows: []
    property int columns: 0
    property int hiddenRows: 0
    property int hiddenColumns: 0

    function count(n, one, many) {
        return n <= 0 ? "" : n + " " + (n === 1 ? one : many)
    }

    implicitHeight: content.implicitHeight + Theme.space2 * 2
    color: Theme.surface
    radius: Theme.radiusSmall
    border.color: Theme.border
    border.width: Theme.hairline

    Accessible.role: Accessible.Table
    Accessible.name: qsTr("Table preview, %1 rows by %2 columns").arg(rows.length + hiddenRows).arg(columns + hiddenColumns)

    Column {
        id: content
        x: Theme.space3
        y: Theme.space2
        width: parent.width - Theme.space3 * 2
        spacing: Theme.space1

        Grid {
            objectName: "grid"
            width: parent.width
            columns: Math.max(1, preview.columns)
            columnSpacing: Theme.space3
            rowSpacing: Theme.space1

            Repeater {
                model: preview.rows.reduce((cells, row) => cells.concat(row), [])

                Text {
                    required property string modelData
                    required property int index
                    width: (content.width - Theme.space3 * (preview.columns - 1)) / Math.max(1, preview.columns)
                    text: modelData
                    elide: Text.ElideRight
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSizeSmall
                    // The first row is often a header; give it a little weight, not a style.
                    font.weight: index < preview.columns ? Theme.weightMedium : Theme.weightRegular
                    color: index < preview.columns ? Theme.textPrimary : Theme.textSecondary
                    Accessible.ignored: true
                }
            }
        }

        Text {
            objectName: "more"
            visible: preview.hiddenRows > 0 || preview.hiddenColumns > 0
            text: qsTr("Also in the note: %1").arg([
                preview.count(preview.hiddenRows, qsTr("more row"), qsTr("more rows")),
                preview.count(preview.hiddenColumns, qsTr("more column"), qsTr("more columns"))
            ].filter(s => s !== "").join(", "))
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.textTertiary
        }
    }
}
