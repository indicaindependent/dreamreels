"""Locate external tools. yt-dlp rots fast; prefer the NEWEST copy on the machine (user-space refreshes in
~/bin or ~/.local/bin beat a stale distro binary), measured by running --version, never by path order."""
from __future__ import annotations
import os, re, shutil, subprocess
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def ytdlp_path() -> str | None:
    cands = [Path.home() / "bin/yt-dlp", Path.home() / ".local/bin/yt-dlp", Path("/usr/local/bin/yt-dlp"), Path("/usr/bin/yt-dlp")]
    w = shutil.which("yt-dlp")
    if w: cands.append(Path(w))
    best, bestv = None, ""
    for p in cands:
        if not p.is_file() or not os.access(p, os.X_OK): continue
        try: v = subprocess.run([str(p), "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception: continue
        if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}(\.\d+)?", v) and v > bestv: best, bestv = str(p), v
    return best

def ytdlp_version() -> str:
    p = ytdlp_path()
    if not p: return ""
    return subprocess.run([p, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()

def mpv_ytdl_opts() -> list[str]:
    p = ytdlp_path(); return [f"--script-opts=ytdl_hook-ytdl_path={p}"] if p else []
