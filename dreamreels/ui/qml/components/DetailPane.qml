import QtQuick
Rectangle {
    id: d
    property var item: ({})
    property int focusBtn: 0        // 0 play, 1 resume, 2 favorite, 3 dreamy
    signal play(bool resume)
    signal favorite()
    signal askDreamy()
    signal close()
    anchors.fill: parent; color: Qt.rgba(0,0,0,0.55); visible: item && item.uid !== undefined
    MouseArea { anchors.fill: parent; onClicked: d.close() }
    Rectangle {
        width: parent.width * 0.78; height: parent.height * 0.72; anchors.centerIn: parent; radius: theme.radius * 1.5; color: theme.surface; border.width: 1; border.color: Qt.rgba(1,1,1,0.08)
        MouseArea { anchors.fill: parent }
        Image { anchors.fill: parent; source: item.backdrop || ""; fillMode: Image.PreserveAspectCrop; opacity: 0.18; asynchronous: true; visible: status === Image.Ready }
        Row { anchors.fill: parent; anchors.margins: 44 * ui.s; spacing: 44 * ui.s
            Rectangle { width: 320 * ui.s; height: 480 * ui.s; radius: theme.radius; color: theme.surface2; clip: true
                Image { anchors.fill: parent; source: item.poster || ""; fillMode: Image.PreserveAspectCrop; asynchronous: true } }
            Column { width: parent.width - 320 * ui.s - 44 * ui.s; spacing: 14 * ui.s
                Text { text: (item.badge || "") + (item.verified ? "  ·  Verified playable" : "  ·  Not yet verified"); color: item.verified ? theme.ok : theme.muted; font.family: theme.fontBody; font.weight: Font.Bold; font.pixelSize: 22 * ui.s; font.letterSpacing: 1.5 }
                Text { width: parent.width; text: item.title || ""; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 52 * ui.s; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight }
                Text { text: [item.subtitle, item.director ? "Directed by " + item.director : "", item.genres].filter(function(x){return x}).join("   ·   "); color: theme.muted; font.family: theme.fontBody; font.pixelSize: 24 * ui.s }
                Text { width: parent.width; text: item.blurb || ""; color: theme.text; opacity: 0.92; wrapMode: Text.WordWrap; maximumLineCount: 6; elide: Text.ElideRight; font.family: theme.fontBody; font.pixelSize: 26 * ui.s; lineHeight: 1.25 }
                Item { height: 10 * ui.s; width: 1 }
                Row { spacing: 18 * ui.s
                    SourceButton { label: item.verified ? "Play" : "Find playable"; icon: item.verified ? "play" : "search"; active: d.focusBtn === 0; current: d.focusBtn === 0; onClicked: d.play(false) }
                    SourceButton { visible: (item.resume || 0) > 30; label: "Resume"; icon: "clock"; active: d.focusBtn === 1; current: d.focusBtn === 1; onClicked: d.play(true) }
                    SourceButton { label: item.favorite ? "Favorited" : "Favorite"; icon: "heart"; active: d.focusBtn === 2; current: d.focusBtn === 2; onClicked: d.favorite() }
                    SourceButton { label: "Ask Dreamy"; icon: "chat"; active: d.focusBtn === 3; current: d.focusBtn === 3; onClicked: d.askDreamy() }
                }
            }
        }
    }
}
