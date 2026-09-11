# DreamReels 2 — "Dreamy" release (alpha)

A forkable, 10-foot home media player for a Linux box under your TV. Python 3.12+, PySide6/QML,
libmpv. Dreamy, the mascot, walks you through setup once; after that the machine grows its own
library every night and never hands you a button that does not play.

    git clone https://github.com/indicaindependent/dreamreels && cd dreamreels && ./install.sh
    python3 -m dreamreels wizard          # pick sources, look, user  -> writes ~/.config/dreamreels/plan.json
    sudo bin/dreamreels-apply --dry-run   # shows exactly what the root half would change
    sudo bin/dreamreels-apply --reboot    # user, mounts, yt-dlp, autologin, service

## What it plays
| lane | where it comes from | how it is verified |
|---|---|---|
| **Public Domain** | archive.org feature films, picked by decade / genre / people | every file must decode 48 frames in mpv before it is marked playable |
| **Channel 83** | public-domain anthology TV (Twilight Zone, Outer Limits 1963-65 *and* 1995-2002, Suspense, One Step Beyond, Thriller, Hitchcock Presents, Lights Out) | same decode proof, pre-mapped episode lists |
| **Toon Town** | 15 classic cartoon series / 334 shorts (Fleischer, Iwerks, Van Beuren, WB, Lantz, UPA…) | same |
| **NAS** | your own SMB shares, discovered and mounted by the wizard, movies / TV / music | local file present |
| **YouTube** | channels you paste as `@handle` links, ad-free through mpv + yt-dlp | 24-frame decode + duration match |

Posters, blurbs, directors and cast come from TMDB (bring your own free Read Access Token).

## Dreamy, the agent
Press **D** (or the Dreamy button). Ask in plain words:

* *find me Orson Welles movies from the 1940s* → PLAY buttons for verified copies, CHECK buttons for candidates
* *was Orson Welles in any movies from the 1940s?* → the answer from TMDB, then *Find playable copies*
* *find me the latest video showing … on Air Force One* → newest YouTube hits, each CHECK-first

Dreamy is deterministic: an intent parser, five tools (library search, TMDB facts, archive.org discover,
yt-dlp search, decode-verify) and templated answers. There is no language model between text from the
internet and an action, so nothing on the internet can instruct your player. A button is labelled **Play**
only after the file has actually decoded on your machine; until then it says **Check**.

## Layout
```
dreamreels/
  core/       config (TOML), sqlite schema + migrations, paths, logging, tool discovery
  wizard/     Dreamy's setup walkthrough (QML) + plan.json writer
  player/     QML shell, libmpv widget, gamepad, resume/favourites
  dreamy/     the agent (agent.py = tools + parser, backend.py = Qt face, mascot.py = SVG poses)
  sources/    archive_org (discover, candidates, decode proof), nas, youtube
  metadata/   tmdb client with on-disk cache
  grower.py   discover -> map -> verify jobs (cron-friendly, <=1 req/s to archive.org)
  doctor.py   measures the machine; every check names its instrument and has a control
  apply.py    the root half: user, fstab, yt-dlp, GDM autologin, systemd user units
  migrate/    importer for DreamReel v1 libraries
  badge/      the IIM "Created with Creative Clarity" badge (unique per install)
tests/        pytest, no Qt required
```

## Commands
| command | does |
|---|---|
| `python3 -m dreamreels player` | run the player (`--windowed`, `--screenshot out.png --after ms`) |
| `python3 -m dreamreels wizard` | setup walkthrough |
| `python3 -m dreamreels grow --discover --limit 40` / `--work 20` / `--status` | grow / verify / inspect the library |
| `python3 -m dreamreels dreamy "…"` | ask Dreamy from a terminal (JSON out) |
| `python3 -m dreamreels doctor` | measure tools, network, token, mounts, library, a live YouTube decode |
| `python3 -m dreamreels verify-url URL` | decode-proof one URL |
| `python3 -m dreamreels import-v1 [--db PATH]` | import a DreamReel v1 library |
| `sudo bin/dreamreels-apply [--dry-run] [--reboot]` | root half of setup |

## Design rules this codebase keeps
* **Verified means decoded.** Not a HEAD, not a 206 on two kilobytes, not a resolve. Frames.
* **Measure, never assume.** `doctor` checks include a negative control (a bogus host that must fail).
* **Newest yt-dlp wins.** `core/tools.py` runs `--version` on every copy it can find and uses the newest; a six-month-old yt-dlp fails YouTube with a misleading error.
* **No emoji in the UI.** Icons are inline SVG; third-party titles are stripped before display.
* **Untrusted text is data.** archive.org, YouTube and TMDB content is displayed, never executed or fed to a model.

See [docs/FORKING.md](docs/FORKING.md) to make it yours, and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the data model.

This product uses the TMDB API but is not endorsed or certified by TMDB. Licence: MIT.
