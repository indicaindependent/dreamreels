import QtQuick
Item {
    id: c
    property var item: ({})
    property bool active: false
    signal clicked()
    width: 220 * ui.s; height: 330 * ui.s
    scale: active ? theme.focusScale : 1.0
    z: active ? 2 : 1
    Behavior on scale { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
    Rectangle {
        id: bg; anchors.fill: parent; radius: theme.radius; color: theme.surface2; clip: true
        Image {
            id: img; anchors.fill: parent; source: item.poster || ""; fillMode: Image.PreserveAspectCrop; asynchronous: true; cache: true
            sourceSize: Qt.size(400, 600); visible: status === Image.Ready
        }
        // text tile fallback when no art
        Column {
            anchors.centerIn: parent; width: parent.width - 28 * ui.s; spacing: 8 * ui.s; visible: img.status !== Image.Ready
            Icon { name: item.kind === "track" ? "music" : (item.kind === "episode" ? "tv" : "film"); px: 44 * ui.s; color: theme.muted; anchors.horizontalCenter: parent.horizontalCenter }
            Text { width: parent.width; text: item.title || ""; color: theme.text; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; maximumLineCount: 4; elide: Text.ElideRight; font.family: theme.fontDisplay; font.weight: Font.DemiBold; font.pixelSize: 24 * ui.s }
            Text { width: parent.width; text: item.year ? item.year : ""; color: theme.muted; horizontalAlignment: Text.AlignHCenter; font.family: theme.fontBody; font.pixelSize: 20 * ui.s }
        }
        // progress bar
        Rectangle { visible: (item.progress || 0) > 0; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 8 * ui.s; color: Qt.rgba(0,0,0,0.55)
            Rectangle { width: parent.width * (item.progress || 0); height: parent.height; color: theme.accent } }
        // verified tick / checking dot
        Rectangle { anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 10 * ui.s; width: 34 * ui.s; height: width; radius: width / 2
            color: item.verified ? theme.ok : Qt.rgba(0,0,0,0.55); border.width: 1; border.color: Qt.rgba(1,1,1,0.25)
            Icon { anchors.centerIn: parent; name: item.verified ? "check" : "clock"; px: 20 * ui.s; color: "#ffffff" } }
    }
    FocusFrame { active: c.active; radius: theme.radius }
    MouseArea { anchors.fill: parent; onClicked: c.clicked(); cursorShape: Qt.PointingHandCursor }
}
