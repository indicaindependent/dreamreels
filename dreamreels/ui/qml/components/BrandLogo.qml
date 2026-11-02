import QtQuick
import "Icons.js" as Icons
// v2.1.0 DreamReels logo: reel mark + two-tone wordmark + version chip. Used by the player and the setup wizard.
Row {
    id: bl
    property real s: 1
    property bool showVersion: true
    spacing: 14 * s
    Image {
        width: 50 * bl.s; height: 50 * bl.s; anchors.verticalCenter: parent.verticalCenter
        sourceSize: Qt.size(160, 160); smooth: true; antialiasing: true; fillMode: Image.PreserveAspectFit
        source: Icons.brandMark(theme.accent.toString(), theme.accent2.toString(), theme.text.toString())
    }
    Row { anchors.verticalCenter: parent.verticalCenter; spacing: 0
        Text { text: "Dream"; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Medium; font.pixelSize: 40 * bl.s; font.letterSpacing: 0.5 * bl.s }
        Text { text: "Reels"; color: theme.accent; font.family: theme.fontDisplay; font.weight: Font.Black; font.pixelSize: 40 * bl.s; font.letterSpacing: 0.5 * bl.s }
    }
    Rectangle { visible: bl.showVersion; anchors.verticalCenter: parent.verticalCenter; radius: height / 2; color: theme.surface2
        border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.10)
        width: vt.implicitWidth + 22 * bl.s; height: vt.implicitHeight + 10 * bl.s
        Text { id: vt; anchors.centerIn: parent; text: "v" + app.version; color: theme.muted; font.family: theme.fontBody; font.weight: Font.DemiBold; font.pixelSize: 18 * bl.s } }
}
