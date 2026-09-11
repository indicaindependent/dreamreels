"""XDG-compliant paths. Nothing is ever written under the repo checkout."""
from __future__ import annotations
import os
from pathlib import Path

def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or (Path.home() / default))

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
REPO_ROOT = Path(__file__).resolve().parents[2]
ASSETS = REPO_ROOT / "assets"

def ensure_dirs() -> None:
    for p in (CONFIG_DIR, DATA_DIR, STATE_DIR, CACHE_DIR, LOG_DIR, POSTER_CACHE):
        p.mkdir(parents=True, exist_ok=True)
