"""archive.org discovery + candidate selection (ported from DreamReel v1 mapper, proven on 1,144 films)
+ a REAL decode proof. The v1 range-GET is kept only as a cheap pre-filter: a 206 on 4 bytes is not a
playable stream (Sep 6 2026 lesson). `verify_decode` is the only thing that may set verified=1."""
from __future__ import annotations
import json, re, subprocess, time, urllib.parse, urllib.request
from .. import __version__, GITHUB_URL

IA = "https://archive.org"
UA = f"DreamReels/{__version__} (+{GITHUB_URL})"
PLAYABLE_RE = re.compile(r"\.(mp4|m4v|webm|ogv|ogg|mkv)$", re.I)
BLOCK_RE = re.compile(r"\b(porn|pornographic|xxx|hardcore|hentai|erotic|adult\s*film|softcore|schulm[a\u00e4]dchen|explicit\s*sex|satanic\s*ritual|devil\s*worship|nazi|neo.?nazi|white\s*power|hate\s*group|self.?harm|suicide\s*(guide|method)|how\s*to\s*(kill|die))\b", re.I)
_last = [0.0]

def _throttle(rps: float = 1.0):
    wait = _last[0] + 1.0 / rps - time.time()
    if wait > 0: time.sleep(wait)
    _last[0] = time.time()

def http_json(url: str, timeout=15, tries=3) -> dict:
    for i in range(tries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            code = getattr(e, "code", 0)
            if code == 404: return {}
            time.sleep(2 * (i + 1))
    return {}

def blocked(text) -> bool: return bool(BLOCK_RE.search(str(text or "")))

def _quality(name, mb):
    if re.search(r"512kb|256kb|240p", name, re.I): return "Low", 1
    if re.search(r"1080|1920|fullhd|fhd", name, re.I) or mb > 1400: return "1080p", 4
    if re.search(r"720|hd\b", name, re.I) or mb > 600: return "720p", 3
    return "SD", 2

def _score(name, size):
    s = 0
    if re.search(r"\.(mp4|m4v)$", name, re.I): s += 1000
    elif re.search(r"\.webm$", name, re.I): s += 700
    elif re.search(r"\.mkv$", name, re.I): s += 500
    elif re.search(r"\.(ogv|ogg)$", name, re.I): s += 400
    if re.search(r"_(PS3|PSP|iPod|iPhone)", name, re.I): s -= 120
    mb = (size or 0) / 1048576
    if 120 < mb < 2500: s += 250
    if mb >= 2500: s -= 60
    return s + min((size or 0) / 1e7, 40)

# underscores are word characters, so \b never fires inside "a_part_1" -- use letter lookarounds instead (found by tests/test_agent_and_sources.py)
PART_RE = re.compile(r"(?<![0-9])(\d{1,2})[\s_-]*of[\s_-]*(\d{1,2})(?![0-9])|(?<![A-Za-z])(part|pt|cd|disc|reel)[\s_-]*(\d{1,2})(?![0-9])", re.I)

def ia_meta(ident: str) -> dict: return http_json(f"{IA}/metadata/{urllib.parse.quote(ident)}") or {"metadata": {}, "files": []}
def stream_url(ia_id: str, name: str) -> str: return f"{IA}/download/{ia_id}/{urllib.parse.quote(name)}"

def candidates(meta: dict, ia_id: str) -> list[dict]:
    files = [{"name": f.get("name", ""), "size": int(f.get("size") or 0)} for f in meta.get("files", []) if PLAYABLE_RE.search(f.get("name", ""))]
    files.sort(key=lambda f: _score(f["name"], f["size"]), reverse=True)
    out = []
    for f in files:
        mb = round(f["size"] / 1048576) if f["size"] else 0; q, qr = _quality(f["name"], mb); m = PART_RE.search(f["name"])
        out.append({"name": f["name"], "size_mb": mb, "quality": q, "qrank": qr, "part": bool(m), "url": stream_url(ia_id, f["name"]), "ia_id": ia_id})
    return out

def strict_pd(meta_md: dict, year: int | None) -> bool:
    lic = str(meta_md.get("licenseurl") or "") + " " + str(meta_md.get("rights") or "")
    return bool(year and year <= 1930) or bool(re.search(r"publicdomain|public\s*domain|/zero/|cc0", lic, re.I))

def search(query: str, rows=50, page=1, sort="downloads desc") -> list[dict]:
    p = urllib.parse.urlencode([("q", query), ("rows", rows), ("page", page), ("output", "json"), ("sort[]", sort)] + [("fl[]", f) for f in ("identifier", "title", "year", "date", "downloads", "subject", "licenseurl", "description", "runtime")])
    j = http_json(f"{IA}/advancedsearch.php?{p}", timeout=25)
    return (j.get("response") or {}).get("docs") or []

def discover_query(decade: int | None = None, genre: str | None = None) -> str:
    q = ["mediatype:movies", "collection:(feature_films OR SciFi_Horror OR Film_Noir OR classic_tv OR comedy_films OR silent_films)"]
    if decade: q.append(f"year:[{decade} TO {decade + 9}]")
    if genre: g = genre.replace("Film-Noir", "noir").replace("Sci-Fi", "science fiction"); q.append(f"(subject:({g}) OR description:({g}))")
    return " AND ".join(q)

def prefilter(url: str, timeout=9) -> tuple[bool, str]:
    """Cheap negative filter only: a 404/500/html body is dead. A pass here proves nothing."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-3"}); r = urllib.request.urlopen(req, timeout=timeout)
        ct = (r.headers.get("content-type") or "").lower(); body = r.read(4)
        return (r.status in (200, 206) and body[:1] != b"<"), f"{r.status} {ct[:30]}"
    except Exception as e: return False, str(e)[:60]

def verify_decode(url: str, frames: int = 48, timeout: int = 60) -> tuple[bool, str, float]:
    """THE proof: mpv decodes `frames` video frames end to end (exit 0 + a 'VO: [null] WxH' line in its own
    log), then ffprobe gives a duration. Returns (ok, note, duration_sec). Never trust anything weaker."""
    import os, tempfile
    fd, logp = tempfile.mkstemp(prefix="dr_mpv_", suffix=".log"); os.close(fd)
    try:
        try:
            from ..core.tools import mpv_ytdl_opts
            p = subprocess.run(["mpv", "--no-config", "--vo=null", "--ao=null", "--hwdec=no", "--no-terminal", f"--frames={frames}", f"--user-agent={UA}", "--msg-level=all=v", f"--log-file={logp}", *mpv_ytdl_opts(), url], capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError: return False, "mpv missing", 0.0
        except subprocess.TimeoutExpired: return False, f"mpv timeout {timeout}s", 0.0
        try: out = open(logp, errors="replace").read()
        except Exception: out = ""
        vo = re.search(r"VO: \[null\] (\d+x\d+)", out)
        if p.returncode != 0 or not vo:
            err = re.findall(r"\]\[(?:error|fatal)\]\[[^\]]+\] ([^\n]{0,90})", out) or re.findall(r"(?:Failed to open|HTTP error|Errors when loading)[^\n]{0,80}", out) or ["no video output line"]
            return False, f"mpv rc={p.returncode} {err[-1][:90]}", 0.0
        dur = 0.0
        try:
            if re.search(r"youtube\.com|youtu\.be", url):  # ffprobe cannot read a watch page; ask yt-dlp for the metadata duration
                from ..core.tools import ytdlp_path
                q = subprocess.run([ytdlp_path() or "yt-dlp", "--no-warnings", "--print", "duration", url], capture_output=True, text=True, timeout=45); dur = float((q.stdout or "0").strip().splitlines()[0] or 0)
            else:
                q = subprocess.run(["ffprobe", "-v", "error", "-user_agent", UA, "-show_entries", "format=duration", "-of", "csv=p=0", url], capture_output=True, text=True, timeout=30); dur = float((q.stdout or "0").strip() or 0)
        except Exception: pass
        return True, f"decoded {frames} frames @ {vo.group(1)}; duration {dur:.0f}s", dur
    finally:
        try: os.unlink(logp)
        except Exception: pass
