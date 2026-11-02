"""Backend exposed to QML. Reads the v2 schema, drives playback through the embedded MpvObject.
Playback truth: `playing` flips only after mpv reports a video/audio track and file-loaded."""
from __future__ import annotations
import shutil
import json, os, re, sqlite3, threading, time
from PySide6.QtCore import QObject, Signal, Slot, Property, QTimer
import logging, time
log = logging.getLogger("dreamreels.player")
from ..core import db as dbmod
from ..core.paths import POSTER_CACHE
from .models import ItemModel
from PySide6.QtCore import QEvent
_EVT = QEvent.Type(QEvent.registerEventType())
class _SqlList(list):
    """Phase R: a list of rail items that remembers the SQL that produced it (sql, args)."""
    sql = None; args = ()

class _CallEvent(QEvent):
    """Carries a callable from a worker thread to the GUI thread (Phase B)."""
    def __init__(self, f): super().__init__(_EVT); self.f = f

SOURCE_LABEL = {"pd": "Public Domain", "chan83": "Channel 83", "toontown": "Toon Town", "gameshow": "Game Shows", "nick90s": "90s Nick", "sesame": "Classic Sesame Street", "nas": "NAS", "youtube": "YouTube", "music": "Music"}

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
            "subtitle": " · ".join(sub), "badge": ("Trailer" if _tr(row) == 1 else "Short" if _tr(row) == 2 else SOURCE_LABEL.get(row["source"], row["source"]))}
def _tr(row):
    try: return row["trailer"] or 0
    except (IndexError, KeyError): return 0

class Backend(QObject):
    railsChanged = Signal(); pageChanged = Signal(); inputRequest = Signal(str, str); playingChanged = Signal(); positionChanged = Signal(); detailChanged = Signal()
    playbackStarted = Signal(); playbackStopped = Signal(); toast = Signal(str)
    def __init__(self, cfg: dict, mpv_getter=None):
        super().__init__(); self.cfg = cfg; self._mpv_getter = mpv_getter; self._mpv = None
        self._rails: list[dict] = []; self._models: dict[str, ItemModel] = {}
        self._playing = False; self._pos = 0.0; self._dur = 0.0; self._paused = False; self._cur_uid = None
        self._detail = {}
        self.toasts = []  # observatory: last 30 toasts with timestamps
        self.toast.connect(lambda m: (self.toasts.append((time.time(), m)), self.toasts.__delitem__(slice(0, max(0, len(self.toasts) - 30))), log.info("toast: %s", m)))
        self._t = QTimer(self); self._t.setInterval(1000); self._t.timeout.connect(self._tick)
        try:   # v2.1.0: Channel 83 is pre-1970 only; hide anything already installed outside that era (reversible, idempotent)
            from ..sources.lanes_seed import prune_chan83_era
            n = prune_chan83_era()
            if n: log.info("Channel 83 era rule hid %d rows", n)
        except Exception as e: log.warning("chan83 era prune failed: %s", e)
        self.loadHome()
    # ---------- data ----------
    def _q(self, sql, args=()):
        c = dbmod.connect()
        try: return c.execute(sql, args).fetchall()
        finally: c.close()
    def _items(self, sql, args=()):
        rows = self._q(sql, args); out = []
        c = dbmod.connect()
        try:   # Phase P (Oct 29 2026): one state query per 400 uids, not one per title
            uids = [r["uid"] for r in rows]; sts = {}
            for k in range(0, len(uids), 400):
                ch = uids[k:k + 400]
                for st in c.execute(f"SELECT * FROM state WHERE uid IN ({','.join('?' * len(ch))})", ch).fetchall(): sts[st["uid"]] = st
            for r in rows: out.append(_row_to_item(r, sts.get(r["uid"])))
        finally: c.close()
        out = _SqlList(out); out.sql, out.args = sql, tuple(args)  # Phase R
        return out
    # ---- Phase R (Oct 13 2026): rails are PREVIEWS of a query; the query itself is kept so 'See all N' can open the whole thing
    _LIMIT_RE = re.compile(r"\s+LIMIT\s+\d+\s*$", re.I)
    def _rail_full_limit(self):
        try: return int((self.cfg.get('ui') or {}).get('rail_full', 500))
        except Exception: return 500
    def _rail_total(self, sql, args):
        base = self._LIMIT_RE.sub('', sql)
        try: return int(self._q(f'SELECT COUNT(*) FROM ({base})', tuple(args))[0][0])
        except Exception as e: log.warning('rail count failed: %s', e); return None
    def _model(self, key, items):
        sql = getattr(items, 'sql', None); args = getattr(items, 'args', ())
        total = None
        if sql and self._LIMIT_RE.search(sql):
            total = self._rail_total(sql, args)
            if total is not None and total > len(items):
                if not hasattr(self, '_rail_sql'): self._rail_sql = {}
                self._rail_sql[key] = (self._LIMIT_RE.sub('', sql), tuple(args), total)
                items = list(items) + [{'uid': f'__more__:{key}', 'title': f'See all {total:,}', 'year': '', 'poster': None, 'backdrop': None, 'blurb': '', 'source': 'ui', 'kind': 'more', 'verified': 1, 'progress': 0, 'subtitle': f'{total:,} titles', 'badge': ''}]
        m = self._models.get(key)
        if m is None: m = ItemModel(items, parent=self); self._models[key] = m
        else: m.setItems(items)
        if hasattr(m, 'setTotal'): m.setTotal(total if total is not None else len(items))
        return m
    # ---- Phase P (Oct 29 2026): grids are PAGED, never capped. First page now, the next page as you scroll near the bottom.
    def _grid_page(self):
        try: return max(60, int((self.cfg.get('ui') or {}).get('grid_page', 240)))
        except Exception: return 240
    def _paged_grid(self, lane, path, title, chips, sql_base, args, key):
        args = tuple(args)
        try: total = int(self._q(f'SELECT COUNT(*) FROM ({sql_base})', args)[0][0])
        except Exception as e: log.warning('grid count failed: %s', e); total = None
        its = self._items(f'{sql_base} LIMIT {self._grid_page()} OFFSET 0', args)
        self._gridq = {'sql': sql_base, 'args': args, 'total': total if total is not None else len(its), 'loaded': len(its), 'key': key}
        self._set_page(lane, path, f"{title}  ({self._gridq['total']:,})", chips, self._grid(key, list(its)), view='grid')
    @Slot()
    def gridMore(self):
        g = getattr(self, '_gridq', None)
        if not g or self.page.get('view') != 'grid' or g['loaded'] >= g['total']: return
        its = self._items(f"{g['sql']} LIMIT {self._grid_page()} OFFSET {g['loaded']}", g['args'])
        if not its: g['total'] = g['loaded']; return
        n = self.GRID_COLS; base = g['loaded']; add = []
        for i in range(0, len(its), n): add.append({"id": f"{g['key']}:{base + i}", "label": "", "model": self._model(f"{g['key']}:{base + i}", list(its[i:i + n]))})
        g['loaded'] += len(its); self._rails = list(self._rails) + add; self.railsChanged.emit()
    def _push_hist(self):
        p = self.page
        if not hasattr(self, '_hist'): self._hist = []
        self._hist.append((p.get('lane', 'home'), list(p.get('path', []))))
        del self._hist[:-40]
    @Slot(str)
    def openRail(self, key):
        """Phase R: open a whole rail as a paged grid. key = the rail/model key registered by _model."""
        ent = getattr(self, '_rail_sql', {}).get(key)
        if not ent: self.toast.emit('Nothing more to show'); return
        sql, args, total = ent
        label = next((r['label'] for r in self._rails if r.get('id') == key), key)
        p = self.page; lane = p.get('lane', 'home'); path = list(p.get('path', [])) + ['rail', key]
        self._push_hist()
        self._paged_grid(lane, path, label, p.get('chips'), sql, args, f'rail:{key}')
    @Slot()
    def loadHome(self):
        rails = []
        cw = self._items("SELECT i.* FROM items i JOIN state s ON s.uid=i.uid WHERE s.resume_sec>30 AND s.duration_sec>0 AND s.resume_sec < s.duration_sec*0.95 AND i.blocked=0 ORDER BY s.last_played DESC LIMIT 20")
        if cw: rails.append({"id": "continue", "label": "Continue Watching", "model": self._model("continue", cw)})
        rp = self._items("SELECT i.* FROM items i JOIN state s ON s.uid=i.uid WHERE s.last_played IS NOT NULL AND i.blocked=0 ORDER BY s.last_played DESC LIMIT 30")   # v2.1.0
        if rp: rails.append({"id": "recent", "label": "Recently Played", "model": self._model("recent", rp)})
        enabled = self.cfg.get("sources", {})
        order = [("nas", "My NAS", "nas"), ("pd", "Public Domain", "publicdomain"), ("chan83", "Channel 83", "chan83"), ("gameshow", "Game Shows", "gameshow"), ("nick90s", "90s Nick", "nick90s"), ("sesame", "Classic Sesame Street", "sesame"), ("toontown", "Toon Town", "toontown"), ("youtube", "YouTube", "youtube"), ("music", "Music", "nas")]
        for src, label, cfgkey in order:
            if not enabled.get(cfgkey, True) and src != "music": continue
            its = self._items("SELECT * FROM items WHERE source=? AND blocked=0 AND trailer=0 AND kind IN ('movie','video','short','episode','track') ORDER BY added DESC LIMIT 30", (src,))
            if its: rails.append({"id": src, "label": label, "model": self._model(src, its)})
        for dec, in self._q("SELECT DISTINCT decade FROM items WHERE decade IS NOT NULL AND blocked=0 AND trailer=0 AND kind='movie' ORDER BY decade DESC LIMIT 4"):
            its = self._items("SELECT * FROM items WHERE decade=? AND blocked=0 AND trailer=0 AND kind='movie' ORDER BY downloads DESC, added DESC LIMIT 30", (dec,))
            if its: rails.append({"id": f"decade:{dec}", "label": f"{dec}s", "model": self._model(f"decade:{dec}", its)})
        self._rails = rails; self.railsChanged.emit()
    @Slot(str)
    def loadLane(self, lane):
        """One lane, deep: rails grouped the way that lane is naturally browsed. Uses the same rail UI as Home."""
        rails = []
        def add(rid, label, its):
            if its: rails.append({"id": rid, "label": label, "model": self._model(rid, its)})
        if lane == "pd":
            add("pd:verified", "Ready to play", self._items("SELECT * FROM items WHERE source='pd' AND verified=1 AND blocked=0 AND trailer=0 ORDER BY added DESC LIMIT 40"))
            for dec, in self._q("SELECT DISTINCT decade FROM items WHERE source='pd' AND decade IS NOT NULL AND blocked=0 AND trailer=0 ORDER BY decade"):
                add(f"decade:{dec}", f"{dec}s", self._items("SELECT * FROM items WHERE source='pd' AND decade=? AND blocked=0 AND trailer=0 ORDER BY downloads DESC, title LIMIT 60", (dec,)))
            add("pd:tvmovie", "TV Movies of the 70s & 80s", self._items("SELECT * FROM items WHERE source='pd' AND blocked=0 AND trailer=0 AND genres LIKE '%TV Movie%' AND year BETWEEN 1970 AND 1989 ORDER BY verified DESC, downloads DESC LIMIT 60"))
            for g in ("Film-Noir", "Horror", "Sci-Fi", "Comedy", "Drama", "Western", "Mystery", "Thriller", "Romance", "Adventure", "Crime", "Documentary"):
                add(f"genre:{g}", g, self._items("SELECT * FROM items WHERE source='pd' AND genres LIKE ? AND blocked=0 AND trailer=0 ORDER BY downloads DESC, title LIMIT 60", (f"%{g}%",)))
            add("pd:trailers", "Trailers", self._items("SELECT * FROM items WHERE source='pd' AND blocked=0 AND trailer=1 ORDER BY verified DESC, added DESC LIMIT 60"))
            add("pd:shorts", "Under 5 minutes", self._items("SELECT * FROM items WHERE source='pd' AND blocked=0 AND trailer=2 ORDER BY verified DESC, downloads DESC LIMIT 60"))
        elif lane in ("chan83", "toontown", "gameshow", "nick90s", "sesame"):
            for uid, title, years in self._q("SELECT uid,title,years FROM shows WHERE source=? ORDER BY title", (lane,)):
                add(f"show:{uid}", f"{title}" + (f"  {years}" if years else ""), self._items("SELECT * FROM items WHERE show_uid=? AND blocked=0 ORDER BY season, episode, title", (uid,)))
        elif lane == "nas":
            for kind, label in (("movie", "Movies"), ("episode", "TV"), ("video", "Videos"), ("track", "Music")):
                add(f"nas:{kind}", label, self._items("SELECT * FROM items WHERE source='nas' AND kind=? AND blocked=0 ORDER BY title LIMIT 200", (kind,)))
            add("nas:recent", "Recently added", self._items("SELECT * FROM items WHERE source='nas' AND blocked=0 AND trailer=0 ORDER BY added DESC LIMIT 40"))
        elif lane == "youtube":
            add("yt:latest", "Latest", self._items("SELECT * FROM items WHERE source='youtube' AND blocked=0 ORDER BY added DESC LIMIT 60"))
            for ch, in self._q("SELECT DISTINCT director FROM items WHERE source='youtube' AND director IS NOT NULL AND director!='' ORDER BY director"):
                add(f"yt:{ch}", ch, self._items("SELECT * FROM items WHERE source='youtube' AND director=? AND blocked=0 ORDER BY added DESC LIMIT 60", (ch,)))
        elif lane == "music":
            add("music:all", "All tracks", self._items("SELECT * FROM items WHERE (source='music' OR kind='track') AND blocked=0 ORDER BY title LIMIT 300"))
        if not rails: rails.append({"id": f"{lane}:empty", "label": {"pd": "Public Domain", "chan83": "Channel 83", "toontown": "Toon Town", "gameshow": "Game Shows", "nick90s": "90s Nick", "sesame": "Classic Sesame Street", "nas": "NAS", "youtube": "YouTube", "music": "Music"}.get(lane, lane) + " - nothing here yet", "model": self._model("empty", [])})
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
            self._post(lambda: (self.toast.emit("Plays" if res == "verified" else f"Could not verify ({res})"), self.openDetail(uid)))   # GUI thread (Phase A law)
        self.toast.emit("Checking that this really plays..."); threading.Thread(target=work, daemon=True).start()
    # ===================== PHASE B (Sep 12 2026): BROWSE TREE, EXPLORER, YOUTUBE, MUSIC, SEARCH =====================
    # A page = (lane, path). Every page renders through the SAME rails UI: "rails" view = labelled rails, "grid" view =
    # label-less rails of 6 (so focus/scroll/click logic is shared). Chips (two rows) are the drill-down buttons.
    GRID_COLS = 6
    AUDIO_EXT = (".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".aac", ".wma")
    VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm", ".mpg", ".mpeg", ".ts", ".wmv", ".flv")
    VIZ = {"off": "", "bars": "[aid1]asplit[ao][a1];[a1]showcqt=s=1920x1080:bar_g=2:sono_g=4:count=6:fps=60,format=yuv420p[vo]",
           "spectrum": "[aid1]asplit[ao][a1];[a1]showspectrum=s=1920x1080:mode=combined:color=fire:scale=cbrt:slide=scroll:fps=60,format=yuv420p[vo]",
           "scope": "[aid1]asplit[ao][a1];[a1]avectorscope=s=1920x1080:mode=lissajous_xy:zoom=1.6:draw=line:rate=60,format=yuv420p[vo]",
           "waves": "[aid1]asplit[ao][a1];[a1]showwaves=s=1920x1080:mode=cline:colors=cyan|magenta:rate=60,format=yuv420p[vo]",
           "freqs": "[aid1]asplit[ao][a1];[a1]showfreqs=s=1920x1080:mode=bar:cmode=separate:fscale=log:colors=yellow|lime,format=yuv420p[vo]"}
    LANE_TITLE = {"pd": "Public Domain", "chan83": "Channel 83", "toontown": "Toon Town", "gameshow": "Game Shows", "nick90s": "90s Nick", "sesame": "Classic Sesame Street", "nas": "NAS", "youtube": "YouTube", "music": "Music", "search": "Search", "home": "Home"}

    def _post(self, fn):
        """Run fn on the GUI thread from any worker thread (QCoreApplication.postEvent -> event())."""
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.postEvent(self, _CallEvent(fn))
    def event(self, ev):
        f = getattr(ev, "f", None)
        if f is not None:
            try: f()
            except Exception as e: log.exception("posted call failed: %s", e)
            return True
        return super().event(ev)

    def _set_page(self, lane, path, title, chips=None, rails=None, view="rails", crumbs=None):
        self._page = {"lane": lane, "path": list(path or []), "title": title, "crumbs": crumbs or [self.LANE_TITLE.get(lane, lane)] + [str(p) for p in (path or [])[1::2]], "chips": chips or [[], []], "view": view}
        self._rails = rails or []
        self.pageChanged.emit(); self.railsChanged.emit()
    def _grid(self, key, items, per_row=None):
        n = per_row or self.GRID_COLS; out = []
        for i in range(0, len(items), n): out.append({"id": f"{key}:{i}", "label": "", "model": self._model(f"{key}:{i}", items[i:i + n])})
        return out or [{"id": f"{key}:empty", "label": "Nothing here yet", "model": self._model("empty", [])}]
    def _chip(self, cid, label, count=None, kind="facet"): return {"id": cid, "label": label, "count": count, "kind": kind}

    @Property("QVariant", notify=pageChanged)
    def page(self): return getattr(self, "_page", {"lane": "home", "path": [], "title": "", "crumbs": [], "chips": [[], []], "view": "rails"})

    def _to_list(self, path):
        """QML hands arrays over as QJSValue; unwrap before iterating (Phase B, found on the TV)."""
        try:
            from PySide6.QtQml import QJSValue
            if isinstance(path, QJSValue): path = path.toVariant()
        except Exception: pass
        if isinstance(path, str): path = [path]
        return [str(x) for x in (path or [])]
    @Slot(str, "QVariant")
    def browseLane(self, lane, path=None):
        self._hist = []
        self._go(lane, path)
    def _go(self, lane, path=None):
        path = self._to_list(path)
        try:
            if lane == "pd": self._browse_pd(path)
            elif lane in ("chan83", "toontown", "gameshow", "nick90s", "sesame"): self._browse_show_lane(lane, path)
            elif lane == "nas": self._browse_nas(path)
            elif lane == "youtube": self._browse_youtube(path)
            elif lane == "music": self._browse_music(path)
            elif lane == "search": self._search(path[0] if path else "")
            else: self.loadHome(); self._set_page("home", [], "", rails=self._rails)
        except Exception as e:
            log.exception("browse(%s,%s) failed: %s", lane, path, e); self.toast.emit(f"Browse failed: {e}")
    @Slot()
    def pageBack(self):
        p = self.page
        h = getattr(self, '_hist', [])
        if h: lane, path = h.pop(); self._go(lane, path); return   # Phase P: exact previous page
        if not p.get("path"): self.loadHome(); self._page = {"lane": "home", "path": [], "title": "", "crumbs": [], "chips": [[], []], "view": "rails"}; self.pageChanged.emit(); return
        self._go(p["lane"], p["path"][:-2])
    @Slot(str)
    def chip(self, cid):
        p = self.page; lane, path = p.get("lane", "home"), list(p.get("path", []))
        kind, _, val = cid.partition(":")
        if kind == "input": self.inputRequest.emit(val, {"search": "Search everything - type and press Enter", "ytsearch": "Search YouTube", "ytadd": "Add a channel: paste @handle or a channel URL"}.get(val, val)); return
        if kind == "action": return self._action(lane, path, val)
        if kind == "viz": self._viz = val; self.toast.emit("Visualizer: " + val); self._apply_viz(); self.pageChanged.emit(); return
        if kind == "go": l2, _, rest = val.partition("|"); self._push_hist(); return self._go(l2, [x for x in rest.split("|") if x])
        if lane in ("search", "home", ""): lane, path = "pd", []   # facet chips always mean the Public Domain catalogue
        path = [x for k2, v2 in zip(path[0::2], path[1::2]) if k2 != "rail" for x in (k2, v2)]   # a facet on an opened rail starts from the lane
        if kind == "sort":   # cycles Popular -> Newest added -> A-Z -> Year
            cur = dict(zip(path[0::2], path[1::2])).get("sort", "popular")
            val = list(self.SORTS)[(list(self.SORTS).index(cur) + 1) % len(self.SORTS)] if cur in self.SORTS else "added"
            if val != "az": path = [x for k2, v2 in zip(path[0::2], path[1::2]) if k2 != "from" for x in (k2, v2)]   # v2.1.0
        # facet chips replace a same-kind facet, toggle OFF when the same one is picked again, else append
        np = []; i = 0; replaced = False
        while i < len(path):
            k2, v2 = path[i], (path[i + 1] if i + 1 < len(path) else "")
            if k2 == kind:
                replaced = True
                if v2 != val or kind == "sort": np += [kind, val]
            else: np += [k2, v2]
            i += 2
        if not replaced: np += [kind, val]
        if [k for k in np[0::2] if k != "sort"] == []: np = ["all", "1"] + np if kind == "sort" else []   # sort from the lane home = sorted 'All titles'; nothing left = lane home
        self._push_hist(); self._go(lane, np)

    # ---- PUBLIC DOMAIN -------------------------------------------------------------------------------
    def _pd_where(self, path):
        w = ["source='pd'", "blocked=0"]; a = []; f = dict(zip(path[0::2], path[1::2]))
        w.append("trailer=1" if "trailers" in f else "trailer=2" if "shorts" in f else "trailer=0")
        if "year" in f: w.append("year=?"); a.append(int(f["year"]))
        if "decade" in f: w.append("decade=?"); a.append(int(f["decade"]))
        if "genre" in f: w.append("(',' || REPLACE(IFNULL(genres,''), ', ', ',') || ',') LIKE ?"); a.append(f"%,{f['genre']},%")   # exact genre, not substring
        if "director" in f: w.append("director LIKE ?"); a.append(f"%{f['director']}%")
        if "ready" in f: w.append("verified=1")
        if "from" in f:   # v2.1.0 A-Z jump bar: start the A-Z list at this letter ('#' = titles that start with a digit or symbol)
            L = str(f["from"])[:1].upper()
            if L == "#": w.append("NOT (UPPER(SUBSTR(LTRIM(title),1,1)) BETWEEN 'A' AND 'Z')")
            elif "A" <= L <= "Z": w.append("UPPER(SUBSTR(LTRIM(title),1,1)) BETWEEN ? AND 'Z'"); a.append(L)   # first letter L..Z only; '[' and digits sort apart and live under '#'
        return " AND ".join(w), a, f
    _LP = "(SELECT last_played FROM state WHERE state.uid=items.uid)"
    SORTS = {"popular": ("Popular", "verified DESC, downloads DESC, title"), "added": ("Newest added", "added DESC, title"),
             "recent": ("Recently played", f"{_LP} IS NULL, {_LP} DESC, verified DESC, downloads DESC, title"),   # v2.1.0: played titles first, newest play first
             "az": ("A-Z", "title COLLATE NOCASE"), "year": ("Year", "year DESC, downloads DESC")}
    LETTERS = ["#"] + [chr(c) for c in range(65, 91)]
    def _browse_pd(self, path):
        where, args, f = self._pd_where(path)
        years = [r[0] for r in self._q("SELECT DISTINCT year FROM items WHERE source='pd' AND blocked=0 AND year IS NOT NULL ORDER BY year")]
        gcount = {}
        for (g,) in self._q("SELECT genres FROM items WHERE source='pd' AND blocked=0 AND genres IS NOT NULL AND genres!=''"):
            for x in str(g).split(","):
                x = x.strip()
                if x: gcount[x] = gcount.get(x, 0) + 1
        srt = f.get("sort", "popular") if f.get("sort") in self.SORTS else "popular"
        row0 = [self._chip("all:1", "All titles" + (" *" if "all" in f else ""), kind="toggle"), self._chip("sort:next", "Sort: " + self.SORTS[srt][0], kind="action"),
                self._chip("ready:1", "Ready to play" + (" *" if "ready" in f else ""), kind="toggle"), self._chip("trailers:1", "Trailers" + (" *" if "trailers" in f else ""), kind="toggle"), self._chip("shorts:1", "Under 5 min" + (" *" if "shorts" in f else ""), kind="toggle"), self._chip("input:search", "Search", kind="action"), self._chip("go:pd|people|directors", "Directors", kind="nav")]
        row0 += [self._chip(f"genre:{g}", g + (" *" if f.get("genre") == g else ""), c) for g, c in sorted(gcount.items(), key=lambda kv: -kv[1])]
        row1 = [self._chip(f"year:{y}", str(y) + (" *" if f.get("year") == str(y) else "")) for y in years]
        if srt == "az":   # v2.1.0: the second chip row becomes an A-Z jump bar while sorted A-Z
            cur = str(f.get("from", ""))[:1].upper()
            row1 = [self._chip(f"from:{L}", L + (" *" if cur == L else ""), kind="facet") for L in self.LETTERS]
        if path and path[0] == "people":
            ds = self._q("SELECT director, COUNT(*) FROM items WHERE source='pd' AND blocked=0 AND director IS NOT NULL AND director!='' GROUP BY director ORDER BY 2 DESC LIMIT 120")
            row1 = [self._chip(f"director:{d}", d, n) for d, n in ds]
            self._set_page("pd", path, "Public Domain - directors", [row0, row1], [{"id": "pd:hint", "label": "Pick a director above", "model": self._model("empty", [])}]); return
        if not [k for k in f if k != "sort"]:  # lane home: curated rails
            rails = []
            def add(rid, label, sql, a=()):
                its = self._items(sql, a)
                if its: rails.append({"id": rid, "label": label, "model": self._model(rid, its)})
            add("pd:ready", "Ready to play", "SELECT * FROM items WHERE source='pd' AND verified=1 AND blocked=0 AND trailer=0 ORDER BY added DESC LIMIT 40")
            add("pd:top", "Most downloaded on archive.org", "SELECT * FROM items WHERE source='pd' AND blocked=0 AND trailer=0 ORDER BY downloads DESC LIMIT 40")
            for dec, in self._q("SELECT DISTINCT decade FROM items WHERE source='pd' AND decade IS NOT NULL AND blocked=0 AND trailer=0 ORDER BY decade"):
                add(f"pd:decade:{dec}", f"{dec}s", "SELECT * FROM items WHERE source='pd' AND decade=? AND blocked=0 AND trailer=0 ORDER BY downloads DESC LIMIT 40", (dec,))
            add("pd:tvmovie", "TV Movies of the 70s & 80s", "SELECT * FROM items WHERE source='pd' AND blocked=0 AND trailer=0 AND genres LIKE '%TV Movie%' AND year BETWEEN 1970 AND 1989 ORDER BY verified DESC, downloads DESC LIMIT 40")
            add("pd:trailers", "Trailers", "SELECT * FROM items WHERE source='pd' AND blocked=0 AND trailer=1 ORDER BY verified DESC, added DESC LIMIT 40")
            add("pd:shorts", "Under 5 minutes", "SELECT * FROM items WHERE source='pd' AND blocked=0 AND trailer=2 ORDER BY verified DESC, downloads DESC LIMIT 40")
            self._set_page("pd", [], "Public Domain", [row0, row1], rails); return
        title = " - ".join([x for x in [self.LANE_TITLE["pd"], "all titles" if "all" in f and len(f) <= 2 else "", f.get("year") or (f.get("decade") + "s" if f.get("decade") else ""), f.get("genre", ""), f.get("director", ""), "ready to play" if "ready" in f else "", "sorted " + self.SORTS[srt][0] if srt != "popular" else "", ("from " + str(f["from"])[:1].upper()) if "from" in f and srt == "az" else ""] if x])
        self._paged_grid("pd", path, title, [row0, row1], f"SELECT * FROM items WHERE {where} ORDER BY {self.SORTS[srt][1]}", tuple(args), "pd:grid")   # Phase P: no 240 cap

    # ---- CHANNEL 83 / TOON TOWN --------------------------------------------------------------------
    def _browse_show_lane(self, lane, path):
        shows = self._q("SELECT uid,title,years,studio FROM shows WHERE source=? ORDER BY title", (lane,))
        f = dict(zip(path[0::2], path[1::2]))
        row0 = [self._chip("action:shuffle", "Shuffle all", kind="action"), self._chip("action:block", "Cartoon block (6)" if lane == "toontown" else "Play a random episode", kind="action"), self._chip("input:search", "Search", kind="action")]
        row1 = [self._chip(f"show:{u}", t + (" *" if f.get("show") == u else "")) for u, t, y, s in shows]
        if "show" in f:
            u = f["show"]; sh = next((s for s in shows if s[0] == u), None)
            if lane in ("chan83", "gameshow", "nick90s", "sesame"):
                rails = []
                for (season,) in self._q("SELECT DISTINCT season FROM items WHERE show_uid=? AND blocked=0 ORDER BY CASE WHEN season=0 THEN 9999 ELSE season END", (u,)):
                    its = self._items("SELECT * FROM items WHERE show_uid=? AND season IS ? AND blocked=0 ORDER BY episode, title", (u, season))
                    if its: rails.append({"id": f"{u}:s{season}", "label": ("Unlisted episodes" if season == 0 else str(season) if season >= 1900 else f"Season {season}") if season is not None else "Episodes", "model": self._model(f"{u}:s{season}", its)})
                self._set_page(lane, path, (sh[1] if sh else "Show") + (f"  {sh[2]}" if sh and sh[2] else ""), [row0, row1], rails)
            else:
                its = self._items("SELECT * FROM items WHERE show_uid=? AND blocked=0 ORDER BY year, title", (u,))
                self._set_page(lane, path, f"{sh[1] if sh else 'Series'}  ({len(its)} shorts)", [row0, row1], self._grid(f"tt:{u}", its), view="grid")
            return
        rails = []
        for u, t, y, s in shows:
            its = self._items("SELECT * FROM items WHERE show_uid=? AND blocked=0 ORDER BY season, episode, year, title LIMIT 60", (u,))
            if its: rails.append({"id": f"show:{u}", "label": t + (f"  {y}" if y else ""), "model": self._model(f"show:{u}", its)})
        self._set_page(lane, [], self.LANE_TITLE[lane], [row0, row1], rails)

    # ---- NAS EXPLORER ---------------------------------------------------------------------------------
    def _nas_roots(self):
        roots = set()
        for (p,) in self._q("SELECT DISTINCT path FROM items WHERE source IN ('nas','music') AND path IS NOT NULL"):
            parts = str(p).split("/")
            if len(parts) > 3: roots.add("/".join(parts[:3]))
        try:
            for m in (self.cfg.get("mounts") or []):
                mp = m.get("mountpoint") if isinstance(m, dict) else str(m)
                if mp: roots.add(mp)
        except Exception: pass
        for base in ("/media", "/mnt"):
            try:
                for e in os.scandir(base):
                    if e.is_dir() and os.path.ismount(e.path): roots.add(e.path)
            except Exception: pass
        return sorted(r for r in roots if os.path.isdir(r))
    def _fs_item(self, full):
        """Return the DB row for a media file, creating a minimal one for files the scanner never saw (local file = playable)."""
        rows = self._items("SELECT * FROM items WHERE path=? LIMIT 1", (full,))
        if rows: return rows[0]
        import hashlib
        name = os.path.splitext(os.path.basename(full))[0]; ext = os.path.splitext(full)[1].lower()
        kind = "track" if ext in self.AUDIO_EXT else "video"; uid = "fs:" + hashlib.sha1(full.encode()).hexdigest()[:16]
        m = re.search(r"\b(19\d\d|20\d\d)\b", name); year = int(m.group(1)) if m else None
        title = re.sub(r"[._]+", " ", re.split(r"\b(19\d\d|20\d\d)\b", name)[0]).strip(" -") or name
        c = dbmod.connect()
        try:
            c.execute("INSERT OR IGNORE INTO items(uid,source,kind,ext_id,title,title_raw,year,path,verified,verified_at,verify_note,added) VALUES(?,?,?,?,?,?,?,?,1,?,?,?)",
                      (uid, "music" if kind == "track" else "nas", kind, full, title, name, year, full, time.time(), "local file (explorer)", time.time())); c.commit()
        finally: c.close()
        return self._items("SELECT * FROM items WHERE uid=?", (uid,))[0]
    def _browse_nas(self, path):
        f = dict(zip(path[0::2], path[1::2])); cur = f.get("dir")
        roots = self._nas_roots()
        row0 = [self._chip("action:scan", "Scan this folder into the library", kind="action") if cur else self._chip("input:search", "Search", kind="action")] + [self._chip(f"dir:{r}", os.path.basename(r) or r, kind="nav") for r in roots]
        if not cur:
            rails = []
            def add(rid, label, its):
                if its: rails.append({"id": rid, "label": label, "model": self._model(rid, its)})
            add("nas:recent", "Recently added", self._items("SELECT * FROM items WHERE source='nas' AND blocked=0 AND trailer=0 ORDER BY added DESC LIMIT 40"))
            for kind, label in (("movie", "Movies"), ("episode", "TV"), ("video", "Videos")):
                add(f"nas:{kind}", label, self._items("SELECT * FROM items WHERE source='nas' AND kind=? AND blocked=0 ORDER BY title LIMIT 200", (kind,)))
            self._set_page("nas", [], "NAS  -  " + (", ".join(roots) if roots else "no shares mounted"), [row0, []], rails or [{"id": "nas:empty", "label": "No NAS items yet - pick a share above to explore it", "model": self._model("empty", [])}]); return
        if not any(cur == r or cur.startswith(r.rstrip("/") + "/") for r in roots): self.toast.emit("Outside the NAS shares"); return
        dirs, files = [], []
        try:
            for e in sorted(os.scandir(cur), key=lambda e: e.name.lower()):
                if e.name.startswith("."): continue
                if e.is_dir(): dirs.append(e.path)
                elif e.is_file() and e.name.lower().endswith(self.VIDEO_EXT + self.AUDIO_EXT): files.append(e.path)
        except Exception as e: self.toast.emit(f"Cannot read folder: {e}")
        row1 = [self._chip(f"dir:{d}", os.path.basename(d), kind="nav") for d in dirs[:400]]
        its = [self._fs_item(p) for p in files[:240]]
        crumbs = ["NAS"] + [p for p in cur.split("/") if p][2:]
        self._set_page("nas", path, f"{os.path.basename(cur) or cur}  ({len(dirs)} folders, {len(files)} files)", [row0, row1], self._grid("nas:dir", its) if its else [{"id": "nas:nofiles", "label": "No media files here - open a folder above", "model": self._model("empty", [])}], view="grid", crumbs=crumbs)

    # ---- YOUTUBE ----------------------------------------------------------------------------------------
    def _yt(self, args, timeout=60):
        import subprocess, json as _j
        from ..core.tools import ytdlp_path
        exe = ytdlp_path() or "yt-dlp"
        out = subprocess.run([exe, "-J", "--flat-playlist", "--no-warnings", "--quiet", *args], capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0: raise RuntimeError((out.stderr or "yt-dlp failed").strip().splitlines()[-1][:160])
        return _j.loads(out.stdout or "{}")
    def _yt_upsert(self, entries, channel_title=None):
        c = dbmod.connect(); n = 0
        try:
            for e in entries or []:
                vid = e.get("id");
                if not vid or e.get("_type") not in (None, "url", "video"): continue
                url = e.get("url") or e.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
                if "youtube.com/watch" not in url and "youtu.be" not in url: url = f"https://www.youtube.com/watch?v={vid}"
                thumb = None
                for t in (e.get("thumbnails") or [])[::-1]:
                    if t.get("url"): thumb = t["url"]; break
                c.execute("INSERT INTO items(uid,source,kind,ext_id,title,title_raw,director,blurb,poster,stream_url,verified,added) VALUES(?,?,?,?,?,?,?,?,?,?,0,?) ON CONFLICT(uid) DO UPDATE SET title=excluded.title, poster=COALESCE(excluded.poster, items.poster), director=COALESCE(excluded.director, items.director)",
                          (f"yt:{vid}", "youtube", "video", vid, e.get("title") or vid, e.get("title"), channel_title or e.get("channel") or e.get("uploader"), e.get("description"), thumb, url, time.time())); n += 1
            c.commit()
        finally: c.close()
        return n
    def _browse_youtube(self, path):
        f = dict(zip(path[0::2], path[1::2]))
        chans = self._q("SELECT channel_id,handle,title FROM yt_channels ORDER BY title")
        row0 = [self._chip("input:ytsearch", "Search YouTube", kind="action"), self._chip("input:ytadd", "+ Add channel", kind="action"), self._chip("go:youtube|manage|1", "Manage channels", kind="nav")]
        row1 = [self._chip(f"chan:{cid}", t or h or cid) for cid, h, t in chans]
        if f.get("manage"):
            row1 = [self._chip(f"action:rmchan|{cid}", f"Remove {t or h}", kind="danger") for cid, h, t in chans]
            self._set_page("youtube", path, f"My channels  ({len(chans)})  -  pick one to remove it", [row0, row1], [{"id": "yt:hint", "label": "Channels are polled for their latest 30 videos", "model": self._model("empty", [])}]); return
        if "chan" in f:
            ch = next((c for c in chans if c[0] == f["chan"]), None); t = (ch[2] or ch[1]) if ch else f["chan"]
            its = self._items("SELECT * FROM items WHERE source='youtube' AND director=? AND blocked=0 ORDER BY added DESC LIMIT 120", (t,))
            self._set_page("youtube", path, f"{t}  ({len(its)})", [row0, row1], self._grid("yt:chan", its), view="grid"); return
        if "q" in f:
            its = self._items("SELECT * FROM items WHERE source='youtube' AND (title LIKE ? OR blurb LIKE ?) AND blocked=0 ORDER BY added DESC LIMIT 60", (f"%{f['q']}%", f"%{f['q']}%"))
            self._set_page("youtube", path, f"YouTube: {f['q']}  ({len(its)})", [row0, row1], self._grid("yt:q", its), view="grid"); return
        rails = []
        its = self._items("SELECT * FROM items WHERE source='youtube' AND blocked=0 ORDER BY added DESC LIMIT 60")
        if its: rails.append({"id": "yt:latest", "label": "Latest", "model": self._model("yt:latest", its)})
        for cid, h, t in chans:
            its = self._items("SELECT * FROM items WHERE source='youtube' AND director=? AND blocked=0 ORDER BY added DESC LIMIT 40", (t or h,))
            if its: rails.append({"id": f"yt:{cid}", "label": t or h, "model": self._model(f"yt:{cid}", its)})
        self._set_page("youtube", [], "YouTube  -  best effort: a result plays only after it passes the decode check", [row0, row1], rails or [{"id": "yt:empty", "label": "Search or add a channel to get started", "model": self._model("empty", [])}])
    def _yt_search_async(self, q):
        self.toast.emit(f"Searching YouTube for {q}...")
        def work():
            try:
                data = self._yt([f"ytsearch12:{q}"]); n = self._yt_upsert(data.get("entries"))
                self._post(lambda: (self.toast.emit(f"{n} results"), self.browseLane("youtube", ["q", q])))
            except Exception as e: self._post(lambda: self.toast.emit(f"YouTube search failed: {e}"))
        threading.Thread(target=work, daemon=True).start()
    def _yt_add_async(self, text):
        t = text.strip(); url = t if t.startswith("http") else f"https://www.youtube.com/{t if t.startswith('@') else '@' + t}"
        self.toast.emit("Reading channel...")
        def work():
            try:
                data = self._yt(["--playlist-items", "1:30", url.rstrip("/") + ("/videos" if "/videos" not in url else "")], timeout=90)
                title = data.get("channel") or data.get("uploader") or data.get("title") or t; cid = data.get("channel_id") or data.get("uploader_id") or t
                n = self._yt_upsert(data.get("entries"), channel_title=title)
                c = dbmod.connect(); c.execute("INSERT OR REPLACE INTO yt_channels(channel_id,handle,title,avatar,added,last_poll) VALUES(?,?,?,?,?,?)", (cid, t, title, None, time.time(), time.time())); c.commit(); c.close()
                self._post(lambda: (self.toast.emit(f"Added {title} ({n} videos)"), self.browseLane("youtube", ["chan", cid])))
            except Exception as e: self._post(lambda: self.toast.emit(f"Could not add channel: {e}"))
        threading.Thread(target=work, daemon=True).start()

    # ---- MUSIC -----------------------------------------------------------------------------------------
    def _browse_music(self, path):
        if not getattr(self, "_art_checked", False):
            self._art_checked = True
            if self._q("SELECT COUNT(*) FROM items WHERE kind='track' AND blocked=0 AND (poster_local IS NULL OR poster_local='')")[0][0]: self._music_art_backfill_async()
        f = dict(zip(path[0::2], path[1::2]))
        n = self._q("SELECT COUNT(*) FROM items WHERE kind='track' AND blocked=0")[0][0]
        viz = getattr(self, "_viz", "bars")
        row0 = [self._chip("action:musicscan", "Scan NAS for music", kind="action"), self._chip("action:shuffle", "Shuffle all", kind="action"), self._chip("input:search", "Search", kind="action")] + [self._chip(f"viz:{k}", ("* " if viz == k else "") + "Viz " + k, kind="toggle") for k in self.VIZ]
        artists = self._q("SELECT director, COUNT(*) FROM items WHERE kind='track' AND blocked=0 AND director IS NOT NULL AND director!='' GROUP BY director ORDER BY 2 DESC LIMIT 200")
        row1 = [self._chip(f"artist:{a}", a + (" *" if f.get("artist") == a else ""), c) for a, c in artists]
        if "album" in f:
            its = self._items("SELECT * FROM items WHERE kind='track' AND blurb=? AND blocked=0 ORDER BY ext_id, title", (f["album"],))
            self._set_page("music", path, f"{f['album']}  ({len(its)} tracks)", [row0, row1], self._grid("mu:album", its), view="grid"); return
        if "artist" in f:
            rails = []
            for (alb,) in self._q("SELECT DISTINCT COALESCE(blurb,'') FROM items WHERE kind='track' AND director=? AND blocked=0 ORDER BY year, blurb", (f["artist"],)):
                its = self._items("SELECT * FROM items WHERE kind='track' AND director=? AND COALESCE(blurb,'')=? AND blocked=0 ORDER BY ext_id, title", (f["artist"], alb))
                if its: rails.append({"id": f"mu:{alb}", "label": alb or "Singles", "model": self._model(f"mu:{f['artist']}:{alb}", its)})
            self._set_page("music", path, f"{f['artist']}", [row0, row1], rails); return
        rails = []
        its = self._items("SELECT * FROM items WHERE kind='track' AND blocked=0 ORDER BY added DESC LIMIT 60")
        if its: rails.append({"id": "mu:recent", "label": "Recently added", "model": self._model("mu:recent", its)})
        for (alb,) in self._q("SELECT blurb FROM items WHERE kind='track' AND blocked=0 AND blurb IS NOT NULL AND blurb!='' GROUP BY blurb ORDER BY COUNT(*) DESC LIMIT 12"):
            t = self._items("SELECT * FROM items WHERE kind='track' AND blurb=? AND blocked=0 ORDER BY ext_id, title LIMIT 40", (alb,))
            if t: rails.append({"id": f"mu:alb:{alb}", "label": alb, "model": self._model(f"mu:alb:{alb}", t)})
        self._set_page("music", [], f"Music  ({n} tracks)  -  visualizer: {viz}", [row0, row1], rails or [{"id": "mu:empty", "label": "No music yet - press 'Scan NAS for music'", "model": self._model("empty", [])}])
    ART_NAMES = ("cover", "folder", "front", "album", "albumart", "artwork")
    def _music_art(self, full, dp):
        """One art file per album folder: embedded picture (mp3 APIC / flac pictures / mp4 covr) else cover.jpg-style file in the folder. Returns a path or None."""
        import hashlib
        from ..core.paths import CACHE_DIR
        d = CACHE_DIR / "music_art"; d.mkdir(parents=True, exist_ok=True)
        out = d / (hashlib.sha1(dp.encode()).hexdigest()[:16] + ".jpg")
        if out.exists() and out.stat().st_size > 0: return str(out)
        try:
            for f in os.listdir(dp):
                b, e = os.path.splitext(f.lower())
                if b in self.ART_NAMES and e in (".jpg", ".jpeg", ".png", ".webp"):
                    shutil.copyfile(os.path.join(dp, f), out); return str(out)
        except Exception: pass
        try:
            import mutagen
            mf = mutagen.File(full)
            data = None
            if mf is not None:
                pics = getattr(mf, "pictures", None)
                if pics: data = pics[0].data
                elif getattr(mf, "tags", None) is not None:
                    t = mf.tags
                    if hasattr(t, "getall"):
                        apic = t.getall("APIC")
                        if apic: data = apic[0].data
                    if data is None and "covr" in t: data = bytes(t["covr"][0])
            if data: out.write_bytes(data); return str(out)
        except Exception: pass
        return None
    def _music_art_backfill_async(self):
        if getattr(self, "_art_running", False): return
        self._art_running = True
        def work():
            n = 0; c = dbmod.connect()
            try:
                rows = c.execute("SELECT path FROM items WHERE kind='track' AND blocked=0 AND (poster_local IS NULL OR poster_local='') AND path IS NOT NULL").fetchall()
                seen = {}
                for (path,) in rows:
                    dp = os.path.dirname(path)
                    if dp not in seen: seen[dp] = self._music_art(path, dp)
                    if seen[dp]: c.execute("UPDATE items SET poster_local=? WHERE path=?", (seen[dp], path)); n += 1
                    if n and n % 300 == 0: c.commit()
                c.commit(); log.info("music art backfill: %d tracks across %d folders, %d folders with art", n, len(seen), sum(1 for v in seen.values() if v))
            except Exception as e: log.exception("music art backfill: %s", e)
            finally: c.close(); self._art_running = False
            if n: self._post(lambda: self.browseLane("music", self.page.get("path") if self.page and self.page.get("lane") == "music" else []))
        threading.Thread(target=work, daemon=True).start()
    def _music_scan_async(self):
        roots = self._nas_roots(); self.toast.emit("Scanning for music... this runs in the background")
        def work():
            n = 0; c = dbmod.connect()
            try:
                import mutagen
                for root in roots:
                    for dp, dn, fn in os.walk(root):
                        dn[:] = [d for d in dn if not d.startswith(".")]
                        for name in fn:
                            if not name.lower().endswith(self.AUDIO_EXT): continue
                            full = os.path.join(dp, name)
                            if c.execute("SELECT 1 FROM items WHERE path=?", (full,)).fetchone(): continue
                            artist = album = title = None; year = None; track = None; art = None
                            try:
                                mf = mutagen.File(full, easy=True)
                                if mf:
                                    g = lambda k: (mf.get(k) or [None])[0]
                                    artist, album, title = g("artist") or g("albumartist"), g("album"), g("title")
                                    d = g("date") or g("year"); m = re.search(r"\d{4}", str(d or "")); year = int(m.group()) if m else None
                                    tn = str(g("tracknumber") or "").split("/")[0]; track = int(tn) if tn.isdigit() else None
                            except Exception: pass
                            base = os.path.splitext(name)[0]
                            if not title:
                                parts = base.split(" - ", 1); title = parts[-1].strip(); artist = artist or (parts[0].strip() if len(parts) > 1 else None)
                            album = album or os.path.basename(dp); artist = artist or os.path.basename(os.path.dirname(dp))
                            import hashlib; uid = "fs:" + hashlib.sha1(full.encode()).hexdigest()[:16]
                            c.execute("INSERT OR IGNORE INTO items(uid,source,kind,ext_id,title,title_raw,year,director,blurb,path,verified,verified_at,verify_note,added) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
                                      (uid, "music", "track", f"{track or 0:03d}", title, base, year, artist, album, full, time.time(), "local file (music scan)", time.time())); n += 1
                            if n % 200 == 0: c.commit(); self._post(lambda n=n: self.toast.emit(f"Music scan: {n} tracks so far"))
                c.commit()
            except Exception as e: log.exception("music scan: %s", e); self._post(lambda: self.toast.emit(f"Music scan stopped: {e}"))
            finally: c.close()
            self._post(lambda: (self.toast.emit(f"Music scan done: {n} new tracks"), self.browseLane("music", []), self._music_art_backfill_async()))
        threading.Thread(target=work, daemon=True).start()
    def _apply_viz(self, kind=None):
        m = self._player()
        if not m: return
        try:
            expr = self.VIZ.get(getattr(self, "_viz", "bars"), "") if (kind or "track") == "track" else ""
            try: m.mpv["lavfi-complex"] = expr
            except Exception: m.command("set", "lavfi-complex", expr)
        except Exception as e: log.warning("visualizer apply failed: %s", e)

    # ---- SEARCH / ACTIONS / INPUT / QUEUE -------------------------------------------------------------
    def _search(self, q):
        q = (q or "").strip(); row0 = [self._chip("input:search", "Search again", kind="action")]
        if not q: self._set_page("search", [], "Search", [row0, []], [{"id": "s:hint", "label": "Type what you are looking for", "model": self._model("empty", [])}]); return
        rails = []; like = f"%{q}%"
        for src, label in (("pd", "Public Domain"), ("chan83", "Channel 83"), ("gameshow", "Game Shows"), ("nick90s", "90s Nick"), ("sesame", "Classic Sesame Street"), ("toontown", "Toon Town"), ("nas", "NAS"), ("youtube", "YouTube"), ("music", "Music")):
            its = self._items("SELECT * FROM items WHERE source=? AND blocked=0 AND (trailer=0 OR ? LIKE '%trailer%') AND (title LIKE ? OR director LIKE ? OR blurb LIKE ? OR CAST(year AS TEXT)=?) ORDER BY verified DESC, downloads DESC, title LIMIT 40", (src, q, like, like, like, q))
            if its: rails.append({"id": f"s:{src}", "label": f"{label}  ({len(its)})", "model": self._model(f"s:{src}", its)})
        self._set_page("search", ["q", q], f"Search: {q}", [row0, []], rails or [{"id": "s:none", "label": f"Nothing matches '{q}'", "model": self._model("empty", [])}])
    @Slot(str, str)
    def inputSubmit(self, kind, text):
        text = (text or "").strip()
        if not text: return
        if kind == "search": self._search(text)
        elif kind == "ytsearch": self._yt_search_async(text)
        elif kind == "ytadd": self._yt_add_async(text)
    def _action(self, lane, path, val):
        act, _, arg = val.partition("|")
        if act == "musicscan": return self._music_scan_async()
        if act == "scan":
            f = dict(zip(path[0::2], path[1::2])); cur = f.get("dir")
            if not cur: return
            self.toast.emit("Indexing folder...")
            def work():
                n = 0
                for dp, dn, fn in os.walk(cur):
                    for name in fn:
                        if name.lower().endswith(self.VIDEO_EXT + self.AUDIO_EXT): self._fs_item(os.path.join(dp, name)); n += 1
                self._post(lambda: (self.toast.emit(f"Indexed {n} files"), self.browseLane("nas", path)))
            threading.Thread(target=work, daemon=True).start(); return
        if act == "rmchan":
            ch = self._q("SELECT title,handle FROM yt_channels WHERE channel_id=?", (arg,))
            c = dbmod.connect(); c.execute("DELETE FROM yt_channels WHERE channel_id=?", (arg,)); c.commit(); c.close()
            self.toast.emit(f"Removed {ch[0][0] if ch else arg}"); return self.browseLane("youtube", ["manage", "1"])
        if act in ("shuffle", "block"):
            import random
            uids = [u for (u,) in self._q({"chan83": "SELECT uid FROM items WHERE source='chan83' AND verified=1 AND blocked=0", "gameshow": "SELECT uid FROM items WHERE source='gameshow' AND verified=1 AND blocked=0", "nick90s": "SELECT uid FROM items WHERE source='nick90s' AND verified=1 AND blocked=0", "sesame": "SELECT uid FROM items WHERE source='sesame' AND verified=1 AND blocked=0", "toontown": "SELECT uid FROM items WHERE source='toontown' AND verified=1 AND blocked=0", "music": "SELECT uid FROM items WHERE kind='track' AND blocked=0"}.get(lane, "SELECT uid FROM items WHERE verified=1 AND blocked=0 AND source=?"), () if lane in ("chan83", "toontown", "music") else (lane,))]
            f = dict(zip(path[0::2], path[1::2]))
            if f.get("show"): uids = [u for (u,) in self._q("SELECT uid FROM items WHERE show_uid=? AND verified=1 AND blocked=0", (f["show"],))]
            if not uids: return self.toast.emit("Nothing playable to shuffle")
            random.shuffle(uids); n = 6 if act == "block" and lane == "toontown" else (1 if act == "block" else len(uids))
            self._queue = uids[1:n]; self.toast.emit(f"Queued {n} - press Back to stop"); return self.play(uids[0], False)
    def _next_or_stop(self):
        q = getattr(self, "_queue", None) or []
        if q: nxt = q.pop(0); self._queue = q; self._save_resume(); self.play(nxt, False)
        else: self.stop()
    @Slot()
    def clearQueue(self): self._queue = []
    def _wd_second(self):
        """Second watchdog strike (45 s): still no frames -> give up honestly."""
        if self._playing and (self._pos or 0) <= 0:
            self._wd_strike = False; log.error("playback watchdog: no time-pos after 45 s (uid=%s)", self._cur_uid); self.toast.emit("Playback did not start - see player.log"); self.stop()
    @Slot(str)
    def playerCmd(self, cmd):
        """Dreamy / voice control of playback: pause | stop | next | seek:<±secs> | vol:<±n> | mute | fullscreen."""
        m = self._player()
        try:
            if cmd == "pause":
                if self._playing: self.togglePause()
            elif cmd == "stop":
                if self._playing: self.stop()
            elif cmd == "next": self._next_or_stop() if self._playing else self.toast.emit("Nothing is playing")
            elif cmd.startswith("seek:"):
                if self._playing: self.seekRel(float(cmd[5:]))
            elif cmd.startswith("vol:") and m:
                try: m.mpv["volume"] = max(0, min(130, float(m.mpv["volume"]) + float(cmd[4:])))
                except Exception: m.command("add", "volume", cmd[4:])
            elif cmd == "mute" and m:
                try: m.mpv["mute"] = not bool(m.mpv["mute"])
                except Exception: m.command("cycle", "mute")
            elif cmd == "fullscreen": self.toast.emit("Fullscreen is F11")
        except Exception as e: log.warning("playerCmd %s: %s", cmd, e); self.toast.emit(f"Could not {cmd}: {e}")
    # ================================================================================================================
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
        if isinstance(uid, str) and uid.startswith('__more__:'): return self.openRail(uid[len('__more__:'):])  # Phase R
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
        try:  # Sep 26 2026: make sure the sound goes to the TV at the moment it matters, not only at boot
            from . import audio as _audio; _ar = _audio.ensure_tv_audio()
            if not _ar.get("ok"): self.toast.emit("TV audio: no HDMI sound device - check the HDMI cable / TV input")
        except Exception as _e: log.warning("TV audio pre-play check failed: %s", _e)
        self._started_at = time.time(); self._first_frame = False
        start = 0.0
        if resume:
            st = self._q("SELECT resume_sec,duration_sec FROM state WHERE uid=?", (uid,))
            if st and st[0]["resume_sec"] and st[0]["duration_sec"] and st[0]["resume_sec"] < st[0]["duration_sec"] * 0.95: start = float(st[0]["resume_sec"])
        self._cur_uid = uid; self._paused = False; self._wd_strike = False
        try:
            self._now = {"uid": uid, "title": row["title"] or "", "artist": row["director"] or "", "album": row["blurb"] or "" if row["kind"] == "track" else "", "poster": _poster(row), "kind": row["kind"], "source": row["source"], "year": row["year"] or 0}; self.nowPlayingChanged.emit()
        except Exception as e: log.debug("nowPlaying: %s", e)
        try: self._apply_viz((self._q("SELECT kind FROM items WHERE uid=?", (uid,)) or [("video",)])[0][0])
        except Exception as _e: log.warning("viz: %s", _e)
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
            if not getattr(self, "_wd_strike", False):   # Phase D: archive.org cold starts can take >15 s; give one more 30 s window before giving up
                self._wd_strike = True; log.warning("playback watchdog: no time-pos after 15 s (uid=%s) - waiting 30 s more", self._cur_uid); self.toast.emit("Still connecting to the source...")
                QTimer.singleShot(30000, self._wd_second); return
            self._wd_strike = False
            log.error("playback watchdog: no time-pos after 45 s (uid=%s)", self._cur_uid); self.toast.emit("Playback did not start - see player.log"); self.stop(); return
        if p is not None: self._pos = float(p)
        if d: self._dur = float(d)
        self.positionChanged.emit()
        if eof and self._playing: self._next_or_stop()
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
        self._playing = False; self.playingChanged.emit(); self.playbackStopped.emit(); self._queue = []
        pg = self.page
        if pg.get("lane") in (None, "home", ""): self.loadHome()
        else: self.browseLane(pg["lane"], pg.get("path", []))
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
    nowPlayingChanged = Signal()
    @Property("QVariant", notify=nowPlayingChanged)
    def nowPlaying(self): return getattr(self, "_now", {}) or {}
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
