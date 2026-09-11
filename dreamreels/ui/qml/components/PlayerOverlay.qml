import QtQuick
Item {
    id: p
    anchors.fill: parent
    property bool showControls: false
    function fmt(s) { s = Math.max(0, Math.floor(s || 0)); var h = Math.floor(s/3600), m = Math.floor((s%3600)/60), x = s%60; return (h ? h + ":" + (m<10?"0":"") : "") + m + ":" + (x<10?"0":"") + x }
    Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 190 * ui.s; visible: p.showControls || backend.paused
        gradient: Gradient { GradientStop { position: 0; color: Qt.rgba(0,0,0,0) } GradientStop { position: 1; color: Qt.rgba(0,0,0,0.85) } }
        Column { x: ui.safe; anchors.bottom: parent.bottom; anchors.bottomMargin: 36 * ui.s; width: parent.width - 2 * ui.safe; spacing: 16 * ui.s
            Row { spacing: 18 * ui.s
                Icon { name: backend.paused ? "play" : "pause"; px: 40 * ui.s; color: "#ffffff"; anchors.verticalCenter: parent.verticalCenter }
                Text { text: backend.nowPlayingTitle; color: "#ffffff"; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 34 * ui.s; anchors.verticalCenter: parent.verticalCenter }
                Text { text: p.fmt(backend.position) + "  /  " + p.fmt(backend.duration); color: "#d0d4dc"; font.family: theme.fontBody; font.pixelSize: 26 * ui.s; anchors.verticalCenter: parent.verticalCenter }
            }
            Rectangle { width: parent.width; height: 10 * ui.s; radius: 5 * ui.s; color: Qt.rgba(1,1,1,0.25)
                Rectangle { width: parent.width * (backend.duration > 0 ? backend.position / backend.duration : 0); height: parent.height; radius: parent.radius; color: theme.accent } }
            Text { text: "Space / Cross: pause   ·   Left/Right or L2/R2: seek 30s   ·   S: subtitles   ·   A: audio   ·   Back: stop"; color: "#a8aebb"; font.family: theme.fontBody; font.pixelSize: 20 * ui.s }
        }
    }
}
