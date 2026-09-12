#!/usr/bin/env bash
# DreamReels installer - Ubuntu/Debian. Idempotent. Creates a venv, installs deps, runs doctor, then Dreamy setup.
set -euo pipefail
cd "$(dirname "$0")"
APT_PKGS="python3 python3-venv python3-pip mpv libmpv2 ffmpeg cifs-utils smbclient fonts-inter fonts-ibm-plex"
if command -v apt-get >/dev/null; then
  echo "[1/4] system packages (sudo)"; sudo apt-get update -qq; sudo apt-get install -y -qq $APT_PKGS || sudo apt-get install -y -qq ${APT_PKGS/libmpv2/libmpv-dev}
fi
echo "[2/4] python venv"; [ -d .venv ] || python3 -m venv .venv --system-site-packages
. .venv/bin/activate; pip install -q -U pip; pip install -q -e ".[gamepad,smb]"
echo "[3/4] doctor"; python -m dreamreels doctor || true
echo "[3b/4] passwordless sudo for the root half of setup (only this one command)"
printf '%s ALL=(root) NOPASSWD: %s/bin/dreamreels-apply *\n' "$USER" "$(pwd)" | sudo tee /etc/sudoers.d/dreamreels >/dev/null; sudo chmod 440 /etc/sudoers.d/dreamreels; sudo visudo -cf /etc/sudoers.d/dreamreels >/dev/null || { sudo rm -f /etc/sudoers.d/dreamreels; echo "sudoers entry rejected - Build will ask you to run dreamreels-apply yourself"; }
echo "[4/4] setup"; python -m dreamreels migrate-db; python -m dreamreels wizard
