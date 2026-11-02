"""XDG-compliant paths. Nothing is ever written under the repo checkout."""
from __future__ import annotations
import os
from pathlib import Path

import sys
IS_WINDOWS = sys.platform == "win32"
FROZEN = bool(getattr(sys, "frozen", False))      # True inside the PyInstaller DreamReels.exe

def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or (Path.home() / default))

if IS_WINDOWS:   # %APPDATA% roams (settings), %LOCALAPPDATA% stays on this PC (library, logs, posters)
    _roam = Path(os.environ.get("APPDATA") or (Path.home() / "AppData/Roaming")) / "DreamReels"
    _local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData/Local")) / "DreamReels"
    CONFIG_DIR = _roam
    DATA_DIR = _local / "data"
    STATE_DIR = _local / "state"
    CACHE_DIR = _local / "cache"
else:
    CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "dreamreels"
    DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "dreamreels"
    STATE_DIR = _xdg("XDG_STATE_HOME", ".local/state") / "dreamreels"
    CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / "dreamreels"
CONFIG_FILE = CONFIG_DIR / "config.toml"
DB_FILE = DATA_DIR / "dreamreels.db"
PLAN_FILE = CONFIG_DIR / "plan.json"          # wizard output, consumed by dreamreels-apply (root)
INSTALL_ID_FILE = DATA_DIR / "install_id"
LOG_DIR = STATE_DIR / "logs"
POSTER_CACHE = CACHE_DIR / "posters"
REPO_ROOT = Path(getattr(sys, "_MEIPASS", "")) if FROZEN and getattr(sys, "_MEIPASS", None) else Path(__file__).resolve().parents[2]
ASSETS = REPO_ROOT / "assets"

def self_cmd(*args: str) -> list:
    """Command line that re-runs DreamReels itself: the exe when frozen, `python -m dreamreels` otherwise."""
    return [sys.executable, *args] if FROZEN else [sys.executable, "-m", "dreamreels", *args]

def detach_kwargs() -> dict:
    """Popen kwargs that let a child outlive the wizard on both platforms."""
    if IS_WINDOWS:
        import subprocess
        return {"creationflags": getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)}
    return {"start_new_session": True}

def ensure_dirs() -> None:
    for p in (CONFIG_DIR, DATA_DIR, STATE_DIR, CACHE_DIR, LOG_DIR, POSTER_CACHE):
        p.mkdir(parents=True, exist_ok=True)
