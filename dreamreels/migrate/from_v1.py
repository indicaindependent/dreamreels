"""Import a DreamReel v1 library (/opt/dreamreel/dreamreel.db) into v2. Idempotent. Copies cached posters.
Blueboxd rows become source=pd (ia_id = ext_id), verified=0 until the v2 decode proof runs; NAS rows keep
their paths and count as verified when the file exists (local files play or they don't)."""
from __future__ import annotations
import os, shutil, sqlite3, sys, time, json
from ..core import db as dbmod
from ..core.paths import POSTER_CACHE

def run(v1_db="/opt/dreamreel/dreamreel.db") -> dict:
    if not os.path.exists(v1_db): return {"error": f"{v1_db} not found"}
    src = sqlite3.connect(f"file:{v1_db}?mode=ro", uri=True); src.row_factory = sqlite3.Row
    dbmod.migrate(); c = dbmod.connect(); POSTER_CACHE.mkdir(parents=True, exist_ok=True); n = {"pd": 0, "nas": 0, "state": 0, "posters": 0}
    def art(path):
        if path and os.path.exists(path):
            dest = POSTER_CACHE / ("v1_" + os.path.basename(path))
            if not dest.exists(): shutil.copy2(path, dest); n["posters"] += 1
            return str(dest)
        return None
    for r in src.execute("SELECT * FROM films"):
        if r["source"] == "blueboxd":
            uid = f"pd:{r['ext_id']}"; kind = "movie"; ia_id = r["ext_id"]; path = None; verified = 0
        elif r["source"] == "nas":
            uid = r["uid"]; kind = "episode" if r["media_kind"] == "tv" else "movie"; ia_id = None; path = r["path"]; verified = 1 if path and os.path.exists(path) else 0
        else: continue
        year = r["year"] or None
        c.execute("""INSERT INTO items(uid,source,kind,ext_id,ia_id,title,title_raw,year,tmdb_id,tmdb_type,blurb,director,runtime_min,genres,decade,poster,backdrop,poster_local,backdrop_local,path,verified,verified_at,verify_note,downloads,strict_pd,added)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(uid) DO UPDATE SET poster_local=COALESCE(items.poster_local,excluded.poster_local), tmdb_id=COALESCE(items.tmdb_id,excluded.tmdb_id), blurb=COALESCE(items.blurb,excluded.blurb)""",
                  (uid, "pd" if r["source"] == "blueboxd" else "nas", kind, r["ext_id"], ia_id, r["title"], r["title_raw"] or r["title"], year, r["tmdb_id"], "movie" if r["tmdb_id"] else None, r["blurb"], r["director"],
                   int(str(r["runtime"] or "0").split()[0]) if str(r["runtime"] or "").split()[:1] and str(r["runtime"]).split()[0].isdigit() else None, None, (year // 10) * 10 if year else None,
                   r["poster"], r["backdrop"], art(r["poster_local"]), art(r["backdrop_local"]), path, verified, time.time() if verified else None, "v1 import" + (" (local file present)" if verified else " (needs v2 decode proof)"), r["downloads"],
                   1 if (year and year <= 1930) else 0, r["added"] or time.time()))
        n["pd" if r["source"] == "blueboxd" else "nas"] += 1
        for jk in (("verify", "map") if r["source"] == "blueboxd" else ("map",)):
            c.execute("INSERT INTO jobs(kind,payload,status,not_before,created,updated) SELECT ?,?, 'pending',?,?,? WHERE NOT EXISTS (SELECT 1 FROM jobs WHERE kind=? AND payload=?)", (jk, json.dumps({"uid": uid}), time.time(), time.time(), time.time(), jk, json.dumps({"uid": uid})))
    for s in src.execute("SELECT * FROM state"):
        uid = s["uid"].replace("blueboxd:", "pd:", 1)
        c.execute("INSERT INTO state(uid,resume_sec,duration_sec,favorite,last_played,play_count) VALUES(?,?,?,?,?,?) ON CONFLICT(uid) DO NOTHING", (uid, s["resume_sec"], s["duration_sec"], s["favorite"], s["last_played"], s["play_count"])); n["state"] += 1
    c.commit(); c.close(); src.close(); return n
