"""dreamreels doctor: measures the machine, never guesses. Each check names its instrument and includes a
control where one exists. Exit 0 = all green, 1 = warnings, 2 = a lane is broken."""
from __future__ import annotations
import json, os, re, shutil, socket, subprocess, sys, time, urllib.request
from pathlib import Path
from .core import config as cfgmod, db as dbmod
from .core.paths import DB_FILE, POSTER_CACHE

def _v(cmd):
    try: r = subprocess.run(cmd, capture_output=True, text=True, timeout=20); return ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[0]
    except Exception as e: return f"ERR {str(e)[:40]}"

def run(youtube_probe: bool = True) -> int:
    cfg = cfgmod.load(); rows = []; worst = 0
    def add(level, name, measured):  # level 0 ok, 1 warn, 2 fail
        nonlocal worst; worst = max(worst, level); rows.append((level, name, measured)); print(["OK  ", "WARN", "FAIL"][level], name.ljust(22), measured)
    # tools
    for tool in ("mpv", "ffprobe"):
        p = shutil.which(tool); add(0 if p else 2, tool, f"{p} {_v([tool, '--version'])[:40]}" if p else "missing")
    from .core.tools import ytdlp_path
    yt = ytdlp_path()
    if yt:
        ver = _v([yt, "--version"]); m = re.match(r"(\d{4})\.(\d{2})\.(\d{2})", ver)
        age = (time.time() - time.mktime((int(m[1]), int(m[2]), int(m[3]), 0, 0, 0, 0, 0, -1))) / 86400 if m else 9999
        add(0 if age < 60 else 1, "yt-dlp", f"{yt} {ver} ({age:.0f} days old){'' if age < 60 else ' - run sudo dreamreels-apply to refresh'}")
    else: add(1 if not cfg["sources"].get("youtube") else 2, "yt-dlp", "missing")
    js = shutil.which("node") or shutil.which("deno"); add(0 if js else (2 if cfg["sources"].get("youtube") else 1), "js runtime", f"{js} {_v([js, '--version'])}" if js else "none (YouTube needs node or deno)")
    # network + archive.org + tmdb (with a bogus-host control)
    def http(url, hdr=None, t=12):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "DreamReels-doctor", **(hdr or {})}), timeout=t); return r.status, r.read(200)
        except Exception as e: return getattr(e, "code", 0), str(e)[:60].encode()
    ctrl = http("https://zzqq-nonexistent-dreamreels.invalid/"); add(0 if ctrl[0] == 0 else 2, "control (bogus host)", f"status={ctrl[0]} (must fail)")
    s, _ = http("https://archive.org/metadata/house_on_haunted_hill_ipod"); add(0 if s == 200 else 2, "archive.org", f"metadata API status={s}")
    tok = cfg["tmdb"].get("read_token", "")
    if tok:
        s, _ = http("https://api.themoviedb.org/3/configuration", {"Authorization": f"Bearer {tok}"}); add(0 if s == 200 else 2, "TMDB token", f"/configuration status={s} (token len {len(tok)})")
    else: add(1, "TMDB token", "not set - text tiles only")
    # mounts
    for m in cfg["nas"].get("mounts") or []:
        mp = "/media/dreamreels/" + re.sub(r"[^A-Za-z0-9_-]", "_", m.split("/")[-1]); mounted = os.path.ismount(mp); n = len(os.listdir(mp)) if mounted else 0
        add(0 if mounted and n else (1 if mounted else 2), f"mount {m}", f"{mp} mounted={mounted} entries={n}")
    # db
    if DB_FILE.exists():
        c = dbmod.connect()
        try:
            v = dict(c.execute("SELECT source||':'||verified, COUNT(*) FROM items GROUP BY 1").fetchall()); j = dict(c.execute("SELECT status, COUNT(*) FROM jobs GROUP BY 1").fetchall())
            last = c.execute("SELECT MAX(updated) FROM jobs WHERE status='done'").fetchone()[0] or 0
            add(0, "library", f"{DB_FILE} items={sum(v.values())} verified={sum(n for k, n in v.items() if k.endswith(':1'))} jobs={j}")
            add(0 if time.time() - last < 2 * 86400 else 1, "grower last run", time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else "never")
        finally: c.close()
    else: add(1, "library", "no database yet - run the wizard / import-v1")
    add(0, "poster cache", f"{POSTER_CACHE} files={len(list(POSTER_CACHE.glob('*.jpg'))) if POSTER_CACHE.exists() else 0}")
    # youtube decode receipt (the only proof that lane works)
    if youtube_probe and cfg["sources"].get("youtube") and yt and js:
        from .sources.archive_org import verify_decode
        ok, note, dur = verify_decode("https://www.youtube.com/watch?v=aqz-KE-bpKQ", frames=24, timeout=90)  # Big Buck Bunny, 10:34, CC-BY
        add(0 if ok and 600 < dur < 660 else 2, "YouTube decode", f"{note} (expect ~634 s)")
    print(f"\n{'ALL GREEN' if worst == 0 else 'WARNINGS' if worst == 1 else 'SOMETHING IS BROKEN'}"); return worst
