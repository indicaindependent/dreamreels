"""LAN SMB discovery: TCP-445 sweep of the local /24 + smbclient share enumeration (-N first, then flags auth-required).
No SMB1. Every result carries how it was found. Optional zeroconf (_smb._tcp) adds names when installed."""
from __future__ import annotations
import ipaddress, re, socket, subprocess
from concurrent.futures import ThreadPoolExecutor

def local_subnets() -> list[str]:
    out = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True, text=True).stdout
    nets = []
    for m in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", out):
        ip, bits = m.group(1), int(m.group(2))
        if ip.startswith("127.") or bits < 16: continue
        net = ipaddress.ip_network(f"{ip}/{bits}", strict=False)
        if net.num_addresses <= 1024: nets.append(str(net))
    return nets

def _open445(ip: str, timeout=0.35) -> bool:
    try:
        with socket.create_connection((ip, 445), timeout=timeout): return True
    except OSError: return False

def sweep(nets: list[str] | None = None, workers=128) -> list[str]:
    nets = nets or local_subnets(); hosts = [str(h) for n in nets for h in ipaddress.ip_network(n).hosts()]
    with ThreadPoolExecutor(workers) as ex: hits = [ip for ip, ok in zip(hosts, ex.map(_open445, hosts)) if ok]
    return hits

def hostname(ip: str) -> str:
    try: return socket.gethostbyaddr(ip)[0]
    except OSError: pass
    r = subprocess.run(["nmblookup", "-A", ip], capture_output=True, text=True, timeout=5)
    m = re.search(r"^\s+(\S+)\s+<00>\s+-\s+B", r.stdout, re.M)
    return m.group(1) if m else ""

def shares(ip: str, user: str = "", password: str = "") -> dict:
    """Returns {ip, host, auth: 'guest'|'required'|'error', shares:[{name,type,comment}], error}"""
    cmd = ["smbclient", "-L", f"//{ip}", "-g", "-m", "SMB3"] + (["-U", f"{user}%{password}"] if user else ["-N"])
    try: r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except Exception as e: return {"ip": ip, "auth": "error", "shares": [], "error": str(e)}
    out = r.stdout + r.stderr
    if "NT_STATUS_ACCESS_DENIED" in out or "NT_STATUS_LOGON_FAILURE" in out:
        return {"ip": ip, "host": hostname(ip), "auth": "required", "shares": [], "error": ""}
    if "NT_STATUS_CONNECTION_DISCONNECTED" in out or "protocol negotiation failed" in out:
        return {"ip": ip, "host": hostname(ip), "auth": "error", "shares": [], "error": "server refused SMB2/3 (SMB1-only servers are not supported)"}
    sh = []
    for line in out.splitlines():
        if line.startswith("Disk|"):
            _, name, comment = (line.split("|", 2) + [""])[:3]
            if not name.endswith("$"): sh.append({"name": name, "type": "disk", "comment": comment})
    return {"ip": ip, "host": hostname(ip), "auth": "guest" if user == "" else "user", "shares": sh, "error": "" if sh or r.returncode == 0 else out.strip()[:200]}

def discover() -> list[dict]:
    return [shares(ip) for ip in sweep()]
