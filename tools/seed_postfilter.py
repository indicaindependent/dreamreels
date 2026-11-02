"""Post-filter a lane seed before install (Phase C). Rules measured from the first builds (chan83add, nick90s):
 v1  - drop 'unlisted' files over 2500 MB (whole-VHS-tape rips) unless the FILE name names the show; nothing over 4000 MB
     - drop 'unlisted' files whose own name names a different well-known show / a marathon tape
     - renumber season-0 rows per show in natural sort order of the title
 v2  - drop ANY row whose item/file text marks a foreign-language dub (Spanish "Aventuras en Pañales" Rugrats, "temporada",
       latino/castellano/dublado/deutsch...) - the SxxEyy matcher cannot see audio language
     - drop DVD structure chunks (VIDEO_TS / VTS_xx_x / .vob) - a VOB chunk is not an episode
     - rescue 'unlisted' rows whose text says "Season N Episode M" / "S1 E3" / "Temporada" into real episodes using TMDB
       (one season call per show+season, cached); falls back to unlisted when TMDB has no such episode
Prints before/after counts per show; writes <out>. Needs /etc/dreamreels/tmdb.token for the rescue step (skips if absent)."""
import json, re, sys, urllib.request, urllib.parse
src, out = sys.argv[1], sys.argv[2]
d = json.load(open(src)); eps = d["episodes"]; shows = {s["show_id"]: s for s in d["shows"]}
TAPE = re.compile(r"\b(vhs|tape|box)\b.*\b(tape|part|box|recording|recordings)\b|\brecorded off\b|\bhome recording\b", re.I)
OTHER = re.compile(r"mst3k|mystery science|marathon|police squad|married with children|seinfeld|simpsons|cheers|friends|frasier|roseanne|full house|home improvement|cosby|golden girls|commercials?|news at|sportscenter", re.I)
LANG = re.compile(r"aventuras|pa[ñn]ales|temporada|cap[ií]tulo|latino|espa[ñn]ol|castellano|dublado|portugu[eê]s|dubbed|deutsch|german|fran[cç]ais|french|italiano|russian|polski|magyar|\b(es|pt|de|fr|it|ru)[-_ ]?dub\b|\bvf\b|\bvostfr\b", re.I)
DVD = re.compile(r"video[_ ]?ts|\bvts[_ ]?\d|\.vob$|\.ifo$|\.bup$", re.I)
SEASON_EP = re.compile(r"season\s*(\d{1,2})\s*[,./-]?\s*(?:episode|ep)\s*(\d{1,3})|temporada\s*(\d{1,2}).{0,12}?(?:episodio|cap[ií]tulo|ep)\s*(\d{1,3})|(?<![a-z])s\s?(\d{1,2})\s+e\s?(\d{1,3})(?!\d)", re.I)
def norm_words(s): return [w for w in re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split() if len(w) > 2 and w not in ("the", "and", "show")]
def names(text, title):
    t = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return all(re.search(r"\b%s\b" % re.escape(w), t) for w in norm_words(title))
def natkey(s): return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", s or "")]
try: TOK = open("/etc/dreamreels/tmdb.token").read().strip()
except Exception: TOK = None
_season_cache = {}
def tmdb_season(tmdb_id, n):
    k = (tmdb_id, n)
    if k not in _season_cache:
        try:
            r = urllib.request.Request(f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{n}", headers={"Authorization": "Bearer " + TOK, "accept": "application/json", "User-Agent": "DreamReels-postfilter/2"})
            _season_cache[k] = {e["episode_number"]: e for e in json.load(urllib.request.urlopen(r, timeout=20)).get("episodes") or []}
        except Exception: _season_cache[k] = {}
    return _season_cache[k]
before = {}; kept = []; dropped = {"lang": 0, "dvd": 0, "tape": 0, "other": 0, "big": 0}; rescued = 0; taken = set()
for e in eps:
    if e["season"] != 0: taken.add((e["show_id"], e["season"], e["episode"]))
for e in eps:
    sid = e["show_id"]; before[sid] = before.get(sid, 0) + 1
    title = shows[sid]["title"]; fname = e["stream_name"]; text = f"{e['ia_id']} {fname}"  # archive.org-provided names only, never the TMDB episode title
    if LANG.search(text): dropped["lang"] += 1; continue
    if DVD.search(fname): dropped["dvd"] += 1; continue
    if e["season"] == 0:
        file_names_show = names(fname, title)
        if e["size_mb"] > 4000: dropped["big"] += 1; continue
        if e["size_mb"] > 2500 and not file_names_show: dropped["big"] += 1; continue
        if OTHER.search(fname) and not file_names_show: dropped["other"] += 1; continue
        if TAPE.search(fname) and not file_names_show: dropped["tape"] += 1; continue
        m = SEASON_EP.search(f"{e.get('title','')} {fname}")
        if m and TOK and shows[sid].get("tmdb_id"):
            g = [x for x in m.groups() if x]; S, E = int(g[0]), int(g[1])
            ep = tmdb_season(shows[sid]["tmdb_id"], S).get(E)
            if ep and (sid, S, E) not in taken:
                e.update({"season": S, "episode": E, "ep_id": f"{sid}-s{S:02d}e{E:03d}", "title": ep.get("name") or e["title"], "air_date": ep.get("air_date"), "tmdb_ep_id": ep.get("id"), "still_path": ep.get("still_path"), "overview": ep.get("overview"), "runtime": ep.get("runtime"), "match": "season-episode-rescue"})
                taken.add((sid, S, E)); rescued += 1
    kept.append(e)
# v3: an unlisted file whose name carries an air date joins a YEAR season (season=1991, episodes ordered by date) so a
# 2,000-file game show browses by year instead of one endless "Unlisted" rail. Undated files stay in season 0.
DATE_RX = [re.compile(r"(?<!\d)((?:19|20)\d\d)[ ._-]?(0[1-9]|1[0-2])[ ._-]?(0[1-9]|[12]\d|3[01])(?!\d)"),          # 1991 12 06 / 1987-05-12 / 19911206
           re.compile(r"(?<!\d)(0?[1-9]|1[0-2])[:/._-](0?[1-9]|[12]\d|3[01])[:/._-]((?:19|20)?\d\d)(?!\d)")]          # 3:10:80 / 7-3-90 / 03.10.1980
def file_date(text):
    m = DATE_RX[0].search(text)
    if m: return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = DATE_RX[1].search(text)
    if m:
        y = int(m.group(3)); y = y if y > 100 else (1900 + y if y >= 30 else 2000 + y)
        return y, int(m.group(1)), int(m.group(2))
    return None
dated = 0
for e in kept:
    if e["season"] == 0:
        dt = file_date(f"{e.get('title','')} {e['stream_name']}")
        if dt and 1950 <= dt[0] <= 2026:
            e["season"] = dt[0]; e["air_date"] = f"{dt[0]:04d}-{dt[1]:02d}-{dt[2]:02d}"; e["match"] = "year-season"; dated += 1
for sid in shows:
    for yr in sorted({e["season"] for e in kept if e["show_id"] == sid and e["season"] >= 1900}):
        ys = sorted([e for e in kept if e["show_id"] == sid and e["season"] == yr], key=lambda e: (e["air_date"], natkey(e["title"])))
        for i, e in enumerate(ys, 1): e["episode"] = i; e["ep_id"] = f"{sid}-y{yr}e{i:04d}"
print("dated unlisted files moved into year seasons:", dated)
out_eps = [e for e in kept if e["season"] != 0]
for sid in shows:
    zs = sorted([e for e in kept if e["show_id"] == sid and e["season"] == 0], key=lambda e: (e["ia_id"], natkey(e["title"])))
    for i, e in enumerate(zs, 1): e["episode"] = i; e["ep_id"] = f"{sid}-s00e{i:04d}"
    out_eps += zs
after = {}
for e in out_eps: after[e["show_id"]] = after.get(e["show_id"], 0) + 1
for sid in shows: print(f"{sid:36} before {before.get(sid,0):4}  after {after.get(sid,0):4}")
print("dropped:", dropped, "| rescued into real episodes:", rescued)
d["episodes"] = out_eps; d["postfilter"] = "seed_postfilter.py v3"
json.dump(d, open(out, "w"), indent=0); print("wrote", out, "episodes", len(out_eps))
