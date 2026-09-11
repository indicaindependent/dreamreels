"""Install identity. Local only - never transmitted. Drives the unique IIM badge."""
from __future__ import annotations
import hashlib, secrets
from .paths import INSTALL_ID_FILE, ensure_dirs

def install_id() -> str:
    ensure_dirs()
    if INSTALL_ID_FILE.exists():
        v = INSTALL_ID_FILE.read_text().strip()
        if len(v) == 32:
            return v
    v = secrets.token_hex(16)
    INSTALL_ID_FILE.write_text(v + "\n")
    return v

def badge_seed(iid: str | None = None) -> int:
    return int(hashlib.sha256((iid or install_id()).encode()).hexdigest()[:8], 16)
