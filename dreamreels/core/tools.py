"""Locate external tools. yt-dlp rots fast; prefer the NEWEST copy on the machine (user-space refreshes in
~/bin or ~/.local/bin beat a stale distro binary), measured by running --version, never by path order."""
from __future__ import annotations
import os, re, shutil, subprocess, sys
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def ytdlp_path() -> str | None:
    cands = [Path.home() / "bin/yt-dlp", Path.home() / ".local/bin/yt-dlp", Path("/usr/local/bin/yt-dlp"), Path("/usr/bin/yt-dlp")]
    if sys.platform == "win32":   # Windows: yt-dlp.exe next to DreamReels.exe, or anywhere on PATH
        cands = [Path(sys.executable).parent / "yt-dlp.exe"]
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


YT_JS_RUNTIME = "node"   # measured Sep 13 2026: without --js-runtimes node yt-dlp warns "No supported JavaScript runtime" and Google refuses the real read
def yt_direct_url(watch_url: str, max_h: int = 1080, timeout: int = 90) -> str:
    """Resolve a YouTube watch URL to one directly decodable media URL (video+audio progressive if possible). Raises on failure."""
    import subprocess
    exe = ytdlp_path() or "yt-dlp"
    fmt = f"b[height<={max_h}][ext=mp4]/bv*[height<={max_h}][ext=mp4]/b"
    out = subprocess.run([exe, "--js-runtimes", YT_JS_RUNTIME, "--no-playlist", "-f", fmt, "-g", watch_url], capture_output=True, text=True, timeout=timeout)
    urls = [l.strip() for l in (out.stdout or "").splitlines() if l.startswith("http")]
    if out.returncode != 0 or not urls: raise RuntimeError((out.stderr or "yt-dlp failed").strip().splitlines()[-1][:160] if (out.stderr or "").strip() else "yt-dlp returned no URL")
    return urls[0]
