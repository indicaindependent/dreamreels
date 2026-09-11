"""QObject face of the Dreamy agent for QML: ask() runs the tools in a thread, answer() carries JSON.
check(uid) runs verify_decode in a thread and emits verified(uid, ok, note) so a CHECK button can become PLAY."""
from __future__ import annotations
import json, threading, time
from PySide6.QtCore import QObject, Signal, Slot, Property
from ..core import db as dbmod
from . import agent
from .mascot import dreamy_svg
from ..core.paths import CACHE_DIR
from ..ui.theme import available as themes_available

class DreamyBackend(QObject):
    answer = Signal(str)           # JSON {text, buttons}
    verified = Signal(str, bool, str)
    busyChanged = Signal()
    def __init__(self, cfg: dict, theme=None):
        super().__init__(); self.cfg = cfg; self._busy = False; self._theme = theme; self._mc = {}
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
            try: res = agent.ask(self.cfg, text)
            except Exception as e: res = {"text": f"Something went wrong: {str(e)[:120]}", "buttons": []}
            self.answer.emit(json.dumps(res)); self._set_busy(False)
        threading.Thread(target=work, daemon=True).start()
    @Slot(str)
    def check(self, uid: str):
        def work():
            from ..sources import archive_org as ia
            c = dbmod.connect()
            try:
                row = c.execute("SELECT * FROM items WHERE uid=?", (uid,)).fetchone()
                if not row: self.verified.emit(uid, False, "gone"); return
                if row["source"] == "youtube":
                    ok, note, dur = ia.verify_decode(row["stream_url"], frames=24, timeout=90)
                    if ok: c.execute("UPDATE items SET verified=1,verified_at=?,verify_note=?,runtime_min=? WHERE uid=?", (time.time(), note, int(dur // 60) or None, uid))
                    else: c.execute("UPDATE items SET verified=0,verified_at=?,verify_note=? WHERE uid=?", (time.time(), note, uid))
                    c.commit(); self.verified.emit(uid, ok, note); return
                meta = ia.ia_meta(row["ia_id"]); cands = [x for x in ia.candidates(meta, row["ia_id"]) if not x["part"]][:3]; note = "no candidate files"
                for cand in cands:
                    ok0, _ = ia.prefilter(cand["url"])
                    if not ok0: continue
                    ok, note, dur = ia.verify_decode(cand["url"])
                    if ok:
                        c.execute("UPDATE items SET stream_url=?,ia_file=?,verified=1,verified_at=?,verify_note=?,runtime_min=COALESCE(runtime_min,?) WHERE uid=?", (cand["url"], cand["name"], time.time(), f"{cand['quality']} {note}", int(dur // 60) or None, uid)); c.commit(); self.verified.emit(uid, True, note); return
                c.execute("UPDATE items SET verified=0,verified_at=?,verify_note=? WHERE uid=?", (time.time(), note, uid)); c.commit(); self.verified.emit(uid, False, note)
            finally: c.close()
        threading.Thread(target=work, daemon=True).start()
