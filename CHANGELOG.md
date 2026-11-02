# Changelog

## 2.1.0 (November 2026)
* Small "Created with Creative Clarity" credit pill (Indica Independent Media) replaces the large corner badge.
* New reel logo and two-tone wordmark.
* A to Z jump bar when a grid is sorted A to Z.
* "Recently played" sort, plus a Recently played row on the home screen.
* Channel 83 now shows only TV first aired before 1970 (`CHAN83_MAX_YEAR`). Later episodes, including 1990s
  files mislabelled as 1960s, are hidden. The 1980s/1990s add-on seed was removed from the public package.
* Windows support: single-file `DreamReels.exe` built on GitHub Actions; Windows settings folders; the
  System user setup step becomes Start menu / Desktop shortcuts with optional start at sign-in; NAS step
  hidden on Windows; the player starts without video (with a log line) if libmpv is missing, instead of crashing.
* Fix: a failed TV-audio check at start-up could crash the player (wrong logger name).
* New `tools/privacy_audit.py` for forkers.

## 2.0 (October 2026)
* Paged grids with no caps, "See all" opens the full grid, exact Back navigation, sort chips.
