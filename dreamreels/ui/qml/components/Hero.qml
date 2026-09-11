import QtQuick
Item {
    id: h
    property var item: ({})
    width: parent ? parent.width : 1920; height: 300 * ui.s
    Rectangle { anchors.fill: parent; color: theme.surface; radius: 0
        Image { anchors.fill: parent; source: item.backdrop || item.poster || ""; fillMode: Image.PreserveAspectCrop; asynchronous: true; opacity: 0.35; visible: status === Image.Ready }
        Rectangle { visible: theme.heroGradient; anchors.fill: parent; gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: theme.bg } GradientStop { position: 0.6; color: Qt.rgba(0,0,0,0) } } }
    }
    Column {
        x: ui.safe; anchors.verticalCenter: parent.verticalCenter; spacing: 10 * ui.s; width: parent.width * 0.55
        Text { text: item.badge || ""; color: theme.accent; font.family: theme.fontBody; font.weight: Font.Bold; font.pixelSize: 22 * ui.s; font.letterSpacing: 2 }
        Text { width: parent.width; text: item.title || "Welcome to DreamReels"; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 56 * ui.s; elide: Text.ElideRight; maximumLineCount: 1 }
        Text { text: item.subtitle || ""; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 24 * ui.s }
        Text { width: parent.width; text: item.blurb || "Pick something below, or press the Dreamy button and just ask."; color: theme.text; opacity: 0.9; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight; font.family: theme.fontBody; font.pixelSize: 24 * ui.s }
    }
}
