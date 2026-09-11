"""Wizard state machine. Steps are data; Dreamy's lines live here so forkers can rewrite them.
Nothing here needs root: the wizard writes config.toml + plan.json; `dreamreels-apply` (P5) performs the root part."""
from __future__ import annotations
import json, os, re, threading, time
from PySide6.QtCore import QObject, Signal, Slot, Property
from ..core import config as cfgmod
from ..core.paths import PLAN_FILE, CACHE_DIR, ensure_dirs
from ..dreamy.mascot import dreamy_svg
from ..ui.theme import available as themes_available

DECADES = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980]
GENRES = ["Film-Noir", "Horror", "Sci-Fi", "Comedy", "Drama", "Western", "Mystery", "Romance", "Thriller", "Adventure", "War", "Documentary", "Animation", "Musical"]
CHAN83 = ["The Twilight Zone", "The Outer Limits (1963 + 1995)", "Suspense", "One Step Beyond", "Thriller", "Alfred Hitchcock Presents", "Lights Out"]
TOON = ["Fleischer", "Ub Iwerks", "Van Beuren", "US War Dept / WB", "Walter Lantz", "Fleischer/Famous", "UPA", "Warner Bros."]

STEPS = [  # id, title, Dreamy pose, Dreamy line
    ("welcome", "Welcome", "celebrate", "Hi, I'm Dreamy. I'll set up your DreamReels in a few short steps. Nothing touches your system until you say so at the end."),
    ("sources", "Pick your sources", "point", "Where should your movies come from? Pick as many as you like. You can add more later."),
    ("pd", "Public Domain", "think", "Archive.org holds thousands of classic films. Tell me the decades and genres you love and I'll go find them, verify they actually play, and keep growing your library every night."),
    ("strict", "Strict public domain", "think", "ON keeps only films published in 1930 or earlier, or ones archive.org marks public domain. OFF shows everything archive.org will stream, including grey-area uploads."),
    ("chan83", "Channel 83", "point", "Anthology television: the strange, the suspenseful, the black-and-white. Which shows do you want mapped?"),
    ("toontown", "Toon Town", "celebrate", "Classic cartoons by studio. Pick the ones you want and I'll map every short."),
    ("nas", "Your NAS", "think", "I'll look around your network for shared drives. Pick the ones with your movies and music. Mounting happens in the final step, with your password."),
    ("youtube", "YouTube", "point", "Paste the channels you follow, one @handle per line. I play them with a native player: there is no ad client to inject into, so there are no ads. This lane depends on tools that break when YouTube changes; I'll show you a health check."),
    ("tmdb", "Movie database key", "think", "Posters and descriptions come from TMDB. It's free: get a Read Access Token at themoviedb.org/settings/api and paste it here. You can skip and add it later."),
    ("skin", "Choose a look", "celebrate", "Three skins. Pick the one that feels like your living room."),
    ("user", "System user", "think", "I'll create a 'dreamreels' user that logs in automatically and starts the player. A password is optional."),
    ("summary", "Ready to build", "point", "Here's everything I'm about to do. Nothing has changed yet. Press Build when you're happy."),
    ("done", "All set", "celebrate", "Setup is written. Run 'sudo dreamreels-apply' to finish the system part, or press Build to do it now."),
]

class WizardBackend(QObject):
    changed = Signal(); nasChanged = Signal(); toast = Signal(str)
    def __init__(self, cfg: dict):
        super().__init__(); ensure_dirs(); self.cfg = cfg; self._i = 0
        self.sel = {"publicdomain": True, "chan83": False, "toontown": False, "nas": False, "youtube": False}
        self.strict = bool(cfg["publicdomain"].get("strict_pd", True))
        self.decades = set(cfg["publicdomain"].get("decades") or [1930, 1940, 1950]); self.genres = set(cfg["publicdomain"].get("genres") or ["Film-Noir", "Horror", "Sci-Fi"])
        self.chan83 = set(CHAN83); self.toon = set(TOON)
        self.handles = list(cfg["youtube"].get("channels") or []); self.tmdb = cfg["tmdb"].get("read_token", "")
        self.theme = cfg["meta"].get("theme", "midnight"); self.username = "dreamreels"; self.password = ""
        self.nas_hosts: list[dict] = []; self.nas_picked: set[str] = set(); self.nas_scanning = False
        self._mascot_cache = {}
    # ---- steps ----
    def _active_steps(self):
        out = []
        for s in STEPS:
            sid = s[0]
            if sid in ("pd", "strict") and not self.sel["publicdomain"]: continue
            if sid in ("chan83", "toontown", "nas", "youtube") and not self.sel[sid]: continue
            out.append(s)
        return out
    @Property(int, notify=changed)
    def index(self): return self._i
    @Property(int, notify=changed)
    def count(self): return len(self._active_steps())
    @Property(str, notify=changed)
    def stepId(self): return self._active_steps()[self._i][0]
    @Property(str, notify=changed)
    def stepTitle(self): return self._active_steps()[self._i][1]
    @Property(str, notify=changed)
    def pose(self): return self._active_steps()[self._i][2]
    @Property(str, notify=changed)
    def line(self): return self._active_steps()[self._i][3]
    @Slot()
    def next(self):
        if self._i < len(self._active_steps()) - 1:
            self._i += 1; self.changed.emit()
            if self.stepId == "nas" and not self.nas_hosts and not self.nas_scanning: self.scanNas()
    @Slot()
    def back(self):
        if self._i > 0: self._i -= 1; self.changed.emit()
    @Slot(str, result=str)
    def mascotUrl(self, pose):
        th = next((t for t in themes_available() if t["name"] == self.theme), None) or {}
        key = (pose, self.theme)
        if key not in self._mascot_cache:
            p = CACHE_DIR / f"dreamy_{pose}_{self.theme}.svg"; p.write_text(dreamy_svg(pose, th.get("accent", "#E11D48"), th.get("accent2", "#60A5FA"), th.get("bg", "#0B0F17")))
            self._mascot_cache[key] = p.as_uri()
        return self._mascot_cache[key]
    # ---- choices ----
    @Property("QVariant", notify=changed)
    def sources(self): return self.sel
    @Slot(str)
    def toggleSource(self, k): self.sel[k] = not self.sel[k]; self.changed.emit()
    @Property(bool, notify=changed)
    def strictPd(self): return self.strict
    @Slot(bool)
    def setStrict(self, v): self.strict = bool(v); self.changed.emit()
    @Property("QVariantList", notify=changed)
    def decadeList(self): return [{"v": d, "label": f"{d}s", "on": d in self.decades} for d in DECADES]
    @Slot(int)
    def toggleDecade(self, d): self.decades ^= {d}; self.changed.emit()
    @Property("QVariantList", notify=changed)
    def genreList(self): return [{"v": g, "label": g, "on": g in self.genres} for g in GENRES]
    @Slot(str)
    def toggleGenre(self, g): self.genres ^= {g}; self.changed.emit()
    @Property("QVariantList", notify=changed)
    def chan83List(self): return [{"v": s, "label": s, "on": s in self.chan83} for s in CHAN83]
    @Slot(str)
    def toggleChan83(self, s): self.chan83 ^= {s}; self.changed.emit()
    @Property("QVariantList", notify=changed)
    def toonList(self): return [{"v": s, "label": s, "on": s in self.toon} for s in TOON]
    @Slot(str)
    def toggleToon(self, s): self.toon ^= {s}; self.changed.emit()
    @Property(str, notify=changed)
    def handlesText(self): return "\n".join(self.handles)
    @Slot(str)
    def setHandlesText(self, t):
        hs = []
        for ln in t.splitlines():
            ln = ln.strip()
            m = re.search(r"(@[\w.\-]+)", ln)
            if m and m.group(1) not in hs: hs.append(m.group(1))
        self.handles = hs; self.changed.emit()
    @Property(str, notify=changed)
    def tmdbToken(self): return self.tmdb
    @Slot(str)
    def setTmdbToken(self, t): self.tmdb = t.strip(); self.changed.emit()
    @Property("QVariantList", notify=changed)
    def themeList(self): return [{"name": t["name"], "label": t["label"], "mood": t["mood"], "bg": t["bg"], "surface": t["surface"], "accent": t["accent"], "accent2": t["accent2"], "text": t["text"], "on": t["name"] == self.theme} for t in themes_available()]
    @Property(str, notify=changed)
    def themeName(self): return self.theme
    @Slot(str)
    def setTheme(self, n): self.theme = n; self._mascot_cache.clear(); self.changed.emit()
    @Property(str, notify=changed)
    def userName(self): return self.username
    @Slot(str)
    def setUserName(self, u): self.username = re.sub(r"[^a-z0-9_-]", "", u.lower()) or "dreamreels"; self.changed.emit()
    @Slot(str)
    def setPassword(self, p): self.password = p
    # ---- NAS ----
    @Property(bool, notify=nasChanged)
    def nasScanning(self): return self.nas_scanning
    @Property("QVariantList", notify=nasChanged)
    def nasHosts(self):
        out = []
        for h in self.nas_hosts:
            for s in h.get("shares") or [{"name": "", "comment": h.get("error") or ("needs a login" if h.get("auth") == "required" else "no shares listed")}]:
                key = f"//{h['ip']}/{s['name']}" if s["name"] else ""
                out.append({"ip": h["ip"], "host": h.get("host") or "", "share": s["name"], "comment": s.get("comment", ""), "key": key, "auth": h.get("auth", ""), "on": key in self.nas_picked})
        return out
    @Slot()
    def scanNas(self):
        if self.nas_scanning: return
        self.nas_scanning = True; self.nasChanged.emit()
        def work():
            try:
                from ..sources.nas_discovery import discover
                self.nas_hosts = discover()
            except Exception as e:
                self.nas_hosts = [{"ip": "-", "host": "", "auth": "error", "shares": [], "error": str(e)}]
            self.nas_scanning = False; self.nasChanged.emit()
        threading.Thread(target=work, daemon=True).start()
    @Slot(str)
    def toggleShare(self, key):
        if key: self.nas_picked ^= {key}; self.nasChanged.emit()
    # ---- summary + write ----
    @Property("QVariantList", notify=changed)
    def summaryLines(self):
        L = []
        src = [k for k, v in self.sel.items() if v]; L.append(("Sources", ", ".join(src) or "none"))
        if self.sel["publicdomain"]: L.append(("Public Domain", f"{'strict' if self.strict else 'everything archive.org streams'} · {', '.join(str(d)+'s' for d in sorted(self.decades))} · {', '.join(sorted(self.genres))}"))
        if self.sel["chan83"]: L.append(("Channel 83", f"{len(self.chan83)} shows, episodes pre-mapped"))
        if self.sel["toontown"]: L.append(("Toon Town", f"{len(self.toon)} studios"))
        if self.sel["nas"]: L.append(("NAS", f"{len(self.nas_picked)} share(s) → /etc/fstab automount (root step)"))
        if self.sel["youtube"]: L.append(("YouTube", f"{len(self.handles)} channel(s); tools installed + health-checked (root step)"))
        L.append(("TMDB", "token set" if self.tmdb else "not set (text tiles until you add one)"))
        L.append(("Skin", self.theme)); L.append(("System", f"user '{self.username}' {'with' if self.password else 'without'} password · autologin · player service · reboot (root step)"))
        return [{"k": k, "v": v} for k, v in L]
    @Slot(result=bool)
    def writePlan(self):
        cfg = self.cfg
        cfg["sources"] = dict(self.sel); cfg["publicdomain"].update({"strict_pd": self.strict, "decades": sorted(self.decades), "genres": sorted(self.genres)})
        cfg["youtube"]["channels"] = list(self.handles); cfg["tmdb"]["read_token"] = self.tmdb; cfg["meta"]["theme"] = self.theme
        cfg["nas"]["mounts"] = sorted(self.nas_picked); cfg["meta"]["setup_complete"] = True
        cfgmod.save(cfg)
        plan = {"version": 1, "written": time.time(), "user": self.username, "password_set": bool(self.password), "mounts": sorted(self.nas_picked), "youtube": self.sel["youtube"], "sources": self.sel, "chan83": sorted(self.chan83), "toontown": sorted(self.toon), "theme": self.theme}
        PLAN_FILE.write_text(json.dumps(plan, indent=2)); os.chmod(PLAN_FILE, 0o600)
        if self.password:
            pw = PLAN_FILE.with_name("plan.secret"); pw.write_text(self.password); os.chmod(pw, 0o600)
        self.toast.emit(f"Wrote {PLAN_FILE}"); self._i = len(self._active_steps()) - 1; self.changed.emit(); return True
