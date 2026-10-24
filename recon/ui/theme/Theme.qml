pragma Singleton
import QtQuick

// Recon's design tokens (CLAUDE.md, Design system). Every colour, size, font
// and duration used in QML comes from here; screens and components never use
// literals (checked by tests/ui/test_no_literals.py). Text contrast against
// every surface is checked by tests/ui/test_theme_contrast.py.
QtObject {
    id: theme

    // ---- Surfaces ---------------------------------------------------------
    readonly property color bg: "#0b0c0e"
    readonly property color surface: "#111215"
    readonly property color raised: "#16181c"
    readonly property color overlay: "#1c1e23"
    readonly property color border: "#23252a"

    // ---- Text -------------------------------------------------------------
    readonly property color textPrimary: "#ececef"
    readonly property color textSecondary: "#9a9ba3"
    // Hints and quiet labels. Don't go darker: 4.6:1 on overlay is the floor.
    readonly property color textTertiary: "#84868f"
    // Text on accent-filled buttons; white fails contrast on these accents.
    // CLAUDE.md calls this `onAccent`, but QML reads `on<Name>` as a signal
    // handler (for `accent`), so the token is `textOnAccent`.
    readonly property color textOnAccent: "#0b0c0e"

    // ---- Status (never red for anything Tyler did) ------------------------
    readonly property color success: "#5fb47a"
    readonly property color warning: "#d9a441"

    // ---- Accent (one per screen: primary button, focus, progress) --------
    // Chosen in Settings: "violet" (default), "cyan" or "green".
    property string accentName: "violet"

    readonly property color accentViolet: "#7c74d9"
    readonly property color accentVioletHover: "#8d86e3"
    readonly property color accentCyan: "#4fb3c9"
    // Cyan and green hovers are a 13% white mix, matching violet's given hover.
    readonly property color accentCyanHover: "#66bdd0"
    readonly property color accentGreen: "#5fb47a"
    readonly property color accentGreenHover: "#74be8b"

    readonly property color accent: accentName === "cyan" ? accentCyan
                                  : accentName === "green" ? accentGreen
                                  : accentViolet
    readonly property color accentHover: accentName === "cyan" ? accentCyanHover
                                       : accentName === "green" ? accentGreenHover
                                       : accentVioletHover
    readonly property color focusRing: accent

    // ---- Block edges (thin left edge per block type, muted) --------------
    readonly property real blockEdgeOpacity: 0.7
    readonly property color blockKeyIdea: accent
    readonly property color blockCommand: "#4fb3c9"
    readonly property color blockTable: "#8a8fa3"
    readonly property color blockScreenshot: "#b37fd1"
    readonly property color blockQuestion: "#d9a441"
    readonly property color blockConfused: "#d98a5f"
    readonly property color blockRoomQuestion: "#5fb47a"
    readonly property color blockVoice: "#7c9fd9"

    function blockEdge(type) {
        switch (type) {
        case "key_idea": return blockKeyIdea
        case "command": return blockCommand
        case "table": return blockTable
        case "screenshot": return blockScreenshot
        case "question": return blockQuestion
        case "confused": return blockConfused
        case "room_question": return blockRoomQuestion
        case "voice": return blockVoice
        default: return border
        }
    }

    // ---- Type -------------------------------------------------------------
    readonly property string fontUi: "Inter"
    readonly property string fontMono: "JetBrains Mono"
    readonly property int fontSizeSmall: 13
    readonly property int fontSizeBody: 14
    readonly property int fontSizeLarge: 15
    readonly property int fontSizeMono: 13
    readonly property int weightRegular: Font.Normal      // 400
    readonly property int weightMedium: Font.Medium       // 500
    readonly property int weightSemiBold: Font.DemiBold   // 600

    // ---- Spacing (4 px grid) ---------------------------------------------
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space5: 20
    readonly property int space6: 24
    readonly property int space8: 32
    readonly property int space12: 48

    // ---- Shape ------------------------------------------------------------
    readonly property int hairline: 1
    readonly property int focusRingWidth: 2
    readonly property int radiusSmall: 6
    readonly property int radiusCard: 8
    readonly property int radiusDialog: 12

    // ---- Panel ------------------------------------------------------------
    readonly property int panelWidthDefault: 420
    readonly property int panelWidthMin: 360
    readonly property int panelWidthMax: 520

    // ---- Motion -----------------------------------------------------------
    // Settings > Reduce motion makes every duration 0.
    property bool reduceMotion: false
    readonly property int durationFast: reduceMotion ? 0 : 150
    readonly property int durationBase: reduceMotion ? 0 : 200
    readonly property int easing: Easing.OutCubic

    // ---- Fonts (bundled, OFL; loaded once with the theme) ------------------
    readonly property list<FontLoader> fonts: [
        FontLoader { source: "fonts/Inter-Regular.ttf" },
        FontLoader { source: "fonts/Inter-Medium.ttf" },
        FontLoader { source: "fonts/Inter-SemiBold.ttf" },
        FontLoader { source: "fonts/JetBrainsMono-Regular.ttf" }
    ]
    readonly property bool fontsReady: fonts.every(loader => loader.status === FontLoader.Ready)
}
