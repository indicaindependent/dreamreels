"""Channel 83 + Toon Town lanes: pre-mapped seed manifests (archive.org item + file per episode/short,
TMDB metadata) exported from the Blueboxd mappers. Installing a lane upserts shows + items and queues a
DECODE verify for every file — nothing is marked playable on the strength of the manifest alone."""
from __future__ import annotations
import json, time
from pathlib import Path
from ..core import db as dbmod

DATA = Path(__file__).resolve().parent.parent / "data"
IMG = "https://image.tmdb.org/t/p/w500"

def _poster(p): return (IMG + p) if p and str(p).startswith("/") else None
def _year(s):
    try: return int(str(s)[:4])
    except Exception: return None

def _enqueue_verify(c, uid):
    if not c.execute("SELECT 1 FROM jobs WHERE kind='verify' AND payload=? AND status IN ('pending','running')", (json.dumps({"uid": uid}),)).fetchone():
        c.execute("INSERT INTO jobs(kind,payload,status,not_before,created,updated) VALUES('verify',?,'pending',?,?,?)", (json.dumps({"uid": uid}), time.time(), time.time(), time.time()))

def install_chan83(c=None) -> dict:
    own = c is None; c = c or dbmod.connect(); seed = json.load(open(DATA / "chan83_seed.json")); now = time.time(); n_show = n_ep = 0
    for s in seed["shows"]:
        uid = f"chan83:{s['show_id']}"; years = f"{s.get('era_start') or ''}-{s.get('era_end') or ''}".strip("-")
        c.execute("INSERT INTO shows(uid,source,title,tmdb_id,years,poster,blurb,studio,era_group,added) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET title=excluded.title,tmdb_id=excluded.tmdb_id,years=excluded.years,poster=COALESCE(excluded.poster,shows.poster),blurb=excluded.blurb",
                  (uid, "chan83", s["title"], s.get("tmdb_id"), years, _poster(s.get("poster_path")), s.get("overview") or s.get("pd_basis"), s.get("network"), s.get("genre"), now)); n_show += 1
    for e in seed["episodes"]:
        uid = f"chan83:{e['ep_id']}"; url = f"https://archive.org/download/{e['ia_id']}/{e['stream_name']}"; y = _year(e.get("air_date")); season = e["season"]
        era = "1995 revival" if season and season >= 100 else "original"; disp_season = season - 100 if season and season >= 100 else season
        title = f"{e['title']}" if e.get("title") else f"Episode {e['episode']}"
        c.execute("""INSERT INTO items(uid,source,kind,ext_id,title,title_raw,year,tmdb_id,tmdb_type,show_uid,season,episode,blurb,director,runtime_min,genres,decade,poster,stream_url,ia_id,ia_file,strict_pd,verified,verify_note,added)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)
                     ON CONFLICT(uid) DO UPDATE SET stream_url=excluded.stream_url,ia_id=excluded.ia_id,ia_file=excluded.ia_file,poster=COALESCE(items.poster,excluded.poster),blurb=COALESCE(items.blurb,excluded.blurb)""",
                  (uid, "chan83", "episode", e["ep_id"], title, e.get("title"), y, e.get("tmdb_ep_id"), "tv_episode", f"chan83:{e['show_id']}", disp_season, e["episode"], e.get("overview"), era, (e.get("runtime_sec") or 0) // 60 or None, "Anthology", (y // 10 * 10) if y else None,
                   _poster(e.get("still_path")), url, e["ia_id"], e["stream_name"], 1 if era == "original" else 0, "seeded from Blueboxd map; awaiting decode", now)); n_ep += 1
        _enqueue_verify(c, uid)
    c.commit(); 
    if own: c.close()
    return {"shows": n_show, "episodes": n_ep}

def install_toontown(c=None) -> dict:
    own = c is None; c = c or dbmod.connect(); seed = json.load(open(DATA / "toontown_seed.json")); now = time.time(); n_ser = n_sh = 0
    for s in seed["series"]:
        uid = f"toontown:{s['series_id']}"; years = f"{s.get('era_start') or ''}-{s.get('era_end') or ''}".strip("-")
        c.execute("INSERT INTO shows(uid,source,title,tmdb_id,years,poster,blurb,studio,era_group,added) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET title=excluded.title,years=excluded.years,blurb=excluded.blurb,studio=excluded.studio",
                  (uid, "toontown", s["title"], s.get("tmdb_id"), years, _poster(s.get("poster_path")), s.get("overview") or s.get("pd_basis"), s.get("studio"), s.get("genre"), now)); n_ser += 1
    for e in seed["shorts"]:
        uid = f"toontown:{e['short_id']}"; url = f"https://archive.org/download/{e['ia_id']}/{e['stream_name']}"; y = _year(e.get("release_date"))
        c.execute("""INSERT INTO items(uid,source,kind,ext_id,title,title_raw,year,tmdb_id,show_uid,season,episode,blurb,director,runtime_min,genres,decade,poster,stream_url,ia_id,ia_file,strict_pd,verified,verify_note,added)
                     VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,1,0,?,?)
                     ON CONFLICT(uid) DO UPDATE SET stream_url=excluded.stream_url,ia_id=excluded.ia_id,ia_file=excluded.ia_file,blurb=COALESCE(items.blurb,excluded.blurb)""",
                  (uid, "toontown", "short", e["short_id"], e.get("title") or e["short_id"], e.get("title"), y, e.get("tmdb_id"), f"toontown:{e['series_id']}", e.get("order_no") or 0, e.get("overview"), e.get("studio"), max(1, (e.get("runtime_sec") or 0) // 60) if e.get("runtime_sec") else None,
                   "Animation" + (", Silent" if e.get("silent") else ""), (y // 10 * 10) if y else None, _poster(e.get("still_path")), url, e["ia_id"], e["stream_name"], "seeded from Blueboxd map; awaiting decode", now)); n_sh += 1
        _enqueue_verify(c, uid)
    c.commit()
    if own: c.close()
    return {"series": n_ser, "shorts": n_sh}
