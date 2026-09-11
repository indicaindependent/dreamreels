import QtQuick
import QtQuick.Controls.Basic
Item {
    id: panel
    property bool open: false
    property var messages: []   // {who:"you"|"dreamy", text, buttons:[{kind,label,uid,query,state}]}
    signal playRequested(string uid)
    signal closeRequested()
    visible: open; anchors.fill: parent
    Rectangle { anchors.fill: parent; color: Qt.rgba(0,0,0,0.55); MouseArea { anchors.fill: parent; onClicked: panel.closeRequested() } }
    Rectangle { id: card; width: Math.min(parent.width * 0.62, 1180 * ui.s); height: parent.height - 120 * ui.s; anchors.centerIn: parent; radius: theme.radius * 1.4; color: theme.surface; border.width: 1; border.color: Qt.rgba(1,1,1,0.12)
        MouseArea { anchors.fill: parent }  // swallow
        Row { id: head; x: 28 * ui.s; y: 22 * ui.s; spacing: 16 * ui.s
            Image { source: dreamy.mascotUrl(dreamy.busy ? "think" : "idle"); width: 72 * ui.s; height: width; sourceSize: Qt.size(160, 160) }
            Column { anchors.verticalCenter: parent.verticalCenter
                Text { text: "Dreamy"; color: theme.text; font.family: theme.fontDisplay; font.weight: Font.Bold; font.pixelSize: 32 * ui.s }
                Text { text: dreamy.busy ? "looking…" : "Ask for a film, a person, a decade, or a YouTube video"; color: theme.muted; font.family: theme.fontBody; font.pixelSize: 20 * ui.s } } }
        ListView { id: list; anchors.top: head.bottom; anchors.topMargin: 18 * ui.s; anchors.bottom: inputBox.top; anchors.bottomMargin: 16 * ui.s; x: 28 * ui.s; width: card.width - 56 * ui.s; clip: true; spacing: 14 * ui.s; model: panel.messages
            onCountChanged: positionViewAtEnd()
            delegate: Column { width: list.width; spacing: 10 * ui.s
                Rectangle { anchors.right: modelData.who === "you" ? parent.right : undefined; width: Math.min(mt.implicitWidth + 36 * ui.s, list.width * 0.9); height: mt.implicitHeight + 28 * ui.s; radius: theme.radius; color: modelData.who === "you" ? theme.accent : theme.surface2
                    Text { id: mt; anchors.centerIn: parent; width: Math.min(implicitWidth, list.width * 0.9 - 36 * ui.s); text: modelData.text; color: modelData.who === "you" ? "#ffffff" : theme.text; wrapMode: Text.WordWrap; font.family: theme.fontBody; font.pixelSize: 24 * ui.s; lineHeight: 1.25 } }
                Flow { width: list.width; spacing: 10 * ui.s; visible: (modelData.buttons || []).length > 0
                    Repeater { model: modelData.buttons || []
                        Rectangle { property var b: modelData; height: 58 * ui.s; width: bl.implicitWidth + 64 * ui.s; radius: height / 2
                            color: b.kind === "play" ? theme.accent : b.kind === "check" ? (b.state === "checking" ? theme.surface2 : theme.surface2) : "transparent"; border.width: b.kind === "ask" || b.kind === "check" ? 2 : 0; border.color: b.kind === "check" ? theme.accent2 : theme.muted
                            Row { anchors.centerIn: parent; spacing: 10 * ui.s
                                Icon { name: b.kind === "play" ? "play" : b.kind === "check" ? (b.state === "failed" ? "close" : b.state === "checking" ? "clock" : "search") : "chat"; px: 24 * ui.s; color: b.kind === "play" ? "#ffffff" : theme.text; anchors.verticalCenter: parent.verticalCenter }
                                Text { id: bl; text: (b.kind === "check" ? (b.state === "checking" ? "Checking… " : b.state === "failed" ? "Won't play: " : "Check: ") : "") + b.label; color: b.kind === "play" ? "#ffffff" : theme.text; font.family: theme.fontBody; font.weight: Font.DemiBold; font.pixelSize: 22 * ui.s; anchors.verticalCenter: parent.verticalCenter } }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: {
                                if (b.kind === "play") panel.playRequested(b.uid)
                                else if (b.kind === "check" && b.state !== "checking" && b.state !== "failed") { panel.setState(b.uid, "checking"); dreamy.check(b.uid) }
                                else if (b.kind === "ask") { if (b.query === "__settings") panel.closeRequested(); else panel.send(b.query) } } } } } } } }
        Rectangle { id: inputBox; anchors.bottom: parent.bottom; anchors.bottomMargin: 22 * ui.s; x: 28 * ui.s; width: card.width - 56 * ui.s; height: 76 * ui.s; radius: theme.radius; color: theme.bg; border.width: 2; border.color: input.activeFocus ? theme.accent : Qt.rgba(1,1,1,0.12)
            TextField { id: input; anchors.fill: parent; anchors.margins: 10 * ui.s; placeholderText: "e.g. find me Orson Welles movies from the 1940s"; color: theme.text; placeholderTextColor: theme.muted; font.family: theme.fontBody; font.pixelSize: 26 * ui.s; background: null; enabled: !dreamy.busy
                onAccepted: { panel.send(text); text = "" } } }
    }
    function send(t) { if (!t || !t.trim()) return; var m = panel.messages.slice(); m.push({who: "you", text: t, buttons: []}); panel.messages = m; dreamy.ask(t) }
    function setState(uid, st) { var m = panel.messages.slice(); for (var i = 0; i < m.length; i++) { var bs = m[i].buttons || []; for (var j = 0; j < bs.length; j++) if (bs[j].uid === uid) { bs[j].state = st; if (st === "verified") bs[j].kind = "play" } } panel.messages = m }
    Connections { target: dreamy
        function onAnswer(js) { var r = JSON.parse(js); var m = panel.messages.slice(); m.push({who: "dreamy", text: r.text, buttons: r.buttons || []}); panel.messages = m }
        function onVerified(uid, ok, note) { panel.setState(uid, ok ? "verified" : "failed"); if (ok) backend.loadHome() } }
    onOpenChanged: if (open) { input.forceActiveFocus(); if (messages.length === 0) messages = [{who: "dreamy", text: "Hi, I'm Dreamy. Ask me for films, people, decades or genres, and I'll only hand you buttons that really play.", buttons: [{kind: "ask", label: "1940s film noir", query: "find me 1940s film noir"}, {kind: "ask", label: "Orson Welles in the 1940s?", query: "was Orson Welles in any movies from the 1940s?"}]}] }
    Keys.onEscapePressed: panel.closeRequested()
}
