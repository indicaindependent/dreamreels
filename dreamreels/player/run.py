"""Player boot. `--screenshot out.png` renders one frame offscreen (no mpv) for QA without touching the TV."""
from __future__ import annotations
import argparse, os, sys, tempfile
from pathlib import Path

def main(cfg: dict, argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dreamreels player")
    ap.add_argument("--screenshot"); ap.add_argument("--after", type=int, default=1500); ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--theme"); ap.add_argument("--windowed", action="store_true"); ap.add_argument("--no-video", action="store_true"); ap.add_argument("--zone", default="rails"); ap.add_argument("--dreamy", default="")
    a, _ = ap.parse_known_args(argv)
    shot = bool(a.screenshot)
    if shot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("QT_QUICK_BACKEND", "software")
    from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal
    from PySide6.QtGui import QGuiApplication, QFontDatabase
    from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
    from .. import __version__, GITHUB_URL
    from ..core.paths import ASSETS, CACHE_DIR, ensure_dirs
    from ..badge.iim import badge_svg
    from ..ui.theme import Theme
    from ..dreamy.backend import DreamyBackend
    from .backend import Backend
    from .gamepad import GamepadBridge
    ensure_dirs()
    app = QGuiApplication(sys.argv[:1])
    for f in (ASSETS / "fonts").glob("*.ttf"): QFontDatabase.addApplicationFont(str(f))
    video_enabled = not shot and not a.no_video
    if video_enabled:
        from .mpv_widget import MpvObject
        qmlRegisterType(MpvObject, "dreamreels", 1, 0, "MpvObject")
    else:
        from PySide6.QtQuick import QQuickItem
        qmlRegisterType(QQuickItem, "dreamreels", 1, 0, "MpvObject")
    badge_path = CACHE_DIR / "badge.svg"; badge_path.write_text(badge_svg())
    qr_path = CACHE_DIR / "github_qr.png"
    try:
        import qrcode; qrcode.make(GITHUB_URL, box_size=10, border=2).save(qr_path)
    except Exception:
        qr_path = badge_path
    class App(QObject):
        changed = Signal()
        def __init__(s): super().__init__(); s._kiosk = not a.windowed and not shot and cfg["meta"].get("input_mode") != "windowed"
        version = Property(str, lambda s: __version__, constant=True)
        githubUrl = Property(str, lambda s: GITHUB_URL, constant=True)
        badgeUrl = Property(str, lambda s: QUrl.fromLocalFile(str(badge_path)).toString(), constant=True)
        qrUrl = Property(str, lambda s: QUrl.fromLocalFile(str(qr_path)).toString(), constant=True)
        kiosk = Property(bool, lambda s: s._kiosk, constant=True)
        shotDreamy = Property(str, lambda s: a.dreamy, constant=True)
        videoEnabled = Property(bool, lambda s: video_enabled, constant=True)
    theme = Theme(a.theme or cfg["meta"].get("theme", "midnight"))
    pad = GamepadBridge(enabled=not shot)
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(Path(__file__).resolve().parents[1] / "ui" / "qml"))
    mpv_holder = {}
    def get_mpv():
        if "m" not in mpv_holder:
            root = engine.rootObjects()[0]; obj = root.findChild(QObject, "mpv")
            mpv_holder["m"] = obj.mpv if obj is not None else None
        return mpv_holder["m"]
    backend = Backend(cfg, get_mpv)
    appobj = App()
    ctx = engine.rootContext()
    dreamy = DreamyBackend(cfg, theme)
    for k, v in (("backend", backend), ("pad", pad), ("theme", theme), ("app", appobj), ("dreamy", dreamy)): ctx.setContextProperty(k, v)
    engine._keep = (backend, pad, theme, appobj, dreamy)  # context objects must outlive the engine
    engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "ui" / "qml" / "Main.qml")))
    if not engine.rootObjects():
        print("QML failed to load", file=sys.stderr); return 2
    win = engine.rootObjects()[0]
    if shot:
        w, h = (int(x) for x in a.size.lower().split("x")); win.setWidth(w); win.setHeight(h)
        win.setProperty("zone", a.zone)
        def grab():
            img = win.grabWindow(); ok = img.save(a.screenshot); print(("saved " if ok else "FAILED ") + a.screenshot, img.width(), img.height()); app.exit(0 if ok else 3)
        QTimer.singleShot(a.after, grab)
    rc = app.exec()
    del engine  # tear the QML tree down before the Python context objects die
    return rc
