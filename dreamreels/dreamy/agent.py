"""Dreamy, the tool-using agent. Deterministic: intent parser -> tools -> templated answer + buttons.
No LLM sits between stranger text (archive.org, YouTube, TMDB) and an action, so nothing on the internet can
instruct this player. Every button is one of: PLAY (decode-verified item in the library), CHECK (a candidate
that must pass verify_decode before it may play), ASK (a follow-up question Dreamy offers).
Pete's rule (Sep 11 2026): Dreamy returns ONLY working playable buttons and factual film-database answers."""
from __future__ import annotations
import json, re, subprocess, time
from ..core import db as dbmod
from ..metadata.tmdb import TMDB
from ..sources import archive_org as ia

GENRES = {"noir": "Film-Noir", "film noir": "Film-Noir", "horror": "Horror", "sci-fi": "Sci-Fi", "scifi": "Sci-Fi", "science fiction": "Sci-Fi", "comedy": "Comedy", "comedies": "Comedy", "drama": "Drama", "western": "Western", "westerns": "Western", "mystery": "Mystery", "romance": "Romance", "thriller": "Thriller", "war": "War", "documentary": "Documentary", "cartoon": "Animation", "cartoons": "Animation", "animation": "Animation", "musical": "Musical", "musicals": "Musical"}
SOURCES = {"public domain": "pd", "archive": "pd", "nas": "nas", "my drive": "nas", "youtube": "youtube", "channel 83": "chan83", "toon town": "toontown", "music": "music"}
STOP = {"find", "me", "movies", "movie", "films", "film", "from", "the", "a", "an", "any", "some", "in", "with", "starring", "by", "directed", "of", "on", "show", "play", "search", "for", "please", "dreamy", "video", "videos", "latest", "newest", "recent", "clip", "was", "were", "is", "did", "does", "has", "have", "what", "who", "which", "tell", "about", "and", "or", "to", "that", "showing", "talking", "at", "it", "s"}

def parse(text: str) -> dict:
    t = " " + text.strip().lower() + " "
    q = {"raw": text.strip(), "intent": "find", "decade": None, "year": None, "genre": None, "source": None, "person": None, "title": None, "youtube": False, "latest": False}
    if re.search(r"^\s*(was|were|is|did|does|has|have|who|what|which|when|how many|tell me about)\b", t.strip()): q["intent"] = "question"
    m = re.search(r"\b(1[89]\d0|20[0-2]0)s\b", t) or re.search(r"\b(the )?(twenties|thirties|forties|fifties|sixties|seventies|eighties|nineties)\b", t)
    if m:
        words = {"twenties": 1920, "thirties": 1930, "forties": 1940, "fifties": 1950, "sixties": 1960, "seventies": 1970, "eighties": 1980, "nineties": 1990}
        q["decade"] = int(m.group(1)) if m.group(1) and m.group(1).isdigit() else words.get(m.group(2) if m.lastindex and m.lastindex >= 2 else "", None)
    y = re.search(r"\b(19\d\d|20[0-2]\d)\b(?!s)", t)
    if y and not q["decade"]: q["year"] = int(y.group(1))
    for k, v in GENRES.items():
        if f" {k} " in t: q["genre"] = v; break
    for k, v in SOURCES.items():
        if k in t: q["source"] = v; break
    if "youtube" in t or re.search(r"\b(latest|newest|recent)\b.*\b(video|clip|interview|speech)\b", t) or re.search(r"\b(video|clip)\b.*\b(of|showing)\b", t): q["youtube"] = True; q["latest"] = bool(re.search(r"\b(latest|newest|recent)\b", t))
    qt = re.search(r"[\"“']([^\"”']{2,80})[\"”']", text)
    if qt: q["title"] = qt.group(1).strip()
    # person = capitalised run of 2-3 words not in stop list (from the ORIGINAL casing)
    cand = re.findall(r"\b([A-Z][a-zA-Z'\.-]+(?:\s+[A-Z][a-zA-Z'\.-]+){1,2})\b", text)
    cand = [c for c in cand if c.lower().split()[0] not in STOP and c.lower() not in ("public domain", "toon town", "channel 83", "air force one", "film noir")]
    if cand: q["person"] = cand[0]
    # free text for youtube = everything minus stop words
    q["free"] = " ".join(w for w in re.sub(r"[^a-z0-9' ]", " ", t).split() if w not in STOP and not re.fullmatch(r"(1[89]\d0|20[0-2]0)s", w))
    return q

_PICTO = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F]+")
def _clean(s: str) -> str: return re.sub(r"\s{2,}", " ", _PICTO.sub("", s or "")).strip()  # third-party titles may carry emoji; the app never shows them
def _btn(kind, label, **kw): d = {"kind": kind, "label": _clean(label)}; d.update(kw); return d

def search_library(q: dict, limit=12) -> list[dict]:
    c = dbmod.connect()
    try:
        sql = "SELECT DISTINCT i.uid,i.title,i.year,i.verified,i.poster_local,i.source,i.director FROM items i"; w = ["i.blocked=0", "i.kind IN ('movie','episode','short','video')"]; p = []
        if q.get("person"):
            sql += " LEFT JOIN item_people ip ON ip.item_uid=i.uid LEFT JOIN people pp ON pp.tmdb_id=ip.tmdb_id"
            w.append("(pp.name LIKE ? OR i.director LIKE ? OR i.title LIKE ?)"); p += [f"%{q['person']}%"] * 3
        if q.get("decade"): w.append("i.decade=?"); p.append(q["decade"])
        if q.get("year"): w.append("i.year BETWEEN ? AND ?"); p += [q["year"] - 1, q["year"] + 1]
        if q.get("genre"): w.append("i.genres LIKE ?"); p.append(f"%{q['genre']}%")
        if q.get("source"): w.append("i.source=?"); p.append(q["source"])
        if q.get("title"): w.append("i.title LIKE ?"); p.append(f"%{q['title']}%")
        if not any(q.get(k) for k in ("person", "decade", "year", "genre", "title")) and not q.get("source"): return []
        rows = c.execute(f"{sql} WHERE {' AND '.join(w)} ORDER BY i.verified DESC, i.downloads DESC, i.year LIMIT ?", p + [limit]).fetchall()
        return [dict(r) for r in rows]
    finally: c.close()

def tmdb_person(cfg: dict, name: str, decade: int | None = None) -> dict | None:
    t = TMDB(cfg["tmdb"].get("read_token", ""))
    if not t.token: return None
    p = t.person(name)
    if not p: return None
    cr = t.person_credits(p["id"]) or {}
    films = []
    for cred in (cr.get("cast") or []) + (cr.get("crew") or []):
        yr = int((cred.get("release_date") or "0000")[:4] or 0)
        if not yr or (decade and not decade <= yr <= decade + 9): continue
        job = cred.get("character") and f"as {cred['character']}" or cred.get("job") or ""
        films.append({"title": cred.get("title"), "year": yr, "job": job, "tmdb_id": cred.get("id"), "pop": cred.get("popularity", 0)})
    seen = set(); out = []
    for f in sorted(films, key=lambda x: (-x["pop"], x["year"])):
        if f["tmdb_id"] in seen: continue
        seen.add(f["tmdb_id"]); out.append(f)
    return {"name": p["name"], "dept": p.get("known_for_department"), "id": p["id"], "films": out}

def discover_pd(q: dict, limit=8) -> list[dict]:
    parts = ["mediatype:movies"]
    if q.get("person"): parts.append(f'("{q["person"]}")')
    if q.get("title"): parts.append(f'title:("{q["title"]}")')
    if q.get("decade"): parts.append(f"year:[{q['decade']} TO {q['decade'] + 9}]")
    if q.get("year"): parts.append(f"year:[{q['year'] - 1} TO {q['year'] + 1}]")
    if q.get("genre"): g = q["genre"].replace("Film-Noir", "noir").replace("Sci-Fi", "science fiction"); parts.append(f"subject:({g})")
    if len(parts) < 2: return []
    docs = ia.search(" AND ".join(parts), rows=limit)
    return [{"ia_id": d["identifier"], "title": str(d.get("title") or d["identifier"]), "year": int(str(d.get("year") or "0")[:4] or 0) or None} for d in docs if d.get("identifier") and not ia.blocked(d.get("title"))]

def youtube_search(query: str, latest=False, limit=5) -> list[dict]:
    sp = "EgIIAQ%3D%3D" if latest else None  # upload_date sort (yt-dlp honours ytsearch only; we sort by upload_date ourselves)
    try:
        from ..core.tools import ytdlp_path
        p = subprocess.run([ytdlp_path() or "yt-dlp", "--flat-playlist", "-J", "--no-warnings", f"ytsearch{limit * 2 if latest else limit}:{query}"], capture_output=True, text=True, timeout=45)
        j = json.loads(p.stdout or "{}")
    except Exception as e: return [{"error": str(e)[:120]}]
    ents = [e for e in (j.get("entries") or []) if e and e.get("id")]
    if latest: ents.sort(key=lambda e: (e.get("upload_date") or e.get("timestamp") or "0"), reverse=True)
    return [{"video_id": e["id"], "title": e.get("title") or e["id"], "channel": e.get("uploader") or e.get("channel") or "", "url": f"https://www.youtube.com/watch?v={e['id']}", "duration": e.get("duration")} for e in ents[:limit]]

def add_candidate(kind: str, ext_id: str, title: str, year=None, source="pd", url=None) -> str:
    """Insert an UNVERIFIED item so a CHECK button has something to verify and PLAY later."""
    uid = f"{source}:{ext_id}"; c = dbmod.connect()
    try:
        c.execute("INSERT OR IGNORE INTO items(uid,source,kind,ext_id,ia_id,title,title_raw,year,decade,stream_url,verified,strict_pd,blocked,added) VALUES(?,?,?,?,?,?,?,?,?,?,0,0,0,?)",
                  (uid, source, kind, ext_id, ext_id if source == "pd" else None, title, title, year, (year // 10) * 10 if year else None, url, time.time()))
        c.execute("INSERT INTO jobs(kind,payload,status,not_before,created,updated) SELECT 'verify',?,'pending',?,?,? WHERE NOT EXISTS (SELECT 1 FROM jobs WHERE kind='verify' AND payload=? AND status IN ('pending','running'))", (json.dumps({"uid": uid}), time.time(), time.time(), time.time(), json.dumps({"uid": uid})))
        c.commit(); return uid
    finally: c.close()

def _describe(q):
    bits = []
    if q.get("person"): bits.append(q["person"])
    if q.get("genre"): bits.append(q["genre"].lower())
    if q.get("decade"): bits.append(f"from the {q['decade']}s")
    if q.get("year"): bits.append(f"around {q['year']}")
    if q.get("title"): bits.append(f'"{q["title"]}"')
    return " ".join(bits) or "that"

def ask(cfg: dict, text: str) -> dict:
    q = parse(text); buttons = []; lines = []
    if q["youtube"] or q["source"] == "youtube":
        if not cfg.get("sources", {}).get("youtube", False): return {"text": "The YouTube lane is switched off in setup. Turn it on in Settings and I can search channels and videos.", "buttons": []}
        hits = youtube_search(q["free"] or q["raw"], latest=q["latest"])
        if hits and hits[0].get("error"): return {"text": f"YouTube search is not working right now ({hits[0]['error']}). Settings has a Repair YouTube button.", "buttons": [_btn("ask", "Open Settings", query="__settings")]}
        if not hits: return {"text": f"I could not find any YouTube videos for {q['free'] or q['raw']}.", "buttons": []}
        lines.append(f"Found {len(hits)} video{'s' if len(hits) != 1 else ''}{' (newest first)' if q['latest'] else ''}. I check each one actually streams before it plays:")
        for h in hits:
            uid = add_candidate("video", h["video_id"], h["title"], None, "youtube", h["url"])
            lines.append(f"• {_clean(h['title'])} — {_clean(h['channel'])}"); buttons.append(_btn("check", _clean(h["title"])[:48], uid=uid))
        return {"text": "\n".join(lines), "buttons": buttons}
    lib = search_library(q)
    playable = [r for r in lib if r["verified"]]; pending = [r for r in lib if not r["verified"]]
    if q["intent"] == "question" and q.get("person"):
        info = tmdb_person(cfg, q["person"], q["decade"])
        if info is None and not cfg["tmdb"].get("read_token"): lines.append("I need a TMDB key to answer facts about people (Settings → Movie database key).")
        elif info is None: lines.append(f"I could not find anyone called {q['person']} in the movie database.")
        else:
            fl = info["films"]; span = f" in the {q['decade']}s" if q["decade"] else ""
            if not fl: lines.append(f"{info['name']} has no credited films{span} in the movie database.")
            else:
                lines.append(f"Yes. {info['name']} ({info['dept'] or 'film'}) has {len(fl)} credited film{'s' if len(fl) != 1 else ''}{span}, including:")
                for f in fl[:6]: lines.append(f"• {f['title']} ({f['year']}){' ' + f['job'] if f['job'] else ''}")
                if len(fl) > 6: lines.append(f"…and {len(fl) - 6} more.")
        if playable: lines.append(f"\n{len(playable)} of these are in your library and verified playable:"); buttons += [_btn("play", f"{r['title']} ({r['year'] or ''})".strip(), uid=r["uid"]) for r in playable[:6]]
        else: buttons.append(_btn("ask", "Find playable copies", query=f"find me {q['person']} movies{(' from the ' + str(q['decade']) + 's') if q['decade'] else ''}"))
        return {"text": "\n".join(lines), "buttons": buttons}
    # find intent
    if playable:
        lines.append(f"Here's what I can play for {_describe(q)} — {len(playable)} verified:")
        buttons += [_btn("play", f"{r['title']} ({r['year'] or ''})".strip(), uid=r["uid"]) for r in playable[:10]]
    if pending:
        lines.append(f"{len(pending)} more in your library have not passed the playback check yet:")
        buttons += [_btn("check", f"{r['title']} ({r['year'] or ''})".strip(), uid=r["uid"]) for r in pending[:6]]
    if not playable and cfg.get("sources", {}).get("publicdomain", True):
        found = discover_pd(q)
        if found:
            lines.append(f"Nothing verified in your library yet, but archive.org lists {len(found)} candidate{'s' if len(found) != 1 else ''} for {_describe(q)}. Press one and I'll test that it really plays:")
            for f in found: uid = add_candidate("movie", f["ia_id"], f["title"], f["year"], "pd"); buttons.append(_btn("check", f"{f['title'][:40]} ({f['year'] or '?'})", uid=uid))
    if not lines: lines.append(f"I could not find anything for {_describe(q)}. Try a name, a decade, or a genre — for example: find me 1940s film noir.")
    return {"text": "\n".join(lines), "buttons": buttons}
