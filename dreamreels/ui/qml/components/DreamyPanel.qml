import QtQuick
import QtQuick.Controls.Basic
// Dreamy side sheet (Phase C, Sep 12 2026). Same API as v1 (open / send / playRequested / closeRequested) plus
// actionsRequested(list) which Main.qml applies on the GUI thread, and navKey/activate for D-pad + keyboard.
Item {
    id: panel
    property bool open: false
    property var messages: []      // {who:"you"|"dreamy", text, buttons:[{kind,label,uid,query,poster,state,action}]}
    property int focusIdx: -1      // focused button in the LAST dreamy message (-1 = text box)
    property bool showHelp: false
    property var caps: []
    signal playRequested(string uid)
    signal closeRequested()
    signal actionsRequested(var actions)
    visible: open; anchors.fill: parent
    Rectangle { anchors.fill: parent; color: Qt.rgba(0, 0, 0, 0.45); MouseArea { anchors.fill: parent; onClicked: panel.closeRequested() } }
    Rectangle {
        id: card; width: Math.min(parent.width * 0.46, 900 * ui.s); height: parent.height; anchors.right: parent.right
        color: Qt.rgba(0.05, 0.05, 0.09, 0.97); border.width: 0
        Rectangle { width: 2; height: parent.height; color: Qt.rgba(1, 1, 1, 0.12) }
        MouseArea { anchors.fill: parent }  // swallow
        Row { id: head; x: 30 * ui.s; y: 24 * ui.s; spacing: 16 * ui.s
            Image { source: dreamy.mascotUrl(dreamy.busy ? "think" : "idle"); width: 64 * ui.s; height: width; sourceSize: Qt.size(160, 160) }
            Column { anchors.verticalCenter: parent.verticalCenter; spacing: 2
                Text { text: "Dreamy"; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 30 * ui.s }
                Text { text: dreamy.busy ? "working on it…" : "Ask for anything the app can do - say \"help\" to see the list"; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 18 * ui.s } }
        }
        Rectangle { id: helpBtn; anchors.right: parent.right; anchors.rightMargin: 30 * ui.s; y: 34 * ui.s; width: 130 * ui.s; height: 44 * ui.s; radius: 22 * ui.s; color: showHelp ? theme.text : Qt.rgba(1, 1, 1, 0.1); border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.25)
            Text { anchors.centerIn: parent; text: showHelp ? "chat" : "what can I say?"; color: showHelp ? "#111" : theme.text; font.family: theme.fontBody; font.pixelSize: 17 * ui.s }
            MouseArea { anchors.fill: parent; onClicked: { showHelp = !showHelp; if (showHelp && caps.length === 0) caps = JSON.parse(dreamy.capabilities()) } } }
        // ---- help view: generated from the tool registry, never hand-written ----
        ListView { visible: showHelp; anchors.top: head.bottom; anchors.topMargin: 22 * ui.s; anchors.bottom: inputBox.top; anchors.bottomMargin: 14 * ui.s; x: 30 * ui.s; width: parent.width - 60 * ui.s; clip: true; spacing: 12 * ui.s; model: caps
            delegate: Column { width: ListView.view.width; spacing: 4 * ui.s
                Text { text: modelData.desc; color: theme.text; font.family: theme.fontBody; font.weight: Font.Medium; font.pixelSize: 21 * ui.s; wrapMode: Text.Wrap; width: parent.width }
                Flow { width: parent.width; spacing: 8 * ui.s
                    Repeater { model: modelData.examples
                        Rectangle { height: 36 * ui.s; width: exT.implicitWidth + 24 * ui.s; radius: 18 * ui.s; color: Qt.rgba(1, 1, 1, 0.08); border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.18)
                            Text { id: exT; anchors.centerIn: parent; text: "“" + modelData + "”"; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 16 * ui.s }
                            MouseArea { anchors.fill: parent; onClicked: { showHelp = false; panel.send(modelData) } } } } } } }
        // ---- chat ----
        ListView {
            id: list; visible: !showHelp; anchors.top: head.bottom; anchors.topMargin: 18 * ui.s; anchors.bottom: inputBox.top; anchors.bottomMargin: 14 * ui.s
            x: 30 * ui.s; width: parent.width - 60 * ui.s; clip: true; spacing: 14 * ui.s; model: panel.messages
            onCountChanged: positionViewAtEnd()
            delegate: Column { width: list.width; spacing: 8 * ui.s
                property bool isLast: index === panel.messages.length - 1 && modelData.who === "dreamy"
                Rectangle { width: Math.min(list.width, msgText.implicitWidth + 32 * ui.s); height: msgText.implicitHeight + 24 * ui.s; radius: 16 * ui.s
                    anchors.right: modelData.who === "you" ? parent.right : undefined
                    color: modelData.who === "you" ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.06)
                    Text { id: msgText; x: 16 * ui.s; y: 12 * ui.s; width: list.width - 32 * ui.s; text: modelData.text; color: theme.text; font.family: theme.fontBody; font.pixelSize: 21 * ui.s; wrapMode: Text.Wrap } }
                Flow { width: list.width; spacing: 10 * ui.s
                    Repeater { model: modelData.buttons || []
                        Rectangle { property var b: modelData; property bool hasPoster: !!(b.poster && b.poster.length); property bool foc: isLast && index === panel.focusIdx
                            height: hasPoster ? 96 * ui.s : 50 * ui.s; width: hasPoster ? Math.min(list.width, bl.implicitWidth + 96 * ui.s) : bl.implicitWidth + 40 * ui.s; radius: hasPoster ? 12 * ui.s : height / 2
                            color: foc ? theme.text : (b.state === "verified" || b.kind === "play") ? Qt.rgba(0.2, 0.75, 0.4, 0.22) : b.state === "failed" ? Qt.rgba(1, 0.3, 0.3, 0.18) : Qt.rgba(1, 1, 1, 0.09)
                            border.width: foc ? 0 : 1; border.color: (b.kind === "play" || b.state === "verified") ? Qt.rgba(0.3, 0.9, 0.5, 0.6) : Qt.rgba(1, 1, 1, 0.2)
                            scale: foc ? 1.04 : 1; Behavior on scale { NumberAnimation { duration: 100 } }
                            Image { visible: hasPoster; x: 6 * ui.s; y: 6 * ui.s; width: 56 * ui.s; height: 84 * ui.s; source: hasPoster ? b.poster : ""; fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize: Qt.size(120, 180) }
                            Text { id: bl; x: hasPoster ? 72 * ui.s : 20 * ui.s; anchors.verticalCenter: parent.verticalCenter; width: Math.min(implicitWidth, list.width - 110 * ui.s); elide: Text.ElideRight
                                text: (b.kind === "play" || b.state === "verified" ? "▶ " : b.kind === "check" ? (b.state === "checking" ? "… " : b.state === "failed" ? "✕ " : "✓? ") : b.kind === "nav" ? "→ " : "") + b.label
                                color: foc ? "#111" : theme.text; font.family: theme.fontBody; font.weight: Font.Medium; font.pixelSize: 19 * ui.s }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: panel.press(b) } } } } }
        }
        // ---- input ----
        Rectangle { id: inputBox; anchors.bottom: parent.bottom; anchors.bottomMargin: 26 * ui.s; x: 30 * ui.s; width: parent.width - 60 * ui.s; height: 70 * ui.s; radius: 14 * ui.s
            color: Qt.rgba(1, 1, 1, 0.08); border.width: 2; border.color: (input.activeFocus && panel.focusIdx < 0) ? theme.text : Qt.rgba(1, 1, 1, 0.2)
            TextField { id: input; anchors.fill: parent; anchors.margins: 8 * ui.s; placeholderText: "e.g. show me 1948 film noir · play Detour · shuffle toon town"; color: theme.text; placeholderTextColor: theme.muted
                font.family: theme.fontBody; font.pixelSize: 22 * ui.s; background: Item {}
                onAccepted: { if (panel.focusIdx >= 0 && !text.trim()) { panel.activate(); return } panel.send(text); text = "" }
                Keys.onUpPressed: panel.navKey(0, -1); Keys.onDownPressed: panel.navKey(0, 1)
                Keys.onPressed: (e) => { if (e.key === Qt.Key_Tab) { panel.navKey(0, 1); e.accepted = true } } }
            Text { anchors.right: parent.right; anchors.rightMargin: 14 * ui.s; anchors.verticalCenter: parent.verticalCenter; visible: !input.text.length && panel.focusIdx < 0
                text: "↑↓ results · Enter · Esc"; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 15 * ui.s }
        }
    }
    function lastButtons() { var m = panel.messages; for (var i = m.length - 1; i >= 0; i--) if (m[i].who === "dreamy") return m[i].buttons || []; return [] }
    function navKey(dx, dy) { var n = lastButtons().length; if (!n) return; if (dy > 0) focusIdx = Math.min(n - 1, focusIdx + 1); else if (dy < 0) focusIdx = Math.max(-1, focusIdx - 1); else if (dx) focusIdx = Math.max(-1, Math.min(n - 1, focusIdx + dx)) }
    function activate() { var bs = lastButtons(); if (focusIdx >= 0 && focusIdx < bs.length) press(bs[focusIdx]) }
    function press(b) {
        if (b.kind === "play" || b.state === "verified") panel.playRequested(b.uid)
        else if (b.kind === "check" && b.state !== "checking" && b.state !== "failed") { panel.setState(b.uid, "checking"); dreamy.check(b.uid) }
        else if (b.kind === "ask" && b.query) panel.send(b.query)
        else if (b.kind === "nav" && b.action) panel.actionsRequested([b.action])
    }
    function send(t) { if (!t || !t.trim()) return; showHelp = false; var m = panel.messages.slice(); m.push({who: "you", text: t, buttons: []}); panel.messages = m; focusIdx = -1; dreamy.ask(t) }
    function setState(uid, st) { var m = panel.messages.slice(); for (var i = 0; i < m.length; i++) { var bs = m[i].buttons || []; for (var j = 0; j < bs.length; j++) if (bs[j].uid === uid) { bs[j].state = st; if (st === "verified") bs[j].kind = "play" } } panel.messages = m }
    Connections { target: dreamy
        function onAnswer(js) { var r = JSON.parse(js); var m = panel.messages.slice(); m.push({who: "dreamy", text: r.text, buttons: r.buttons || []}); panel.messages = m; focusIdx = -1
            if (r.actions && r.actions.length) panel.actionsRequested(r.actions) }
        function onVerified(uid, ok, note) { panel.setState(uid, ok ? "verified" : "failed"); if (!ok) { var m = panel.messages.slice(); m.push({who: "dreamy", text: "That copy did not pass the playback check (" + note + ").", buttons: []}); panel.messages = m } } }
    onOpenChanged: if (open) { input.forceActiveFocus(); focusIdx = -1; if (messages.length === 0) messages = [{who: "dreamy", text: "Hi, I'm Dreamy. Tell me what to do - open a lane, play a title, browse a year or genre, shuffle cartoons, explore the NAS, search YouTube, play music. Press \"what can I say?\" for the full list. I only hand you a Play button after a copy has actually decoded.", buttons: [{kind: "ask", label: "what can you do", query: "help"}, {kind: "ask", label: "show me 1940s film noir", query: "show me 1940s film noir"}, {kind: "ask", label: "cartoon block", query: "cartoon block"}]}] }
    Keys.onEscapePressed: panel.closeRequested()
}
