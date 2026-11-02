"""QObject face of the Dreamy agent for QML: ask() runs the tools in a thread, answer() carries JSON.
check(uid) runs verify_decode in a thread and emits verified(uid, ok, note) so a CHECK button can become PLAY."""
from __future__ import annotations
import json, threading, time
from PySide6.QtCore import QObject, Signal, Slot, Property
from ..core import db as dbmod
from . import agent
from . import tools as dtools
from PySide6.QtCore import QCoreApplication
from ..player.backend import _CallEvent
from .mascot import dreamy_svg
from ..core.paths import CACHE_DIR
from ..ui.theme import available as themes_available

class DreamyBackend(QObject):
    answer = Signal(str)           # JSON {text, buttons}
    verified = Signal(str, bool, str)
    busyChanged = Signal()
    def __init__(self, cfg: dict, theme=None):
        super().__init__(); self.cfg = cfg; self._busy = False; self._theme = theme; self._mc = {}
    def _post(self, fn): QCoreApplication.postEvent(self, _CallEvent(fn))
    def event(self, ev):
        f = getattr(ev, "f", None)
        if f is not None:
            try: f()
            except Exception as e: import logging; logging.getLogger("dreamreels.player.dreamy").exception("posted call failed: %s", e)
            return True
        return super().event(ev)
    @Slot(result=str)
    def capabilities(self): return json.dumps(dtools.capabilities())
    @Slot(str, result=str)
    def mascotUrl(self, pose: str) -> str:
        name = self._theme.name if self._theme is not None else self.cfg['meta'].get('theme', 'midnight')
        th = next((t for t in themes_available() if t['name'] == name), {})
        key = (pose, name)
        if key not in self._mc:
            p = CACHE_DIR / f'dreamy_{pose}_{name}.svg'; p.write_text(dreamy_svg(pose, th.get('accent', '#E11D48'), th.get('accent2', '#60A5FA'), th.get('bg', '#0B0F17'))); self._mc[key] = p.as_uri()
        return self._mc[key]
    @Property(bool, notify=busyChanged)
    def busy(self): return self._busy
    def _set_busy(self, v): self._busy = v; self.busyChanged.emit()
    @Slot(str)
    def ask(self, text: str):
        if not text.strip() or self._busy: return
        self._set_busy(True)
        def work():
            try: res = dtools.route(self.cfg, text)
            except Exception as e: res = {"text": f"Something went wrong: {str(e)[:120]}", "buttons": [], "actions": []}
            self._post(lambda: (self.answer.emit(json.dumps(res)), self._set_busy(False)))   # GUI thread, never a raw-thread emit (Phase A law)
        threading.Thread(target=work, daemon=True).start()
    @Slot(str)
    def check(self, uid: str):
        def work():
            from ..sources import archive_org as ia
            c = dbmod.connect()
            try:
                row = c.execute("SELECT * FROM items WHERE uid=?", (uid,)).fetchone()
                if not row: self._post(lambda _a=(uid, False, "gone"): self.verified.emit(*_a)); return
                if row["source"] == "youtube":
                    from ..core.tools import yt_direct_url
                    try: direct = yt_direct_url(row["stream_url"])
                    except Exception as e: direct = None; note = f"yt-dlp: {str(e)[:80]}"
                    ok, note, dur = ia.verify_decode(direct, frames=24, timeout=90) if direct else (False, note, 0)
                    if ok: c.execute("UPDATE items SET verified=1,verified_at=?,verify_note=?,runtime_min=? WHERE uid=?", (time.time(), note, int(dur // 60) or None, uid))
                    else: c.execute("UPDATE items SET verified=0,verified_at=?,verify_note=? WHERE uid=?", (time.time(), note, uid))
                    c.commit(); self._post(lambda _a=(uid, ok, note): self.verified.emit(*_a)); return
                meta = ia.ia_meta(row["ia_id"]); cands = [x for x in ia.candidates(meta, row["ia_id"]) if not x["part"]][:3]; note = "no candidate files"
                for cand in cands:
                    ok0, _ = ia.prefilter(cand["url"])
                    if not ok0: continue
                    ok, note, dur = ia.verify_decode(cand["url"])
                    if ok:
                        c.execute("UPDATE items SET stream_url=?,ia_file=?,verified=1,verified_at=?,verify_note=?,runtime_min=COALESCE(runtime_min,?) WHERE uid=?", (cand["url"], cand["name"], time.time(), f"{cand['quality']} {note}", int(dur // 60) or None, uid)); c.commit(); self._post(lambda _a=(uid, True, note): self.verified.emit(*_a)); return
                c.execute("UPDATE items SET verified=0,verified_at=?,verify_note=? WHERE uid=?", (time.time(), note, uid)); c.commit(); self._post(lambda _a=(uid, False, note): self.verified.emit(*_a))
            finally: c.close()
        threading.Thread(target=work, daemon=True).start()
