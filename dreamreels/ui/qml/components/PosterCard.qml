import QtQuick
// Poster card (Phase D, Sep 13 2026): three shapes from one component.
//   portrait 2:3  - films / episodes (TMDB posters)
//   wide 16:9     - YouTube videos: the thumbnail IS the button, YouTube-sized, title under it
//   square 1:1    - music tracks: album art with title + artist under it
Item {
    id: card
    property var item: ({})
    property bool active: false
    signal clicked()
    // Sep 26 2026 polish: TV episodes carry 16:9 TMDB stills, so they get the wide YouTube-style card (still + title + SxxEyy under it)
    property bool wide: (item && (item.source === "youtube" || item.kind === "episode"))
    property bool hovered: false
    property bool lit: active || hovered
    property bool watched: ((item && item.progress) || 0) >= 0.95
    property bool square: (item && item.kind === "track")
    property bool more: (item && item.kind === "more")   // Phase R: 'See all N' drill-down card
    width: (wide ? 444 : square ? 250 : 220) * ui.s; height: 330 * ui.s
    property real imgH: (wide ? 250 : square ? 250 : 330) * ui.s
    scale: lit ? 1.06 : 1.0; z: lit ? 2 : 1
    MouseArea { anchors.fill: parent; z: 5; hoverEnabled: true; onEntered: card.hovered = true; onExited: card.hovered = false; onClicked: card.clicked(); cursorShape: Qt.PointingHandCursor }
    Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
    Rectangle {
        id: frame; width: parent.width; height: card.imgH; radius: theme.radius; color: theme.surface; clip: true
        border.width: card.more ? 3 : (active ? 4 : (hovered ? 2 : 0)); border.color: card.more ? theme.accent : (active ? theme.text : Qt.rgba(1, 1, 1, 0.6))
        Image {
            id: img; anchors.fill: parent; source: item.poster || ""; fillMode: Image.PreserveAspectCrop; asynchronous: true; cache: true
            sourceSize: wide ? Qt.size(640, 360) : Qt.size(400, 600); visible: status === Image.Ready
        }
        Column {
            anchors.centerIn: parent; width: parent.width - 28 * ui.s; spacing: 8 * ui.s; visible: img.status !== Image.Ready
            Text { width: parent.width; text: item.title || ""; color: theme.text; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; maximumLineCount: wide ? 3 : 5; elide: Text.ElideRight; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: (square ? 22 : 24) * ui.s }
            Text { width: parent.width; text: square ? (item.subtitle || "") : (item.year ? item.year : ""); color: theme.muted; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight; font.family: theme.fontBody; font.pixelSize: 18 * ui.s }
        }
        Rectangle { visible: (item.progress || 0) > 0 && !card.watched; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 6 * ui.s; color: Qt.rgba(1, 1, 1, 0.18)
            Rectangle { width: parent.width * (item.progress || 0); height: parent.height; color: theme.accent } }
        // watched tag (bottom-left): the film was played to >=95%, so Play restarts it from the top
        Rectangle { visible: card.watched; anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 10 * ui.s; height: 28 * ui.s; width: wtT.implicitWidth + 16 * ui.s; radius: 6 * ui.s; color: Qt.rgba(0, 0, 0, 0.7); border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.35)
            Text { id: wtT; anchors.centerIn: parent; text: "WATCHED"; color: "white"; font.family: theme.fontBody; font.pixelSize: 14 * ui.s; font.weight: Font.Bold; font.letterSpacing: 1 } }
        // verified badge (top-right): green tick = decode-proven, dim = not yet
        Rectangle { visible: !square && !card.more; anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 10 * ui.s; width: 34 * ui.s; height: width; radius: width / 2
            color: item.verified ? theme.ok : Qt.rgba(0, 0, 0, 0.55); border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.25)
            Text { anchors.centerIn: parent; text: item.verified ? "✓" : "?"; color: "white"; font.pixelSize: 20 * ui.s; font.weight: Font.Bold } }
        // duration / channel pill for wide cards (YouTube-style)
        Rectangle { visible: wide && item.source === "youtube" && !!(item.subtitle); anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 10 * ui.s; height: 30 * ui.s; width: pillT.implicitWidth + 16 * ui.s; radius: 6 * ui.s; color: Qt.rgba(0, 0, 0, 0.75)
            Text { id: pillT; anchors.centerIn: parent; text: item.subtitle || ""; color: "white"; font.family: theme.fontBody; font.pixelSize: 16 * ui.s } }
    }
    // caption under wide / square cards (portrait posters carry their own title art)
    Column { visible: wide || square; anchors.top: frame.bottom; anchors.topMargin: 10 * ui.s; width: parent.width; spacing: 2 * ui.s
        Text { width: parent.width; text: item.title || ""; color: lit ? theme.text : Qt.rgba(1, 1, 1, 0.9); wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; font.family: theme.fontBody; font.weight: Font.Medium; font.pixelSize: 19 * ui.s }
        Text { width: parent.width; text: (square || item.kind === "episode") ? (item.subtitle || "") : (item.badge || ""); color: theme.muted; elide: Text.ElideRight; font.family: theme.fontBody; font.pixelSize: 16 * ui.s } }
}
