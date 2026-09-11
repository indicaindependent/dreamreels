"""dreamreels-apply: the ROOT half of setup. Reads the wizard's plan.json and performs, idempotently:
  1. system user (audio/video/input/render groups), optional password
  2. /etc/dreamreels/smb-creds (0600) + /etc/fstab cifs automounts for the picked shares
  3. yt-dlp refresh (latest release binary -> /usr/local/bin/yt-dlp) when the YouTube lane is on
  4. GDM autologin (mirrors the proven DreamReel v1 mechanism: gdm3 custom.conf + a systemd USER unit)
  5. systemd user unit dreamreels.service, enabled for graphical-session.target
  6. optional reboot
--dry-run prints every command and file it WOULD write and changes nothing. Every step re-reads the
system afterwards and reports what it measured, not what it intended."""
from __future__ import annotations
import argparse, json, os, pwd, grp, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

ETC = Path("/etc/dreamreels"); FSTAB = Path("/etc/fstab"); GDM = Path("/etc/gdm3/custom.conf")
UNIT = """[Unit]
Description=DreamReels player (kiosk)
PartOf=graphical-session.target
After=graphical-session.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
Environment=QT_QPA_PLATFORM=wayland
Environment=WAYLAND_DISPLAY=wayland-0
Environment=LC_NUMERIC=C
ExecStartPre=/bin/sleep 3
ExecStart=/usr/bin/python3 -m dreamreels player
WorkingDirectory=/opt/dreamreels
StandardOutput=append:%h/.local/state/dreamreels/player.log
StandardError=append:%h/.local/state/dreamreels/player.log
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical-session.target
"""
GROW_TIMER = """[Unit]
Description=DreamReels library grower (nightly)

[Timer]
OnCalendar=*-*-* 03:00:00
RandomizedDelaySec=30m
Persistent=true

[Install]
WantedBy=timers.target
"""
GROW_SERVICE = """[Unit]
Description=DreamReels library grower

[Service]
Type=oneshot
WorkingDirectory=/opt/dreamreels
ExecStart=/usr/bin/python3 -m dreamreels grow --discover --limit 60
ExecStart=/usr/bin/python3 -m dreamreels grow --work 400
"""

class Apply:
    def __init__(self, plan: dict, dry: bool, home_of_plan: Path):
        self.plan = plan; self.dry = dry; self.user = plan.get("user", "dreamreels"); self.report = []; self.plan_dir = home_of_plan
    def log(self, ok, what, measured=""): self.report.append((ok, what, measured)); print(("DRY   " if self.dry else ("OK    " if ok else "FAIL  ")) + what + (f"  -> {measured}" if measured else ""))
    def run(self, cmd, **kw):
        print("  $ " + " ".join(cmd))
        if self.dry: return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.run(cmd, capture_output=True, text=True, **kw)
    def write(self, path: Path, text: str, mode=0o644):
        print(f"  write {path} ({len(text.encode())} B, {oct(mode)})")
        if self.dry: return
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text); os.chmod(path, mode)
    # 1 ---------------------------------------------------------------
    def step_user(self):
        try: pw = pwd.getpwnam(self.user); existed = True
        except KeyError: pw = None; existed = False
        groups = [g for g in ("audio", "video", "input", "render", "plugdev") if g in {x.gr_name for x in grp.getgrall()}]
        if not existed: self.run(["useradd", "-m", "-s", "/bin/bash", "-G", ",".join(groups), self.user])
        else: self.run(["usermod", "-a", "-G", ",".join(groups), self.user])
        secret = self.plan_dir / "plan.secret"
        if self.plan.get("password_set") and secret.exists():
            if not self.dry: subprocess.run(["chpasswd"], input=f"{self.user}:{secret.read_text().strip()}\n", text=True, check=False); secret.unlink()
            else: print("  $ chpasswd <<< (password from plan.secret; file deleted after use)")
        elif not self.plan.get("password_set"): self.run(["passwd", "-d", self.user])
        if self.dry: self.log(True, f"user {self.user}", "not created (dry-run)"); return
        try: pw = pwd.getpwnam(self.user); gs = [g.gr_name for g in grp.getgrall() if self.user in g.gr_mem]; self.log(True, f"user {self.user}", f"uid={pw.pw_uid} groups={','.join(gs)}")
        except KeyError: self.log(False, f"user {self.user}", "not present after useradd")
        self.home = Path(pw.pw_dir) if pw else Path(f"/home/{self.user}")
    # 2 ---------------------------------------------------------------
    def step_mounts(self):
        mounts = self.plan.get("mounts") or []
        if not mounts: self.log(True, "NAS mounts", "none selected"); return
        creds = ETC / "smb-creds"
        if not creds.exists():
            self.write(creds, "username=guest\npassword=\n", 0o600); print("  (guest credentials written; edit /etc/dreamreels/smb-creds for a login share)")
        uid = pwd.getpwnam(self.user).pw_uid if not self.dry and self._user_exists() else 1000
        lines = FSTAB.read_text().splitlines() if FSTAB.exists() else []
        added = 0
        for m in mounts:
            mp = "/media/dreamreels/" + re.sub(r"[^A-Za-z0-9_-]", "_", m.split("/")[-1]) or "share"
            already = [l.split()[1] for l in lines if l.strip() and not l.startswith("#") and l.split()[0].lower() == m.lower()]
            if already: print(f"  {m} already in fstab at {already[0]} - reusing, no second mount"); self.reused = getattr(self, "reused", []) + [(m, already[0])]; continue
            lines.append(f"{m} {mp} cifs credentials={creds},uid={uid},gid={uid},iocharset=utf8,vers=3.0,nofail,x-systemd.automount,x-systemd.mount-timeout=15,_netdev 0 0"); added += 1
            self.run(["mkdir", "-p", mp])
        if added:
            if not self.dry: shutil.copy2(FSTAB, FSTAB.with_suffix(f".bak.dreamreels-{int(time.time())}"))
            self.write(FSTAB, "\n".join(lines) + "\n"); self.run(["systemctl", "daemon-reload"])
        if self.dry: self.log(True, f"NAS mounts ({len(mounts)})", f"{added} fstab line(s) would be added"); return
        txt = FSTAB.read_text().lower(); present = sum(1 for m in mounts if m.lower() in txt); self.log(present == len(mounts), f"NAS mounts ({len(mounts)})", f"{present}/{len(mounts)} in fstab after write" + (f"; reused {len(getattr(self, 'reused', []))} existing" if getattr(self, "reused", None) else ""))
    def _user_exists(self):
        try: pwd.getpwnam(self.user); return True
        except KeyError: return False
    # 3 ---------------------------------------------------------------
    def step_ytdlp(self):
        if not self.plan.get("youtube"): self.log(True, "yt-dlp", "YouTube lane off, skipped"); return
        before = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True).stdout.strip() if shutil.which("yt-dlp") else "absent"
        url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"; dest = Path("/usr/local/bin/yt-dlp")
        print(f"  download {url} -> {dest}")
        if not self.dry:
            try:
                tmp = dest.with_suffix(".new"); urllib.request.urlretrieve(url, tmp); os.chmod(tmp, 0o755)
                v = subprocess.run([str(tmp), "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
                if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}(\.\d+)?", v): tmp.replace(dest)
                else: tmp.unlink(); self.log(False, "yt-dlp", f"downloaded file did not run ({v[:40]})"); return
            except Exception as e: self.log(False, "yt-dlp", str(e)[:100]); return
        after = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True).stdout.strip() if shutil.which("yt-dlp") else "absent"
        node = shutil.which("node") or shutil.which("deno") or "NONE (yt-dlp needs a JS runtime for YouTube)"
        self.log(True, "yt-dlp", f"{before} -> {after}; js runtime: {node}")
    # 4 ---------------------------------------------------------------
    def step_autologin(self):
        if not GDM.exists(): self.log(False, "GDM autologin", f"{GDM} missing (not a GDM system; lightdm/sddm not handled yet)"); return
        txt = GDM.read_text(); new = txt
        if "[daemon]" not in new: new = "[daemon]\n" + new
        new = re.sub(r"^\s*#?\s*AutomaticLoginEnable\s*=.*$", "", new, flags=re.M); new = re.sub(r"^\s*#?\s*AutomaticLogin\s*=.*$", "", new, flags=re.M)
        new = new.replace("[daemon]", f"[daemon]\nAutomaticLoginEnable = true\nAutomaticLogin = {self.user}", 1); new = re.sub(r"\n{3,}", "\n\n", new)
        if new != txt:
            if not self.dry: shutil.copy2(GDM, GDM.with_suffix(f".conf.bak.dreamreels-{int(time.time())}"))
            self.write(GDM, new)
        got = re.search(r"^AutomaticLogin\s*=\s*(\S+)", GDM.read_text(), re.M)
        self.log(bool(got and got.group(1) == self.user) or self.dry, "GDM autologin", f"AutomaticLogin={got.group(1) if got else 'unset'}" + (" (would become %s)" % self.user if self.dry else ""))
    # 5 ---------------------------------------------------------------
    def step_service(self):
        home = Path(pwd.getpwnam(self.user).pw_dir) if self._user_exists() else Path(f"/home/{self.user}")
        ud = home / ".config/systemd/user"; unit = ud / "dreamreels.service"
        (home / '.local/state/dreamreels').mkdir(parents=True, exist_ok=True) if not self.dry else None
        self.write(unit, UNIT); self.write(ud / "dreamreels-grow.service", GROW_SERVICE); self.write(ud / "dreamreels-grow.timer", GROW_TIMER)
        wants = ud / "graphical-session.target.wants"; tw = ud / "timers.target.wants"
        for d, n in ((wants, "dreamreels.service"), (tw, "dreamreels-grow.timer")):
            print(f"  symlink {d / n} -> ../{n}")
            if not self.dry:
                d.mkdir(parents=True, exist_ok=True); ln = d / n
                if not ln.exists(): ln.symlink_to(f"../{n}")
        if not self.dry and self._user_exists():
            uid = pwd.getpwnam(self.user).pw_uid; subprocess.run(["chown", "-R", f"{uid}:{uid}", str(home / ".config")], capture_output=True)
            subprocess.run(["loginctl", "enable-linger", self.user], capture_output=True)
        # config + cache for the new user: copy the wizard author's config if the user has none
        src = self.plan_dir / "config.toml"  # plan.json and config.toml share ~/.config/dreamreels
        if src.exists():
            dst = home / ".config/dreamreels/config.toml"; print(f"  copy {src} -> {dst}")
            if not self.dry and not dst.exists(): dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst); os.chmod(dst, 0o600); subprocess.run(["chown", "-R", f"{self.user}:{self.user}", str(home / ".config/dreamreels")], capture_output=True)
        # library + poster cache travel with the install, else the new user boots to an empty player
        for rel in (".local/share/dreamreels", ".cache/dreamreels"):
            src_d = self.plan_dir.parent.parent / rel; dst_d = home / rel
            if src_d.is_dir() and not dst_d.exists():
                print(f"  copy {src_d} -> {dst_d}")
                if not self.dry: shutil.copytree(src_d, dst_d, ignore=shutil.ignore_patterns("*.tmp", "*.lock", "logs")); subprocess.run(["chown", "-R", f"{self.user}:{self.user}", str(dst_d)], capture_output=True)
        # the library stores absolute poster/file paths under the wizard author's home; point them at the new home
        src_home = self.plan_dir.parent.parent; dbf = home / ".local/share/dreamreels/dreamreels.db"
        if not self.dry and dbf.exists() and src_home != home:
            import sqlite3; c = sqlite3.connect(dbf)
            n = 0
            for col in ("poster_local", "backdrop_local", "path"):
                try: n += c.execute(f"UPDATE items SET {col}=replace({col},?,?) WHERE {col} LIKE ?", (str(src_home) + "/", str(home) + "/", str(src_home) + "/%")).rowcount
                except sqlite3.OperationalError: pass
            c.commit(); left = c.execute("SELECT COUNT(*) FROM items WHERE poster_local LIKE ?", (str(src_home) + "/%",)).fetchone()[0]; c.close()
            print(f"  rewrote {n} library paths {src_home} -> {home}; remaining author-home paths: {left}")
        # a brand-new GNOME user gets the Welcome tour on first login unless this file exists
        done = home / ".config/gnome-initial-setup-done"; print(f"  write {done} = yes")
        if not self.dry: done.parent.mkdir(parents=True, exist_ok=True); done.write_text("yes\n"); subprocess.run(["chown", "-R", f"{self.user}:{self.user}", str(home / ".config")], capture_output=True)
        # kiosk: never blank, never lock, never sleep (best effort; measured back)
        if not self.dry and self._user_exists():
            for schema, key, val in (("org.gnome.desktop.session", "idle-delay", "uint32 0"), ("org.gnome.desktop.screensaver", "lock-enabled", "false"), ("org.gnome.settings-daemon.plugins.power", "sleep-inactive-ac-type", "'nothing'")):
                r = subprocess.run(["sudo", "-u", self.user, "dbus-run-session", "--", "gsettings", "set", schema, key, val], capture_output=True, text=True, timeout=60)
                g = subprocess.run(["sudo", "-u", self.user, "dbus-run-session", "--", "gsettings", "get", schema, key], capture_output=True, text=True, timeout=60).stdout.strip()
                print(f"  gsettings {schema} {key} -> {g or r.stderr.strip()[:60]}")
        if not self.dry and self._user_exists(): subprocess.run(["chown", "-R", f"{self.user}:{self.user}", str(home)], capture_output=True)  # everything apply created under $HOME belongs to the user (state dir was root-owned once)
        ok = self.dry or (unit.exists() and (wants / "dreamreels.service").is_symlink()); self.log(ok, "systemd user units", f"{unit} + grow timer 03:00" + ("" if self.dry else f"; enabled={ok}"))
    # 6 ---------------------------------------------------------------
    def step_reboot(self, allow: bool):
        if not allow: self.log(True, "reboot", "skipped (--no-reboot); autologin takes effect on next boot"); return
        self.run(["systemctl", "reboot"]); self.log(True, "reboot", "requested")

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dreamreels-apply"); ap.add_argument("--plan", default=None); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--no-reboot", action="store_true"); ap.add_argument("--reboot", action="store_true")
    a = ap.parse_args(argv)
    if os.geteuid() != 0 and not a.dry_run: print("dreamreels-apply must run as root (sudo). Use --dry-run to preview.", file=sys.stderr); return 2
    plan_path = Path(a.plan) if a.plan else None
    if plan_path is None:
        from .core.paths import PLAN_FILE  # same definition the wizard writes to: ~/.config/dreamreels/plan.json
        rel = PLAN_FILE.relative_to(Path.home()) if PLAN_FILE.is_relative_to(Path.home()) else Path(".config/dreamreels/plan.json")
        cands = [Path(pwd.getpwnam(os.environ["SUDO_USER"]).pw_dir) / rel] if os.environ.get("SUDO_USER") else []
        cands += [PLAN_FILE] + sorted(Path("/home").glob(f"*/{rel}"), key=lambda q: -q.stat().st_mtime)
        plan_path = next((p for p in cands if p.exists()), None)
    if not plan_path or not plan_path.exists(): print("no plan.json found - run `dreamreels wizard` first", file=sys.stderr); return 3
    plan = json.loads(plan_path.read_text()); print(f"plan: {plan_path} (written {time.strftime('%Y-%m-%d %H:%M', time.localtime(plan.get('written', 0)))}) user={plan.get('user')} mounts={len(plan.get('mounts') or [])} youtube={plan.get('youtube')} theme={plan.get('theme')}\n")
    A = Apply(plan, a.dry_run, plan_path.parent)
    for step in (A.step_user, A.step_mounts, A.step_ytdlp, A.step_autologin, A.step_service): 
        try: step()
        except Exception as e: A.log(False, step.__name__, f"exception: {str(e)[:120]}")
    A.step_reboot(a.reboot and not a.no_reboot and not a.dry_run)
    fails = [r for r in A.report if not r[0]]
    print(f"\n{'DRY-RUN complete, nothing changed' if a.dry_run else ('ALL STEPS OK' if not fails else f'{len(fails)} step(s) FAILED')}")
    return 0 if not fails else 1
