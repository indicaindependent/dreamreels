"""Dreamy tool router (Phase C, Sep 12 2026).

Dreamy is a TOOL-USING agent: every request is routed to a named tool with a JSON-serialisable result
{text, buttons[], actions[]}. Tools are deterministic (regex + slot filling over the library), so the same sentence
always does the same thing and the "what can I say" panel is GENERATED from this registry - it can never promise a
capability that does not exist. Actions are applied by the player on the GUI thread (browse, play, queue, input...).
A Play button is only ever produced for a row with verified=1; everything else is a "check" button.
Open questions about people/films fall through to the v1 agent (TMDB-backed) and, if configured, to a remote LLM
(cfg["dreamy"]["llm_url"] + ["llm_key"], optional) - never required for any command to work.
"""
from __future__ import annotations
import re, os, json, time, logging
from . import agent
from ..core import db as dbmod
log = logging.getLogger("dreamreels.player.dreamy")

GENRES = {"noir": "Film-Noir", "film noir": "Film-Noir", "film-noir": "Film-Noir", "horror": "Horror", "scary": "Horror", "sci-fi": "Sci-Fi", "scifi": "Sci-Fi", "science fiction": "Sci-Fi",
          "comedy": "Comedy", "comedies": "Comedy", "funny": "Comedy", "drama": "Drama", "western": "Western", "westerns": "Western", "cowboy": "Western", "mystery": "Mystery", "mysteries": "Mystery",
          "thriller": "Thriller", "thrillers": "Thriller", "romance": "Romance", "romantic": "Romance", "adventure": "Adventure", "crime": "Crime", "gangster": "Crime", "documentary": "Documentary",
          "documentaries": "Documentary", "war": "War", "musical": "Musical", "musicals": "Musical", "animation": "Animation", "cartoon": "Animation", "family": "Family", "fantasy": "Fantasy", "history": "History", "action": "Action"}
LANES = {"public domain": "pd", "pd": "pd", "archive": "pd", "classic movies": "pd", "nas": "nas", "my nas": "nas", "the nas": "nas", "share": "nas", "network": "nas", "youtube": "youtube", "yt": "youtube",
         "music": "music", "songs": "music", "mp3s": "music", "toon town": "toontown", "toontown": "toontown", "game shows": "gameshow", "game show": "gameshow", "gameshow": "gameshow", "gameshows": "gameshow", "90s nick": "nick90s", "nick": "nick90s", "nickelodeon": "nick90s", "nick90s": "nick90s", "sesame street": "sesame", "sesame": "sesame", "classic sesame street": "sesame", "elmo": "sesame", "big bird": "sesame", "cartoons": "toontown", "channel 83": "chan83", "channel eighty three": "chan83", "anthology": "chan83", "search": "search", "home": "home"}
LANE_LABEL = {"pd": "Public Domain", "nas": "NAS", "youtube": "YouTube", "music": "Music", "toontown": "Toon Town", "gameshow": "Game Shows", "nick90s": "90s Nick", "sesame": "Classic Sesame Street", "chan83": "Channel 83", "search": "Search", "home": "Home"}
VIZ = ("bars", "spectrum", "scope", "waves", "freqs", "off")

def _q(sql, args=()):
    c = dbmod.connect()
    try: return [dict(r) for r in c.execute(sql, args).fetchall()]
    finally: c.close()
def _btn(kind, label, **kw): d = {"kind": kind, "label": agent._clean(label)[:60]}; d.update(kw); return d
def _item_btns(rows, limit=10):
    out = []
    for r in rows[:limit]:
        lab = f"{r['title']} ({r['year']})" if r.get("year") else r["title"]
        out.append(_btn("play" if r.get("verified") else "check", lab, uid=r["uid"], poster=r.get("poster") or r.get("poster_local") or "", year=r.get("year"), source=r.get("source")))
    return out
def _res(text, buttons=None, actions=None): return {"text": text, "buttons": buttons or [], "actions": actions or []}
def _lane_in(t):
    for k in sorted(LANES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(k)}\b", t): return LANES[k]
    return None
def _genre_in(t):
    for k in sorted(GENRES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(k)}\b", t): return GENRES[k]
    return None
def _year_in(t):
    m = re.search(r"\b(1[89]\d\d|20[0-2]\d)\b(?!s)", t); return m.group(1) if m else None
def _decade_in(t):
    m = re.search(r"\b(1[89]\d0|20[0-2]0)s\b", t)
    if m: return m.group(1)
    m = re.search(r"\b(twenties|thirties|forties|fifties|sixties|seventies|eighties)\b", t)
    return {"twenties": "1920", "thirties": "1930", "forties": "1940", "fifties": "1950", "sixties": "1960", "seventies": "1970", "eighties": "1980"}.get(m.group(1)) if m else None
def _person_in(text):
    m = re.search(r"\b(?:by|directed by|from|starring|with)\s+([A-Z][\w'.-]+(?:\s+[A-Z][\w'.-]+){1,2})", text)
    if m: return m.group(1)
    q = agent.parse(text); return q.get("person")
def _title_rows(title, verified_only=False, limit=12):
    like = f"%{title.strip()}%"
    rows = _q(f"SELECT * FROM items WHERE blocked=0 AND kind!='track' AND (title LIKE ? OR title_raw LIKE ?){' AND verified=1' if verified_only else ''} ORDER BY verified DESC, (title=?) DESC, downloads DESC, title LIMIT ?", (like, like, title.strip(), limit))
    return rows

# ---------------------------------------------------------------- tools -------------------------------------------------
TOOLS = []
def tool(name, desc, examples, *patterns):
    def deco(fn):
        TOOLS.append({"name": name, "desc": desc, "examples": examples, "patterns": [re.compile(p, re.I) for p in patterns], "fn": fn}); return fn
    return deco

@tool("help", "Tell you what I can do", ["what can you do", "help"], r"^(help|what can (you|i) (do|say|ask)|commands|how do (i|you) .*)\??$")
def t_help(cfg, text, m):
    lines = ["Here is everything I can do - say it any way you like:"]
    for t in TOOLS:
        if t["name"] != "help": lines.append(f"• {t['desc']} - e.g. \"{t['examples'][0]}\"")
    return _res("\n".join(lines), [_btn("ask", f"Try: {t['examples'][0]}", query=t["examples"][0]) for t in TOOLS[1:7]])

@tool("player", "Control playback: pause, resume, stop, next, skip ahead or back", ["pause", "stop", "next", "skip ahead 5 minutes"],
      r"^(pause|resume|unpause|stop( playing| the movie)?|next( one| episode| track)?|skip( this)?|skip (ahead|forward|back|backwards)( \d+ (seconds?|minutes?))?|rewind( \d+ (seconds?|minutes?))?|go back \d+ (seconds?|minutes?)|louder|quieter|mute|unmute|fullscreen)$")
def t_player(cfg, text, m):
    t = text.lower().strip(); n = re.search(r"(\d+) (seconds?|minutes?)", t); secs = (int(n.group(1)) * (60 if n.group(2).startswith("min") else 1)) if n else 30
    if t.startswith(("pause", "resume", "unpause")): cmd = "pause"
    elif t.startswith("stop"): cmd = "stop"
    elif t.startswith(("next", "skip this")): cmd = "next"
    elif "back" in t or "rewind" in t: cmd = f"seek:-{secs}"
    elif t.startswith("skip"): cmd = f"seek:{secs}"
    elif t in ("louder",): cmd = "vol:+10"
    elif t in ("quieter",): cmd = "vol:-10"
    elif t in ("mute", "unmute"): cmd = "mute"
    else: cmd = "fullscreen"
    return _res({"pause": "Toggling pause.", "stop": "Stopping.", "next": "Next in the queue.", "mute": "Toggling mute.", "fullscreen": "Toggling fullscreen."}.get(cmd, f"Seeking {cmd.split(':')[1]} seconds." if cmd.startswith("seek") else "Volume adjusted."), actions=[{"type": "player", "cmd": cmd}])

@tool("go_lane", "Open a lane: Home, Public Domain, NAS, YouTube, Music, Toon Town, Channel 83", ["open public domain", "go to toon town", "take me home"],
      r"^(open|go to|go|show( me)?|take me( to)?|switch to|bring up)\s+(the\s+)?(home|public domain|pd|nas|my nas|the nas|youtube|yt|music|toon town|toontown|cartoons|channel 83|search)\s*(lane|page|section)?$")
def t_go(cfg, text, m):
    lane = _lane_in(text.lower()) or "home"
    return _res(f"Opening {LANE_LABEL.get(lane, lane)}.", actions=[{"type": "browse", "lane": lane, "path": []}, {"type": "close"}])

@tool("browse_pd", "Browse Public Domain by year, decade, genre or director", ["show me 1948 film noir", "browse 1930s horror", "movies directed by Alfred Hitchcock", "what do you have from 1922"],
      r"^(show( me)?|browse|open|list|what do you have( from| in)?|what (films|movies) (are|do you have)( from| in)?|anything( from| in)?|give me)\b.*\b(1[89]\d\d|20[0-2]\d|1[89]\d0s|20[0-2]0s|twenties|thirties|forties|fifties|sixties|seventies|noir|horror|sci-fi|scifi|comedy|comedies|drama|western|westerns|mystery|thriller|romance|adventure|crime|documentary|documentaries|war|musical|directed by|by [A-Z])",
      r"^(movies|films)\s+(directed )?by\s+[A-Z]")
def t_browse_pd(cfg, text, m):
    t = text.lower(); path = []; bits = []
    y, d, g = _year_in(t), _decade_in(t), _genre_in(t); p = _person_in(text) if re.search(r"\b(by|directed)\b", t) else None
    if y: path += ["year", y]; bits.append(y)
    elif d: path += ["decade", d]; bits.append(f"the {d}s")
    if g: path += ["genre", g]; bits.append(g)
    if p: path += ["director", p]; bits.append(f"directed by {p}")
    if not path: return None
    where = ["source='pd'", "blocked=0"]; args = []
    if y: where.append("year=?"); args.append(int(y))
    elif d: where.append("decade=?"); args.append(int(d))
    if g: where.append("genres LIKE ?"); args.append(f"%{g}%")
    if p: where.append("director LIKE ?"); args.append(f"%{p}%")
    rows = _q(f"SELECT * FROM items WHERE {' AND '.join(where)} ORDER BY verified DESC, downloads DESC LIMIT 8", tuple(args))
    n = _q(f"SELECT COUNT(*) AS n, SUM(verified) AS v FROM items WHERE {' AND '.join(where)}", tuple(args))[0]
    desc = " ".join(bits)
    if not n["n"]: return _res(f"Nothing in the Public Domain catalogue for {desc} yet. I can look on archive.org for it.", [_btn("ask", f"Search archive.org for {desc}", query=f"find me {desc} movies")])
    return _res(f"{n['n']} titles for {desc}, {n['v'] or 0} verified playable. Opening that page - here are the first few:", _item_btns(rows), [{"type": "browse", "lane": "pd", "path": path}])

@tool("play_title", "Play a film, episode or short by name", ["play Night of the Living Dead", "put on The Twilight Zone", "watch Betty Boop"],
      r"^(play|put on|start|watch|i want to watch|let'?s watch)\s+(?!some music|music|something random|a random|random)(.+?)(\s+please)?$")
def t_play(cfg, text, m):
    title = m.group(2).strip(" .!\"'")
    if re.fullmatch(r"(it|that|this|the (movie|film))", title.lower()): return None
    shows = _q("SELECT uid, title, source FROM shows WHERE lower(title) LIKE ? ORDER BY length(title) LIMIT 3", (f"%{title.lower()}%",))
    if shows and (shows[0]["title"].lower() == title.lower() or shows[0]["title"].lower().startswith(title.lower())):
        sh = shows[0]; n = _q("SELECT COUNT(*) AS n FROM items WHERE show_uid=? AND verified=1 AND blocked=0", (sh["uid"],))[0]["n"]
        return _res(f"{sh['title']} is a series ({n} playable episodes) - starting a random one and opening the show page.", [], [{"type": "browse", "lane": sh["source"], "path": ["show", sh["uid"]]}, {"type": "chip", "id": "action:block"}, {"type": "close"}])
    rows = _title_rows(title)
    if not rows: return _res(f"I don't have anything called \"{title}\" in the library. I can search archive.org or YouTube for it.", [_btn("ask", f"Find {title} on archive.org", query=f"find me {title}"), _btn("ask", f"Find {title} on YouTube", query=f"youtube {title}")])
    exact = [r for r in rows if r["title"].lower() == title.lower()]
    top = exact[0] if exact else rows[0]
    if len(rows) == 1 or exact:
        if top["verified"]: return _res(f"Playing {top['title']}" + (f" ({top['year']})" if top.get("year") else "") + ".", _item_btns([top]), [{"type": "play", "uid": top["uid"]}, {"type": "close"}])
        return _res(f"I have {top['title']} but it has not passed the playback check yet - press Check and I will verify it plays before handing you Play.", _item_btns([top]))
    return _res(f"I found {len(rows)} matches for \"{title}\" - pick one:", _item_btns(rows))

@tool("shuffle", "Shuffle a lane, play a random episode, or a 6-short cartoon block", ["shuffle toon town", "random channel 83 episode", "cartoon block", "surprise me"],
      r"^(shuffle|random|surprise me|something random|play (something|anything)( random)?|cartoon block|play a (random )?(cartoon|episode|short|movie|film)|i'?m bored)\b.*")
def t_shuffle(cfg, text, m):
    t = text.lower(); lane = _lane_in(t) or ("toontown" if "cartoon" in t or "short" in t else "chan83" if "episode" in t else "pd")
    block = "block" in t
    act = "action:block" if (block or (lane == "chan83" and "episode" in t and "shuffle" not in t)) else "action:shuffle"
    what = "a cartoon block (6 shorts)" if block else f"a random {LANE_LABEL.get(lane, lane)} pick" if act == "action:block" else f"shuffling {LANE_LABEL.get(lane, lane)}"
    return _res(f"Starting {what}. Press Back to stop the queue.", actions=[{"type": "browse", "lane": lane, "path": []}, {"type": "chip", "id": act}, {"type": "close"}])

@tool("continue", "Continue what you were watching", ["continue watching", "resume my movie"], r"^(continue|resume)( watching| my (movie|film|show|episode))?$|^what was i watching\??$")
def t_continue(cfg, text, m):
    rows = _q("SELECT i.* FROM items i JOIN state s ON s.uid=i.uid WHERE s.resume_sec>30 AND s.duration_sec>0 AND s.resume_sec < s.duration_sec*0.95 AND i.blocked=0 ORDER BY s.last_played DESC LIMIT 6")
    if not rows: return _res("Nothing is part-watched right now.")
    return _res(f"You were watching {rows[0]['title']}. Resume it, or pick another:", _item_btns(rows), [{"type": "play", "uid": rows[0]["uid"], "resume": True}, {"type": "close"}] if len(rows) == 1 else [])

@tool("nas", "Explore the NAS or open a folder by name", ["explore the nas", "open the tv folder on the nas", "scan the nas for music"],
      r"^(explore|browse|open|show( me)?)\s+(the\s+)?(nas|share|network|my files)( (folder|drive|share))?(\s+(folder\s+)?(.+))?$", r"^(open|browse|show( me)?)\s+(the\s+)?(.+?)\s+folder( on the nas)?$", r"^scan (the )?(nas|share)( for (music|movies|videos))?$")
def t_nas(cfg, text, m):
    t = text.lower()
    if t.startswith("scan"): 
        if "music" in t: return _res("Scanning the NAS for music in the background - I will tell you when it is done.", actions=[{"type": "browse", "lane": "music", "path": []}, {"type": "chip", "id": "action:musicscan"}, {"type": "close"}])
        return _res("Opening the NAS - use 'Scan this folder into the library' inside any folder.", actions=[{"type": "browse", "lane": "nas", "path": []}, {"type": "close"}])
    want = None
    mm = re.search(r"(?:open|browse|show(?: me)?)\s+(?:the\s+)?(.+?)\s+folder", t)
    if mm and mm.group(1) not in ("nas", "share", "network"): want = mm.group(1)
    elif m.lastindex and m.lastindex >= 9 and m.group(9): want = m.group(9).strip()
    roots = _nas_roots()
    if want:
        hits = []
        for r in roots:
            for dp, dn, fn in os.walk(r):
                depth = dp[len(r):].count("/")
                for d in dn:
                    if want in d.lower(): hits.append(os.path.join(dp, d))
                if depth >= 2: dn[:] = []
                if len(hits) > 20: break
        if not hits: return _res(f"No folder called \"{want}\" on the NAS shares ({', '.join(roots) or 'none mounted'}). Opening the explorer instead.", actions=[{"type": "browse", "lane": "nas", "path": []}, {"type": "close"}])
        if len(hits) == 1: return _res(f"Opening {hits[0]}.", actions=[{"type": "browse", "lane": "nas", "path": ["dir", hits[0]]}, {"type": "close"}])
        return _res(f"{len(hits)} folders match \"{want}\" - pick one:", [_btn("nav", os.path.basename(h), action={"type": "browse", "lane": "nas", "path": ["dir", h]}) for h in hits[:8]])
    return _res("Opening the NAS explorer." if roots else "No NAS share is mounted right now - run the setup wizard to add one.", actions=[{"type": "browse", "lane": "nas", "path": []}, {"type": "close"}] if roots else [])
def _nas_roots():
    roots = set()
    for r in _q("SELECT DISTINCT path FROM items WHERE source IN ('nas','music') AND path IS NOT NULL"):
        parts = str(r["path"]).split("/")
        if len(parts) > 3: roots.add("/".join(parts[:3]))
    for base in ("/media", "/mnt"):
        try:
            for e in os.scandir(base):
                if e.is_dir() and os.path.ismount(e.path): roots.add(e.path)
        except Exception: pass
    return sorted(x for x in roots if os.path.isdir(x))

@tool("youtube_channel", "Add or remove a YouTube channel", ["add the channel @veritasium", "remove channel veritasium", "my channels"],
      r"^(add|subscribe( to)?|follow)\s+(the\s+)?(youtube\s+)?channel\s+(.+)$", r"^(remove|unsubscribe( from)?|unfollow|delete)\s+(the\s+)?(youtube\s+)?channel\s+(.+)$", r"^(my|show( me)?( my)?|list( my)?|manage) (youtube )?channels$")
def t_ytchan(cfg, text, m):
    t = text.lower()
    if re.match(r"^(my|show|list|manage)", t): return _res("Here are your channels.", actions=[{"type": "browse", "lane": "youtube", "path": ["manage", "1"]}, {"type": "close"}])
    handle = m.group(5).strip(" .")
    if re.match(r"^(remove|unsubscribe|unfollow|delete)", t):
        rows = _q("SELECT channel_id,title,handle FROM yt_channels WHERE lower(title) LIKE ? OR lower(handle) LIKE ?", (f"%{handle.lower().lstrip('@')}%", f"%{handle.lower().lstrip('@')}%"))
        if not rows: return _res(f"No saved channel matches \"{handle}\".", actions=[{"type": "browse", "lane": "youtube", "path": ["manage", "1"]}])
        return _res(f"Removing {rows[0]['title'] or rows[0]['handle']}.", actions=[{"type": "browse", "lane": "youtube", "path": ["manage", "1"]}, {"type": "chip", "id": f"action:rmchan|{rows[0]['channel_id']}"}])
    return _res(f"Adding {handle} - reading its latest 30 videos. They will show as Check until each passes the decode test.", actions=[{"type": "browse", "lane": "youtube", "path": []}, {"type": "ytadd", "text": handle}, {"type": "close"}])

@tool("music", "Play music by artist or album, shuffle your music, pick a visualizer", ["play some music", "play music by Miles Davis", "shuffle my music", "visualizer spectrum"],
      r"^(play|put on)\s+(some\s+)?(music|songs|tunes)(\s+by\s+(.+))?$", r"^(play|put on)\s+(the album|album)\s+(.+)$", r"^(shuffle|random)\s+(my\s+)?(music|songs|tracks)$", r"^(visuali[sz]er|viz)\s+(bars|spectrum|scope|waves|freqs|off)$", r"^(turn|switch) (the )?visuali[sz]er (on|off)$")
def t_music(cfg, text, m):
    t = text.lower(); n = _q("SELECT COUNT(*) AS n FROM items WHERE kind='track' AND blocked=0")[0]["n"]
    vm = re.search(r"(bars|spectrum|scope|waves|freqs|off)$", t)
    if t.startswith(("visual", "viz", "turn", "switch")):
        k = vm.group(1) if vm else ("off" if t.endswith("off") else "bars")
        return _res(f"Visualizer set to {k}.", actions=[{"type": "chip_direct", "id": f"viz:{k}"}])
    if not n: return _res("No music is indexed yet. Say 'scan the nas for music' and I will index every mp3/flac on the share.", [_btn("ask", "Scan the NAS for music", query="scan the nas for music")])
    by = re.search(r"\bby\s+(.+)$", text, re.I); alb = re.search(r"\balbum\s+(.+)$", text, re.I)
    if alb:
        rows = _q("SELECT DISTINCT blurb FROM items WHERE kind='track' AND blurb LIKE ? LIMIT 3", (f"%{alb.group(1).strip()}%",))
        if rows: return _res(f"Opening the album {rows[0]['blurb']}.", actions=[{"type": "browse", "lane": "music", "path": ["album", rows[0]["blurb"]]}, {"type": "close"}])
        return _res(f"No album matching \"{alb.group(1)}\".")
    if by:
        rows = _q("SELECT director, COUNT(*) AS n FROM items WHERE kind='track' AND director LIKE ? GROUP BY director ORDER BY n DESC LIMIT 3", (f"%{by.group(1).strip()}%",))
        if rows: return _res(f"Playing {rows[0]['director']} ({rows[0]['n']} tracks).", actions=[{"type": "browse", "lane": "music", "path": ["artist", rows[0]["director"]]}, {"type": "chip", "id": "action:shuffle"}, {"type": "close"}])
        return _res(f"No artist matching \"{by.group(1)}\" in your music.")
    return _res(f"Shuffling your {n} tracks with the visualizer on.", actions=[{"type": "browse", "lane": "music", "path": []}, {"type": "chip", "id": "action:shuffle"}, {"type": "close"}])

@tool("search", "Search everything at once", ["search for twilight", "look up welles"], r"^(search( for| everything for)?|look up|look for)\s+(.+)$")
def t_search(cfg, text, m):
    q = m.group(m.lastindex).strip()
    rows = _q("SELECT * FROM items WHERE blocked=0 AND (title LIKE ? OR director LIKE ?) ORDER BY verified DESC, downloads DESC LIMIT 8", (f"%{q}%", f"%{q}%"))
    return _res(f"{len(rows)} quick hits for \"{q}\" - full results are on the Search page." if rows else f"Nothing in the library matches \"{q}\". Try 'find me {q}' and I will look on archive.org.", _item_btns(rows), [{"type": "browse", "lane": "search", "path": [q]}])

@tool("about", "Tell you about a film in your library, or a person (from the movie database)", ["tell me about Detour", "who was Orson Welles", "was Boris Karloff in any 1930s films"],
      r"^(tell me about|what is|what'?s|describe|info on|information about)\s+(.+)$", r"^(who (is|was)|was|is|did)\s+[A-Z].*\??$")
def t_about(cfg, text, m):
    if re.match(r"^(who|was|is|did)\b", text, re.I): return None   # people -> v1 TMDB agent
    title = m.group(2).strip(" ?.\"'")
    rows = _title_rows(title, limit=3)
    if not rows: return None
    r = rows[0]; bits = [r["title"] + (f" ({r['year']})" if r.get("year") else "")]
    if r.get("director"): bits.append(f"Directed by {r['director']}.")
    if r.get("genres"): bits.append(r["genres"] + ".")
    if r.get("runtime_min"): bits.append(f"{r['runtime_min']} min.")
    if r.get("blurb"): bits.append(r["blurb"][:400])
    bits.append("It is verified playable." if r.get("verified") else "It has not passed the playback check yet.")
    return _res(" ".join(bits), _item_btns(rows))

# ---------------------------------------------------------------- router ------------------------------------------------
def capabilities():
    return [{"name": t["name"], "desc": t["desc"], "examples": t["examples"]} for t in TOOLS]

def route(cfg: dict, text: str) -> dict:
    raw = (text or "").strip(); t = re.sub(r"\s+", " ", raw).strip(" .!")
    if not t: return _res("Say something like 'find me 1940s film noir' or 'help'.")
    t_l = t.lower()
    if t_l.startswith("dreamy"): t = t[6:].lstrip(" ,:"); t_l = t.lower()
    for tool_ in TOOLS:
        for pat in tool_["patterns"]:
            m = pat.match(t) or pat.match(t_l)
            if m:
                try:
                    r = tool_["fn"](cfg, t, m)
                    if r is not None: r["tool"] = tool_["name"]; log.info("DREAMY tool=%s text=%r", tool_["name"], t[:80]); return r
                except Exception as e:
                    log.exception("dreamy tool %s failed: %s", tool_["name"], e); return _res(f"That tool hit an error ({str(e)[:80]}).", [], [])
                break
    # fall through: v1 find/question agent (library search + TMDB people + archive.org discovery)
    try:
        r = agent.ask(cfg, t); r.setdefault("actions", []); r["tool"] = "find"
        for b in r.get("buttons", []):
            if b.get("uid"):
                row = _q("SELECT poster, poster_local, year, source FROM items WHERE uid=?", (b["uid"],))
                if row: b.setdefault("poster", row[0]["poster"] or row[0]["poster_local"] or ""); b.setdefault("year", row[0]["year"]); b.setdefault("source", row[0]["source"])
        return r
    except Exception as e:
        log.exception("dreamy v1 agent failed: %s", e); return _res(f"I could not work that out ({str(e)[:80]}). Say 'help' to see what I can do.")
