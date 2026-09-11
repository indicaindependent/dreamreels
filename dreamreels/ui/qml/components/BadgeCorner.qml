import QtQuick
// Logo + version (top-left) and the dynamic IIM badge (bottom-right). Badge click -> QR/URL panel (and browser if present).
Item {
    id: bc
    anchors.fill: parent
    signal badgeClicked()
    Row { x: ui.safe; y: 22 * ui.s; spacing: 14 * ui.s
        Icon { name: "reel"; px: 44 * ui.s; color: theme.accent; anchors.verticalCenter: parent.verticalCenter }
        Text { text: "DreamReels"; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 40 * ui.s; anchors.verticalCenter: parent.verticalCenter }
        Rectangle { anchors.verticalCenter: parent.verticalCenter; radius: 8 * ui.s; color: theme.surface2; width: vt.implicitWidth + 18 * ui.s; height: vt.implicitHeight + 8 * ui.s
            Text { id: vt; anchors.centerIn: parent; text: "v" + app.version; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 20 * ui.s } }
    }
    Image {
        id: badge; source: app.badgeUrl; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: ui.safe * 0.6
        width: 300 * ui.s; fillMode: Image.PreserveAspectFit; sourceSize.width: 900; smooth: true
        opacity: ma.containsMouse ? 1.0 : 0.85
        MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bc.badgeClicked() }
    }
}
