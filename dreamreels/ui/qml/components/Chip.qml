import QtQuick
Item {
    id: c
    property string label: ""
    property bool on: false
    property bool active: false
    signal clicked()
    width: t.implicitWidth + 40 * ui.s; height: 60 * ui.s
    Rectangle { anchors.fill: parent; radius: height / 2; color: on ? theme.accent : theme.surface2; border.width: 2; border.color: on ? theme.accent : Qt.rgba(1,1,1,0.10)
        Behavior on color { ColorAnimation { duration: 160 } } }
    FocusFrame { active: c.active; radius: height / 2 }
    Row { anchors.centerIn: parent; spacing: 10 * ui.s
        Icon { visible: on; name: "check"; px: 24 * ui.s; color: "#ffffff"; anchors.verticalCenter: parent.verticalCenter }
        Text { id: t; text: c.label; color: on ? "#ffffff" : theme.text; font.family: theme.fontBody; font.weight: Font.DemiBold; font.pixelSize: 24 * ui.s; anchors.verticalCenter: parent.verticalCenter } }
    MouseArea { anchors.fill: parent; onClicked: c.clicked(); cursorShape: Qt.PointingHandCursor }
}
