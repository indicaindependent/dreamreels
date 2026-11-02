"""Windows replacement for the Linux 'System user' step: Start menu + Desktop shortcuts, optional sign-in start.
No extra dependencies: the .lnk files are written by PowerShell's WScript.Shell COM object, which ships with Windows."""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

def _target() -> tuple[str, str]:
    """(program, arguments) that start the player."""
    if getattr(sys, "frozen", False):
        return sys.executable, "player"
    return sys.executable, "-m dreamreels player"

def _folders(start_at_login: bool) -> list[Path]:
    appdata = Path(os.environ.get("APPDATA") or (Path.home() / "AppData/Roaming"))
    out = [appdata / "Microsoft/Windows/Start Menu/Programs", Path.home() / "Desktop"]
    if start_at_login: out.append(appdata / "Microsoft/Windows/Start Menu/Programs/Startup")
    return out

def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"

def install(start_at_login: bool = False) -> list[Path]:
    if sys.platform != "win32":
        raise RuntimeError("Windows only")
    prog, args = _target(); made = []
    for folder in _folders(start_at_login):
        folder.mkdir(parents=True, exist_ok=True); lnk = folder / "DreamReels.lnk"
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + _ps_quote(lnk) + ");"
              "$s.TargetPath=" + _ps_quote(prog) + ";$s.Arguments=" + _ps_quote(args) + ";"
              "$s.WorkingDirectory=" + _ps_quote(Path(prog).parent) + ";$s.IconLocation=" + _ps_quote(prog + ",0") + ";"
              "$s.Description='DreamReels';$s.Save()")
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           capture_output=True, text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0 and lnk.exists(): made.append(lnk)
    return made

def remove() -> list[Path]:
    gone = []
    for folder in _folders(True):
        lnk = folder / "DreamReels.lnk"
        if lnk.exists(): lnk.unlink(); gone.append(lnk)
    return gone
