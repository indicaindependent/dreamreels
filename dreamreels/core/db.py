"""SQLite schema v2 with forward-only migrations. WAL mode."""
from __future__ import annotations
import sqlite3, time
from .paths import DB_FILE, ensure_dirs

SCHEMA = [
"""
CREATE TABLE IF NOT EXISTS items(
  uid TEXT PRIMARY KEY,            -- source:ext_id
  source TEXT NOT NULL,            -- pd|chan83|toontown|nas|youtube|music
  kind TEXT NOT NULL,              -- movie|episode|short|video|track
  ext_id TEXT, title TEXT NOT NULL, title_raw TEXT, year INTEGER,
  tmdb_id INTEGER, tmdb_type TEXT, imdb_id TEXT,
  show_uid TEXT, season INTEGER, episode INTEGER,
  blurb TEXT, director TEXT, runtime_min INTEGER, genres TEXT, decade INTEGER,
  poster TEXT, backdrop TEXT, poster_local TEXT, backdrop_local TEXT,
  path TEXT, stream_url TEXT, ia_id TEXT, ia_file TEXT,
  strict_pd INTEGER DEFAULT 0, blocked INTEGER DEFAULT 0,
  verified INTEGER DEFAULT 0, verified_at REAL, verify_note TEXT,
  downloads INTEGER, added REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_items_source ON items(source, kind);
CREATE INDEX IF NOT EXISTS ix_items_show ON items(show_uid, season, episode);
CREATE INDEX IF NOT EXISTS ix_items_decade ON items(decade);
CREATE TABLE IF NOT EXISTS shows(
  uid TEXT PRIMARY KEY, source TEXT, title TEXT, tmdb_id INTEGER, years TEXT,
  poster TEXT, poster_local TEXT, blurb TEXT, studio TEXT, era_group TEXT, added REAL
);
CREATE TABLE IF NOT EXISTS people(
  tmdb_id INTEGER PRIMARY KEY, name TEXT, role TEXT, portrait TEXT, portrait_local TEXT, selected INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS item_people(item_uid TEXT, tmdb_id INTEGER, job TEXT, PRIMARY KEY(item_uid, tmdb_id, job));
CREATE TABLE IF NOT EXISTS state(
  uid TEXT PRIMARY KEY, resume_sec REAL, duration_sec REAL, favorite INTEGER DEFAULT 0,
  last_played REAL, play_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, payload TEXT, status TEXT DEFAULT 'pending',
  attempts INTEGER DEFAULT 0, not_before REAL, created REAL, updated REAL, note TEXT
);
CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs(status, not_before);
CREATE TABLE IF NOT EXISTS http_cache(key TEXT PRIMARY KEY, etag TEXT, body BLOB, fetched REAL);
CREATE TABLE IF NOT EXISTS yt_channels(channel_id TEXT PRIMARY KEY, handle TEXT, title TEXT, avatar TEXT, added REAL, last_poll REAL);
CREATE TABLE IF NOT EXISTS provenance(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, action TEXT, target TEXT, origin TEXT, note TEXT
);
""",
]

def connect(path=None) -> sqlite3.Connection:
    ensure_dirs()
    c = sqlite3.connect(str(path or DB_FILE), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def migrate(c: sqlite3.Connection | None = None) -> int:
    own = c is None
    c = c or connect()
    c.execute("CREATE TABLE IF NOT EXISTS schema_version(v INTEGER NOT NULL)")
    cur = c.execute("SELECT MAX(v) FROM schema_version").fetchone()[0] or 0
    for i, sql in enumerate(SCHEMA, start=1):
        if i > cur:
            c.executescript(sql)
            c.execute("INSERT INTO schema_version(v) VALUES(?)", (i,))
            c.commit()
    v = c.execute("SELECT MAX(v) FROM schema_version").fetchone()[0]
    if own:
        c.close()
    return v

def provenance(c: sqlite3.Connection, action: str, target: str, origin: str, note: str = "") -> None:
    c.execute("INSERT INTO provenance(ts,action,target,origin,note) VALUES(?,?,?,?,?)", (time.time(), action, target, origin, note))
