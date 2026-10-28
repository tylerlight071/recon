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
        "chevronLeft": "M15 6 L9 12 L15 18",
        "undo": "M9 14 L4 9 L9 4 M4 9 H14 A6 6 0 0 1 14 21 H11",
        "grip": "M9 6 h0.01 M15 6 h0.01 M9 12 h0.01 M15 12 h0.01 M9 18 h0.01 M15 18 h0.01",
        "mic": "M12 3 A3 3 0 0 1 15 6 V12 A3 3 0 0 1 9 12 V6 A3 3 0 0 1 12 3 Z M5 11 A7 7 0 0 0 19 11 M12 18 V21",
        "clock": "M12 3 A9 9 0 1 1 11.99 3 Z M12 7 V12 L15 14",
        "library": "M5 4 V20 M9 4 V20 M13.5 4.5 L18.5 19.5 M4 20 H20",
        "home": "M4 11 L12 4 L20 11 M6 9.5 V20 H18 V9.5 M10 20 V14 H14 V20",
        "sliders": "M4 7 H13 M17 7 H20 M15 5 V9 M4 17 H7 M11 17 H20 M9 15 V19",
        "bulb": "M9 18 H15 M10 21 H14 M8.5 14.5 A6 6 0 1 1 15.5 14.5 V16 H8.5 Z",
        "terminal": "M5 7 L10 12 L5 17 M12 17 H19",
        "table": "M4 5 H20 V19 H4 Z M4 10 H20 M4 14.5 H20 M10 5 V19",
        "image": "M4 5 H20 V19 H4 Z M4 16 L9 11 L13 15 L16 12 L20 16 M15.5 8.5 h0.01",
        "question": "M12 3 A9 9 0 1 1 11.99 3 Z M9.5 9.5 A2.5 2.5 0 1 1 13 11.8 C12.4 12.2 12 12.7 12 13.5 M12 17 h0.01",
        "squiggle": "M3 12 C5 8 7 8 9 12 C11 16 13 16 15 12 C17 8 19 8 21 12",
        "bubble": "M5 5 H19 V15 H11 L7 19 V15 H5 Z M9 10 h0.01 M12 10 h0.01 M15 10 h0.01"
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
