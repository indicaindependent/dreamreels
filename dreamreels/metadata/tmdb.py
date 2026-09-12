"""TMDB v3 with a Read Access Token. Every response cached in http_cache (30 d). Images cached to disk.
This product uses the TMDB API but is not endorsed or certified by TMDB."""
from __future__ import annotations
import hashlib, json, re, time, urllib.parse, urllib.request
from ..core import db as dbmod
from ..core.paths import POSTER_CACHE
from .. import __version__, GITHUB_URL
API = "https://api.themoviedb.org/3"; IMG = "https://image.tmdb.org/t/p/"
UA = f"DreamReels/{__version__} (+{GITHUB_URL})"

def _fetch_image_bytes(url: str, timeout=15) -> bytes | None:
    """image.tmdb.org is a multi-CDN host; some edges are unreachable from some networks (measured: one CDN's
    edge gave 'No route to host' over a VPN egress while another edge served 200). Try the resolver's answer first, then every
    A record from Google DoH, pinning SNI + Host so the CDN still serves the right site."""
    import http.client, json, socket, ssl
    from urllib.parse import urlparse
    u = urlparse(url); host = u.hostname; pathq = u.path + (("?" + u.query) if u.query else "")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status == 200: return r.read()
    except Exception: pass
    ips = []
    try:
        req = urllib.request.Request(f"https://dns.google/resolve?name={host}&type=A", headers={"User-Agent": UA, "Accept": "application/dns-json"})
        with urllib.request.urlopen(req, timeout=8) as r: ips = [a["data"] for a in json.load(r).get("Answer", []) if a.get("type") == 1]
    except Exception: pass
    try: ips += [ai[4][0] for ai in socket.getaddrinfo(host, 443, socket.AF_INET)]
    except Exception: pass
    seen = set()
    for ip in ips:
        if ip in seen: continue
        seen.add(ip)
        try:
            ctx = ssl.create_default_context(); conn = http.client.HTTPSConnection(ip, 443, timeout=timeout, context=ctx)
            conn._server_hostname = host  # SNI
            conn.sock = ctx.wrap_socket(socket.create_connection((ip, 443), timeout=timeout), server_hostname=host)
            conn.request("GET", pathq, headers={"Host": host, "User-Agent": UA}); r = conn.getresponse(); data = r.read(); conn.close()
            if r.status == 200 and data: return data
        except Exception: continue
    return None

class TMDB:
    def __init__(self, token: str): self.token = token
    def _get(self, path: str, params: dict | None = None, ttl=30 * 86400):
        if not self.token: return None
        url = f"{API}{path}?{urllib.parse.urlencode(params or {})}"; key = "tmdb:" + hashlib.sha1(url.encode()).hexdigest()
        c = dbmod.connect()
        try:
            row = c.execute("SELECT body, fetched FROM http_cache WHERE key=?", (key,)).fetchone()
            if row and time.time() - row["fetched"] < ttl: return json.loads(row["body"])
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}", "User-Agent": UA, "accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r: body = r.read()
            except Exception as e:
                if getattr(e, "code", 0) == 404: body = b"{}"
                else: return json.loads(row["body"]) if row else None
            c.execute("INSERT OR REPLACE INTO http_cache(key,etag,body,fetched) VALUES(?,?,?,?)", (key, "", body, time.time())); c.commit()
            return json.loads(body or b"{}")
        finally: c.close()
    def search_movie(self, title: str, year: int | None = None) -> dict | None:
        p = {"query": title, "include_adult": "false"}
        if year: p["year"] = year
        j = self._get("/search/movie", p) or {}; res = j.get("results") or []
        if not res and year: j = self._get("/search/movie", {"query": title, "include_adult": "false"}) or {}; res = j.get("results") or []
        if not res: return None
        norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
        for r in res:
            ry = int((r.get("release_date") or "0000")[:4] or 0)
            if norm(r.get("title")) == norm(title) and (not year or abs(ry - year) <= 2): return r
        r = res[0]; ry = int((r.get("release_date") or "0000")[:4] or 0)
        return r if (not year or abs(ry - year) <= 3) else None
    def movie(self, tmdb_id: int) -> dict | None: return self._get(f"/movie/{tmdb_id}", {"append_to_response": "credits"})
    def tv(self, tmdb_id: int) -> dict | None: return self._get(f"/tv/{tmdb_id}")
    def season(self, tmdb_id: int, n: int) -> dict | None: return self._get(f"/tv/{tmdb_id}/season/{n}")
    def search_tv(self, title: str, year: int | None = None) -> dict | None:
        j = self._get("/search/tv", {"query": title, **({"first_air_date_year": year} if year else {})}) or {}; res = j.get("results") or []; return res[0] if res else None
    def person(self, name: str) -> dict | None:
        j = self._get("/search/person", {"query": name}) or {}; res = j.get("results") or []; return res[0] if res else None
    def person_credits(self, pid: int) -> dict | None: return self._get(f"/person/{pid}/movie_credits")
    @staticmethod
    def image(path: str | None, size="w500") -> str | None:
        if not path: return None
        POSTER_CACHE.mkdir(parents=True, exist_ok=True); dest = POSTER_CACHE / (hashlib.sha1(f"{size}{path}".encode()).hexdigest()[:16] + ".jpg")
        if dest.exists() and dest.stat().st_size > 1000: return str(dest)
        data = _fetch_image_bytes(f"{IMG}{size}{path}")
        if data and len(data) > 1000: dest.write_bytes(data); return str(dest)
        return None
    def enrich(self, m: dict) -> dict:
        """Flatten a movie+credits response into item columns."""
        crew = ((m.get("credits") or {}).get("crew") or []); director = ", ".join(c["name"] for c in crew if c.get("job") == "Director")[:120]
        cast = [(c["id"], c["name"]) for c in ((m.get("credits") or {}).get("cast") or [])[:8]]
        year = int((m.get("release_date") or "0000")[:4] or 0) or None
        return {"tmdb_id": m.get("id"), "tmdb_type": "movie", "imdb_id": m.get("imdb_id"), "title": m.get("title"), "year": year, "blurb": m.get("overview"), "director": director,
                "runtime_min": m.get("runtime"), "genres": ", ".join(g["name"] for g in m.get("genres") or []), "decade": (year // 10) * 10 if year else None,
                "poster": f"{IMG}w500{m['poster_path']}" if m.get("poster_path") else None, "backdrop": f"{IMG}w1280{m['backdrop_path']}" if m.get("backdrop_path") else None,
                "poster_local": self.image(m.get("poster_path"), "w500"), "backdrop_local": self.image(m.get("backdrop_path"), "w1280"), "_cast": cast}
