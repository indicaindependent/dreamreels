"""DreamReels Observatory - the reporting + observation layer for the running player.

A tiny HTTP server inside the player process (default 0.0.0.0:8474, LAN/RFC1918 clients only) that
lets a human - or an agent acting as one - SEE and DRIVE the real screen instead of guessing:

  GET  /                 dashboard: live screenshot, playback telemetry, toasts, log tail, drive buttons
  GET  /status           JSON: app state, current item, mpv telemetry (hwdec-current, codec, drops, sync,
                         cache, fps, resolution), GPU/session facts, poster-cache coverage, counts
  GET  /shot.png         a real grab of the window (rendered frame, not a mock)
  GET  /log?n=200        tail of player.log
  GET  /toasts           the last 30 toasts with timestamps
  GET  /items?source=&q= look up uids to drive with
  POST /do               {"action": "key", "key": "Right"}          synthetic key press to the window
                         {"action": "click", "x": 0.5, "y": 0.5}    click at window-relative coords (0..1)
                         {"action": "play", "uid": "..."}           backend.play
                         {"action": "lane", "name": "chan83"}       backend.loadLane
                         {"action": "stop"|"pause"|"seek", "secs": 30}
                         {"action": "detail", "uid": "..."}         backend.openDetail
                         {"action": "set", "zone": "rails", "railIdx": 0, "colIdx": 0}  window properties

Everything that touches Qt runs on the GUI thread (posted through a QTimer and awaited), so the
server can never race the scene graph. All values are read live from mpv/Qt at request time - the
observatory never caches a measurement.
"""
from __future__ import annotations
import ipaddress, json, logging, os, platform, subprocess, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("dreamreels.player")

MPV_PROPS = ["hwdec-current", "hwdec", "video-codec", "video-format", "audio-codec-name", "ao", "vo",
             "time-pos", "duration", "pause", "paused-for-cache", "cache-buffering-state", "demuxer-cache-duration",
             "container-fps", "estimated-vf-fps", "display-fps", "estimated-display-fps", "frame-drop-count",
             "decoder-frame-drop-count", "vo-delayed-frame-count", "mistimed-frame-count", "avsync", "video-sync",
             "interpolation", "scale", "cscale", "dscale", "deband", "speed", "volume", "mute", "path", "media-title",
             "video-bitrate", "audio-bitrate", "width", "height", "dwidth", "dheight", "video-params/pixelformat",
             "video-params/colormatrix", "video-params/primaries", "video-params/gamma", "current-vo", "gpu-context",
             "hwdec-interop", "eof-reached", "seeking", "core-idle", "file-format"]


def _is_private(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
        return a.is_private or a.is_loopback or a.is_link_local
    except ValueError:
        return False


class Observatory:
    def __init__(self, app, win, backend, cfg, log_file: Path, version: str, host="0.0.0.0", port=8474):
        self.app, self.win, self.backend, self.cfg = app, win, backend, cfg
        self.log_file, self.version = log_file, version
        self.t0 = time.time(); self.host, self.port = host, port
        self._srv = None
        from PySide6.QtCore import QTimer, QObject, QEvent
        self._QTimer = QTimer
        self._lock = threading.Lock()
        self._queue: list = []
        self._pump = QTimer(); self._pump.setInterval(20); self._pump.timeout.connect(self._drain); self._pump.start()

    # ---------- GUI-thread bridge ----------
    def _drain(self):
        while True:
            with self._lock:
                if not self._queue: return
                fn, box, ev = self._queue.pop(0)
            try: box["r"] = fn()
            except Exception as e: box["e"] = repr(e)
            ev.set()

    def gui(self, fn, timeout=8.0):
        box, ev = {}, threading.Event()
        with self._lock: self._queue.append((fn, box, ev))
        if not ev.wait(timeout): raise TimeoutError("GUI thread did not answer in %.0fs" % timeout)
        if "e" in box: raise RuntimeError(box["e"])
        return box.get("r")

    # ---------- measurements ----------
    def mpv_state(self) -> dict:
        m = self.backend._player()
        if m is None: return {"available": False}
        out = {"available": True}
        for p in MPV_PROPS:
            try: v = m._get_property(p)
            except Exception as e: v = None
            out[p] = v if isinstance(v, (int, float, str, bool)) or v is None else str(v)
        return out

    def poster_coverage(self) -> dict:
        try:
            from ..core import db as dbmod
            c = dbmod.connect()
            rows = c.execute("SELECT source, COUNT(*) n, SUM(verified) v, SUM(poster_local IS NOT NULL AND poster_local!='') pl, SUM(poster IS NOT NULL AND poster!='') pr FROM items GROUP BY source").fetchall()
            c.close()
            return {r["source"]: {"items": r["n"], "verified": r["v"] or 0, "poster_local": r["pl"] or 0, "poster_remote": r["pr"] or 0} for r in rows}
        except Exception as e:
            return {"error": repr(e)}

    def system_facts(self) -> dict:
        f = {"python": platform.python_version(), "kernel": platform.release(), "session": os.environ.get("XDG_SESSION_TYPE"),
             "qpa": os.environ.get("QT_QPA_PLATFORM"), "wayland": os.environ.get("WAYLAND_DISPLAY"), "user": os.environ.get("USER")}
        for k, cmd in {"mpv": ["mpv", "--version"], "ffmpeg": ["ffmpeg", "-version"], "yt_dlp": ["yt-dlp", "--version"]}.items():
            try: f[k] = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.splitlines()[0][:120]
            except Exception as e: f[k] = f"ERR {e.__class__.__name__}"
        try:
            v = subprocess.run(["vainfo"], capture_output=True, text=True, timeout=8, env={**os.environ, "LIBVA_MESSAGING_LEVEL": "0"})
            drv = [l.strip() for l in (v.stdout + v.stderr).splitlines() if "Driver version" in l or "vainfo: Driver" in l]
            prof = [l.split(":")[0].strip() for l in v.stdout.splitlines() if l.strip().startswith("VAProfile")]
            f["vaapi"] = {"driver": drv[0] if drv else None, "profiles": len(prof), "h264": any("H264" in p for p in prof), "hevc": any("HEVC" in p for p in prof), "av1": any("AV1" in p for p in prof), "vp9": any("VP9" in p for p in prof)}
        except Exception as e:
            f["vaapi"] = {"error": e.__class__.__name__}
        try:
            import PySide6; from PySide6.QtQuick import QQuickWindow
            f["pyside"] = PySide6.__version__
            f["scenegraph"] = str(QQuickWindow.graphicsApi()).split(".")[-1]
        except Exception: pass
        return f

    def status(self) -> dict:
        def _win():
            return {"zone": self.win.property("zone"), "railIdx": self.win.property("railIdx"), "colIdx": self.win.property("colIdx"),
                    "detailBtn": self.win.property("detailBtn"), "topIdx": self.win.property("topIdx"), "size": [self.win.width(), self.win.height()],
                    "visible": self.win.isVisible(), "active": self.win.isActive(), "playing": self.backend.playing,
                    "rails": [r.get("label") for r in (self.backend.rails or [])] if isinstance(self.backend.rails, list) else None,
                    "detail": {k: self.backend.detail.get(k) for k in ("uid", "title", "verified", "source")} if isinstance(self.backend.detail, dict) and self.backend.detail else None,
                    "current_uid": getattr(self.backend, "_cur_uid", None)}
        st = {"app": {"version": self.version, "uptime_s": round(time.time() - self.t0, 1), "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")}}
        try: st["window"] = self.gui(_win)
        except Exception as e: st["window"] = {"error": repr(e)}
        try: st["mpv"] = self.gui(self.mpv_state)
        except Exception as e: st["mpv"] = {"error": repr(e)}
        st["toasts"] = [{"t": time.strftime("%H:%M:%S", time.localtime(t)), "msg": m} for t, m in self.backend.toasts[-10:]]
        st["library"] = self.poster_coverage()
        st["system"] = self.system_facts()
        return st

    def shot(self) -> bytes:
        def _grab():
            from PySide6.QtCore import QBuffer, QIODevice
            img = self.win.grabWindow(); buf = QBuffer(); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG"); return bytes(buf.data())
        return self.gui(_grab, timeout=15)

    # ---------- driving ----------
    def do(self, req: dict) -> dict:
        from PySide6.QtCore import Qt, QEvent, QPointF, QCoreApplication
        from PySide6.QtGui import QKeyEvent, QMouseEvent
        a = req.get("action")
        if a == "key":
            name = req.get("key", ""); mods = Qt.NoModifier
            key = getattr(Qt, f"Key_{name}", None)
            if key is None: return {"ok": False, "error": f"unknown key {name}"}
            text = name if len(name) == 1 else ""
            def _k():
                for et in (QEvent.KeyPress, QEvent.KeyRelease):
                    QCoreApplication.sendEvent(self.win, QKeyEvent(et, key, mods, text))
                return True
            return {"ok": self.gui(_k), "key": name}
        if a == "click":
            x, y = float(req.get("x", 0.5)), float(req.get("y", 0.5))
            def _c():
                w, h = self.win.width(), self.win.height(); pos = QPointF(x * w if x <= 1 else x, y * h if y <= 1 else y)
                for et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                    QCoreApplication.sendEvent(self.win, QMouseEvent(et, pos, pos, Qt.LeftButton, Qt.LeftButton if et == QEvent.MouseButtonPress else Qt.NoButton, Qt.NoModifier))
                return [pos.x(), pos.y()]
            return {"ok": True, "at": self.gui(_c)}
        if a == "play": return {"ok": self.gui(lambda: (self.backend.play(req["uid"], bool(req.get("resume", False))), True)[1])}
        if a == "detail": return {"ok": self.gui(lambda: (self.backend.openDetail(req["uid"]), True)[1])}
        if a == "lane": return {"ok": self.gui(lambda: (self.backend.loadLane(req["name"]), True)[1])}
        if a == "home": return {"ok": self.gui(lambda: (self.backend.loadHome(), True)[1])}
        if a == "stop": return {"ok": self.gui(lambda: (self.backend.stop(), True)[1])}
        if a == "pause": return {"ok": self.gui(lambda: (self.backend.togglePause(), True)[1])}
        if a == "seek": return {"ok": self.gui(lambda: (self.backend.seekRel(float(req.get("secs", 30))), True)[1])}
        if a == "set":
            def _s():
                for k in ("zone", "railIdx", "colIdx", "detailBtn", "topIdx"):
                    if k in req: self.win.setProperty(k, req[k])
                return True
            return {"ok": self.gui(_s)}
        return {"ok": False, "error": f"unknown action {a}"}

    def items(self, source=None, q=None, limit=25):
        from ..core import db as dbmod
        c = dbmod.connect(); sql = "SELECT uid,title,source,kind,verified,year FROM items WHERE 1=1"; args = []
        if source: sql += " AND source=?"; args.append(source)
        if q: sql += " AND title LIKE ?"; args.append(f"%{q}%")
        sql += " ORDER BY title LIMIT ?"; args.append(int(limit))
        rows = [dict(r) for r in c.execute(sql, args).fetchall()]; c.close(); return rows

    def log_tail(self, n=200) -> str:
        try:
            lines = self.log_file.read_text(errors="replace").splitlines()
            return "\n".join(l for l in lines if "delegatemodel" not in l and "gc.stat" not in l)[-60000:] if n <= 0 else "\n".join([l for l in lines if "delegatemodel" not in l and "gc.stat" not in l][-n:])
        except Exception as e: return f"log unreadable: {e}"

    # ---------- server ----------
    def start(self):
        obs = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _send(self, code, body, ctype="application/json"):
                if isinstance(body, (dict, list)): body = json.dumps(body, indent=1, default=str).encode()
                elif isinstance(body, str): body = body.encode()
                self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)
            def _guard(self):
                if not _is_private(self.client_address[0]): self._send(403, {"error": "LAN only"}); return False
                return True
            def do_GET(self):
                if not self._guard(): return
                u = urllib.parse.urlparse(self.path); qs = dict(urllib.parse.parse_qsl(u.query))
                try:
                    if u.path == "/status": return self._send(200, obs.status())
                    if u.path == "/shot.png": return self._send(200, obs.shot(), "image/png")
                    if u.path == "/log": return self._send(200, obs.log_tail(int(qs.get("n", 200))), "text/plain; charset=utf-8")
                    if u.path == "/toasts": return self._send(200, [{"t": t, "msg": m} for t, m in obs.backend.toasts])
                    if u.path == "/items": return self._send(200, obs.items(qs.get("source"), qs.get("q"), int(qs.get("limit", 25))))
                    if u.path == "/do": return self._send(200, obs.do(qs))
                    if u.path == "/": return self._send(200, DASHBOARD, "text/html; charset=utf-8")
                    self._send(404, {"error": "no such route"})
                except Exception as e:
                    log.exception("observatory %s failed", u.path); self._send(500, {"error": repr(e)})
            def do_POST(self):
                if not self._guard(): return
                n = int(self.headers.get("Content-Length", 0) or 0); raw = self.rfile.read(n) if n else b"{}"
                try: req = json.loads(raw or b"{}")
                except Exception: req = dict(urllib.parse.parse_qsl(raw.decode(errors="replace")))
                try: self._send(200, obs.do(req))
                except Exception as e: log.exception("observatory do failed"); self._send(500, {"error": repr(e)})
        try:
            self._srv = ThreadingHTTPServer((self.host, self.port), H); self._srv.daemon_threads = True
            threading.Thread(target=self._srv.serve_forever, daemon=True, name="observatory").start()
            log.info("observatory listening on http://%s:%d/  (LAN clients only)", self.host, self.port)
        except OSError as e:
            log.error("observatory could not bind %s:%d: %s", self.host, self.port, e)


DASHBOARD = """<!doctype html><html><head><meta charset="utf-8"><title>DreamReels Observatory</title>
<style>
body{margin:0;background:#0b0c12;color:#e6e6ef;font:14px/1.4 system-ui,sans-serif}
header{padding:10px 16px;background:#141626;display:flex;gap:16px;align-items:center;border-bottom:1px solid #26283d}
h1{font-size:16px;margin:0;font-weight:600}.muted{color:#8b8fa8}
main{display:grid;grid-template-columns:minmax(480px,1fr) 420px;gap:12px;padding:12px}
section{background:#141626;border:1px solid #26283d;border-radius:8px;padding:10px}
img#shot{width:100%;border-radius:6px;background:#000;display:block}
table{width:100%;border-collapse:collapse}td{padding:2px 6px;border-bottom:1px solid #1f2134;vertical-align:top}td:first-child{color:#8b8fa8;white-space:nowrap}
.ok{color:#4fd18b}.warn{color:#f2b544}.bad{color:#ff6b6b}
button{background:#26283d;color:#e6e6ef;border:1px solid #3a3d5c;border-radius:6px;padding:6px 10px;cursor:pointer}button:hover{background:#33365a}
.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;max-width:220px}.row{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
pre{background:#0b0c12;border:1px solid #26283d;border-radius:6px;padding:8px;max-height:260px;overflow:auto;font-size:12px;white-space:pre-wrap}
input{background:#0b0c12;color:#e6e6ef;border:1px solid #3a3d5c;border-radius:6px;padding:6px}
</style></head><body>
<header><h1>DreamReels Observatory</h1><span class="muted" id="hdr">connecting</span><label class="muted" style="margin-left:auto"><input type="checkbox" id="live" checked> live (2 s)</label></header>
<main>
<div><section><img id="shot" alt="live screen"></section>
<section><b>Drive</b><div class="row"><div class="pad">
<span></span><button data-k="Up">Up</button><span></span>
<button data-k="Left">Left</button><button data-k="Return">Select</button><button data-k="Right">Right</button>
<span></span><button data-k="Down">Down</button><span></span></div>
<div><div class="row"><button data-k="Escape">Back</button><button data-k="Space">Play/Pause</button><button data-k="P">Pause</button><button data-k="S">Subs</button><button data-k="A">Audio</button></div>
<div class="row"><button data-a="stop">Stop</button><button data-a="home">Home</button><button data-a="seek" data-secs="-30">-30 s</button><button data-a="seek" data-secs="30">+30 s</button></div>
<div class="row"><input id="uid" placeholder="uid (see /items)" size="34"><button id="playuid">Play uid</button><button id="detailuid">Open detail</button></div>
<div class="row">Lane: <button data-l="pd">Public Domain</button><button data-l="chan83">Channel 83</button><button data-l="toontown">Toon Town</button><button data-l="nas">NAS</button><button data-l="youtube">YouTube</button><button data-l="music">Music</button></div></div></div></section></div>
<div><section><b>Playback telemetry</b><table id="mpv"></table></section>
<section><b>Window / app</b><table id="win"></table></section>
<section><b>Library</b><table id="lib"></table></section>
<section><b>System</b><table id="sys"></table></section>
<section><b>Toasts</b><pre id="toasts"></pre></section>
<section><b>player.log (tail)</b><pre id="log"></pre></section></div>
</main>
<script>
const $=s=>document.querySelector(s);const rows=(el,o)=>{el.innerHTML=Object.entries(o||{}).map(([k,v])=>{let c='';if(k=='hwdec-current')c=v&&v!='no'?'ok':'warn';if(/drop|mistimed|delayed/.test(k))c=(v>0)?'warn':'ok';return `<tr><td>${k}</td><td class="${c}">${v===null?'<span class=muted>null</span>':(typeof v=='object'?JSON.stringify(v):v)}</td></tr>`}).join('')};
async function tick(){try{const s=await (await fetch('/status')).json();$('#hdr').textContent=`v${s.app.version} · up ${s.app.uptime_s}s · ${s.app.time}`;
const m=s.mpv||{};const keep=['hwdec-current','video-codec','video-format','width','height','dwidth','dheight','container-fps','estimated-vf-fps','display-fps','frame-drop-count','decoder-frame-drop-count','vo-delayed-frame-count','mistimed-frame-count','avsync','video-sync','interpolation','scale','cscale','deband','time-pos','duration','pause','paused-for-cache','demuxer-cache-duration','video-bitrate','audio-codec-name','ao','media-title'];const mm={};keep.forEach(k=>mm[k]=m[k]);rows($('#mpv'),mm);
rows($('#win'),s.window);const lib={};Object.entries(s.library||{}).forEach(([k,v])=>lib[k]=`${v.verified}/${v.items} verified · posters local ${v.poster_local} remote ${v.poster_remote}`);rows($('#lib'),lib);rows($('#sys'),s.system);
$('#toasts').textContent=(s.toasts||[]).map(t=>t.t+'  '+t.msg).join('\\n')||'(none)';$('#shot').src='/shot.png?t='+Date.now();
const lg=await (await fetch('/log?n=40')).text();$('#log').textContent=lg;}catch(e){$('#hdr').textContent='offline: '+e}}
async function post(o){await fetch('/do',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)});setTimeout(tick,400)}
document.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>post({action:'key',key:b.dataset.k}));
document.querySelectorAll('[data-a]').forEach(b=>b.onclick=()=>post({action:b.dataset.a,secs:b.dataset.secs}));
document.querySelectorAll('[data-l]').forEach(b=>b.onclick=()=>post({action:'lane',name:b.dataset.l}));
$('#playuid').onclick=()=>post({action:'play',uid:$('#uid').value});$('#detailuid').onclick=()=>post({action:'detail',uid:$('#uid').value});
$('#shot').onclick=e=>{const r=e.target.getBoundingClientRect();post({action:'click',x:(e.clientX-r.left)/r.width,y:(e.clientY-r.top)/r.height})};
tick();setInterval(()=>{if($('#live').checked)tick()},2000);
</script></body></html>"""
