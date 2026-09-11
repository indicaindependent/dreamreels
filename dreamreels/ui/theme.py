"""Theme tokens as a QObject. QML reads `theme.bg`, `theme.focus`... and re-binds when the theme changes.
Properties are declared in the class body (PySide registers them in the QMetaObject only at class creation)."""
from __future__ import annotations
import json
from pathlib import Path
from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtGui import QFontDatabase

THEMES_DIR = Path(__file__).parent / "themes"

def available() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(THEMES_DIR.glob("*.json"))]

def _installed(family: str, fallback: str) -> str:
    fams = set(QFontDatabase.families())
    return family if family in fams else fallback

class Theme(QObject):
    changed = Signal()
    def __init__(self, name: str = "midnight"):
        super().__init__(); self._d = {}; self.load(name)
    @Slot(str)
    def load(self, name: str):
        p = THEMES_DIR / f"{name}.json"
        if not p.exists(): p = THEMES_DIR / "midnight.json"
        self._d = json.loads(p.read_text())
        fb = _installed("DejaVu Sans", "Sans Serif")
        self._d["fontDisplay"] = _installed(self._d["fontDisplay"], fb)
        self._d["fontBody"] = _installed(self._d["fontBody"], fb)
        self.changed.emit()
    @Slot(result="QVariantList")
    def all(self): return available()
    name = Property(str, lambda self, k="name": str(self._d.get(k, "")), notify=changed)
    label = Property(str, lambda self, k="label": str(self._d.get(k, "")), notify=changed)
    mood = Property(str, lambda self, k="mood": str(self._d.get(k, "")), notify=changed)
    bg = Property(str, lambda self, k="bg": str(self._d.get(k, "")), notify=changed)
    surface = Property(str, lambda self, k="surface": str(self._d.get(k, "")), notify=changed)
    surface2 = Property(str, lambda self, k="surface2": str(self._d.get(k, "")), notify=changed)
    text = Property(str, lambda self, k="text": str(self._d.get(k, "")), notify=changed)
    muted = Property(str, lambda self, k="muted": str(self._d.get(k, "")), notify=changed)
    accent = Property(str, lambda self, k="accent": str(self._d.get(k, "")), notify=changed)
    accent2 = Property(str, lambda self, k="accent2": str(self._d.get(k, "")), notify=changed)
    focus = Property(str, lambda self, k="focus": str(self._d.get(k, "")), notify=changed)
    focusInner = Property(str, lambda self, k="focusInner": str(self._d.get(k, "")), notify=changed)
    danger = Property(str, lambda self, k="danger": str(self._d.get(k, "")), notify=changed)
    ok = Property(str, lambda self, k="ok": str(self._d.get(k, "")), notify=changed)
    fontDisplay = Property(str, lambda self, k="fontDisplay": str(self._d.get(k, "")), notify=changed)
    fontBody = Property(str, lambda self, k="fontBody": str(self._d.get(k, "")), notify=changed)
    radius = Property(float, lambda self, k="radius": float(self._d.get(k, 0)), notify=changed)
    focusScale = Property(float, lambda self, k="focusScale": float(self._d.get(k, 0)), notify=changed)
    glow = Property(bool, lambda self, k="glow": bool(self._d.get(k, False)), notify=changed)
    heroGradient = Property(bool, lambda self, k="heroGradient": bool(self._d.get(k, False)), notify=changed)
