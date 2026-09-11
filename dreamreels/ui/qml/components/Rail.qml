import QtQuick
Item {
    id: r
    property string label: ""
    property var model: null
    property bool active: false
    property int col: 0
    signal pick(int index)
    width: parent ? parent.width : 1920; height: 330 * ui.s + 88 * ui.s
    Text { id: lbl; x: ui.safe; y: 0; text: r.label; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 34 * ui.s }
    Text { anchors.left: lbl.right; anchors.leftMargin: 18 * ui.s; anchors.baseline: lbl.baseline; text: (r.model ? r.model.rowCount() : 0) + " titles"; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 22 * ui.s }
    ListView {
        id: lv; x: 0; y: 60 * ui.s; width: parent.width; height: 330 * ui.s + 24 * ui.s
        orientation: ListView.Horizontal; spacing: 22 * ui.s; model: r.model; clip: false
        leftMargin: ui.safe; rightMargin: ui.safe; interactive: false
        currentIndex: r.col; highlightMoveDuration: 200; preferredHighlightBegin: ui.safe; preferredHighlightEnd: ui.safe + 220 * ui.s * 4; highlightRangeMode: ListView.ApplyRange
        delegate: PosterCard {
            item: ({uid: uid, title: title, year: year, poster: poster, kind: kind, verified: verified, progress: progress})
            active: r.active && index === r.col
            onClicked: { r.col = index; r.pick(index) }
        }
    }
}
