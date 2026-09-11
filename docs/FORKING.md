# Forking DreamReels

1. Fork on GitHub, clone, `./install.sh` (Debian/Ubuntu: python3-pyside6, mpv, libmpv, ffmpeg, yt-dlp, node).
2. `python3 -m dreamreels wizard`. Pick 1-3 sources. Each source has its own short walkthrough.
   * Public Domain: decades, genres, people, and whether STRICT-PD is on (licence-tagged or pre-1931 only).
   * NAS: the wizard scans your LAN for SMB hosts, lists shares, you tick folders (music included).
   * YouTube: paste `@handle` links. yt-dlp needs a JavaScript runtime (node or deno).
3. Pick a skin (midnight / paper / neon) — themes live in `dreamreels/ui/theme.py`, one dict each.
4. Name the system user (default `dreamreels`), password optional.
5. `sudo bin/dreamreels-apply --dry-run` — read it. Then `--reboot`.

## Making it yours
* **Branding**: `dreamreels/__init__.py` holds the version, GitHub URL and badge text. The badge is generated
  per install (`badge/iim.py`) and links to *your* fork URL once you change `GITHUB_URL`.
* **Themes**: add a dict to `theme.py`; the wizard offers every theme it finds.
* **A new source**: implement `discover()` / `candidates()` / `verify()` in `sources/`, add a lane to
  `config.default()` and a card in `wizard/qml/`. The grower and Dreamy pick it up through the `items` table.
* **Dreamy vocabulary**: `dreamy/agent.py` — `GENRES`, `SOURCES`, `STOP` and `parse()`.

## Things that will bite you
* yt-dlp rots in weeks. `doctor` warns past 60 days; `apply` refreshes it; `tools.ytdlp_path()` always
  uses the newest copy on the machine.
* A 206 from a range request is not a playable stream. Use `verify-url`.
* mpv wants `LC_NUMERIC=C` under systemd (the unit sets it).
* `mod_log`-style silent write failures: run `doctor` after any schema change; it prints job counts.
