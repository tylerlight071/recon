// Phase 0 smoke test window: Inter text and one 200 ms ease-out slide.
// Literal colours are fine here: this isn't part of ui/ and never ships.
import QtQuick
import QtQuick.Window

Window {
    id: root
    objectName: "smokeWindow"
    title: "Recon QML smoke test"
    width: 420
    height: 240
    visible: true
    color: "#0b0c0e"

    signal animationFinished()

    function startAnimation() {
        slide.start()
    }

    Text {
        objectName: "label"
        text: "Recon renders Inter at 15 px"
        font.family: "Inter"
        font.pixelSize: 15
        font.weight: Font.Medium
        color: "#ececef"
        anchors.horizontalCenter: parent.horizontalCenter
        y: 48
    }

    Text {
        text: "Regular 400 · Medium 500 · SemiBold 600"
        font.family: "Inter"
        font.pixelSize: 13
        color: "#9a9ba3"
        anchors.horizontalCenter: parent.horizontalCenter
        y: 80
    }

    Rectangle {
        id: bar
        objectName: "bar"
        x: 24
        y: 150
        width: 120
        height: 8
        radius: 4
        color: "#7c74d9"

        NumberAnimation {
            id: slide
            target: bar
            property: "x"
            from: 24
            to: 276
            duration: 200
            easing.type: Easing.OutCubic
            onFinished: root.animationFinished()
        }
    }
}
