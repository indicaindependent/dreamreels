import QtQuick
Item {
    id: b
    property string label: ""
    property string icon: "film"
    property bool active: false
    property bool current: false
    signal clicked()
    width: row.implicitWidth + 44 * ui.s; height: 68 * ui.s
    Rectangle {
        anchors.fill: parent; radius: theme.radius
        color: current ? theme.accent : (active ? theme.surface2 : theme.surface)
        border.width: 1; border.color: current ? theme.accent : Qt.rgba(1,1,1,0.06)
        scale: active ? 1.04 : 1.0
        Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on color { ColorAnimation { duration: 180 } }
    }
    FocusFrame { active: b.active; radius: theme.radius }
    Row {
        id: row; anchors.centerIn: parent; spacing: 12 * ui.s
        Icon { name: b.icon; px: 30 * ui.s; color: b.current ? "#ffffff" : theme.text; anchors.verticalCenter: parent.verticalCenter }
        Text { text: b.label; color: b.current ? "#ffffff" : theme.text; font.family: theme.fontDisplay; font.weight: Font.DemiBold; font.pixelSize: 26 * ui.s; anchors.verticalCenter: parent.verticalCenter }
    }
    MouseArea { anchors.fill: parent; hoverEnabled: true; onClicked: b.clicked(); cursorShape: Qt.PointingHandCursor }
}
