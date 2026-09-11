import QtQuick
import "Icons.js" as Icons
Image {
    id: ic
    property string name: "info"
    property color color: "white"
    property int px: 32
    width: px; height: px
    sourceSize: Qt.size(px * 2, px * 2)
    source: Icons.svg(name, color.toString())
    fillMode: Image.PreserveAspectFit
    smooth: true; antialiasing: true
}
