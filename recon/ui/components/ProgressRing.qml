import QtQuick
import QtQuick.Shapes
import "../theme"

// Room progress as a ring that fills smoothly. value is 0..1 (clamped).
Item {
    id: ring

    property real value: 0
    property string valueText: ""
    readonly property real clampedValue: Math.max(0, Math.min(1, value))
    property real shownValue: clampedValue

    implicitWidth: Theme.ringSize
    implicitHeight: Theme.ringSize

    Accessible.role: Accessible.ProgressBar
    Accessible.name: valueText === "" ? "Progress" : "Progress, " + valueText

    Behavior on shownValue { NumberAnimation { duration: Theme.durationSlow; easing.type: Theme.easing } }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: Theme.border
            strokeWidth: Theme.ringStroke
            fillColor: Theme.clear

            PathAngleArc {
                centerX: ring.width / 2
                centerY: ring.height / 2
                radiusX: (ring.width - Theme.ringStroke) / 2
                radiusY: (ring.height - Theme.ringStroke) / 2
                startAngle: 0
                sweepAngle: 360
            }
        }

        ShapePath {
            strokeColor: Theme.accent
            strokeWidth: Theme.ringStroke
            fillColor: Theme.clear
            capStyle: ShapePath.RoundCap

            PathAngleArc {
                centerX: ring.width / 2
                centerY: ring.height / 2
                radiusX: (ring.width - Theme.ringStroke) / 2
                radiusY: (ring.height - Theme.ringStroke) / 2
                startAngle: -90
                sweepAngle: 360 * ring.shownValue
            }
        }
    }
}
