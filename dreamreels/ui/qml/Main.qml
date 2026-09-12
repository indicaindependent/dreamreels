import QtQuick
import QtQuick.Window
import dreamreels 1.0
import "components"

Window {
    id: win
    visible: true
    width: 1920; height: 1080
    color: theme.bg
    title: "DreamReels"
    visibility: app.kiosk ? Window.FullScreen : Window.Windowed

    // ---- ui scale + safe area (5% overscan) ----
    QtObject { id: ui; property real s: Math.min(win.width / 1920, win.height / 1080); property real safe: 0.05 * win.width }

    // ---- focus model ----
    property string zone: "top"      // top | rails | detail | player | badge
    property int topIdx: 0
    property int railIdx: 0
    property int colIdx: 0
    property var topButtons: [
        {id: "home", label: "Home", icon: "reel"},
        {id: "pd", label: "Public Domain", icon: "film"},
        {id: "chan83", label: "Channel 83", icon: "tv"},
        {id: "toontown", label: "Toon Town", icon: "toon"},
        {id: "nas", label: "NAS", icon: "folder"},
        {id: "youtube", label: "YouTube", icon: "youtube"},
        {id: "music", label: "Music", icon: "music"},
        {id: "search", label: "Search", icon: "search"},
        {id: "dreamy", label: "Dreamy", icon: "chat"},
        {id: "settings", label: "Settings", icon: "settings"}
    ]
    property int detailBtn: 0
    property bool qrOpen: false
    property string toastText: ""

    function heroItem() { var it = backend.railItem(railIdx, colIdx); return it && it.uid ? it : {} }
    function clampCol() { var m = backend.railModel(railIdx); if (!m) { colIdx = 0; return } var n = m.rowCount(); if (colIdx >= n) colIdx = Math.max(0, n - 1) }
    function activateTop(i) {
        var b = topButtons[i]; topIdx = i
        if (b.id === "home") { backend.loadHome(); zone = "rails"; railIdx = 0; colIdx = 0 }
        else if (b.id === "dreamy") dreamyPanel.open = true
        else if (b.id === "search") { dreamyPanel.open = true; toast("Type what you are looking for - Dreamy searches the library") }
        else if (b.id === "settings") toast("Settings: run 'python3 -m dreamreels wizard' to change sources or skin")
        else { backend.loadLane(b.id); zone = "rails"; railIdx = 0; colIdx = 0 }
    }
    function toast(t) { toastText = t; toastTimer.restart() }
    Timer { id: toastTimer; interval: 2200; onTriggered: toastText = "" }
    Timer { id: ctrlTimer; interval: 3500; onTriggered: playerOverlay.showControls = false }
    function poke() { playerOverlay.showControls = true; ctrlTimer.restart() }

    function nav(dx, dy) {
        if (backend.playing) { if (dx) backend.seekRel(dx * 30); poke(); return }
        if (qrOpen) return
        if (zone === "detail") { detailBtn = Math.max(0, Math.min(3, detailBtn + dx)); return }
        if (zone === "top") {
            if (dx) topIdx = (topIdx + dx + topButtons.length) % topButtons.length
            if (dy > 0 && backend.rails.length) { zone = "rails"; clampCol() }
            return
        }
        if (zone === "rails") {
            if (dy < 0) { if (railIdx === 0) zone = "top"; else railIdx--; clampCol(); return }
            if (dy > 0) { if (railIdx < backend.rails.length - 1) railIdx++; clampCol(); return }
            var m = backend.railModel(railIdx); if (!m) return
            colIdx = Math.max(0, Math.min(m.rowCount() - 1, colIdx + dx))
        }
    }
    function select() {
        if (backend.playing) { backend.togglePause(); poke(); return }
        if (qrOpen) { qrOpen = false; return }
        if (zone === "top") { activateTop(topIdx); return }
        if (zone === "rails") { var it = heroItem(); if (it.uid) { backend.openDetail(it.uid); detailBtn = 0; zone = "detail" } return }
        if (zone === "detail") {
            var d = backend.detail
            if (detailBtn === 0) { if (d.verified) { backend.closeDetail(); zone = "rails"; backend.play(d.uid, false) } else backend.verifyNow(d.uid) }
            else if (detailBtn === 1) { backend.closeDetail(); zone = "rails"; backend.play(d.uid, true) }
            else if (detailBtn === 2) backend.toggleFavorite(d.uid)
            else { var d = backend.detail; dreamyPanel.open = true; if (d && d.title) dreamyPanel.send("tell me about \"" + d.title + "\"") }
        }
    }
    function back() {
        if (backend.playing) { backend.stop(); zone = "rails"; return }
        if (qrOpen) { qrOpen = false; return }
        if (zone === "detail") { backend.closeDetail(); zone = "rails"; return }
        if (zone === "rails") { zone = "top"; return }
    }

    // ---- keyboard: works for forkers without a pad ----
    Item {
        id: keys; anchors.fill: parent; focus: true
        Keys.onPressed: (e) => {
            if (dreamyPanel.open) { if (e.key === Qt.Key_Escape) { dreamyPanel.open = false; e.accepted = true } return }
            switch (e.key) {
            case Qt.Key_Left: nav(-1, 0); break
            case Qt.Key_Right: nav(1, 0); break
            case Qt.Key_Up: nav(0, -1); break
            case Qt.Key_Down: nav(0, 1); break
            case Qt.Key_Return: case Qt.Key_Enter: case Qt.Key_Space: select(); break
            case Qt.Key_Escape: case Qt.Key_Backspace: back(); break
            case Qt.Key_P: if (backend.playing) { backend.togglePause(); poke() } break
            case Qt.Key_S: if (backend.playing) backend.cycleSub(); break
            case Qt.Key_A: if (backend.playing) backend.cycleAudio(); break
            case Qt.Key_I: if (zone === "rails") select(); break
            case Qt.Key_D: case Qt.Key_C: dreamyPanel.open = true; break
            case Qt.Key_Q: if (!app.kiosk) Qt.quit(); break
            case Qt.Key_F11: win.visibility = win.visibility === Window.FullScreen ? Window.Windowed : Window.FullScreen; break
            default: return
            }
            e.accepted = true
        }
    }
    Connections { target: pad
        function onNavLeft() { nav(-1, 0) } function onNavRight() { nav(1, 0) } function onNavUp() { nav(0, -1) } function onNavDown() { nav(0, 1) }
        function onSelect() { select() } function onBack() { back() } function onPlayPause() { if (backend.playing) { backend.togglePause(); poke() } else select() }
        function onInfo() { if (zone === "rails") select() } function onHome() { activateTop(0) } function onDreamy() { activateTop(8) }
        function onSeekFwd() { if (backend.playing) { backend.seekRel(30); poke() } } function onSeekBack() { if (backend.playing) { backend.seekRel(-30); poke() } }
        function onRailPrev() { nav(0, -1) } function onRailNext() { nav(0, 1) }
    }
    Connections { target: backend
        function onToast(t) { toast(t) }
        function onPlaybackStarted() { poke() }
        function onRailsChanged() { clampCol() }
    }

    // ---- video layer (v1 FBO technique). Skipped in screenshot/offscreen mode. ----
    Loader { id: videoLoader; anchors.fill: parent; active: app.videoEnabled; visible: backend.playing; z: 50
        sourceComponent: Component { Item { anchors.fill: parent; Rectangle { anchors.fill: parent; color: "black" } MpvObject { id: mpvItem; objectName: "mpv"; anchors.fill: parent } } } }
    MouseArea { anchors.fill: parent; z: 51; visible: backend.playing; hoverEnabled: true; onPositionChanged: poke(); onClicked: { backend.togglePause(); poke() } }
    PlayerOverlay { id: playerOverlay; z: 52; visible: backend.playing }

    // ---- home surface ----
    Item {
        id: home; anchors.fill: parent; visible: !backend.playing
        Hero { id: hero; y: 100 * ui.s; item: zone === "rails" ? heroItem() : {} ; opacity: zone === "rails" ? 1 : 0.9 }
        Row { id: topBar; x: ui.safe; y: 100 * ui.s + hero.height + 22 * ui.s; spacing: 14 * ui.s
            Repeater { model: topButtons
                SourceButton { label: modelData.label; icon: modelData.icon; active: zone === "top" && index === topIdx; current: zone !== "top" && index === topIdx && modelData.id === "home"
                    onClicked: { zone = "top"; activateTop(index) } } }
        }
        ListView {
            id: railsView; x: 0; y: topBar.y + topBar.height + 26 * ui.s; width: parent.width; height: parent.height - y
            model: backend.rails; spacing: 8 * ui.s; clip: true; interactive: false
            currentIndex: zone === "rails" ? railIdx : 0; highlightMoveDuration: 220; preferredHighlightBegin: 0; preferredHighlightEnd: 440 * ui.s; highlightRangeMode: ListView.ApplyRange
            delegate: Rail { label: modelData.label; model: backend.railModel(index); active: zone === "rails" && index === railIdx; col: (zone === "rails" && index === railIdx) ? colIdx : -1
                onPick: (i) => { zone = "rails"; railIdx = index; colIdx = i; select() } }
        }
        Text { visible: backend.rails.length === 0; anchors.centerIn: parent; text: "Your library is empty. Run Dreamy setup (dreamreels wizard) to add sources."; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 28 * ui.s }
        BadgeCorner { onBadgeClicked: qrOpen = true }
    }
    DetailPane { z: 60; item: backend.detail; focusBtn: detailBtn; visible: zone === "detail" && !backend.playing
        onPlay: (r) => { detailBtn = r ? 1 : 0; select() } onFavorite: { detailBtn = 2; select() } onAskDreamy: { detailBtn = 3; select() } onClose: back() }

    // ---- badge -> QR / URL panel (kiosks have no browser) ----
    Rectangle { z: 70; anchors.fill: parent; color: Qt.rgba(0,0,0,0.6); visible: qrOpen
        MouseArea { anchors.fill: parent; onClicked: qrOpen = false }
        Rectangle { anchors.centerIn: parent; width: 900 * ui.s; height: 520 * ui.s; radius: theme.radius * 1.5; color: theme.surface; border.width: 1; border.color: Qt.rgba(1,1,1,0.1)
            Row { anchors.fill: parent; anchors.margins: 40 * ui.s; spacing: 40 * ui.s
                Image { source: app.qrUrl; width: 420 * ui.s; height: 420 * ui.s; sourceSize: Qt.size(840, 840); smooth: false }
                Column { spacing: 16 * ui.s; width: parent.width - 460 * ui.s; anchors.verticalCenter: parent.verticalCenter
                    Text { text: "Created with Creative Clarity"; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 40 * ui.s; wrapMode: Text.WordWrap; width: parent.width }
                    Text { text: "DreamReels is free, open source and forkable. Scan to visit the project on GitHub, or open:"; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 24 * ui.s; wrapMode: Text.WordWrap; width: parent.width }
                    Text { text: app.githubUrl; color: theme.accent2; font.family: theme.fontBody; font.pixelSize: 24 * ui.s; wrapMode: Text.WrapAnywhere; width: parent.width }
                    Text { text: "Indica Independent Media  ·  v" + app.version; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 20 * ui.s }
                    Text { text: "This product uses the TMDB API but is not endorsed or certified by TMDB."; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 16 * ui.s; wrapMode: Text.WordWrap; width: parent.width }
                }
            }
        }
    }
    // ---- toast ----
    Rectangle { z: 80; visible: toastText !== ""; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 60 * ui.s
        radius: theme.radius; color: theme.surface2; border.width: 1; border.color: theme.accent; width: tt.implicitWidth + 48 * ui.s; height: tt.implicitHeight + 28 * ui.s
        Text { id: tt; anchors.centerIn: parent; text: toastText; color: theme.text; font.family: theme.fontBody; font.pixelSize: 26 * ui.s } }

    DreamyPanel { id: dreamyPanel; z: 50
        Component.onCompleted: if (app.shotDreamy) { open = true; send(app.shotDreamy) }
        onCloseRequested: open = false
        onPlayRequested: (uid) => { open = false; backend.play(uid) } }
}
