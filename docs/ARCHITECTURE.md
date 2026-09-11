# Architecture

One sqlite file (`~/.local/share/dreamreels/dreamreels.db`), schema in `core/db.py`, migrated on start.

| table | purpose |
|---|---|
| `items` | one row per playable thing: `uid` = `source:ext_id`; `kind` movie/episode/short/track/video; TMDB fields; `stream_url` / `path`; `verified` 0/1 + `verified_at` + `verify_note` (what proved it); `strict_pd`; `blocked` |
| `people` / `item_people` | TMDB cast + directors for Dreamy's person search |
| `shows` / `episodes` | Channel 83 + NAS TV |
| `state` | resume position, favourite, play count |
| `jobs` | grower queue: `map` (TMDB), `verify` (decode), retried 3x with backoff |
| `http_cache` | TMDB + archive.org responses, 30 days |

Flow: **wizard** writes config + `plan.json` → **apply** (root) makes the machine → **grower** discovers on
archive.org, maps on TMDB, verifies by decoding → **player** shows only `verified=1` in rails → **Dreamy**
searches the same table, and can enqueue new candidates as CHECK buttons.

The decode proof (`sources/archive_org.verify_decode`): `mpv --vo=null --ao=null --frames=48` must exit 0 and
log `VO: [null] WxH`; duration from ffprobe (or `yt-dlp --print duration` for YouTube). Anything weaker
has produced false positives in this project's history and is not accepted.
