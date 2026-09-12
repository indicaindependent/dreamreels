import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import "components"

Window {
    id: win
    visible: true; width: 1920; height: 1080; color: theme.bg; title: "DreamReels setup"
    visibility: app.kiosk ? Window.FullScreen : Window.Windowed
    QtObject { id: ui; property real s: Math.min(win.width / 1920, win.height / 1080); property real safe: 0.05 * win.width }

    // top brand row
    Row { x: ui.safe; y: 26 * ui.s; spacing: 14 * ui.s
        Icon { name: "reel"; px: 44 * ui.s; color: theme.accent; anchors.verticalCenter: parent.verticalCenter }
        Text { text: "DreamReels"; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 40 * ui.s; anchors.verticalCenter: parent.verticalCenter }
        Rectangle { anchors.verticalCenter: parent.verticalCenter; radius: 8 * ui.s; color: theme.surface2; width: vt.implicitWidth + 18 * ui.s; height: vt.implicitHeight + 8 * ui.s
            Text { id: vt; anchors.centerIn: parent; text: "v" + app.version; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 20 * ui.s } }
    }
    // progress dots
    Row { anchors.right: parent.right; anchors.rightMargin: ui.safe; y: 40 * ui.s; spacing: 10 * ui.s
        Repeater { model: wiz.count; Rectangle { width: index === wiz.index ? 34 * ui.s : 12 * ui.s; height: 12 * ui.s; radius: 6 * ui.s; color: index <= wiz.index ? theme.accent : theme.surface2; Behavior on width { NumberAnimation { duration: 200 } } } }
    }
    Image { source: app.badgeUrl; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: ui.safe * 0.6; width: 260 * ui.s; fillMode: Image.PreserveAspectFit; sourceSize.width: 800; opacity: 0.85 }

    // Dreamy column
    Item { id: left; x: ui.safe; y: 120 * ui.s; width: 520 * ui.s; height: parent.height - y - 100 * ui.s
        Image { id: mascot; source: wiz.mascotUrl(wiz.pose); width: 380 * ui.s; height: width; sourceSize: Qt.size(760, 760); anchors.horizontalCenter: parent.horizontalCenter; y: 40 * ui.s; smooth: true
            SequentialAnimation on y { loops: Animation.Infinite; running: true; NumberAnimation { to: 52 * ui.s; duration: 1800; easing.type: Easing.InOutSine } NumberAnimation { to: 40 * ui.s; duration: 1800; easing.type: Easing.InOutSine } } }
        Rectangle { id: bubble; anchors.top: mascot.bottom; anchors.topMargin: 26 * ui.s; width: parent.width; height: bt.implicitHeight + 48 * ui.s; radius: theme.radius * 1.4; color: theme.surface; border.width: 1; border.color: Qt.rgba(1,1,1,0.10)
            Rectangle { width: 26 * ui.s; height: width; rotation: 45; color: theme.surface; anchors.horizontalCenter: parent.horizontalCenter; y: -13 * ui.s }
            Text { id: bt; anchors.centerIn: parent; width: parent.width - 48 * ui.s; text: wiz.line; color: theme.text; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 26 * ui.s; lineHeight: 1.3 } }
    }

    // step content
    Item { id: right; x: left.x + left.width + 60 * ui.s; y: 120 * ui.s; width: parent.width - x - ui.safe; height: parent.height - y - 200 * ui.s
        Text { id: title; text: wiz.stepTitle; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 54 * ui.s }
        Text { anchors.left: title.right; anchors.leftMargin: 20 * ui.s; anchors.baseline: title.baseline; text: "step " + (wiz.index + 1) + " of " + wiz.count; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 24 * ui.s }
        Loader { id: body; anchors.top: title.bottom; anchors.topMargin: 36 * ui.s; width: parent.width; height: parent.height - y
            sourceComponent: wiz.stepId === "welcome" ? welcome : wiz.stepId === "sources" ? sources : wiz.stepId === "pd" ? pd : wiz.stepId === "strict" ? strict : wiz.stepId === "chan83" ? chan83 : wiz.stepId === "toontown" ? toontown : wiz.stepId === "nas" ? nas : wiz.stepId === "youtube" ? youtube : wiz.stepId === "tmdb" ? tmdb : wiz.stepId === "skin" ? skin : wiz.stepId === "user" ? user : wiz.stepId === "summary" ? summary : done }
    }
    // nav
    Row { anchors.right: parent.right; anchors.rightMargin: ui.safe + 300 * ui.s; anchors.bottom: parent.bottom; anchors.bottomMargin: 60 * ui.s; spacing: 18 * ui.s
        SourceButton { visible: wiz.index > 0 && wiz.stepId !== "done"; label: "Back"; icon: "back"; onClicked: wiz.back() }
        SourceButton { visible: wiz.stepId !== "summary" && wiz.stepId !== "done"; label: wiz.stepId === "welcome" ? "Let's go" : "Next"; icon: "play"; current: true; onClicked: wiz.next() }
        SourceButton { visible: wiz.stepId === "summary"; label: "Build"; icon: "check"; current: true; onClicked: wiz.build() }
        SourceButton { visible: wiz.stepId === "done" && !wiz.building; label: wiz.built ? "Open DreamReels" : "Close"; icon: "check"; current: true; onClicked: Qt.quit() }
    }
    Item { anchors.fill: parent; focus: true; Keys.onPressed: (e) => { if (e.key === Qt.Key_Escape && !app.kiosk) Qt.quit(); else if (e.key === Qt.Key_Right || e.key === Qt.Key_Return) { if (wiz.stepId === "summary") wiz.build(); else if (wiz.stepId === "done") { if (!wiz.building) Qt.quit() } else wiz.next() } else if (e.key === Qt.Key_Left || e.key === Qt.Key_Backspace) wiz.back(); else return; e.accepted = true } }

    // ---- step bodies ----
    Component { id: welcome; Column { spacing: 22 * ui.s
        Text { width: parent.width; text: "A 10-foot player for your living room: public-domain cinema, anthology TV, classic cartoons, your own NAS, and the YouTube channels you actually follow."; color: theme.text; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 30 * ui.s; lineHeight: 1.3 }
        Text { width: parent.width; text: "Use the arrow keys, a game controller, or the mouse. Nothing is installed or changed until the last step."; color: theme.muted; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 26 * ui.s }
        Text { width: parent.width; text: "Free and open source. Created with Creative Clarity by Indica Independent Media."; color: theme.muted; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 22 * ui.s } } }
    Component { id: sources; Flow { width: parent.width; spacing: 24 * ui.s
        BigToggleCard { title: "Public Domain"; icon: "film"; blurb: "Thousands of classics from archive.org, verified playable."; on: wiz.sources.publicdomain; onClicked: wiz.toggleSource("publicdomain") }
        BigToggleCard { title: "Channel 83"; icon: "tv"; blurb: "Anthology TV: Twilight Zone, Outer Limits, Hitchcock and more."; on: wiz.sources.chan83; onClicked: wiz.toggleSource("chan83") }
        BigToggleCard { title: "Toon Town"; icon: "toon"; blurb: "Classic cartoons by studio: Fleischer, Iwerks, Lantz, UPA."; on: wiz.sources.toontown; onClicked: wiz.toggleSource("toontown") }
        BigToggleCard { title: "Your NAS"; icon: "folder"; blurb: "Movies, shows and music on your own network drives."; on: wiz.sources.nas; onClicked: wiz.toggleSource("nas") }
        BigToggleCard { title: "YouTube"; icon: "youtube"; blurb: "The channels you follow, in a native ad-free player."; on: wiz.sources.youtube; onClicked: wiz.toggleSource("youtube") } } }
    Component { id: pd; Column { spacing: 26 * ui.s; width: parent.width
        Text { text: "Decades"; color: theme.muted; font.family: theme.fontBody; font.weight: Font.Bold; font.pixelSize: 22 * ui.s; font.letterSpacing: 2 }
        Flow { width: parent.width; spacing: 14 * ui.s; Repeater { model: wiz.decadeList; Chip { label: modelData.label; on: modelData.on; onClicked: wiz.toggleDecade(modelData.v) } } }
        Text { text: "Genres"; color: theme.muted; font.family: theme.fontBody; font.weight: Font.Bold; font.pixelSize: 22 * ui.s; font.letterSpacing: 2 }
        Flow { width: parent.width; spacing: 14 * ui.s; Repeater { model: wiz.genreList; Chip { label: modelData.label; on: modelData.on; onClicked: wiz.toggleGenre(modelData.v) } } }
        Text { width: parent.width; text: "Actors and directors can be added once your movie database key is in (a later step) - Dreamy will look them up by name."; color: theme.muted; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 22 * ui.s } } }
    Component { id: strict; Row { spacing: 30 * ui.s; width: parent.width
        BigToggleCard { width: 420 * ui.s; height: 300 * ui.s; title: "Strict: ON"; icon: "check"; blurb: "Only films published 1930 or earlier, or marked public domain by archive.org. Smaller and clean."; on: wiz.strictPd; onClicked: wiz.setStrict(true) }
        BigToggleCard { width: 420 * ui.s; height: 300 * ui.s; title: "Strict: OFF"; icon: "film"; blurb: "Everything archive.org will actually stream, including grey-area uploads. Bigger library, your call."; on: !wiz.strictPd; onClicked: wiz.setStrict(false) } } }
    Component { id: chan83; Flow { width: parent.width; spacing: 14 * ui.s; Repeater { model: wiz.chan83List; Chip { label: modelData.label; on: modelData.on; onClicked: wiz.toggleChan83(modelData.v) } } } }
    Component { id: toontown; Flow { width: parent.width; spacing: 14 * ui.s; Repeater { model: wiz.toonList; Chip { label: modelData.label; on: modelData.on; onClicked: wiz.toggleToon(modelData.v) } } } }
    Component { id: nas; Column { spacing: 16 * ui.s; width: parent.width
        Row { spacing: 16 * ui.s; SourceButton { label: wiz.nasScanning ? "Scanning your network..." : "Scan again"; icon: "search"; onClicked: wiz.scanNas() }
              Text { anchors.verticalCenter: parent.verticalCenter; text: wiz.nasHosts.length + " share(s) found"; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 24 * ui.s } }
        Repeater { model: wiz.nasHosts
            Rectangle { width: right.width; height: 74 * ui.s; radius: theme.radius; color: modelData.on ? theme.surface2 : theme.surface; border.width: modelData.on ? 2 : 1; border.color: modelData.on ? theme.accent : Qt.rgba(1,1,1,0.08)
                Row { anchors.fill: parent; anchors.margins: 16 * ui.s; spacing: 20 * ui.s
                    Icon { name: modelData.share ? "folder" : "info"; px: 34 * ui.s; color: modelData.on ? theme.accent : theme.muted; anchors.verticalCenter: parent.verticalCenter }
                    Column { anchors.verticalCenter: parent.verticalCenter
                        Text { text: (modelData.share ? "//" + (modelData.host || modelData.ip) + "/" + modelData.share : (modelData.host || modelData.ip)); color: theme.text; font.family: theme.fontBody; font.weight: Font.DemiBold; font.pixelSize: 26 * ui.s }
                        Text { text: modelData.ip + (modelData.comment ? "  ·  " + modelData.comment : "") + (modelData.auth === "required" ? "  ·  needs a login" : ""); color: theme.muted; font.family: theme.fontBody; font.pixelSize: 20 * ui.s } } }
                MouseArea { anchors.fill: parent; onClicked: wiz.toggleShare(modelData.key) } } }
        Text { visible: !wiz.nasScanning && wiz.nasHosts.length === 0; width: parent.width; text: "No SMB servers answered on this network. Check the NAS is on and shares are enabled (SMB 2 or 3). You can rerun this from Settings later."; color: theme.muted; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 24 * ui.s } } }
    Component { id: youtube; Column { spacing: 16 * ui.s; width: parent.width
        Rectangle { width: parent.width; height: 320 * ui.s; radius: theme.radius; color: theme.surface; border.width: 1; border.color: Qt.rgba(1,1,1,0.10)
            TextArea { anchors.fill: parent; anchors.margins: 16 * ui.s; text: wiz.handlesText; placeholderText: "@handle or https://youtube.com/@handle, one per line"; color: theme.text; placeholderTextColor: theme.muted; font.family: theme.fontBody; font.pixelSize: 26 * ui.s; wrapMode: TextEdit.Wrap; background: null; onEditingFinished: wiz.setHandlesText(text) } }
        Text { width: parent.width; text: wiz.handlesText.split("\n").filter(function(x){return x}).length + " channel(s) recognised. Health check and tool install happen in the build step; the lane shows Repair YouTube if it ever breaks."; color: theme.muted; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 22 * ui.s } } }
    Component { id: tmdb; Column { spacing: 16 * ui.s; width: parent.width
        Rectangle { width: parent.width; height: 80 * ui.s; radius: theme.radius; color: theme.surface; border.width: 1; border.color: Qt.rgba(1,1,1,0.10)
            TextField { anchors.fill: parent; anchors.margins: 10 * ui.s; text: wiz.tmdbToken; placeholderText: "Paste your TMDB Read Access Token (starts with eyJ...)"; color: theme.text; placeholderTextColor: theme.muted; font.family: theme.fontBody; font.pixelSize: 26 * ui.s; background: null; onEditingFinished: wiz.setTmdbToken(text) } }
        Text { width: parent.width; text: "themoviedb.org → Settings → API → API Read Access Token. This product uses the TMDB API but is not endorsed or certified by TMDB."; color: theme.muted; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 22 * ui.s } } }
    Component { id: skin; Row { spacing: 26 * ui.s
        Repeater { model: wiz.themeList
            Item { id: sk; width: 330 * ui.s; height: 420 * ui.s; property var t: modelData
                Rectangle { anchors.fill: parent; radius: theme.radius; color: sk.t.bg; border.width: sk.t.on ? 4 : 1; border.color: sk.t.on ? theme.accent : Qt.rgba(1,1,1,0.15)
                    Column { anchors.fill: parent; anchors.margins: 22 * ui.s; spacing: 14 * ui.s
                        Rectangle { width: parent.width; height: 120 * ui.s; radius: 10; color: sk.t.surface
                            Row { anchors.centerIn: parent; spacing: 10; Repeater { model: 4; Rectangle { width: 44 * ui.s; height: 66 * ui.s; radius: 6; color: index === 1 ? sk.t.accent : Qt.lighter(sk.t.surface, 1.4); border.width: index === 1 ? 3 : 0; border.color: sk.t.accent2 } } } }
                        Text { text: sk.t.label; color: sk.t.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 30 * ui.s }
                        Text { width: parent.width; text: sk.t.mood; color: sk.t.text; opacity: 0.7; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 22 * ui.s }
                        Row { spacing: 8; Repeater { model: [sk.t.accent, sk.t.accent2, sk.t.surface, sk.t.text]; Rectangle { width: 34 * ui.s; height: width; radius: width / 2; color: modelData; border.width: 1; border.color: Qt.rgba(0,0,0,0.2) } } } } }
                FocusFrame { active: sk.t.on; radius: theme.radius }
                MouseArea { anchors.fill: parent; onClicked: wiz.setTheme(sk.t.name) } } } } }
    Component { id: user; Column { spacing: 18 * ui.s; width: parent.width
        Rectangle { width: 600 * ui.s; height: 80 * ui.s; radius: theme.radius; color: theme.surface; border.width: 1; border.color: Qt.rgba(1,1,1,0.10)
            TextField { anchors.fill: parent; anchors.margins: 10 * ui.s; text: wiz.userName; color: theme.text; font.family: theme.fontBody; font.pixelSize: 26 * ui.s; background: null; onEditingFinished: wiz.setUserName(text) } }
        Rectangle { width: 600 * ui.s; height: 80 * ui.s; radius: theme.radius; color: theme.surface; border.width: 1; border.color: Qt.rgba(1,1,1,0.10)
            TextField { anchors.fill: parent; anchors.margins: 10 * ui.s; placeholderText: "Password (optional)"; echoMode: TextInput.Password; color: theme.text; placeholderTextColor: theme.muted; font.family: theme.fontBody; font.pixelSize: 26 * ui.s; background: null; onEditingFinished: wiz.setPassword(text) } }
        Text { width: parent.width; text: "The user logs in automatically at boot and runs only the player. Your own account is untouched."; color: theme.muted; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 22 * ui.s } } }
    Component { id: summary; Column { spacing: 10 * ui.s; width: parent.width
        Repeater { model: wiz.summaryLines
            Row { spacing: 20 * ui.s; Text { width: 220 * ui.s; text: modelData.k; color: theme.muted; font.family: theme.fontBody; font.weight: Font.Bold; font.pixelSize: 24 * ui.s }
                  Text { width: right.width - 240 * ui.s; text: modelData.v; color: theme.text; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 24 * ui.s } } } } }
    Component { id: done; Column { spacing: 14 * ui.s; width: parent.width
        Rectangle { width: parent.width; height: 420 * ui.s; radius: theme.radius; color: theme.surface2; clip: true
            ListView { id: blog; anchors.fill: parent; anchors.margins: 16 * ui.s; model: wiz.buildLines; spacing: 6 * ui.s; onCountChanged: positionViewAtEnd()
                delegate: Text { width: blog.width; text: modelData; wrapMode: Text.WrapAnywhere; font.family: "DejaVu Sans Mono"; font.pixelSize: 21 * ui.s
                    color: modelData.indexOf("FAIL") === 0 ? "#ff6b6b" : modelData.indexOf("OK") === 0 ? theme.accent2 : theme.text } } }
        Text { width: parent.width; text: wiz.building ? "Working..." : (wiz.built ? "All set. The player is running - press Open DreamReels." : (wiz.buildLines.length ? "Something needs a hand - the FAIL line says what." : "")); color: theme.muted; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 24 * ui.s } } }
}
