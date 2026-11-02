import QtQuick
import "Icons.js" as Icons
// Logo + version (top-left) and the small IIM credit pill (bottom-right). v2.1.0 (Nov 1 2026): the old 300 px SVG badge
// was too big and got clipped; this pill is native QML text, sized to its own contents, so it can never be cut off.
// Clicking the pill still opens the QR / project-link panel (kiosks have no browser).
Item {
    id: bc
    anchors.fill: parent
    signal badgeClicked()
    BrandLogo { x: ui.safe; y: 22 * ui.s; s: ui.s }
    Rectangle {
        id: pill
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.rightMargin: ui.safe * 0.5; anchors.bottomMargin: 18 * ui.s
        height: 40 * ui.s; width: pr.implicitWidth + 22 * ui.s; radius: height / 2
        color: theme.surface; opacity: ma.containsMouse ? 0.98 : 0.80
        border.width: 1; border.color: ma.containsMouse ? theme.accent : Qt.rgba(1, 1, 1, 0.10)
        Behavior on opacity { NumberAnimation { duration: 150 } }
        Row { id: pr; anchors.centerIn: parent; spacing: 9 * ui.s
            Image { width: 26 * ui.s; height: 26 * ui.s; anchors.verticalCenter: parent.verticalCenter; sourceSize: Qt.size(96, 96); smooth: true; antialiasing: true
                source: Icons.iimMark(theme.accent.toString(), theme.accent2.toString()) }
            Text { anchors.verticalCenter: parent.verticalCenter; text: app.badgeText; color: theme.muted; font.family: theme.fontBody; font.weight: Font.DemiBold; font.pixelSize: 16 * ui.s }
        }
        MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bc.badgeClicked() }
    }
}
