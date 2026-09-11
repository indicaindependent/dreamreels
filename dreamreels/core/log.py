from __future__ import annotations
import logging, logging.handlers
from .paths import LOG_DIR, ensure_dirs

def setup(name: str = "dreamreels") -> logging.Logger:
    ensure_dirs()
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(LOG_DIR / f"{name}.log", maxBytes=2_000_000, backupCount=5)
    fh.setFormatter(fmt); log.addHandler(fh)
    sh = logging.StreamHandler(); sh.setFormatter(fmt); log.addHandler(sh)
    return log
