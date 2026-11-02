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
        {id: "gameshow", label: "Game Shows", icon: "tv"},
        {id: "nick90s", label: "90s Nick", icon: "toon"},
        {id: "sesame", label: "Sesame Street", icon: "toon"},
        {id: "toontown", label: "Toon Town", icon: "toon"},
        {id: "nas", label: "NAS", icon: "folder"},
        {id: "youtube", label: "YouTube", icon: "youtube"},
        {id: "music", label: "Music", icon: "music"},
        {id: "search", label: "Search", icon: "search"},
        {id: "dreamy", label: "Dreamy", icon: "chat"},
        {id: "settings", label: "Settings", icon: "settings"}
    ]
    property int detailBtn: 0
    property int chipRow: 0
    property int chipIdx: 0
    property bool inputOpen: false
    property string inputKind: ""
    property string inputPrompt: ""
    function hasChips() { var c = backend.page.chips; return c && ((c[0] && c[0].length) || (c[1] && c[1].length)) }
    function openInput(kind, prompt) { inputKind = kind; inputPrompt = prompt; inputField.text = ""; inputOpen = true; inputField.forceActiveFocus() }
    function closeInput() { inputOpen = false; keys.forceActiveFocus() }
    property bool qrOpen: false
    property var navStack: []   // Phase P: where you were on each page, so Back lands you exactly there
    function pushNav() { var a = navStack.slice(); a.push({zone: zone, railIdx: railIdx, colIdx: colIdx, chipRow: chipRow, chipIdx: chipIdx}); if (a.length > 40) a.shift(); navStack = a }
    function popNav() { var a = navStack.slice(); var s = a.pop(); navStack = a; return s }
    property string toastText: ""

    function heroItem() { var it = backend.railItem(railIdx, colIdx); return it && it.uid ? it : {} }
    function clampCol() { var m = backend.railModel(railIdx); if (!m) { colIdx = 0; return } var n = m.rowCount(); if (colIdx >= n) colIdx = Math.max(0, n - 1) }
    function activateTop(i) {
        var b = topButtons[i]; topIdx = i
        navStack = []
        if (b.id === "home") { backend.browseLane("home", []); zone = "rails"; railIdx = 0; colIdx = 0 }
        else if (b.id === "dreamy") dreamyPanel.open = true
        else if (b.id === "search") { backend.browseLane("search", []); openInput("search", "Search everything - type and press Enter") }
        else if (b.id === "settings") toast("Settings: run 'python3 -m dreamreels wizard' to change sources or skin")
        else { backend.browseLane(b.id, []); zone = "rails"; railIdx = 0; colIdx = 0 }
    }
    function toast(t) { toastText = t; toastTimer.restart() }
    Timer { id: toastTimer; interval: 2200; onTriggered: toastText = "" }
    Timer { id: ctrlTimer; interval: 3500; onTriggered: playerOverlay.showControls = false }
    function poke() { playerOverlay.showControls = true; ctrlTimer.restart() }

    function nav(dx, dy) { if (dreamyPanel.open) { dreamyPanel.navKey(dx, dy); return } _nav(dx, dy); pad.ack(zone + ":" + topIdx + ":" + railIdx + ":" + colIdx + ":" + detailBtn) }   // ack = QA receipt (Phase A)
    function _nav(dx, dy) {
        if (backend.playing) { if (dx) backend.seekRel(dx * 30); poke(); return }
        if (qrOpen) return
        if (zone === "detail") { detailBtn = Math.max(0, Math.min(3, detailBtn + dx)); return }
        if (zone === "top") {
            if (dx) topIdx = (topIdx + dx + topButtons.length) % topButtons.length
            if (dy > 0) { if (hasChips()) { zone = "chips"; chipRow = (backend.page.chips[0] && backend.page.chips[0].length) ? 0 : 1; chipIdx = 0 } else if (backend.rails.length) { zone = "rails"; clampCol() } }
            return
        }
        if (zone === "chips") {
            var rows = backend.page.chips; var row = rows[chipRow] || []
            if (dx) { chipIdx = Math.max(0, Math.min(row.length - 1, chipIdx + dx)); return }
            if (dy < 0) { if (chipRow === 1 && rows[0] && rows[0].length) { chipRow = 0; chipIdx = Math.min(chipIdx, rows[0].length - 1) } else zone = "top"; return }
            if (dy > 0) { if (chipRow === 0 && rows[1] && rows[1].length) { chipRow = 1; chipIdx = Math.min(chipIdx, rows[1].length - 1) } else if (backend.rails.length) { zone = "rails"; clampCol() }; return }
            return
        }
        if (zone === "rails") {
            if (dy < 0) { if (railIdx === 0) zone = hasChips() ? "chips" : "top"; else railIdx--; clampCol(); return }
            if (dy > 0) { if (railIdx < backend.rails.length - 1) railIdx++; clampCol(); if (backend.page.view === "grid" && railIdx >= backend.rails.length - 3) backend.gridMore(); return }
            var m = backend.railModel(railIdx); if (!m) return
            colIdx = Math.max(0, Math.min(m.rowCount() - 1, colIdx + dx))
        }
    }
    function select() {
        if (dreamyPanel.open) { dreamyPanel.activate(); return }
        if (backend.playing) { backend.togglePause(); poke(); return }
        if (qrOpen) { qrOpen = false; return }
        if (zone === "top") { activateTop(topIdx); return }
        if (zone === "chips") { var row = backend.page.chips[chipRow] || []; var cp = row[chipIdx]; if (cp) { var cid = "" + cp.id; if (cid.indexOf("input:") !== 0 && cid.indexOf("action:") !== 0) pushNav(); backend.chip(cid); railIdx = 0; colIdx = 0 } return }
        if (zone === "rails") { var it = heroItem(); if (!it.uid) return
            if (it.kind === "more") { pushNav(); backend.openDetail(it.uid); zone = "rails"; railIdx = 0; colIdx = 0; return }   // Phase P: 'See all' opens the grid, never an empty detail card
            backend.openDetail(it.uid); detailBtn = 0; zone = "detail"; return }
        if (zone === "detail") {
            var d = backend.detail; var uid = "" + ((d && d.uid) || ""); var ok = !!(d && d.verified)   // copy FIRST: closeDetail() blanks backend.detail and d tracks it live -> play("") = "Not found"
            if (uid === "") { backend.toastMsg("Nothing selected"); return }
            if (detailBtn === 0) { if (ok) { backend.play(uid, false); backend.closeDetail(); zone = "rails" } else backend.verifyNow(uid) }
            else if (detailBtn === 1) { backend.play(uid, true); backend.closeDetail(); zone = "rails" }
            else if (detailBtn === 2) backend.toggleFavorite(uid)
            else { var d = backend.detail; dreamyPanel.open = true; if (d && d.title) dreamyPanel.send("tell me about \"" + d.title + "\"") }
        }
    }
    function back() {
        if (dreamyPanel.open) { dreamyPanel.open = false; keys.forceActiveFocus(); return }
        if (backend.playing) { backend.stop(); zone = "rails"; return }
        if (qrOpen) { qrOpen = false; return }
        if (zone === "detail") { backend.closeDetail(); zone = "rails"; return }
        if (zone === "rails" || zone === "chips") { if (backend.page.path && backend.page.path.length) { backend.pageBack(); var s = popNav()
                if (s) { zone = s.zone; chipRow = s.chipRow; chipIdx = s.chipIdx; railIdx = Math.min(s.railIdx, Math.max(0, backend.rails.length - 1)); colIdx = s.colIdx } else { railIdx = 0; colIdx = 0; zone = "rails" }
                if (zone === "chips" && !hasChips()) zone = "rails"; clampCol(); return } zone = "top"; return }
    }

    // ---- keyboard: works for forkers without a pad ----
    Item {
        id: keys; anchors.fill: parent; focus: true
        Keys.onPressed: (e) => {
            if (inputOpen) { if (e.key === Qt.Key_Escape) { closeInput(); e.accepted = true } return }
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
        function onPageChanged() { chipIdx = Math.min(chipIdx, Math.max(0, ((backend.page.chips[chipRow] || []).length) - 1)); if (zone === "chips" && !hasChips()) zone = "rails" }
        function onInputRequest(kind, prompt) { openInput(kind, prompt) }
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
                    onClicked: { keys.forceActiveFocus(); zone = "top"; activateTop(index) } } }
        }
        Item {   // ---- Phase B: page header + drill-down chips ----
            id: pageHead; x: 0; y: topBar.y + topBar.height + 10 * ui.s; width: parent.width
            property var pg: backend.page
            property bool hasTitle: pg && pg.title && pg.title.length > 0
            height: (hasTitle ? 74 * ui.s : 0) + ((pg && pg.chips && pg.chips[0] && pg.chips[0].length) ? 58 * ui.s : 0) + ((pg && pg.chips && pg.chips[1] && pg.chips[1].length) ? 58 * ui.s : 0)
            Text { visible: pageHead.hasTitle; x: ui.safe; y: 0; text: pageHead.pg && pageHead.pg.crumbs ? pageHead.pg.crumbs.join("   >   ") : ""; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 20 * ui.s }
            Text { visible: pageHead.hasTitle; x: ui.safe; y: 26 * ui.s; width: parent.width - 2 * ui.safe; elide: Text.ElideRight; text: pageHead.pg ? pageHead.pg.title : ""; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 34 * ui.s }
            Repeater {
                model: 2
                ListView {
                    id: chipRowView; property int rowNo: index
                    x: 0; y: (pageHead.hasTitle ? 74 * ui.s : 0) + rowNo * 58 * ui.s; width: pageHead.width; height: 50 * ui.s
                    visible: count > 0; orientation: ListView.Horizontal; spacing: 10 * ui.s; leftMargin: ui.safe; rightMargin: ui.safe; clip: true; interactive: false
                    model: pageHead.pg && pageHead.pg.chips ? pageHead.pg.chips[rowNo] : []
                    currentIndex: (zone === "chips" && chipRow === rowNo) ? chipIdx : -1
                    highlightMoveDuration: 160; preferredHighlightBegin: ui.safe; preferredHighlightEnd: width - ui.safe - 300 * ui.s; highlightRangeMode: ListView.ApplyRange
                    delegate: Rectangle {
                        property bool focused: zone === "chips" && chipRow === chipRowView.rowNo && index === chipIdx
                        property bool selected: modelData.label.indexOf(" *") >= 0 || modelData.label.indexOf("* ") === 0
                        height: 46 * ui.s; width: chipText.implicitWidth + 34 * ui.s; radius: 23 * ui.s
                        color: focused ? theme.text : (selected ? Qt.rgba(1, 1, 1, 0.22) : (modelData.kind === "action" ? Qt.rgba(1, 1, 1, 0.13) : Qt.rgba(1, 1, 1, 0.07)))
                        border.width: focused ? 0 : 2; border.color: modelData.kind === "danger" ? "#ff5a5f" : (modelData.kind === "action" ? Qt.rgba(1, 1, 1, 0.35) : Qt.rgba(1, 1, 1, 0.14))
                        scale: focused ? 1.06 : 1.0; Behavior on scale { NumberAnimation { duration: 120 } }
                        Text { id: chipText; anchors.centerIn: parent; text: modelData.label + (modelData.count ? "  " + modelData.count : ""); color: focused ? "#111" : theme.text; font.family: theme.fontBody; font.weight: focused ? Font.Bold : Font.Medium; font.pixelSize: 22 * ui.s }
                        MouseArea { anchors.fill: parent; hoverEnabled: true; onEntered: { zone = "chips"; chipRow = chipRowView.rowNo; chipIdx = index } onClicked: { keys.forceActiveFocus(); zone = "chips"; chipRow = chipRowView.rowNo; chipIdx = index; select() } }
                    }
                }
            }
        }
        ListView {
            id: railsView; x: 0; y: pageHead.y + pageHead.height + 16 * ui.s; width: parent.width; height: parent.height - y
            model: backend.rails; spacing: 8 * ui.s; clip: true; interactive: false
            WheelHandler { onWheel: (ev) => { keys.forceActiveFocus(); if (zone !== "rails") { zone = "rails"; clampCol() } nav(0, ev.angleDelta.y < 0 ? 1 : -1) } }   // mouse wheel browses rails (Phase A)
            currentIndex: zone === "rails" ? railIdx : 0; highlightMoveDuration: 220; preferredHighlightBegin: 0; preferredHighlightEnd: 440 * ui.s; highlightRangeMode: ListView.ApplyRange
            delegate: Rail { label: modelData.label; model: backend.railModel(index); active: zone === "rails" && index === railIdx; col: (zone === "rails" && index === railIdx) ? colIdx : -1
                onPick: (i) => { keys.forceActiveFocus(); zone = "rails"; railIdx = index; colIdx = i; select() } }
        }
        Text { visible: backend.rails.length === 0; anchors.centerIn: parent; text: "Your library is empty. Run Dreamy setup (dreamreels wizard) to add sources."; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 28 * ui.s }
        BadgeCorner { onBadgeClicked: qrOpen = true }
    }
    Rectangle {   // ---- Phase B: keyboard text input (search / YouTube / add channel) ----
        id: inputBox; visible: inputOpen; z: 70; anchors.centerIn: parent; width: 1100 * ui.s; height: 190 * ui.s; radius: 18 * ui.s
        color: Qt.rgba(0.06, 0.06, 0.1, 0.96); border.width: 2; border.color: Qt.rgba(1, 1, 1, 0.25)
        Text { x: 34 * ui.s; y: 26 * ui.s; text: inputPrompt; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 24 * ui.s }
        Rectangle { x: 34 * ui.s; y: 72 * ui.s; width: parent.width - 68 * ui.s; height: 70 * ui.s; radius: 12 * ui.s; color: Qt.rgba(1, 1, 1, 0.08); border.width: 2; border.color: inputField.activeFocus ? theme.text : Qt.rgba(1, 1, 1, 0.2)
            TextInput { id: inputField; anchors.fill: parent; anchors.margins: 16 * ui.s; verticalAlignment: TextInput.AlignVCenter; color: theme.text; font.family: theme.fontBody; font.pixelSize: 30 * ui.s; clip: true; selectByMouse: true
                onAccepted: { var t = text; closeInput(); backend.inputSubmit(inputKind, t) } }
        }
        Text { x: 34 * ui.s; y: 152 * ui.s; text: "Enter = go   ·   Esc = cancel   ·   (Dreamy voice input arrives in Phase C)"; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 18 * ui.s }
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

    // Phase D: now-playing card (music + video titles) - shows for 7 s at each start, on the player's own thread of truth (backend.nowPlaying)
    Rectangle { id: npCard; z: 45; visible: backend.playing && npTimer.running && !!(backend.nowPlaying && backend.nowPlaying.title)
        x: 48 * ui.s; y: parent.height - height - 48 * ui.s; width: Math.min(parent.width * 0.5, npRow.implicitWidth + 40 * ui.s); height: 140 * ui.s; radius: 18 * ui.s; color: Qt.rgba(0, 0, 0, 0.72); border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.18)
        Row { id: npRow; anchors.fill: parent; anchors.margins: 16 * ui.s; spacing: 20 * ui.s
            Rectangle { width: 108 * ui.s; height: width; radius: 10 * ui.s; color: Qt.rgba(1, 1, 1, 0.08); clip: true
                Image { anchors.fill: parent; source: (backend.nowPlaying && backend.nowPlaying.poster) || ""; fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize: Qt.size(300, 300) } }
            Column { anchors.verticalCenter: parent.verticalCenter; spacing: 4 * ui.s; width: Math.min(700 * ui.s, npCard.parent.width * 0.4)
                Text { width: parent.width; text: (backend.nowPlaying && backend.nowPlaying.title) || ""; color: "white"; elide: Text.ElideRight; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 30 * ui.s }
                Text { width: parent.width; visible: text.length > 0; text: backend.nowPlaying ? [backend.nowPlaying.artist, backend.nowPlaying.album].filter(function (x) { return x }).join("  ·  ") : ""; color: Qt.rgba(1, 1, 1, 0.75); elide: Text.ElideRight; font.family: theme.fontBody; font.pixelSize: 21 * ui.s }
                Text { width: parent.width; text: backend.nowPlaying ? ((backend.nowPlaying.kind === "track" ? "Now playing" : "Now watching") + (backend.nowPlaying.year ? "  ·  " + backend.nowPlaying.year : "")) : ""; color: Qt.rgba(1, 1, 1, 0.5); font.family: theme.fontBody; font.pixelSize: 17 * ui.s } } }
        Timer { id: npTimer; interval: 7000 }
        Connections { target: backend; function onNowPlayingChanged() { npTimer.restart() } } }
    DreamyPanel { id: dreamyPanel; z: 50
        Component.onCompleted: if (app.shotDreamy) { open = true; send(app.shotDreamy) }
        onCloseRequested: { open = false; keys.forceActiveFocus() }
        onPlayRequested: (uid) => { open = false; keys.forceActiveFocus(); backend.play(uid, false) }
        onActionsRequested: (acts) => { applyDreamyActions(acts) } }
    function applyDreamyActions(acts) {   // Phase C: Dreamy's tool results become real app actions, on the GUI thread
        for (var i = 0; i < acts.length; i++) { var a = acts[i]
            if (a.type === "browse") { backend.browseLane(a.lane, a.path || []); zone = "rails"; railIdx = 0; colIdx = 0 }
            else if (a.type === "chip") backend.chip(a.id)
            else if (a.type === "chip_direct") backend.chip(a.id)
            else if (a.type === "play") { backend.play(a.uid, !!a.resume) }
            else if (a.type === "ytadd") backend.inputSubmit("ytadd", a.text)
            else if (a.type === "ytsearch") backend.inputSubmit("ytsearch", a.text)
            else if (a.type === "player") backend.playerCmd(a.cmd)
            else if (a.type === "close") { dreamyPanel.open = false; keys.forceActiveFocus() }
        }
    }
}
