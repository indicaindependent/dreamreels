"""The Build step. Pure Python, no Qt: the wizard runs it in a thread, `python3 -m dreamreels build` runs it
from a terminal. Every line it logs is a measured fact about this machine, not a hope."""
from __future__ import annotations
import os, shutil, subprocess, sys, time
from pathlib import Path
from ..core import config as cfgmod, db as dbmod
from ..core.paths import PLAN_FILE, STATE_DIR, LOG_DIR

APPLY = Path(__file__).resolve().parent.parent.parent / "bin" / "dreamreels-apply"
UNIT = Path.home() / ".config/systemd/user/dreamreels.service"

def _run(cmd, timeout=600, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw); return r.returncode, (r.stdout or "") + (r.stderr or "")

def run_build(cfg: dict, log=print, launch_player: bool = True) -> dict:
    out = {"ok": True, "steps": []}
    def step(name, ok, note=""): out["steps"].append((name, ok, note)); log(("OK   " if ok else "FAIL ") + name + (f"  {note}" if note else "")); out["ok"] = out["ok"] and ok
    dbmod.migrate(); log(f"config {cfgmod.CONFIG_FILE}")
    src = cfg.get("sources", {})
    # 1) pre-mapped lanes
    if src.get("chan83") or src.get("toontown"):
        from ..sources import lanes_seed
        c = dbmod.connect()
        if src.get("chan83"): r = lanes_seed.install_chan83(c); step("Channel 83 seeded", r["episodes"] > 0, f"{r['shows']} shows, {r['episodes']} episodes queued for decode check")
        if src.get("toontown"): r = lanes_seed.install_toontown(c); step("Toon Town seeded", r["shorts"] > 0, f"{r['series']} series, {r['shorts']} shorts queued for decode check")
        c.close()
    # 2) root half (user, mounts, yt-dlp, autologin, service). Needs sudo without a password prompt; install.sh grants it.
    plan_ok = PLAN_FILE.exists()
    if plan_ok and APPLY.exists():
        rc, txt = _run(["sudo", "-n", str(APPLY), "--no-reboot", "--plan", str(PLAN_FILE)], cwd=str(APPLY.parent.parent), timeout=900)
        if rc == 0: step("System setup (root)", True, "user, mounts, yt-dlp, autologin, service written")
        elif "sudo" in txt.lower() and ("password" in txt.lower() or "not allowed" in txt.lower() or "may not run" in txt.lower()):
            step("System setup (root)", UNIT.exists(), "no passwordless sudo for this user" + (" - service already installed, continuing" if UNIT.exists() else f" - run: sudo {APPLY} --reboot"))
        elif UNIT.exists(): step("System setup (root)", True, "skipped - this user has no sudo, but the service is already installed (" + (txt.strip().splitlines()[-1][:80] if txt.strip() else f"rc={rc}") + ")")
        else: step("System setup (root)", False, txt.strip().splitlines()[-1][:160] if txt.strip() else f"rc={rc}")
    else: step("System setup (root)", False, "plan.json missing" if not plan_ok else "bin/dreamreels-apply missing")
    # 3) grower in the background: discover for the chosen decades/genres, then work the verify queue
    LOG_DIR.mkdir(parents=True, exist_ok=True); glog = open(LOG_DIR / "grow-build.log", "ab")
    args = [sys.executable, "-m", "dreamreels", "grow", "--work", "400"] + (["--discover", "--limit", "60"] if src.get("publicdomain") else [])
    p = subprocess.Popen(args, stdout=glog, stderr=glog, cwd=str(APPLY.parent.parent), start_new_session=True)
    time.sleep(1.5); alive = p.poll() is None; step("Library grower started", alive, f"pid {p.pid}, log {LOG_DIR / 'grow-build.log'}; titles appear as each one decodes")
    # 4) the player
    if launch_player:
        if UNIT.exists() and shutil.which("systemctl"):
            rc, txt = _run(["systemctl", "--user", "daemon-reload"]); rc, txt = _run(["systemctl", "--user", "restart", "dreamreels.service"]); time.sleep(4)
            rc2, st = _run(["systemctl", "--user", "is-active", "dreamreels.service"]); step("Player service", st.strip() == "active", f"dreamreels.service {st.strip()}" + ("" if st.strip() == "active" else f"; {txt.strip()[:120]}"))
        else:
            q = subprocess.Popen([sys.executable, "-m", "dreamreels", "player"], cwd=str(APPLY.parent.parent), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(3)
            step("Player launched", q.poll() is None, f"pid {q.pid} (no service installed yet)")
    return out
