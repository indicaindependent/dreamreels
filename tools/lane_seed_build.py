#!/usr/bin/env python3
"""DreamReels v2.2 Phase C seed builder (Oct 13 2026). Generalises chan83_extend.py (Sep 26) to any show lane.
SOURCE LAW (Pete, Oct 13 2026): archive.org is the ONLY external video source. No YouTube, nothing else.

  python3 lane_seed_build.py <lane> <out.json> [show_id ...]      lane in: chan83add | gameshow | nick90s

Runs ON the DreamReels box (needs /etc/dreamreels/tmdb.token). For each show: TMDB show + season/episode lists;
archive.org items from title-precision queries; every playable file (>40 MB, not trailer/clip) is matched to ONE TMDB
episode by (1) SxxEyy in item title or file name, (2) an air date in the name (daily strips: game shows), (3) a strict
fuzzy title match. Unmatched files on an item whose own title names the show are kept ONLY for shows flagged loose=True
(game shows and 90s Nick, where archive.org episode naming is chaotic) as season 0 "unlisted" episodes with the file
name as title; otherwise dropped, never guessed. Output is the chan83_seed.json shape so install_chan83()/install_lane()
can ingest it; the grower's DECODE verify is still what makes anything playable."""
import json, re, sys, time, urllib.parse, urllib.request, difflib, datetime
LANE = sys.argv[1]; OUT = sys.argv[2]; ONLY = set(sys.argv[3:])
TOK = open("/etc/dreamreels/tmdb.token").read().strip()
UA = {"User-Agent": "DreamReels-lane-seed/2.2 (archive.org only)"}
TMDB = "https://api.themoviedb.org/3"
PLAY = re.compile(r"\.(mp4|m4v|mkv|webm|ogv|avi|mpg|mpeg)$", re.I)
SE = re.compile(r"[sS](\d{1,2})\s*[eE](\d{1,3})|(?<!\d)(\d{1,2})x(\d{2,3})(?!\d)")
BAD = re.compile(r"trailer|preview|promo|commercial only|sample|\.ia\.mp4$|_512kb|\bclip\b|\bintro\b|\bopening\b|\bclosing\b|\bcredits\b|bumper", re.I)
DATE_PATTERNS = [
    (re.compile(r"(?<!\d)(19[5-9]\d|20[0-2]\d)[-._ ]?(\d{2})[-._ ]?(\d{2})(?!\d)"), "ymd"),      # 1995-05-05, 19950505
    (re.compile(r"(?<!\d)(\d{1,2})[-._ ](\d{1,2})[-._ ](\d{2}|\d{4})(?!\d)"), "mdy"),              # 5-5-95, 05.05.1995
]
_last = [0.0]
def throttle(rps=1.0):
    w = _last[0] + 1.0 / rps - time.time()
    if w > 0: time.sleep(w)
    _last[0] = time.time()
def get(url, hdr=None, tries=3, timeout=25):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={**UA, **(hdr or {})})
            with urllib.request.urlopen(r, timeout=timeout) as f: return json.loads(f.read().decode("utf-8", "replace"))
        except Exception as e:
            if getattr(e, "code", 0) == 404: return {}
            time.sleep(2 * (i + 1))
    return {}
def tmdb(path, **q): return get(TMDB + path + ("?" + urllib.parse.urlencode(q) if q else ""), {"Authorization": "Bearer " + TOK, "accept": "application/json"})
def ia_search(q, rows=120):
    throttle()
    u = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode([("q", q), ("rows", rows), ("output", "json"), ("sort[]", "downloads desc")] + [("fl[]", f) for f in ("identifier", "title", "year", "downloads", "description")])
    return (get(u).get("response") or {}).get("docs") or []
def ia_files(ident):
    throttle()
    m = get(f"https://archive.org/metadata/{ident}/files")
    return [f for f in (m.get("result") or []) if PLAY.search(f.get("name", "")) and not BAD.search(f.get("name", "")) and float(f.get("size") or 0) > 40e6]
def norm(s):
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", str(s or "").lower()); s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(the|a|an|of|and|in|to|episode|ep|part|pt|tv|show|series|full|hd|hq|remastered|complete|classic|with commercials|nickelodeon|nick)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()
def strip_show(text, show_title):
    t = norm(text); st = norm(show_title)
    for tok in st.split(): t = re.sub(r"\b%s\b" % re.escape(tok), " ", t)
    return re.sub(r"\s+", " ", t).strip()
def quality(f):
    n = f.get("name", ""); mb = float(f.get("size") or 0) / 1e6
    return (3 if re.search(r"1080|1920", n) else 2 if re.search(r"720", n) or mb > 700 else 1, mb)
def dates_in(text, lo, hi):
    """All plausible air dates (ISO) found in text, limited to the show's run years lo..hi."""
    out = []
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            try:
                if kind == "ymd": y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                else:
                    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3)); y = y + (1900 if y >= 50 else 2000) if y < 100 else y
                dt = datetime.date(y, mo, d)
                if lo - 1 <= y <= hi + 1: out.append(dt.isoformat())
            except Exception: continue
    return out
def names_show(text, show_title):
    """Does this archive.org item/file title plainly name the show? (loose-mode gate)"""
    st = norm(show_title).split(); t = norm(text)
    return bool(st) and all(re.search(r"\b%s\b" % re.escape(w), t) for w in st if len(w) > 2)

# ---------------------------------------------------------------------------------------------------------------
# (show_id, TMDB title, first_air_year, [IA queries], genre, basis note, seasons-or-None, loose)
C_TV = "mediatype:movies"
def Q(*phrases):  # title-precision archive.org query
    return " OR ".join(f'title:("{p}")' for p in phrases)
LANES = {
 "chan83add": [
  ("beyond-belief-fact-or-fiction", "Beyond Belief: Fact or Fiction", 1997, [Q("beyond belief fact or fiction", "beyond belief: fact or fiction") + f" AND {C_TV}", f'title:("beyond belief") AND description:(frakes OR brolin OR "fact or fiction") AND {C_TV}'], "anthology", "1997-2002 Dick Clark anthology (Frakes); archive.org fan copies.", None, False),
  ("unsolved-mysteries-1987", "Unsolved Mysteries", 1987, [Q("unsolved mysteries") + f" AND {C_TV}"], "documentary", "1987-2002 Robert Stack era; archive.org fan copies (VHS rips).", None, True),
  ("rescue-911", "Rescue 911", 1989, [Q("rescue 911") + f" AND {C_TV}"], "reality", "1989-96 William Shatner; archive.org fan copies.", None, True),
 ],
 "gameshow": [
  ("supermarket-sweep-1990", "Supermarket Sweep", 1990, [Q("supermarket sweep") + f" AND {C_TV}"], "game", "1990-95 Lifetime / 2000-03 PAX run, David Ruprecht.", None, True),
  ("card-sharks-1978", "Card Sharks", 1978, [Q("card sharks") + f" AND {C_TV}"], "game", "1978-81 NBC Jim Perry; 1986-89 CBS Bob Eubanks.", None, True),
  ("press-your-luck-1983", "Press Your Luck", 1983, [Q("press your luck") + f" AND {C_TV}", f'title:(whammy) AND {C_TV}'], "game", "1983-86 CBS Peter Tomarken; Whammy! 2002-03 GSN.", None, True),
  ("price-is-right-1972", "The Price Is Right", 1972, [Q("price is right") + f" AND {C_TV}"], "game", "1972- CBS, Bob Barker era 1972-2007.", None, True),
  ("wheel-of-fortune-1975", "Wheel of Fortune", 1975, [Q("wheel of fortune") + f" AND {C_TV}"], "game", "1975-91 NBC daytime Woolery/Sajak; 1983- syndicated.", None, True),
  ("match-game-1973", "Match Game", 1973, [Q("match game") + f" AND {C_TV}"], "game", "1973-82 CBS Gene Rayburn.", None, True),
  ("family-feud-1976", "Family Feud", 1976, [Q("family feud") + f" AND {C_TV}"], "game", "1976-85 ABC Richard Dawson.", None, True),
  ("25000-pyramid", "The $25,000 Pyramid", 1982, [Q("25,000 pyramid", "$25,000 pyramid", "25000 pyramid", "$100,000 pyramid", "10,000 pyramid", "20,000 pyramid") + f" AND {C_TV}"], "game", "1973-91 Dick Clark Pyramid family.", None, True),
  ("password-plus", "Password Plus", 1979, [Q("password plus", "super password") + f" AND {C_TV}"], "game", "1979-82 NBC Allen Ludden / Tom Kennedy; Super Password 1984-89.", None, True),
  ("tic-tac-dough-1978", "Tic-Tac-Dough", 1978, [Q("tic tac dough", "tic-tac-dough") + f" AND {C_TV}"], "game", "1978-86 syndicated Wink Martindale.", None, True),
  ("jokers-wild-1972", "The Joker's Wild", 1972, [Q("joker's wild", "jokers wild") + f" AND {C_TV}"], "game", "1972-75 CBS, 1977-86 syndicated Jack Barry/Bill Cullen.", None, True),
  ("sale-of-the-century-1983", "Sale of the Century", 1983, [Q("sale of the century") + f" AND {C_TV} AND NOT title:(australia OR australian OR 9 OR nine)"], "game", "1983-89 NBC Jim Perry (US).", None, True),
  ("classic-concentration", "Classic Concentration", 1987, [Q("classic concentration") + f" AND {C_TV}", f'title:(concentration) AND description:(trebek) AND {C_TV}'], "game", "1987-91 NBC Alex Trebek.", None, True),
  ("blockbusters-1980", "Blockbusters", 1980, [Q("blockbusters") + f' AND description:(cullen OR "game show") AND {C_TV}'], "game", "1980-82 NBC Bill Cullen; 1987 revival.", None, True),
  ("lets-make-a-deal-1963", "Let's Make a Deal", 1963, [Q("let's make a deal", "lets make a deal") + f" AND {C_TV}"], "game", "1963-76 NBC/ABC Monty Hall.", None, True),
 ],
 "nick90s": [
  ("rugrats", "Rugrats", 1991, [Q("rugrats") + f" AND {C_TV}"], "animation", "1991-2004 Nickelodeon; archive.org fan copies.", None, True),
  ("doug-1991", "Doug", 1991, [f'title:(doug) AND (title:(nickelodeon OR nicktoons) OR description:(nickelodeon OR "jim jinkins")) AND {C_TV}'], "animation", "1991-94 Nickelodeon run.", None, True),
  ("ren-and-stimpy", "The Ren & Stimpy Show", 1991, [Q("ren and stimpy", "ren & stimpy", "ren stimpy") + f" AND {C_TV}"], "animation", "1991-96 Nickelodeon.", None, True),
  ("rockos-modern-life", "Rocko's Modern Life", 1993, [Q("rocko's modern life", "rockos modern life", "rocko") + f" AND {C_TV}"], "animation", "1993-96 Nickelodeon.", None, True),
  ("hey-arnold", "Hey Arnold!", 1996, [Q("hey arnold") + f" AND {C_TV}"], "animation", "1996-2004 Nickelodeon.", None, True),
  ("are-you-afraid-of-the-dark", "Are You Afraid of the Dark?", 1990, [Q("are you afraid of the dark") + f" AND {C_TV}"], "anthology", "1990-96, 1999-2000 Nickelodeon/YTV.", None, True),
  ("clarissa-explains-it-all", "Clarissa Explains It All", 1991, [Q("clarissa explains it all", "clarissa") + f" AND {C_TV}"], "comedy", "1991-94 Nickelodeon.", None, True),
  ("pete-and-pete", "The Adventures of Pete & Pete", 1993, [Q("pete and pete", "pete & pete") + f" AND {C_TV}"], "comedy", "1993-96 Nickelodeon.", None, True),
  ("salute-your-shorts", "Salute Your Shorts", 1991, [Q("salute your shorts") + f" AND {C_TV}"], "comedy", "1991-92 Nickelodeon.", None, True),
  ("legends-of-the-hidden-temple", "Legends of the Hidden Temple", 1993, [Q("legends of the hidden temple") + f" AND {C_TV}"], "game", "1993-95 Nickelodeon.", None, True),
  ("double-dare-1986", "Double Dare", 1986, [Q("double dare") + f" AND (title:(nickelodeon OR 1986 OR 1987 OR 1988 OR 1989 OR family OR super sloppy) OR description:(nickelodeon OR summers)) AND {C_TV}"], "game", "1986-93 Nickelodeon Marc Summers.", None, True),
  ("nickelodeon-guts", "Nickelodeon GUTS", 1992, [Q("nickelodeon guts", "nick guts", "global guts") + f" AND {C_TV}"], "game", "1992-96 Nickelodeon Mike O'Malley.", None, True),
  ("all-that", "All That", 1994, [Q("all that") + f" AND (title:(nickelodeon OR snick) OR description:(nickelodeon OR snick OR kenan)) AND {C_TV}"], "comedy", "1994-2005 Nickelodeon.", None, True),
  ("kenan-and-kel", "Kenan & Kel", 1996, [Q("kenan and kel", "kenan & kel") + f" AND {C_TV}"], "comedy", "1996-2000 Nickelodeon.", None, True),
  ("rocket-power", "Rocket Power", 1999, [Q("rocket power") + f" AND {C_TV}"], "animation", "1999-2004 Nickelodeon.", None, True),
  ("catdog", "CatDog", 1998, [Q("catdog", "cat dog") + f" AND description:(nickelodeon OR nicktoons) AND {C_TV}", Q("catdog") + f" AND {C_TV}"], "animation", "1998-2005 Nickelodeon.", None, True),
  ("kablam", "KaBlam!", 1996, [Q("kablam") + f" AND {C_TV}"], "animation", "1996-2000 Nickelodeon.", None, True),
  ("alex-mack", "The Secret World of Alex Mack", 1994, [Q("alex mack") + f" AND {C_TV}"], "drama", "1994-98 Nickelodeon.", None, True),
  ("figure-it-out", "Figure It Out", 1997, [Q("figure it out") + f" AND (title:(nickelodeon) OR description:(nickelodeon OR summer sanders)) AND {C_TV}"], "game", "1997-99 Nickelodeon.", None, True),
  ("wild-and-crazy-kids", "Wild & Crazy Kids", 1990, [Q("wild and crazy kids", "wild & crazy kids") + f" AND {C_TV}"], "game", "1990-92 Nickelodeon.", None, True),
 ],
 "sesame": [
  # loose=False on purpose: the decade compilation items name the show on every file, so loose mode would flood season 0 with
  # unnumbered segments; only files carrying a production episode number (or SxxEyy / air date) are kept.
  ("sesame-street", "Sesame Street", 1969, [Q("sesame street") + f" AND title:(episode) AND {C_TV}", Q("sesame street") + f" AND title:(1960s OR 1970s OR 1980s OR 1990s OR classic OR full) AND {C_TV}"], "kids", "1969-2001 Children's Television Workshop classic era (seasons 1-32); archive.org fan copies.", None, False),
 ],
}
SOURCE = {"chan83add": "chan83", "gameshow": "gameshow", "nick90s": "nick90s", "sesame": "sesame"}[LANE]
# Phase S: production-episode-number matching (Sesame Street items are titled 'Sesame Street Episode 0847', never SxxEyy).
# season = where the number falls in TMDB's cumulative per-season episode counts; classic cut = max_season.
EPNUM_SHOWS = {"sesame-street": {"max_season": 32}}
EPNUM = re.compile(r"(?:episode|ep\.?|#|\bss)\s*#?\s*(\d{1,4})(?!\d)", re.I)
ROWS = {"sesame": 1000}.get(LANE, 120)

def build_show(show_id, title, year, queries, genre, basis, seasons, loose):
    s = (tmdb("/search/tv", query=title, first_air_date_year=year).get("results") or [None])[0] or (tmdb("/search/tv", query=title).get("results") or [None])[0]
    if not s: print("TMDB miss", title, flush=True); return None, []
    det = tmdb(f"/tv/{s['id']}"); lo = int((det.get("first_air_date") or str(year))[:4]); hi = int((det.get("last_air_date") or det.get("first_air_date") or str(year))[:4])
    eps = []
    for se in det.get("seasons") or []:
        n = se.get("season_number")
        if not n or (seasons and n not in seasons): continue
        for e in tmdb(f"/tv/{s['id']}/season/{n}").get("episodes") or []:
            eps.append({"season": n, "episode": e["episode_number"], "name": e.get("name") or "", "key": norm(e.get("name")), "id": e.get("id"), "still": e.get("still_path"), "air": e.get("air_date"), "over": e.get("overview"), "rt": e.get("runtime")})
    counts = {}
    for e in eps: counts[e["season"]] = max(counts.get(e["season"], 0), e["episode"])   # per-season episode counts for the epnum matcher
    keys = [e["key"] for e in eps]; by_air = {}
    for e in eps:
        if e["air"]: by_air.setdefault(e["air"], []).append(e)
    seen = set(); cands = []
    for q in queries:
        for d in ia_search(q, ROWS):
            ident = d.get("identifier")
            if not ident or ident in seen: continue
            seen.add(ident)
            for f in ia_files(ident): cands.append((ident, d.get("title") or "", f))
    picked = {}; unlisted = []
    for ident, ititle, f in cands:
        name = f["name"]; text = f"{ititle} {name}"; target = None; how = ""
        m = SE.search(text)
        if m:
            S, E = (int(m.group(1)), int(m.group(2))) if m.group(1) else (int(m.group(3)), int(m.group(4)))
            target = next((e for e in eps if e["season"] == S and e["episode"] == E), None); how = "sxxeyy" if target else ""
        if target is None and show_id in EPNUM_SHOWS:
            m2 = EPNUM.search(name) or EPNUM.search(ititle)
            if m2:
                n_prod = int(m2.group(1)); cum = 0
                for sn in sorted(counts):
                    if n_prod <= cum + counts[sn]:
                        if sn <= EPNUM_SHOWS[show_id]["max_season"]:
                            E2 = n_prod - cum
                            target = next((e for e in eps if e["season"] == sn and e["episode"] == E2), None) or {"season": sn, "episode": E2, "name": f"Episode {n_prod:04d}", "air": None, "id": None, "still": None, "over": None, "rt": None}
                            how = "epnum" if target.get("id") else "epnum-noTMDBrow"
                        break
                    cum += counts[sn]
        if target is None and by_air:
            ds = [d for d in dates_in(text, lo, hi) if d in by_air]
            if len(ds) == 1 and len(by_air[ds[0]]) == 1: target = by_air[ds[0]][0]; how = "airdate"
        if target is None and keys:
            probe = strip_show(re.sub(r"\.[a-z0-9]+$", "", name), title) or strip_show(ititle, title)
            if len(probe) >= 6:
                best = difflib.get_close_matches(probe, keys, n=2, cutoff=0.82)
                if best:
                    r1 = difflib.SequenceMatcher(None, probe, best[0]).ratio(); r2 = difflib.SequenceMatcher(None, probe, best[1]).ratio() if len(best) > 1 else 0
                    if r1 >= 0.86 and r1 - r2 >= 0.06: target = eps[keys.index(best[0])]; how = "title"
        if target is None:
            if loose and (names_show(ititle, title) or names_show(name, title)):
                unlisted.append((ident, ititle, f))
            continue
        q = quality(f); k = (target["season"], target["episode"])
        if k not in picked or q > picked[k][0]:
            picked[k] = (q, {"ep_id": f"{show_id}-s{k[0]:02d}e{k[1]:03d}", "show_id": show_id, "season": k[0], "episode": k[1], "title": target["name"], "air_date": target["air"], "tmdb_ep_id": target["id"], "still_path": target["still"], "overview": target["over"], "runtime": target["rt"], "ia_id": ident, "stream_name": name, "size_mb": round(q[1]), "match": how})
    out = sorted((v[1] for v in picked.values()), key=lambda e: (e["season"], e["episode"]))
    # loose: unlisted files become season-0 rows, titled from the file name, de-duplicated by cleaned name
    seen_names = set(); n0 = 0
    for ident, ititle, f in sorted(unlisted, key=lambda x: -quality(x[2])[1]):
        clean = re.sub(r"\.[a-z0-9]+$", "", f["name"]); clean = re.sub(r"[._]+", " ", clean).strip()
        key = norm(clean)
        if not key or key in seen_names: continue
        seen_names.add(key); n0 += 1
        ds = dates_in(f"{ititle} {f['name']}", lo, hi)
        out.append({"ep_id": f"{show_id}-s00e{n0:04d}", "show_id": show_id, "season": 0, "episode": n0, "title": clean[:120], "air_date": ds[0] if ds else None, "tmdb_ep_id": None, "still_path": None, "overview": None, "runtime": None, "ia_id": ident, "stream_name": f["name"], "size_mb": round(float(f.get("size") or 0) / 1e6), "match": "unlisted"})
    show = {"show_id": show_id, "title": det.get("name") or title, "tmdb_id": s["id"], "era_start": lo, "era_end": hi, "poster_path": det.get("poster_path"), "backdrop_path": det.get("backdrop_path"), "overview": det.get("overview"), "network": ((det.get("networks") or [{}])[0]).get("name"), "pd_basis": basis, "pd_mode": "seasons" if seasons else "all", "genre": genre, "lane": SOURCE, "loose": loose}
    hows = {}
    for e in out: hows[e["match"]] = hows.get(e["match"], 0) + 1
    print(f"{title}: tmdb={s['id']} eps_in_scope={len(eps)} ia_items={len(seen)} files={len(cands)} matched={len(out)} {hows}", flush=True)
    return show, out

shows, episodes = [], []
for row in LANES[LANE]:
    if ONLY and row[0] not in ONLY: continue
    try:
        sh, eps = build_show(*row)
        if sh and eps: shows.append(sh); episodes.extend(eps)
    except Exception as e: print("ERR", row[0], e, flush=True)
    json.dump({"exported": time.strftime("%Y-%m-%d"), "lane": SOURCE, "origin": "lane_seed_build.py v2.2 (TMDB metadata + archive.org files only)", "shows": shows, "episodes": episodes}, open(OUT, "w"), indent=0)
print("DONE lane", LANE, "shows", len(shows), "episodes", len(episodes), "->", OUT)
