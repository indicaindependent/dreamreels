import QtQuick
Item {
    id: c
    property string title: ""
    property string blurb: ""
    property string icon: "film"
    property bool on: false
    property bool active: false
    signal clicked()
    width: 300 * ui.s; height: 260 * ui.s
    scale: active ? 1.04 : 1.0
    Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    Rectangle { anchors.fill: parent; radius: theme.radius; color: on ? theme.surface2 : theme.surface; border.width: on ? 3 : 1; border.color: on ? theme.accent : Qt.rgba(1,1,1,0.08)
        Rectangle { visible: on; anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 14 * ui.s; width: 36 * ui.s; height: width; radius: width / 2; color: theme.accent
            Icon { anchors.centerIn: parent; name: "check"; px: 22 * ui.s; color: "#ffffff" } }
        Column { anchors.fill: parent; anchors.margins: 24 * ui.s; spacing: 12 * ui.s
            Icon { name: c.icon; px: 56 * ui.s; color: on ? theme.accent : theme.muted }
            Text { text: c.title; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 30 * ui.s }
            Text { width: parent.width; text: c.blurb; color: theme.muted; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 20 * ui.s; maximumLineCount: 3; elide: Text.ElideRight }
        }
    }
    FocusFrame { active: c.active; radius: theme.radius }
    MouseArea { anchors.fill: parent; onClicked: c.clicked(); cursorShape: Qt.PointingHandCursor }
}
