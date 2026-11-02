# PyInstaller spec for the single-file Windows build. Run from the repo root:
#   pyinstaller --noconfirm packaging/windows/DreamReels.spec
# libmpv-2.dll must be in packaging/windows/vendor/ first (the GitHub workflow fetches a pinned, hash-checked copy).
import os
from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
VENDOR = os.path.join(SPECPATH, "vendor")

datas = [
    (os.path.join(ROOT, "dreamreels", "ui"), os.path.join("dreamreels", "ui")),      # QML, JS, skins
    (os.path.join(ROOT, "dreamreels", "data"), os.path.join("dreamreels", "data")),  # lane seeds
    (os.path.join(ROOT, "assets"), "assets"),                                        # fonts, icons, Dreamy art
]
binaries = []
dll = os.path.join(VENDOR, "libmpv-2.dll")
if os.path.isfile(dll):
    binaries.append((dll, "."))            # lands in the bundle root, which mpv_widget puts on PATH
else:
    print("WARNING: libmpv-2.dll missing from packaging/windows/vendor - the exe will start without video")

a = Analysis(
    [os.path.join(SPECPATH, "dreamreels_entry.py")],     # top-level script, absolute import (see the file)
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "dreamreels.player.run", "dreamreels.wizard.run", "dreamreels.wizard.win_shortcuts",
        "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtQuickControls2", "PySide6.QtSvg", "PySide6.QtOpenGL",
    ],
    excludes=["evdev", "tkinter"],                       # evdev is Linux-only (gamepad); its absence is handled
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="DreamReels",
    icon=os.path.join(ROOT, "assets", "app", "dreamreels.ico"),
    console=False,                                       # no black console window behind the player
    upx=False,                                           # UPX-packed Qt DLLs trip antivirus and save little
    onefile=True,
)
