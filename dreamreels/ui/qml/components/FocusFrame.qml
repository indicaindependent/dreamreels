import QtQuick
// Dual-ring focus (2px inner dark + outer accent) so it reads on light AND dark poster art.
Item {
    id: f
    property bool active: false
    property real radius: theme.radius
    property real ringWidth: 4
    anchors.fill: parent; anchors.margins: -ringWidth * 1.5
    visible: active
    Rectangle { anchors.fill: parent; radius: f.radius + f.ringWidth; color: "transparent"; border.width: f.ringWidth; border.color: theme.focus }
    Rectangle { anchors.fill: parent; anchors.margins: f.ringWidth; radius: f.radius + 2; color: "transparent"; border.width: 2; border.color: theme.focusInner }
    Rectangle { visible: theme.glow; anchors.fill: parent; anchors.margins: -10; radius: f.radius + 14; color: "transparent"; border.width: 10; border.color: theme.focus; opacity: 0.18 }
}
