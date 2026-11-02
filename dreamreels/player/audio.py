"""TV audio selection (Sep 12 2026). Measured on the reference box: a fresh PipeWire session picks the card's *Analog Stereo*
profile, so sound leaves the box's own speaker while the film plays on the HDMI TV. The HDMI sinks are not even
exposed until the card profile changes. This module makes the choice the way a person would - look at what is
plugged in, pick the HDMI output whose port reports a connected display - and is idempotent + fail-soft.
WirePlumber persists both the profile and the default sink per user, so this runs at every player boot as a check."""
from __future__ import annotations
import json, subprocess, time, logging, re
log = logging.getLogger("dreamreels.player.audio")

def _sh(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout); return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e: return 1, str(e)

def _dump():
    rc, out = _sh(["pw-dump"], 15)
    if rc != 0: return None
    try: return json.loads(out)
    except Exception: return None

def _alsa_devices(objs):
    for o in objs or []:
        if o.get("type") == "PipeWire:Interface:Device" and (o.get("info", {}).get("props", {}) or {}).get("device.api") == "alsa": yield o

def _sinks(objs):
    for o in objs or []:
        if o.get("type") == "PipeWire:Interface:Node":
            p = o.get("info", {}).get("props", {}) or {}
            if p.get("media.class") == "Audio/Sink": yield o["id"], p.get("node.name", ""), p.get("node.description", "")

def status() -> dict:
    objs = _dump()
    if objs is None: return {"available": False, "note": "pw-dump not available (no PipeWire session?)"}
    rc, out = _sh(["wpctl", "inspect", "@DEFAULT_AUDIO_SINK@"])
    name = ""
    for l in out.splitlines():
        if "node.name" in l: name = l.split("=", 1)[-1].strip().strip('"')
    return {"available": True, "default_sink": name, "sinks": [s for s in _sinks(objs)]}

def _kernel_hdmi_present() -> str:
    """Name of the display the KERNEL sees on an HDMI audio pin (ELD monitor_present=1), or "". Independent of PipeWire."""
    import glob
    for f in glob.glob("/proc/asound/card*/eld#*"):
        try: t = open(f).read()
        except Exception: continue
        if re.search(r"monitor_present\s+1", t):
            m = re.search(r"monitor_name\s+(.+)", t); return (m.group(1).strip() if m else "HDMI display")
    return ""

def _restart_pipewire() -> str:
    """Measured Sep 26 2026 on the reference box: after a boot with the TV off/asleep, PipeWire's ALSA card enumeration
    lacked hdmi-output-0 entirely (only extra1/extra3, both unavailable) while the kernel ELD already showed the 75S431
    present. Nothing re-enumerates on its own; a WirePlumber+PipeWire restart did, and WirePlumber then restored the
    persisted hdmi-stereo profile + default sink by itself. Fail-soft; returns a note."""
    rc, out = _sh(["systemctl", "--user", "restart", "wireplumber", "pipewire", "pipewire-pulse"], 20)
    time.sleep(4.0)
    return "pipewire re-enumerated" if rc == 0 else f"pipewire restart failed: {out.strip()[:80]}"

def ensure_tv_audio(prefer_surround: bool = False, _retry: bool = True) -> dict:
    """Pick an HDMI output if one is connected and the default is still the analog jack. Returns a measured summary.
    If PipeWire exposes no available HDMI profile but the kernel sees a display on an HDMI pin, restart the PipeWire
    stack once and re-check (boot race: card enumerated before the TV answered)."""
    objs = _dump()
    if objs is None: return {"ok": False, "changed": False, "note": "pw-dump unavailable - PipeWire session not running for this user"}
    changed = False; notes = []
    for dev in _alsa_devices(objs):
        info = dev.get("info", {}); params = info.get("params", {}) or {}
        profiles = params.get("EnumProfile", []) or []; active = (params.get("Profile", []) or [{}])[0]
        act_name = str(active.get("name", "")); act_idx = active.get("index")
        hdmi = [p for p in profiles if "hdmi" in str(p.get("name", "")).lower() and str(p.get("available", "")) == "yes" and "input" not in str(p.get("name", "")).lower()]
        if not hdmi: notes.append(f"device {dev['id']}: no connected HDMI output (active profile {act_name or act_idx})"); continue
        want_kind = "surround" if prefer_surround else "stereo"
        pick = sorted(hdmi, key=lambda p: (want_kind not in str(p.get("name", "")).lower(), int(p.get("priority", 0)) * -1))[0]
        if "hdmi" in act_name.lower():
            notes.append(f"device {dev['id']}: already on {active.get('description', act_name)}")
        else:
            rc, out = _sh(["wpctl", "set-profile", str(dev["id"]), str(pick["index"])])
            if rc != 0: notes.append(f"device {dev['id']}: set-profile failed: {out.strip()[:80]}"); continue
            changed = True; notes.append(f"device {dev['id']}: profile {active.get('description', act_name) or act_idx} -> {pick.get('description')}")
            time.sleep(2.0)
    objs = _dump() or []
    hdmi_sinks = [(i, n, d) for i, n, d in _sinks(objs) if "hdmi" in n.lower() or "hdmi" in d.lower()]
    if hdmi_sinks:
        cur = status().get("default_sink", "")
        if "hdmi" not in cur.lower():
            sid, name, desc = hdmi_sinks[0]
            rc, out = _sh(["wpctl", "set-default", str(sid)])
            if rc == 0: changed = True; notes.append(f"default sink -> {desc or name}")
            else: notes.append(f"set-default failed: {out.strip()[:80]}")
        rc, out = _sh(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        try:
            vol = float(out.split()[1])
            if vol < 0.5: _sh(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "1.0"]); notes.append(f"sink volume {vol:.2f} -> 1.00 (the TV remote controls loudness)")
        except Exception: pass
    final = status().get("default_sink", "")
    ok = "hdmi" in final.lower()
    if not ok and _retry:
        seen = _kernel_hdmi_present()
        if seen:
            notes.append(f"kernel sees {seen} on an HDMI pin but PipeWire has no HDMI profile -> {_restart_pipewire()}")
            log.warning("TV audio: %s", notes[-1])
            r2 = ensure_tv_audio(prefer_surround, _retry=False); r2["note"] = "; ".join(notes) + "; " + r2.get("note", ""); r2["changed"] = True
            return r2
    res = {"ok": ok, "changed": changed, "default_sink": final, "note": "; ".join(notes) or ("default sink is HDMI" if ok else "no HDMI sink found")}
    (log.info if ok else log.warning)("TV audio: default_sink=%s changed=%s %s", final, changed, res["note"])
    return res

if __name__ == "__main__":
    print(json.dumps(ensure_tv_audio(), indent=1))
