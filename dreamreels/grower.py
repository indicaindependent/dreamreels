"""The grower: discover -> map -> verify -> art, as resumable jobs in the `jobs` table.
Run `dreamreels grow --discover --limit 40` then `dreamreels grow --work 20` (cron-friendly, <=1 IA req/s).
verified=1 is set ONLY by archive_org.verify_decode."""
from __future__ import annotations
import json, re, time
from .core import db as dbmod, config as cfgmod
from .core.log import setup
from .sources import archive_org as ia
from .metadata.tmdb import TMDB
log = setup("grower")

def _job(c, kind, payload, delay=0):
    c.execute("INSERT INTO jobs(kind,payload,status,not_before,created,updated) VALUES(?,?,'pending',?,?,?)", (kind, json.dumps(payload), time.time() + delay, time.time(), time.time()))

def discover(cfg: dict, limit: int = 40) -> int:
    """Seed unverified pd items for every selected decade x genre. Skips items already present or blocked."""
    pd = cfg["publicdomain"]; strict = pd.get("strict_pd", True); n = 0
    c = dbmod.connect()
    try:
        combos = [(d, g) for d in (pd.get("decades") or [None]) for g in (pd.get("genres") or [None])]
        per = max(5, limit // max(1, len(combos)))
        # Sep 26 2026: discovery had plateaued (2 new PD titles in 7 nights). Cause, measured: every night fetched PAGE 1 of the
        # same downloads-sorted query per combo, so the same top rows were re-seen and skipped. Now a per-combo page cursor
        # (DATA_DIR/discover_cursor.json) walks deeper each night and wraps when a page comes back short; plus one
        # "recently uploaded" pass per decade so fresh archive.org uploads are seen the week they land.
        from .core import paths as _paths
        _cur_f = _paths.DATA_DIR / "discover_cursor.json"
        try: _cur = json.load(open(_cur_f))
        except Exception: _cur = {}
        def _pages(dec, gen):
            key = f"{dec}|{gen}"; page = int(_cur.get(key, 0)) + 1
            rows = ia.search(ia.discover_query(dec, gen), rows=per, page=page)
            _cur[key] = page if len(rows) >= per else 0
            return rows
        for dec, gen in combos:
            for d in _pages(dec, gen):
                ident = d.get("identifier"); title = str(d.get("title") or "").strip()
                if not ident or not title: continue
                uid = f"pd:{ident}"
                if c.execute("SELECT 1 FROM items WHERE uid=?", (uid,)).fetchone(): continue
                if ia.blocked(title) or ia.blocked(d.get("description")): c.execute("INSERT OR IGNORE INTO items(uid,source,kind,ext_id,ia_id,title,blocked,added) VALUES(?,?,?,?,?,?,1,?)", (uid, "pd", "movie", ident, ident, title, time.time())); continue
                year = int(str(d.get("year") or "0")[:4] or 0) or None
                sp = 1 if ia.strict_pd(d, year) else 0
                c.execute("INSERT OR IGNORE INTO items(uid,source,kind,ext_id,ia_id,title,title_raw,year,decade,downloads,strict_pd,blocked,verified,added) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,0,?)",
                          (uid, "pd", "movie", ident, ident, title, title, year, (year // 10) * 10 if year else dec, int(d.get("downloads") or 0), sp, time.time()))
                _job(c, "map", {"uid": uid}); n += 1
        for dec in (pd.get("decades") or [None]):
            try:
                for d in ia.search(ia.discover_query(dec, None), rows=20, sort="publicdate desc"):
                    ident = d.get("identifier"); title = str(d.get("title") or "").strip()
                    if not ident or not title or c.execute("SELECT 1 FROM items WHERE uid=?", (f"pd:{ident}",)).fetchone(): continue
                    if ia.blocked(title) or ia.blocked(d.get("description")): continue
                    year = int(str(d.get("year") or "0")[:4] or 0) or None
                    c.execute("INSERT OR IGNORE INTO items(uid,source,kind,ext_id,ia_id,title,title_raw,year,decade,downloads,strict_pd,blocked,verified,added) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,0,?)",
                              (f"pd:{ident}", "pd", "movie", ident, ident, title, title, year, (year // 10) * 10 if year else dec, int(d.get("downloads") or 0), 1 if ia.strict_pd(d, year) else 0, time.time()))
                    _job(c, "map", {"uid": f"pd:{ident}"}); n += 1
            except Exception as _e: log.warning("fresh-uploads pass %s: %s", dec, _e)
        try: json.dump(_cur, open(_cur_f, "w"))
        except Exception as _e: log.warning("cursor save: %s", _e)
        c.commit(); log.info("discover seeded %d", n); return n
    finally: c.close()

def discover_tvmovies(cfg: dict, pages: int = 1, rows: int = 100) -> int:
    """Phase C-TVM: seed 1970-1989 made-for-TV movies from archive.org (ia.TVMOVIE_QUERY), tagged genres='TV Movie'.
    Walks a page cursor (DATA_DIR/discover_cursor.json key 'tvmovie') so a nightly single page keeps finding new uploads;
    pass pages>1 for the one-off backfill. Items already present just gain the tag."""
    from .core import paths as _paths
    c = dbmod.connect(); n = tagged = 0
    try:
        _cur_f = _paths.DATA_DIR / "discover_cursor.json"
        try: _cur = json.load(open(_cur_f))
        except Exception: _cur = {}
        page = int(_cur.get("tvmovie", 0))
        for _ in range(pages):
            page += 1
            rows_ = ia.search(ia.TVMOVIE_QUERY, rows=rows, page=page)
            for d in rows_:
                ident = d.get("identifier"); title = str(d.get("title") or "").strip()
                if not ident or not title: continue
                uid = f"pd:{ident}"
                if ia.blocked(title) or ia.blocked(d.get("description")): continue
                row = c.execute("SELECT genres FROM items WHERE uid=?", (uid,)).fetchone()
                if row:
                    if "TV Movie" not in (row["genres"] or ""):
                        c.execute("UPDATE items SET genres=CASE WHEN genres IS NULL OR genres='' THEN 'TV Movie' ELSE genres || ', TV Movie' END WHERE uid=?", (uid,)); tagged += 1
                    continue
                year = int(str(d.get("year") or "0")[:4] or 0) or None
                c.execute("INSERT OR IGNORE INTO items(uid,source,kind,ext_id,ia_id,title,title_raw,year,decade,downloads,strict_pd,blocked,verified,genres,verify_note,added) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,0,'TV Movie','tvmovie family',?)",
                          (uid, "pd", "movie", ident, ident, title, title, year, (year // 10) * 10 if year else None, int(d.get("downloads") or 0), 1 if ia.strict_pd(d, year) else 0, time.time()))
                _job(c, "map", {"uid": uid}); n += 1
            if len(rows_) < rows: page = 0; break
        _cur["tvmovie"] = page
        try: json.dump(_cur, open(_cur_f, "w"))
        except Exception as _e: log.warning("cursor save: %s", _e)
        c.commit(); log.info("tvmovie discover seeded %d, tagged %d existing", n, tagged); return n
    finally: c.close()

def _map_one(c, cfg, uid):
    row = c.execute("SELECT * FROM items WHERE uid=?", (uid,)).fetchone()
    if not row: return "gone"
    t = TMDB(cfg["tmdb"].get("read_token", ""))
    hit = None
    if t.token:
        hit = {"id": row["tmdb_id"]} if row["tmdb_id"] else t.search_movie(row["title_raw"] or row["title"], row["year"])
    if hit:
        m = t.movie(hit["id"])
        if not m or not m.get("id"): _job(c, "verify", {"uid": uid}); return "unmapped"
        e = t.enrich(m); cast = e.pop("_cast")
        if "TV Movie" in (row["genres"] or "") and "TV Movie" not in (e["genres"] or ""): e["genres"] = (e["genres"] + ", TV Movie") if e["genres"] else "TV Movie"
        c.execute("UPDATE items SET tmdb_id=?,tmdb_type=?,imdb_id=?,title=?,year=COALESCE(?,year),blurb=?,director=?,runtime_min=?,genres=?,decade=COALESCE(?,decade),poster=?,backdrop=?,poster_local=?,backdrop_local=? WHERE uid=?",
                  (e["tmdb_id"], e["tmdb_type"], e["imdb_id"], e["title"], e["year"], e["blurb"], e["director"], e["runtime_min"], e["genres"], e["decade"], e["poster"], e["backdrop"], e["poster_local"], e["backdrop_local"], uid))
        for pid, name in cast:
            c.execute("INSERT OR IGNORE INTO people(tmdb_id,name,role) VALUES(?,?,'actor')", (pid, name)); c.execute("INSERT OR IGNORE INTO item_people(item_uid,tmdb_id,job) VALUES(?,?,'actor')", (uid, pid))
    if not c.execute("SELECT 1 FROM jobs WHERE kind='verify' AND payload=? AND status IN ('pending','running','done')", (json.dumps({"uid": uid}),)).fetchone(): _job(c, "verify", {"uid": uid})
    if hit and hit.get("_match"): c.execute("UPDATE items SET verify_note=COALESCE(verify_note,'') || ? WHERE uid=? AND COALESCE(verify_note,'') NOT LIKE '%match:%'", (f" match:{hit['_match'][0]}:{hit['_match'][1]}", uid))
    return "mapped" if hit else "unmapped"

def _cache_art(c, row):
    """Pull a seeded item's remote TMDB still into the local poster cache so the player never depends on the image CDN at draw time."""
    try:
        p = row["poster"] or ""
        if row["poster_local"] or "/t/p/" not in p: return
        path = "/" + p.split("/t/p/", 1)[1].split("/", 1)[1]
        loc = TMDB.image(path, "w500")
        if loc: c.execute("UPDATE items SET poster_local=? WHERE uid=?", (loc, row["uid"]))
    except Exception as e: log.info("art cache skipped %s: %s", row["uid"], e)

def _verify_one(c, uid):
    row = c.execute("SELECT * FROM items WHERE uid=?", (uid,)).fetchone()
    if row and row["source"] == "youtube":   # Phase D: YouTube rows have no ia_id; resolve through yt-dlp (node runtime) and decode THAT
        from .core.tools import yt_direct_url
        try: direct = yt_direct_url(row["stream_url"])
        except Exception as e:
            c.execute("UPDATE items SET verified=0,verified_at=?,verify_note=? WHERE uid=?", (time.time(), f"yt-dlp: {str(e)[:120]}", uid)); return f"yt-dlp: {str(e)[:60]}"
        ok, note, dur = ia.verify_decode(direct, frames=24, timeout=90)
        if ok:
            c.execute("UPDATE items SET verified=1,verified_at=?,verify_note=?,runtime_min=COALESCE(runtime_min,?) WHERE uid=?", (time.time(), f"youtube {note}", int(dur // 60) if dur else None, uid)); return "verified"
        c.execute("UPDATE items SET verified=0,verified_at=?,verify_note=? WHERE uid=?", (time.time(), note, uid)); return note
    if not row or not row["ia_id"]: return "gone"
    if row["ia_file"] and row["stream_url"]:  # pre-mapped lanes name the exact file: decode THAT first, fall back to the item's other files
        ok, note, dur = ia.verify_decode(row["stream_url"])
        if ok:
            c.execute("UPDATE items SET verified=1,verified_at=?,verify_note=?,runtime_min=COALESCE(runtime_min,?) WHERE uid=?", (time.time(), f"mapped-file {note}", int(dur // 60) if dur else None, uid))
            _cache_art(c, row); return "verified"
    meta = ia.ia_meta(row["ia_id"]); cands = [x for x in ia.candidates(meta, row["ia_id"]) if not x["part"]][:4]
    md = meta.get("metadata") or {}
    if row["strict_pd"] == 0 and ia.strict_pd(md, row["year"]): c.execute("UPDATE items SET strict_pd=1 WHERE uid=?", (uid,))
    for cand in cands:
        ok, note = ia.prefilter(cand["url"])
        if not ok: continue
        ok, note, dur = ia.verify_decode(cand["url"])
        if ok:
            c.execute("UPDATE items SET stream_url=?,ia_file=?,verified=1,verified_at=?,verify_note=?,runtime_min=COALESCE(runtime_min,?) WHERE uid=?", (cand["url"], cand["name"], time.time(), f"{cand['quality']} {note}", int(dur // 60) or None, uid)); return "verified"
    c.execute("UPDATE items SET verified=0,verified_at=?,verify_note=? WHERE uid=?", (time.time(), f"no decodable file among {len(cands)} candidates", uid)); return "unplayable"

TRAILER_RX = re.compile(r"\btrailers?\b|\bteaser\b|\btv spot\b", re.I)
def classify_trailers(c) -> dict:
    """Phase T: set items.trailer from the title (1) or the decoded/TMDB duration (2). Idempotent; never touches tracks."""
    n1 = n2 = n0 = 0
    for r in c.execute("SELECT uid,title,title_raw,verify_note,runtime_min,trailer FROM items WHERE kind IN ('movie','video','short','episode') AND source!='music'").fetchall():
        t = 0
        if TRAILER_RX.search(f"{r['title'] or ''} {r['title_raw'] or ''}"): t = 1
        else:
            dur = None
            m = re.search(r"duration (\d+)s", r["verify_note"] or "")
            if m: dur = int(m.group(1))
            if (dur is not None and 0 < dur < 300) or (dur is None and r["runtime_min"] is not None and 0 < r["runtime_min"] < 5): t = 2
        if t != (r["trailer"] or 0):
            c.execute("UPDATE items SET trailer=? WHERE uid=?", (t, r["uid"]))
            n1 += t == 1; n2 += t == 2; n0 += t == 0
    c.commit(); return {"to_trailer": n1, "to_short": n2, "to_feature": n0}

def work(cfg: dict, limit: int = 20) -> dict:
    c = dbmod.connect(); done = {}
    try:
        # a job left 'running' by a killed grower is orphaned after 15 min: give it back
        c.execute("UPDATE jobs SET status='pending',updated=? WHERE status='running' AND updated<?", (time.time(), time.time() - 900)); c.commit()
        try: done["tvmovie_discover"] = discover_tvmovies(cfg)
        except Exception as e: log.warning("discover_tvmovies: %s", e)
        try: done["trailer_classify"] = classify_trailers(c)
        except Exception as e: log.warning("classify_trailers: %s", e)
        # verified titles still drawing from the remote image CDN: pull their art local, a few per pass
        for r in c.execute("SELECT * FROM items WHERE verified=1 AND poster_local IS NULL AND poster LIKE '%/t/p/%' LIMIT ?", (int((cfg.get("grower") or {}).get("art_per_pass", 200)),)).fetchall(): _cache_art(c, r)
        c.commit()
        # verifies first (they are what makes a title playable), then maps, oldest first within each
        rows = c.execute("SELECT * FROM jobs WHERE status='pending' AND not_before<=? ORDER BY (kind='verify') DESC, id LIMIT ?", (time.time(), limit)).fetchall()
        for j in rows:
            c.execute("UPDATE jobs SET status='running',attempts=attempts+1,updated=? WHERE id=?", (time.time(), j["id"])); c.commit()
            try:
                p = json.loads(j["payload"]); res = _map_one(c, cfg, p["uid"]) if j["kind"] == "map" else _verify_one(c, p["uid"]) if j["kind"] == "verify" else "unknown"
                c.execute("UPDATE jobs SET status='done',note=?,updated=? WHERE id=?", (res, time.time(), j["id"]))
            except Exception as e:
                st = "pending" if j["attempts"] < 3 else "failed"
                c.execute("UPDATE jobs SET status=?,note=?,not_before=?,updated=? WHERE id=?", (st, str(e)[:200], time.time() + 600 * (j["attempts"] + 1), time.time(), j["id"])); res = "error"
            c.commit(); done[res] = done.get(res, 0) + 1; log.info("job %s %s -> %s", j["id"], j["kind"], res)
        return done
    finally: c.close()

def status() -> dict:
    c = dbmod.connect()
    try:
        return {"items": dict(c.execute("SELECT source||':'||verified, COUNT(*) FROM items GROUP BY 1").fetchall()), "jobs": dict(c.execute("SELECT kind||':'||status, COUNT(*) FROM jobs GROUP BY 1").fetchall())}
    finally: c.close()
