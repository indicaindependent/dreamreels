#!/usr/bin/env python3
"""reset_Dreamreels.py - put DreamReels back to a fresh first-run and re-run the Dreamy setup wizard.

    sudo python3 /home/dreamreels/reset_Dreamreels.py            # keep the library, redo setup
    sudo python3 /home/dreamreels/reset_Dreamreels.py --wipe-library   # also delete the database + poster cache
    sudo python3 /home/dreamreels/reset_Dreamreels.py --dry-run  # show what would happen, change nothing

What it does, in order (every step prints OK/FAIL and is measured, not assumed):
  1. re-execs itself as the app user if you ran it as someone else (sudo)
  2. stops the kiosk player and any running grower
  3. backs up config.toml + plan.json to ~/.config/dreamreels/backups/<timestamp>/
  4. removes config.toml + plan.json  -> setup_complete is false -> the app opens in the wizard
     (--wipe-library also removes the SQLite database and the poster cache; the NAS mount, the
      system user and GDM autologin are left alone - the wizard's Build step reuses them)
  5. restarts the kiosk service, which now shows the wizard on the TV if this user owns the screen;
     otherwise tells you to log out so the autologin session comes back
"""
from __future__ import annotations
import argparse, os, pwd, shutil, subprocess, sys, time
from pathlib import Path

APP_USER = os.environ.get("DREAMREELS_USER", "dreamreels")

def sh(cmd, check=False):
    r = subprocess.run(cmd, text=True, capture_output=True)
    if check and r.returncode: raise SystemExit(f"FAIL {' '.join(cmd)}\n{r.stderr.strip()}")
    return r

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wipe-library", action="store_true", help="also delete the database and poster cache")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    a = ap.parse_args()

    me = pwd.getpwuid(os.getuid()).pw_name
    if me != APP_USER:
        try: pw = pwd.getpwnam(APP_USER)
        except KeyError: print(f"FAIL: user {APP_USER} does not exist - nothing to reset"); return 2
        env = ["env", f"XDG_RUNTIME_DIR=/run/user/{pw.pw_uid}", f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{pw.pw_uid}/bus", f"HOME={pw.pw_dir}"]
        print(f"re-running as {APP_USER} ...")
        os.execvp("sudo", ["sudo", "-u", APP_USER] + env + [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])

    home = Path.home()
    cfg_dir = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "dreamreels"
    data_dir = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "dreamreels"
    cache_dir = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / "dreamreels"
    targets = [cfg_dir / "config.toml", cfg_dir / "plan.json"]
    if a.wipe_library: targets += [data_dir / "dreamreels.db", data_dir / "dreamreels.db-wal", data_dir / "dreamreels.db-shm", cache_dir / "posters"]
    present = [t for t in targets if t.exists()]

    print(f"DreamReels reset as {me}")
    print(f"  will stop     : dreamreels.service (kiosk player) + any 'dreamreels grow' process")
    print(f"  will back up  : {', '.join(str(t) for t in targets[:2] if t.exists()) or 'nothing (no config present)'}")
    print(f"  will remove   : {', '.join(str(t) for t in present) or 'nothing'}")
    print(f"  will keep     : system user, GDM autologin, NAS mount" + ("" if a.wipe_library else ", the library database and poster cache"))
    if a.dry_run: print("dry run - nothing changed"); return 0
    if not a.yes and sys.stdin.isatty():
        if input("type RESET to continue: ").strip() != "RESET": print("aborted"); return 1

    # 2. stop the player and the grower
    sh(["systemctl", "--user", "stop", "dreamreels.service"])
    sh(["pkill", "-u", APP_USER, "-f", "dreamreels grow"])
    time.sleep(1)
    active = sh(["systemctl", "--user", "is-active", "dreamreels.service"]).stdout.strip()
    print(f"  {'OK  ' if active != 'active' else 'FAIL'} player stopped ({active})")

    # 3. back up, 4. remove
    stamp = time.strftime("%Y%m%d-%H%M%S"); bdir = cfg_dir / "backups" / stamp
    if any(t.exists() for t in targets[:2]):
        bdir.mkdir(parents=True, exist_ok=True)
        for t in targets[:2]:
            if t.exists(): shutil.copy2(t, bdir / t.name)
        print(f"  OK   backed up to {bdir}")
    for t in present:
        if t.is_dir(): shutil.rmtree(t, ignore_errors=True)
        else: t.unlink(missing_ok=True)
    left = [t for t in present if t.exists()]
    print(f"  {'OK  ' if not left else 'FAIL'} removed {len(present) - len(left)}/{len(present)}" + (f" - still present: {left}" if left else ""))

    # read the effect back: the app must now report setup incomplete
    chk = sh([sys.executable, "-m", "dreamreels", "config"], check=False)
    fresh = "setup_complete = false" in chk.stdout.replace('"', "").lower()
    print(f"  {'OK  ' if fresh else 'FAIL'} app reports setup_complete=false" + ("" if fresh else f" ({chk.stderr.strip()[:120]})"))

    # 5. bring the wizard up
    seat = sh(["loginctl", "list-sessions", "--no-legend"]).stdout
    owns_screen = any(APP_USER in ln and "seat0" in ln for ln in seat.splitlines())
    if owns_screen:
        sh(["systemctl", "--user", "restart", "dreamreels.service"]); time.sleep(4)
        st = sh(["systemctl", "--user", "is-active", "dreamreels.service"]).stdout.strip()
        print(f"  {'OK  ' if st == 'active' else 'FAIL'} kiosk restarted -> Dreamy setup wizard is on the screen ({st})")
    else:
        print(f"  --   {APP_USER} does not own the screen right now, so the wizard cannot be shown from here.")
        print(f"       Log out of the current desktop (or reboot): GDM auto-logs in {APP_USER} and the wizard opens.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
