"""Fill show-level metadata (poster, years, overview, verified TMDB id) in a lane seed from TMDB.
Why: the gameshow seed came back with years=None / poster=False for all 13 shows and two suspicious TMDB ids
(Match Game -> 9, Family Feud -> 296239). For each show: read /tv/{id}; if the show_id carries a year suffix
(e.g. family-feud-1976) and TMDB's first_air_date is more than 2 years off, re-search TMDB with that year and take the
best hit whose first_air_date is within 2 years. Prints a before/after table; writes <out>."""
import json, re, sys, urllib.request, urllib.parse
src, out = sys.argv[1], sys.argv[2]
TOK = open("/etc/dreamreels/tmdb.token").read().strip()
def tm(path, **q):
    u = f"https://api.themoviedb.org/3{path}" + ("?" + urllib.parse.urlencode(q) if q else "")
    r = urllib.request.Request(u, headers={"Authorization": "Bearer " + TOK, "accept": "application/json", "User-Agent": "DreamReels-showfill/1"})
    return json.load(urllib.request.urlopen(r, timeout=20))
d = json.load(open(src)); changed = []
import os, collections
KEEP = set(filter(None, os.environ.get("KEEP_IDS", "").split(",")))   # show_ids whose TMDB id must not be replaced
for s in d["shows"]:
    m = re.search(r"-(19\d\d|20\d\d)$", s["show_id"]); want = int(m.group(1)) if m else None
    det = tm(f"/tv/{s['tmdb_id']}") if s.get("tmdb_id") else {}
    fy = int((det.get("first_air_date") or "0")[:4] or 0)
    note = "kept"
    if s["show_id"] not in KEEP and (want and det and abs(fy - want) > 2 or (want and not det)):
        hits = tm("/search/tv", query=re.sub(r"^The\s+", "", s["title"]), first_air_date_year=want).get("results") or []
        hits += tm("/search/tv", query=s["title"]).get("results") or []
        good = [h for h in hits if abs(int((h.get("first_air_date") or "0")[:4] or 0) - want) <= 2]
        if good:
            good.sort(key=lambda h: -(h.get("popularity") or 0)); det = tm(f"/tv/{good[0]['id']}")
            note = f"REPLACED {s['tmdb_id']} -> {det['id']}"; s["tmdb_id"] = det["id"]
            # episode matches were made against the WRONG show's episode list: demote them to unlisted (postfilter renumbers / rescues)
            for e in d["episodes"]:
                if e["show_id"] == s["show_id"] and e["season"] != 0:
                    e.update({"season": 0, "episode": 0, "match": "unlisted", "title": e.get("stream_name") or e["title"], "tmdb_ep_id": None, "still_path": None, "air_date": None, "overview": None})
        else: note = f"KEPT (no TMDB hit near {want})"
    if det:
        fy = (det.get("first_air_date") or "")[:4]; ly = (det.get("last_air_date") or "")[:4]
        s["years"] = f"{fy}-{ly}" if fy and ly and fy != ly else fy or None
        s["era_start"] = s.get("era_start") or fy or None; s["era_end"] = s.get("era_end") or ly or None
        s["poster_path"] = s.get("poster_path") or det.get("poster_path"); s["poster"] = s["poster_path"]
        s["backdrop_path"] = s.get("backdrop_path") or det.get("backdrop_path")
        s["overview"] = det.get("overview") or s.get("overview")
        s["tmdb_name"] = det.get("name"); nets = [n["name"] for n in det.get("networks") or []]; s["network"] = s.get("network") or (nets[0] if nets else None)
    if not s.get("poster"):   # archive.org item thumbnail of the show's biggest item as the poster of last resort (archive.org only)
        big = collections.Counter(e["ia_id"] for e in d["episodes"] if e["show_id"] == s["show_id"]).most_common(1)
        if big: s["poster_path"] = s["poster"] = f"https://archive.org/services/img/{big[0][0]}"; note += " +ia-thumb"
    changed.append((s["show_id"], s.get("tmdb_id"), s.get("tmdb_name"), s.get("years"), bool(s.get("poster")), note))
for c in changed: print(f"{c[0]:26} tmdb={str(c[1]):7} {str(c[2])[:26]:26} {str(c[3]):10} poster={c[4]!s:5} {c[5]}")
json.dump(d, open(out, "w"), indent=0); print("wrote", out)
