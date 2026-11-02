"""The Build step. Pure Python, no Qt: the wizard runs it in a thread, `python3 -m dreamreels build` runs it
from a terminal. Every line it logs is a measured fact about this machine, not a hope."""
from __future__ import annotations
import json, os, shutil, subprocess, sys, time
from pathlib import Path
from ..core import config as cfgmod, db as dbmod
from ..core.paths import PLAN_FILE, STATE_DIR, LOG_DIR, IS_WINDOWS, self_cmd, detach_kwargs

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
    if IS_WINDOWS:
        try:
            plan = json.loads(PLAN_FILE.read_text()) if plan_ok else {}
            from .win_shortcuts import install as _sc
            made = _sc(start_at_login=bool(plan.get("start_at_login")))
            step("Shortcuts", bool(made), ", ".join(str(m) for m in made)[:200] or "none created")
        except Exception as e: step("Shortcuts", False, str(e)[:160])
    elif plan_ok and APPLY.exists():
        rc, txt = _run(["sudo", "-n", str(APPLY), "--no-reboot", "--plan", str(PLAN_FILE)], cwd=str(APPLY.parent.parent), timeout=900)
        if rc == 0: step("System setup (root)", True, "user, mounts, yt-dlp, autologin, service written")
        elif "sudo" in txt.lower() and ("password" in txt.lower() or "not allowed" in txt.lower() or "may not run" in txt.lower()):
            step("System setup (root)", UNIT.exists(), "no passwordless sudo for this user" + (" - service already installed, continuing" if UNIT.exists() else f" - run: sudo {APPLY} --reboot"))
        elif UNIT.exists(): step("System setup (root)", True, "skipped - this user has no sudo, but the service is already installed (" + (txt.strip().splitlines()[-1][:80] if txt.strip() else f"rc={rc}") + ")")
        else: step("System setup (root)", False, txt.strip().splitlines()[-1][:160] if txt.strip() else f"rc={rc}")
    else: step("System setup (root)", False, "plan.json missing" if not plan_ok else "bin/dreamreels-apply missing")
    if IS_WINDOWS: pass   # TV audio below is PipeWire-only; Windows uses its default output device
    # 2b) TV audio: pick the connected HDMI output for this session (WirePlumber persists it)
    if not IS_WINDOWS:
        try:
            from ..player import audio as _audio; ar = _audio.ensure_tv_audio(); step("TV audio (HDMI)", ar["ok"], ar["note"][:150])
        except Exception as e: step("TV audio (HDMI)", False, str(e)[:120])
    # 3) grower in the background: discover for the chosen decades/genres, then work the verify queue
    LOG_DIR.mkdir(parents=True, exist_ok=True); glog = open(LOG_DIR / "grow-build.log", "ab")
    args = self_cmd("grow", "--work", "400") + (["--discover", "--limit", "60"] if src.get("publicdomain") else [])
    p = subprocess.Popen(args, stdout=glog, stderr=glog, cwd=str(APPLY.parent.parent), **detach_kwargs())
    time.sleep(1.5); alive = p.poll() is None; step("Library grower started", alive, f"pid {p.pid}, log {LOG_DIR / 'grow-build.log'}; titles appear as each one decodes")
    # 4) the player
    if launch_player:
        if not IS_WINDOWS and UNIT.exists() and shutil.which("systemctl"):
            rc, txt = _run(["systemctl", "--user", "daemon-reload"]); rc, txt = _run(["systemctl", "--user", "restart", "dreamreels.service"]); time.sleep(4)
            rc2, st = _run(["systemctl", "--user", "is-active", "dreamreels.service"]); step("Player service", st.strip() == "active", f"dreamreels.service {st.strip()}" + ("" if st.strip() == "active" else f"; {txt.strip()[:120]}"))
        else:
            q = subprocess.Popen(self_cmd("player"), cwd=str(APPLY.parent.parent), **detach_kwargs(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(3)
            step("Player launched", q.poll() is None, f"pid {q.pid} (no service installed yet)")
    return out
