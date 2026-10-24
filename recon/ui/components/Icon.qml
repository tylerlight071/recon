import QtQuick
import QtQuick.Shapes
import "../theme"

// Recon's own line icons, drawn on a 24x24 grid with round strokes.
// Unknown names draw nothing. Decorative: the control using it carries the
// accessible name.
Item {
    id: icon

    property string name: ""
    property color color: Theme.textSecondary

    readonly property var paths: ({
        "plus": "M12 5 V19 M5 12 H19",
        "close": "M6 6 L18 18 M18 6 L6 18",
        "check": "M5 12.5 L10 17.5 L19 7",
        "chevron": "M9 6 L15 12 L9 18",
        "undo": "M9 14 L4 9 L9 4 M4 9 H14 A6 6 0 0 1 14 21 H11",
        "grip": "M9 6 h0.01 M15 6 h0.01 M9 12 h0.01 M15 12 h0.01 M9 18 h0.01 M15 18 h0.01",
        "mic": "M12 3 A3 3 0 0 1 15 6 V12 A3 3 0 0 1 9 12 V6 A3 3 0 0 1 12 3 Z M5 11 A7 7 0 0 0 19 11 M12 18 V21",
        "clock": "M12 3 A9 9 0 1 1 11.99 3 Z M12 7 V12 L15 14"
    })

    implicitWidth: Theme.iconSize
    implicitHeight: Theme.iconSize
    Accessible.ignored: true

    Shape {
        width: Theme.iconViewBox
        height: Theme.iconViewBox
        scale: icon.width / Theme.iconViewBox
        transformOrigin: Item.TopLeft
        preferredRendererType: Shape.CurveRenderer
        visible: icon.paths[icon.name] !== undefined

        ShapePath {
            strokeColor: icon.color
            strokeWidth: Theme.iconStroke
            fillColor: Theme.clear
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin

            PathSvg { path: icon.paths[icon.name] || "" }
        }
    }
}
