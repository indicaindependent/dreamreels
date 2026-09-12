"""Backend exposed to QML. Reads the v2 schema, drives playback through the embedded MpvObject.
Playback truth: `playing` flips only after mpv reports a video/audio track and file-loaded."""
from __future__ import annotations
import json, os, sqlite3, threading, time
from PySide6.QtCore import QObject, Signal, Slot, Property, QTimer
import logging, time
log = logging.getLogger("dreamreels.player")
from ..core import db as dbmod
from ..core.paths import POSTER_CACHE
from .models import ItemModel

SOURCE_LABEL = {"pd": "Public Domain", "chan83": "Channel 83", "toontown": "Toon Town", "nas": "NAS", "youtube": "YouTube", "music": "Music"}

def _poster(row) -> str:
    pl = row["poster_local"] if "poster_local" in row.keys() else None
    if pl and os.path.exists(pl): return "file://" + pl
    return row["poster"] or ""

def _row_to_item(row, state=None) -> dict:
    prog = 0.0
    if state and state["duration_sec"]: prog = max(0.0, min(1.0, (state["resume_sec"] or 0) / state["duration_sec"]))
    sub = []
    if row["year"]: sub.append(str(row["year"]))
    if row["kind"] == "episode" and row["season"] is not None: sub.append(f"S{row['season']:02d}E{(row['episode'] or 0):02d}")
    if row["runtime_min"]: sub.append(f"{row['runtime_min']} min")
    return {"uid": row["uid"], "title": row["title"], "year": row["year"] or 0, "poster": _poster(row), "backdrop": row["backdrop_local"] and "file://" + row["backdrop_local"] or (row["backdrop"] or ""),
            "blurb": row["blurb"] or "", "source": row["source"], "kind": row["kind"], "verified": bool(row["verified"]), "progress": prog,
            "subtitle": " · ".join(sub), "badge": SOURCE_LABEL.get(row["source"], row["source"])}

class Backend(QObject):
    railsChanged = Signal(); playingChanged = Signal(); positionChanged = Signal(); detailChanged = Signal()
    playbackStarted = Signal(); playbackStopped = Signal(); toast = Signal(str)
    def __init__(self, cfg: dict, mpv_getter=None):
        super().__init__(); self.cfg = cfg; self._mpv_getter = mpv_getter; self._mpv = None
        self._rails: list[dict] = []; self._models: dict[str, ItemModel] = {}
        self._playing = False; self._pos = 0.0; self._dur = 0.0; self._paused = False; self._cur_uid = None
        self._detail = {}
        self.toasts = []  # observatory: last 30 toasts with timestamps
        self.toast.connect(lambda m: (self.toasts.append((time.time(), m)), self.toasts.__delitem__(slice(0, max(0, len(self.toasts) - 30))), log.info("toast: %s", m)))
        self._t = QTimer(self); self._t.setInterval(1000); self._t.timeout.connect(self._tick)
        self.loadHome()
    # ---------- data ----------
    def _q(self, sql, args=()):
        c = dbmod.connect()
        try: return c.execute(sql, args).fetchall()
        finally: c.close()
    def _items(self, sql, args=()):
        rows = self._q(sql, args); out = []
        c = dbmod.connect()
        try:
            for r in rows:
                st = c.execute("SELECT * FROM state WHERE uid=?", (r["uid"],)).fetchone()
                out.append(_row_to_item(r, st))
        finally: c.close()
        return out
    def _model(self, key, items):
        m = self._models.get(key)
        if m is None: m = ItemModel(items, parent=self); self._models[key] = m
        else: m.setItems(items)
        return m
    @Slot()
    def loadHome(self):
        rails = []
        cw = self._items("SELECT i.* FROM items i JOIN state s ON s.uid=i.uid WHERE s.resume_sec>30 AND s.duration_sec>0 AND s.resume_sec < s.duration_sec*0.95 AND i.blocked=0 ORDER BY s.last_played DESC LIMIT 20")
        if cw: rails.append({"id": "continue", "label": "Continue Watching", "model": self._model("continue", cw)})
        enabled = self.cfg.get("sources", {})
        order = [("nas", "My NAS", "nas"), ("pd", "Public Domain", "publicdomain"), ("chan83", "Channel 83", "chan83"), ("toontown", "Toon Town", "toontown"), ("youtube", "YouTube", "youtube"), ("music", "Music", "nas")]
        for src, label, cfgkey in order:
            if not enabled.get(cfgkey, True) and src != "music": continue
            its = self._items("SELECT * FROM items WHERE source=? AND blocked=0 AND kind IN ('movie','video','short','episode','track') ORDER BY added DESC LIMIT 30", (src,))
            if its: rails.append({"id": src, "label": label, "model": self._model(src, its)})
        for dec, in self._q("SELECT DISTINCT decade FROM items WHERE decade IS NOT NULL AND blocked=0 AND kind='movie' ORDER BY decade DESC LIMIT 4"):
            its = self._items("SELECT * FROM items WHERE decade=? AND blocked=0 AND kind='movie' ORDER BY downloads DESC, added DESC LIMIT 30", (dec,))
            if its: rails.append({"id": f"decade:{dec}", "label": f"{dec}s", "model": self._model(f"decade:{dec}", its)})
        self._rails = rails; self.railsChanged.emit()
    @Slot(str)
    def loadLane(self, lane):
        """One lane, deep: rails grouped the way that lane is naturally browsed. Uses the same rail UI as Home."""
        rails = []
        def add(rid, label, its):
            if its: rails.append({"id": rid, "label": label, "model": self._model(rid, its)})
        if lane == "pd":
            add("pd:verified", "Ready to play", self._items("SELECT * FROM items WHERE source='pd' AND verified=1 AND blocked=0 ORDER BY added DESC LIMIT 40"))
            for dec, in self._q("SELECT DISTINCT decade FROM items WHERE source='pd' AND decade IS NOT NULL AND blocked=0 ORDER BY decade"):
                add(f"decade:{dec}", f"{dec}s", self._items("SELECT * FROM items WHERE source='pd' AND decade=? AND blocked=0 ORDER BY downloads DESC, title LIMIT 60", (dec,)))
            for g in ("Film-Noir", "Horror", "Sci-Fi", "Comedy", "Drama", "Western", "Mystery", "Thriller", "Romance", "Adventure", "Crime", "Documentary"):
                add(f"genre:{g}", g, self._items("SELECT * FROM items WHERE source='pd' AND genres LIKE ? AND blocked=0 ORDER BY downloads DESC, title LIMIT 60", (f"%{g}%",)))
        elif lane in ("chan83", "toontown"):
            for uid, title, years in self._q("SELECT uid,title,years FROM shows WHERE source=? ORDER BY title", (lane,)):
                add(f"show:{uid}", f"{title}" + (f"  {years}" if years else ""), self._items("SELECT * FROM items WHERE show_uid=? AND blocked=0 ORDER BY season, episode, title", (uid,)))
        elif lane == "nas":
            for kind, label in (("movie", "Movies"), ("episode", "TV"), ("video", "Videos"), ("track", "Music")):
                add(f"nas:{kind}", label, self._items("SELECT * FROM items WHERE source='nas' AND kind=? AND blocked=0 ORDER BY title LIMIT 200", (kind,)))
            add("nas:recent", "Recently added", self._items("SELECT * FROM items WHERE source='nas' AND blocked=0 ORDER BY added DESC LIMIT 40"))
        elif lane == "youtube":
            add("yt:latest", "Latest", self._items("SELECT * FROM items WHERE source='youtube' AND blocked=0 ORDER BY added DESC LIMIT 60"))
            for ch, in self._q("SELECT DISTINCT director FROM items WHERE source='youtube' AND director IS NOT NULL AND director!='' ORDER BY director"):
                add(f"yt:{ch}", ch, self._items("SELECT * FROM items WHERE source='youtube' AND director=? AND blocked=0 ORDER BY added DESC LIMIT 60", (ch,)))
        elif lane == "music":
            add("music:all", "All tracks", self._items("SELECT * FROM items WHERE (source='music' OR kind='track') AND blocked=0 ORDER BY title LIMIT 300"))
        if not rails: rails.append({"id": f"{lane}:empty", "label": {"pd": "Public Domain", "chan83": "Channel 83", "toontown": "Toon Town", "nas": "NAS", "youtube": "YouTube", "music": "Music"}.get(lane, lane) + " - nothing here yet", "model": self._model("empty", [])})
        self._rails = rails; self.railsChanged.emit()
    @Slot(str)
    def verifyNow(self, uid):
        """Decode-verify one title on demand (detail page 'Check' button); reopens the detail with the result."""
        import threading
        def work():
            from .. import grower
            c = dbmod.connect()
            try: res = grower._verify_one(c, uid); c.commit()
            except Exception as e: res = f"error {e}"
            finally: c.close()
            self.toast.emit("Plays" if res == "verified" else f"Could not verify ({res})"); self.openDetail(uid)
        self.toast.emit("Checking that this really plays..."); threading.Thread(target=work, daemon=True).start()
    @Property("QVariantList", notify=railsChanged)
    def rails(self): return [{"id": r["id"], "label": r["label"]} for r in self._rails]
    @Slot(int, result=QObject)
    def railModel(self, i): return self._rails[i]["model"] if 0 <= i < len(self._rails) else None
    @Slot(int, int, result="QVariant")
    def railItem(self, i, j): return self._rails[i]["model"].get(j) if 0 <= i < len(self._rails) else {}
    @Slot(str, str, result=QObject)
    def browse(self, mode, key):
        if mode == "source": its = self._items("SELECT * FROM items WHERE source=? AND blocked=0 ORDER BY title", (key,))
        elif mode == "decade": its = self._items("SELECT * FROM items WHERE decade=? AND blocked=0 ORDER BY year, title", (int(key),))
        elif mode == "genre": its = self._items("SELECT * FROM items WHERE genres LIKE ? AND blocked=0 ORDER BY year, title", (f"%{key}%",))
        elif mode == "show": its = self._items("SELECT * FROM items WHERE show_uid=? AND blocked=0 ORDER BY season, episode", (key,))
        elif mode == "search": its = self._items("SELECT * FROM items WHERE (title LIKE ? OR director LIKE ? OR blurb LIKE ?) AND blocked=0 ORDER BY title LIMIT 200", (f"%{key}%",)*3)
        else: its = []
        return self._model(f"browse:{mode}:{key}", its)
    @Slot(str)
    def openDetail(self, uid):
        r = self._q("SELECT * FROM items WHERE uid=?", (uid,)); st = self._q("SELECT * FROM state WHERE uid=?", (uid,))
        if not r: self._detail = {}; self.detailChanged.emit(); return
        d = _row_to_item(r[0], st[0] if st else None)
        d.update({"director": r[0]["director"] or "", "genres": r[0]["genres"] or "", "resume": (st[0]["resume_sec"] if st else 0) or 0, "favorite": bool(st and st[0]["favorite"])})
        self._detail = d; self.detailChanged.emit()
    @Property("QVariant", notify=detailChanged)
    def detail(self): return self._detail
    @Slot()
    def closeDetail(self): self._detail = {}; self.detailChanged.emit()
    @Slot(str)
    def toggleFavorite(self, uid):
        c = dbmod.connect(); c.execute("INSERT INTO state(uid,favorite) VALUES(?,1) ON CONFLICT(uid) DO UPDATE SET favorite=1-favorite", (uid,)); c.commit(); c.close(); self.openDetail(uid)
    # ---------- playback ----------
    def _player(self):
        if self._mpv is None and self._mpv_getter: self._mpv = self._mpv_getter()
        return self._mpv
    @Slot(str)
    def toastMsg(self, m): self.toast.emit(m)
    @Slot(str)
    @Slot(str, bool)
    def play(self, uid, resume=True):
        if not uid: log.warning("play(): EMPTY uid from QML"); self.toast.emit("Nothing selected"); return  # QML calls play(uid) with one arg; without the 1-arg overload Qt logs 'Insufficient arguments' and the Play button is dead
        r = self._q("SELECT * FROM items WHERE uid=?", (uid,))
        if not r: log.warning("play(%s): not found", uid); self.toast.emit("Not found"); return
        row = r[0]; url = row["path"] or row["stream_url"]
        if not url: log.warning("play(%s): no path/stream_url", uid); self.toast.emit("No playable source yet - ask Dreamy to find one"); return
        m = self._player()
        if m is None: log.error("play(%s): mpv object not found in the QML scene", uid); self.toast.emit("Player unavailable"); return
        log.info("play(%s) resume=%s url=%s", uid, resume, url[:120])
        self._started_at = time.time(); self._first_frame = False
        start = 0.0
        if resume:
            st = self._q("SELECT resume_sec,duration_sec FROM state WHERE uid=?", (uid,))
            if st and st[0]["resume_sec"] and st[0]["duration_sec"] and st[0]["resume_sec"] < st[0]["duration_sec"] * 0.95: start = float(st[0]["resume_sec"])
        self._cur_uid = uid; self._paused = False
        def go():
            try:
                m.play(url)
                if start > 5: m.wait_for_property("duration", lambda v: v is not None, timeout=20); m.seek(start, reference="absolute")
            except Exception as e: log.error("play(%s): mpv raised %s", uid, e); self.toast.emit(f"Playback failed: {e}")
        threading.Thread(target=go, daemon=True).start()
        self._playing = True; self.playingChanged.emit(); self.playbackStarted.emit(); self._t.start()
        c = dbmod.connect(); c.execute("INSERT INTO state(uid,last_played,play_count) VALUES(?,?,1) ON CONFLICT(uid) DO UPDATE SET last_played=excluded.last_played, play_count=play_count+1", (uid, time.time())); c.commit(); c.close()
    def _tick(self):
        m = self._player()
        if not m: return
        try:
            p = m.time_pos; d = m.duration; eof = m.eof_reached
        except Exception as e: log.warning("tick: mpv property read failed: %s", e); return
        if p is not None and not getattr(self, "_first_frame", False):
            self._first_frame = True; log.info("playback started: time_pos=%.2f duration=%s video=%s", float(p), d, getattr(m, "video_format", None))
        if p is None and self._playing and time.time() - getattr(self, "_started_at", time.time()) > 15:  # armed but nothing decoded: say so instead of a silent black screen
            log.error("playback watchdog: no time-pos after 15 s (uid=%s)", self._cur_uid); self.toast.emit("Playback did not start - see player.log"); self.stop(); return
        if p is not None: self._pos = float(p)
        if d: self._dur = float(d)
        self.positionChanged.emit()
        if eof and self._playing: self.stop()
        elif int(self._pos) % 10 == 0: self._save_resume()
    def _save_resume(self):
        if not self._cur_uid or not self._dur: return
        c = dbmod.connect(); c.execute("INSERT INTO state(uid,resume_sec,duration_sec) VALUES(?,?,?) ON CONFLICT(uid) DO UPDATE SET resume_sec=excluded.resume_sec,duration_sec=excluded.duration_sec", (self._cur_uid, self._pos, self._dur)); c.commit(); c.close()
    @Slot()
    def stop(self):
        self._save_resume(); self._t.stop()
        m = self._player()
        try:
            if m: m.command("stop")
        except Exception: pass
        self._playing = False; self.playingChanged.emit(); self.playbackStopped.emit(); self.loadHome()
    @Slot()
    def togglePause(self):
        m = self._player()
        if m: self._paused = not self._paused; m.pause = self._paused; self.positionChanged.emit()
    @Slot(float)
    def seekRel(self, secs):
        m = self._player()
        if m:
            try: m.seek(secs, reference="relative")
            except Exception: pass
    @Slot()
    def cycleSub(self):
        m = self._player()
        if m: m.command("cycle", "sub")
    @Slot()
    def cycleAudio(self):
        m = self._player()
        if m: m.command("cycle", "audio")
    @Property(bool, notify=playingChanged)
    def playing(self): return self._playing
    @Property(bool, notify=positionChanged)
    def paused(self): return self._paused
    @Property(float, notify=positionChanged)
    def position(self): return self._pos
    @Property(float, notify=positionChanged)
    def duration(self): return self._dur
    @Property(str, notify=positionChanged)
    def nowPlayingTitle(self):
        if not self._cur_uid: return ""
        r = self._q("SELECT title FROM items WHERE uid=?", (self._cur_uid,)); return r[0]["title"] if r else ""
