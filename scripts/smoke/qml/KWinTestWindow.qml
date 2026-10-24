// Phase 0 KWin rule test window; shows its own title and size.
// Literal colours are fine here: this isn't part of ui/ and never ships.
import QtQuick
import QtQuick.Window

Window {
    id: win
    width: 600
    height: 400
    visible: true
    color: "#111215"

    Text {
        anchors.centerIn: parent
        horizontalAlignment: Text.AlignHCenter
        text: win.title + "\n" + win.width + " × " + win.height
        font.pixelSize: 18
        color: "#ececef"
    }
}
