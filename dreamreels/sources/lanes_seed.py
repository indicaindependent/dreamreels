"""Channel 83 + Toon Town lanes: pre-mapped seed manifests (archive.org item + file per episode/short,
TMDB metadata) exported from the Blueboxd mappers. Installing a lane upserts shows + items and queues a
DECODE verify for every file — nothing is marked playable on the strength of the manifest alone."""
from __future__ import annotations
import json, time
from pathlib import Path
from ..core import db as dbmod

DATA = Path(__file__).resolve().parent.parent / "data"
IMG = "https://image.tmdb.org/t/p/w500"

def _poster(p): return (IMG + p) if p and str(p).startswith("/") else (str(p) if p and str(p).startswith("http") else None)
def _year(s):
    try: return int(str(s)[:4])
    except Exception: return None

# ---- v2.1.0 (Nov 1 2026): Channel 83 is pre-1970 television only ---------------------------------------------------
# Forkers: change CHAN83_MAX_YEAR to widen or narrow the era. Some archive.org uploads file a later revival inside the
# original show's folder (the 1995 Outer Limits sits in "The Outer Limits/Season N - Complete" and was mapped onto 1963
# episode metadata). For those shows a file must carry the original series' marker to count as the original.
import re as _re
CHAN83_MAX_YEAR = 1969
CHAN83_FILE_MUST_CONTAIN = {"the-outer-limits": "1963"}
_LATER_YEAR_IN_NAME = _re.compile(r"\((?:19[7-9]\d|20\d\d)\)")

def chan83_show_ok(s) -> bool:
    y = _year(s.get("era_start"))
    return y is None or y <= CHAN83_MAX_YEAR

def chan83_ep_ok(e) -> bool:
    y = _year(e.get("air_date"))
    if y is not None and y > CHAN83_MAX_YEAR: return False
    if (e.get("season") or 0) >= 100: return False                      # seasons 100+ are the mapped revival series
    name = str(e.get("stream_name") or "")
    if _LATER_YEAR_IN_NAME.search(name): return False                   # e.g. "The Outer Limits (1995)/..."
    need = CHAN83_FILE_MUST_CONTAIN.get(e.get("show_id"))
    return not need or need in name

def prune_chan83_era(c=None) -> int:
    """Hide (blocked=1, reversible) Channel 83 rows already installed that fall outside the era. Cheap; runs at player start."""
    own = c is None; c = c or dbmod.connect()
    shows_late = [r[0] for r in c.execute("SELECT uid FROM shows WHERE source='chan83' AND CAST(substr(IFNULL(years,''),1,4) AS INTEGER) > ?", (CHAN83_MAX_YEAR,))]
    must = " OR ".join(f"(show_uid='chan83:{k}' AND IFNULL(ia_file,'') NOT LIKE '%{v}%')" for k, v in CHAN83_FILE_MUST_CONTAIN.items()) or "0"
    q = (f"UPDATE items SET blocked=1, verify_note='hidden: outside Channel 83 era (pre-{CHAN83_MAX_YEAR + 1} only)' "
         f"WHERE source='chan83' AND blocked=0 AND (IFNULL(year,0) > ? OR director='1995 revival' OR IFNULL(ia_file,'') GLOB '*(19[7-9][0-9])*' "
         f"OR IFNULL(ia_file,'') GLOB '*(20[0-9][0-9])*' OR {must}" + (f" OR show_uid IN ({','.join('?' * len(shows_late))})" if shows_late else "") + ")")
    n = c.execute(q, (CHAN83_MAX_YEAR, *shows_late)).rowcount
    if shows_late: c.execute(f"DELETE FROM shows WHERE uid IN ({','.join('?' * len(shows_late))})", shows_late)
    c.commit()
    if own: c.close()
    return n

def _enqueue_verify(c, uid):
    if not c.execute("SELECT 1 FROM jobs WHERE kind='verify' AND payload=? AND status IN ('pending','running')", (json.dumps({"uid": uid}),)).fetchone():
        c.execute("INSERT INTO jobs(kind,payload,status,not_before,created,updated) VALUES('verify',?,'pending',?,?,?)", (json.dumps({"uid": uid}), time.time(), time.time(), time.time()))

def install_chan83(c=None) -> dict:
    own = c is None; c = c or dbmod.connect(); seed = json.load(open(DATA / "chan83_seed.json")); now = time.time(); n_show = n_ep = 0
    if (DATA / "chan83_seed_extra.json").exists():  # Sep 26 2026: curated extra PD shows built by chan83_extend.py (TMDB + archive.org, strict match)
        try:
            extra = json.load(open(DATA / "chan83_seed_extra.json")); seed = {**seed, "shows": list(seed["shows"]) + list(extra.get("shows", [])), "episodes": list(seed["episodes"]) + list(extra.get("episodes", []))}
        except Exception as _e: print("chan83_seed_extra.json unreadable:", _e)
    seed = {**seed, "shows": [x for x in seed["shows"] if chan83_show_ok(x)]}
    keep = {x["show_id"] for x in seed["shows"]}
    seed["episodes"] = [x for x in seed["episodes"] if x.get("show_id") in keep and chan83_ep_ok(x)]
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
    c.commit(); prune_chan83_era(c)
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


def install_lane(seed_path, c=None) -> dict:
    """Phase C (Oct 13 2026): install ANY show-lane seed produced by tools/lane_seed_build.py (shape = chan83_seed.json plus
    seed["lane"] = the items.source / shows.source value, e.g. chan83 | gameshow | nick90s). Same rules as install_chan83:
    upsert shows + episodes, queue a DECODE verify for every file, nothing playable on the strength of the manifest.
    Season 0 rows are 'unlisted' episodes (file named the show but matched no TMDB episode); they carry the file name as title."""
    import json as _json
    own = c is None; c = c or dbmod.connect(); seed = _json.load(open(seed_path)); src = seed.get("lane") or "chan83"; now = time.time(); n_show = n_ep = 0
    genre_label = {"gameshow": "Game Show", "nick90s": "Nickelodeon", "sesame": "Kids", "chan83": "Anthology"}.get(src, "TV")
    if src == "chan83":   # v2.1.0: same pre-1970 rule as install_chan83
        seed = {**seed, "shows": [x for x in seed["shows"] if chan83_show_ok(x)]}
        keep = {x["show_id"] for x in seed["shows"]}
        seed["episodes"] = [x for x in seed["episodes"] if x.get("show_id") in keep and chan83_ep_ok(x)]
    for s in seed["shows"]:
        uid = f"{src}:{s['show_id']}"; years = f"{s.get('era_start') or ''}-{s.get('era_end') or ''}".strip("-")
        c.execute("INSERT INTO shows(uid,source,title,tmdb_id,years,poster,blurb,studio,era_group,added) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET title=excluded.title,tmdb_id=excluded.tmdb_id,years=excluded.years,poster=COALESCE(excluded.poster,shows.poster),blurb=excluded.blurb",
                  (uid, src, s["title"], s.get("tmdb_id"), years, _poster(s.get("poster_path")), s.get("overview") or s.get("pd_basis"), s.get("network"), s.get("genre"), now)); n_show += 1
    for e in seed["episodes"]:
        uid = f"{src}:{e['ep_id']}"; url = f"https://archive.org/download/{e['ia_id']}/{e['stream_name']}"; y = _year(e.get("air_date")); season = e["season"]
        title = e.get("title") or f"Episode {e['episode']}"
        note = "unlisted file (named the show, no TMDB episode match); awaiting decode" if season == 0 else f"seeded by lane_seed_build ({e.get('match','')}); awaiting decode"
        c.execute("""INSERT INTO items(uid,source,kind,ext_id,title,title_raw,year,tmdb_id,tmdb_type,show_uid,season,episode,blurb,director,runtime_min,genres,decade,poster,stream_url,ia_id,ia_file,strict_pd,verified,verify_note,added)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?)
                     ON CONFLICT(uid) DO UPDATE SET stream_url=excluded.stream_url,ia_id=excluded.ia_id,ia_file=excluded.ia_file,poster=COALESCE(items.poster,excluded.poster),blurb=COALESCE(items.blurb,excluded.blurb)""",
                  (uid, src, "episode", e["ep_id"], title, e.get("title"), y, e.get("tmdb_ep_id"), "tv_episode", f"{src}:{e['show_id']}", season, e["episode"], e.get("overview"), None, e.get("runtime"), genre_label, (y // 10 * 10) if y else None,
                   _poster(e.get("still_path")), url, e["ia_id"], e["stream_name"], note, now)); n_ep += 1
        _enqueue_verify(c, uid)
    c.commit()
    if src == "chan83": prune_chan83_era(c)
    if own: c.close()
    return {"lane": src, "shows": n_show, "episodes": n_ep}
