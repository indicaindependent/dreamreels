"""DreamReels v2.2 Phase M (Oct 13 2026): title normalizer + confidence matcher for archive.org -> TMDB.
Pure functions, no I/O. The grower's mapper calls `variants()` to get search strings and `pick()` to choose a hit.

Measured defect it fixes: 1,401 of 3,848 verified PD titles carried junk tokens ("Satan's Cheerleaders ( 1977)",
"The Ten Commandments / Blu-ray / x264 / MKV / 720p / Commentary", "Beyond The Valley Of The Dolls(1970) BD RIP"),
the old matcher needed an exact normalized title and a year within 2 (fallback 3), had no article handling and no
tolerance for archive.org's wrong years ("Horror Express" listed 1976, TMDB 1972). Hit rate was 58%."""
from __future__ import annotations
import re, difflib

JUNK = re.compile(r"""\b(?:
 720p|1080p|2160p|480p|576p|4k|uhd|hd|sd|x264|x265|h\.?264|h\.?265|hevc|avc|aac|ac3|dts|
 blu-?ray|bd-?rip|bdrip|bd\s?rip|dvd-?rip|dvdrip|dvd|vhs|vhs-?rip|web-?rip|webrip|hdtv|hdrip|
 mkv|mp4|avi|m4v|mpeg|mpg|xvid|divx|
 uncut|unrated|remastered|restored|colorized|colourized|upscaled|widescreen|fullscreen|
 public\s+domain|full\s+(?:movie|film|length)|feature\s+film|complete(?:\s+&\s+clearer)?|
 english|eng|hard\s*sub(?:s|bed)?|subtitled|subtitles|subs|dubbed|commentary|
 rip|copy|transfer|upload|version|edition|
 ia\s*mp4|512kb
)\b""", re.I | re.X)
TRAILER = re.compile(r"\b(trailer|teaser|preview|promo|clip|excerpt|sample)\b", re.I)
SERIES = re.compile(r"\b(complete\s+series|season\s*\d+|series\s*\d+|s\d{1,2}e\d{1,3}|episodes?|collection|compilation|cartoons?|shorts?)\b", re.I)
YEAR = re.compile(r"(?<!\d)(18[89]\d|19\d\d|20[0-2]\d)(?!\d)")
ART = re.compile(r"^(the|a|an|le|la|les|el|los|las|il|lo|der|die|das|un|une|una|uno)\s+", re.I)

def _norm(s: str) -> str:
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return ART.sub("", s.strip()).strip()

def clean(raw: str) -> dict:
    """Return {'title', 'year', 'flags'} from an archive.org title. year is a hint pulled from the title (may be None)."""
    s = raw or ""; flags = set()
    if TRAILER.search(s): flags.add("trailer")
    if SERIES.search(s): flags.add("series")
    years = [int(y) for y in YEAR.findall(s)]
    yr = years[0] if years else None
    # bracketed/parenthesised tails: "(1977)", "[1982]", "( 1977)", "(complete & clearer)"
    s = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", " ", s)
    # dotted / underscored release names -> spaces when the title has few real spaces
    if s.count(".") + s.count("_") >= 2 and s.count(" ") <= 2: s = re.sub(r"[._]+", " ", s)
    # "AKA" splits: keep the first name
    s = re.split(r"\b(?:aka|a\.k\.a\.)\b", s, flags=re.I)[0]
    # strip the year token itself and everything after a " / " or " | " separator (release notes)
    s = re.split(r"\s+[/|]\s+", s)[0]
    s = YEAR.sub(" ", s)
    s = JUNK.sub(" ", s)
    # leading "Title - subtitle"? keep both segments but also offer the first as a variant (see variants())
    s = re.sub(r"\s*[-–—]\s*$", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -–—:;,.")
    return {"title": s, "year": yr, "flags": flags}

def variants(raw: str, year: int | None = None) -> list[tuple[str, int | None]]:
    """Ordered (query, year) pairs to try against /search/movie. Deduplicated, most specific first."""
    c = clean(raw); t = c["title"]; y = year or c["year"]
    out: list[tuple[str, int | None]] = []
    def add(q, yy):
        q = re.sub(r"\s{2,}", " ", (q or "").strip())
        if len(q) >= 2 and (q, yy) not in out: out.append((q, yy))
    add(t, y)
    if y: add(t, None)
    # "Main Title - Subtitle" and "Main Title: Subtitle" -> main title alone
    for sep in (" - ", " – ", ": ", " — "):
        if sep in t: add(t.split(sep)[0], y); add(t.split(sep)[0], None)
    # possessive / quote clean: Charlie Chaplin's "Tillies Punctured Romance" -> Tillies Punctured Romance
    q = re.findall(r"[\"“”']([^\"“”']{3,})[\"“”']", raw or "")
    for qq in q: add(qq, y)
    # the raw title as the user typed it, last resort
    add(raw, y)
    return out[:6]

def score(result: dict, query: str, year: int | None) -> float:
    """0..1 confidence that a TMDB /search/movie result is the archive.org item."""
    rt = result.get("title") or ""; ot = result.get("original_title") or ""
    nq = _norm(query); sim = max(difflib.SequenceMatcher(None, nq, _norm(rt)).ratio(), difflib.SequenceMatcher(None, nq, _norm(ot)).ratio())
    exact = (nq == _norm(rt)) or (nq == _norm(ot))
    ry = int((result.get("release_date") or "0000")[:4] or 0)
    s = 0.62 * sim + (0.15 if exact else 0.0)
    if year and ry:
        dy = abs(ry - year)
        s += 0.23 if dy == 0 else 0.17 if dy == 1 else 0.08 if dy <= 3 else -0.05 if dy <= 8 else -0.3
    elif not year: s += 0.08
    if result.get("video"): s -= 0.1          # TMDB "video" = direct-to-video/bootleg entries, rarely the item
    if result.get("adult"): s -= 0.5
    return max(0.0, min(1.0, s))

def pick(results: list[dict], query: str, year: int | None, threshold: float = 0.80) -> tuple[dict | None, float, str]:
    """Choose one result or None. Returns (result, confidence, reason)."""
    if not results: return None, 0.0, "no results"
    scored = sorted(((score(r, query, year), r) for r in results), key=lambda x: -x[0])
    best, r = scored[0]
    # the "archive.org year is wrong" case: exactly one exact-title match within 8 years -> accept at reduced confidence
    exact = [rr for rr in results if _norm(rr.get("title")) == _norm(query) or _norm(rr.get("original_title")) == _norm(query)]
    if best < threshold and len(exact) == 1 and year:
        ry = int((exact[0].get("release_date") or "0000")[:4] or 0)
        if ry and abs(ry - year) <= 8: return exact[0], 0.80, f"unique exact title, year off by {abs(ry-year)}"
    if best >= threshold:
        # ambiguity guard: two candidates within 0.05 of each other and both >= threshold -> prefer the one closer in year, else refuse
        if len(scored) > 1 and scored[1][0] >= threshold and scored[0][0] - scored[1][0] < 0.05:
            r2 = scored[1][1]
            y1 = int((r.get("release_date") or "0000")[:4] or 0); y2 = int((r2.get("release_date") or "0000")[:4] or 0)
            if year and y1 and y2 and abs(y1 - year) != abs(y2 - year):
                return (r if abs(y1 - year) < abs(y2 - year) else r2), best, "tie broken by year"
            return None, best, "ambiguous: two near-equal candidates"
        return r, best, "score"
    return None, best, f"below threshold ({best:.2f})"
