from __future__ import annotations
import argparse, os, sys
from pathlib import Path
def main(cfg: dict, argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dreamreels wizard"); ap.add_argument("--screenshot"); ap.add_argument("--after", type=int, default=1500); ap.add_argument("--step", type=int, default=0); ap.add_argument("--theme"); ap.add_argument("--windowed", action="store_true")
    a, _ = ap.parse_known_args(argv); shot = bool(a.screenshot)
    if shot: os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("QT_QUICK_BACKEND", "software")
    from PySide6.QtCore import QObject, Property, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication, QFontDatabase
    from PySide6.QtQml import QQmlApplicationEngine
    import PySide6.QtQuick  # noqa: F401 - without this the root Window is wrapped as plain QWindow (no grabWindow)
    from .. import __version__, GITHUB_URL
    from ..core.paths import ASSETS, CACHE_DIR, ensure_dirs
    from ..badge.iim import badge_svg
    from ..ui.theme import Theme
    from .backend import WizardBackend
    ensure_dirs(); app = QGuiApplication(sys.argv[:1])
    for f in (ASSETS / "fonts").glob("*.ttf"): QFontDatabase.addApplicationFont(str(f))
    badge_path = CACHE_DIR / "badge.svg"; badge_path.write_text(badge_svg())
    class App(QObject):
        version = Property(str, lambda s: __version__, constant=True); githubUrl = Property(str, lambda s: GITHUB_URL, constant=True)
        badgeUrl = Property(str, lambda s: QUrl.fromLocalFile(str(badge_path)).toString(), constant=True)
        kiosk = Property(bool, lambda s: not a.windowed and not shot, constant=True)
    theme = Theme(a.theme or cfg["meta"].get("theme", "midnight")); wiz = WizardBackend(cfg); appobj = App()
    wiz.changed.connect(lambda: theme.load(wiz.theme) if theme.name != wiz.theme else None)
    engine = QQmlApplicationEngine(); engine._keep = (theme, wiz, appobj)
    qml = Path(__file__).resolve().parents[1] / "ui" / "qml"; engine.addImportPath(str(qml))
    for k, v in (("wiz", wiz), ("theme", theme), ("app", appobj)): engine.rootContext().setContextProperty(k, v)
    engine.load(QUrl.fromLocalFile(str(qml / "Wizard.qml")))
    if not engine.rootObjects(): print("QML failed to load", file=sys.stderr); return 2
    win = engine.rootObjects()[0]
    if shot:
        for _ in range(a.step): wiz.next()
        win.setWidth(1920); win.setHeight(1080)
        def grab():
            try:
                img = win.grabWindow(); ok = img.save(a.screenshot); print(("saved " if ok else "FAILED ") + a.screenshot); app.exit(0 if ok else 3)
            except Exception as e:
                print("GRAB FAILED", e); app.exit(4)
        QTimer.singleShot(a.after, grab)
    rc = app.exec(); del engine; return rc
