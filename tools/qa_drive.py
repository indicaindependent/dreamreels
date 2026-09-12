#!/usr/bin/env python3
"""qa_drive.py - drive the running DreamReels player like a human through the Observatory and grade it.

    python3 tools/qa_drive.py [--obs http://127.0.0.1:8474] [--out /tmp/dr_qa]

Every step is an action followed by a MEASUREMENT (window state, mpv telemetry, DB row, toast) - never
"it probably worked". Writes report.md + report.json + one scaled screenshot per step into --out and
prints a PASS/FAIL table. Exit code = number of FAILs.
"""
from __future__ import annotations
import argparse, json, os, sqlite3, subprocess, sys, time, urllib.request, urllib.parse

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--obs", default="http://127.0.0.1:8474"); ap.add_argument("--out", default="/tmp/dr_qa")
    ap.add_argument("--db", default=os.path.expanduser("~/.local/share/dreamreels/dreamreels.db")); a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); R = []; shots = []

    def get(path):
        with urllib.request.urlopen(a.obs + path, timeout=20) as r: return r.read()
    def status(): return json.loads(get("/status"))
    def do(**req):
        rq = urllib.request.Request(a.obs + "/do", data=json.dumps(req).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(rq, timeout=20) as r: return json.loads(r.read())
    def key(k, wait=0.7): do(action="key", key=k); time.sleep(wait)
    def shot(name):
        png = os.path.join(a.out, name + ".png"); jpg = os.path.join(a.out, name + ".jpg")
        open(png, "wb").write(get("/shot.png"))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", png, "-vf", "scale=480:-1", "-q:v", "8", jpg]); os.remove(png); shots.append(jpg); return jpg
    def rec(step, ok, detail):
        R.append({"step": step, "ok": bool(ok), "detail": detail}); print(("PASS " if ok else "FAIL ") + step + "  " + str(detail)[:160], flush=True)
    def q(sql, *args):
        c = sqlite3.connect(a.db); c.row_factory = sqlite3.Row; r = [dict(x) for x in c.execute(sql, args).fetchall()]; c.close(); return r
    def mpv_read():
        m = status()["mpv"]; return {k: m.get(k) for k in ("hwdec-current", "video-codec", "video-format", "width", "height", "container-fps", "display-fps", "estimated-vf-fps", "time-pos", "duration", "frame-drop-count", "decoder-frame-drop-count", "vo-delayed-frame-count", "mistimed-frame-count", "avsync", "paused-for-cache", "demuxer-cache-duration", "audio-codec-name", "ao", "pause")}

    # 0. boot state
    s = status(); w = s["window"]
    rec("boot: window visible+active 1920x1080", w["visible"] and w["active"] and w["size"] == [1920, 1080], w["size"])
    rec("boot: rails present", bool(w["rails"]) and len(w["rails"]) >= 3, w["rails"])
    rec("boot: mpv object wired", s["mpv"].get("available"), s["mpv"].get("available"))
    do(action="stop") if w["playing"] else None; do(action="home"); do(action="set", zone="top", topIdx=0); time.sleep(0.8); shot("00_home")

    # 1. lanes
    for lane, label in (("pd", "Public Domain"), ("chan83", "Channel 83"), ("toontown", "Toon Town"), ("nas", "NAS"), ("youtube", "YouTube"), ("music", "Music")):
        do(action="lane", name=lane); time.sleep(1.2); w = status()["window"]
        n = len(w["rails"] or []); rec(f"lane {label}: rails load", n >= 1, f"{n} rails: {w['rails'][:4]}"); shot(f"01_lane_{lane}")
    do(action="home"); time.sleep(0.8)

    # 2. keyboard path: top -> rails -> move -> open detail
    do(action="set", zone="top", topIdx=0, railIdx=0, colIdx=0); time.sleep(0.3)
    key("Down"); w = status()["window"]; rec("keys: Down leaves top bar into rails", w["zone"] == "rails", w["zone"])
    key("Right"); key("Right"); w = status()["window"]; rec("keys: Right moves column", w["colIdx"] == 2, f"colIdx={w['colIdx']}")
    key("Down"); w = status()["window"]; rec("keys: Down moves rail", w["railIdx"] == 1, f"railIdx={w['railIdx']} ({(w['rails'] or ['?'])[w['railIdx']] if w['rails'] else '?'})")
    key("Return", 1.2); w = status()["window"]; rec("keys: Select opens detail with a uid", w["zone"] == "detail" and bool(w["detail"] and w["detail"].get("uid")), w["detail"]); shot("02_detail")
    det = w["detail"] or {}
    key("Escape"); w = status()["window"]; rec("keys: Back closes detail", w["zone"] == "rails" and not w["detail"], w["zone"])

    # 3. play through the KEYBOARD path on a verified item (the exact path Pete uses)
    v = q("SELECT uid,title FROM items WHERE source='chan83' AND verified=1 ORDER BY title LIMIT 1")[0]
    do(action="detail", uid=v["uid"]); do(action="set", zone="detail", detailBtn=0); time.sleep(0.6)
    key("Return", 1.0); t0 = time.time(); time.sleep(9); s = status(); m = mpv_read(); w = s["window"]
    started = w["playing"] and m["time-pos"] is not None and m["time-pos"] > 2
    rec(f"play (keyboard Select on detail): {v['title']}", started, {"uid": w["current_uid"], "time-pos": m["time-pos"], "codec": m["video-codec"], "toasts": s["toasts"][-2:]}); shot("03_playing")
    rec("play: hardware decode active (hwdec-current)", m["hwdec-current"] not in (None, "no", ""), m["hwdec-current"])
    rec("play: no frame drops in first 9 s", (m["frame-drop-count"] or 0) == 0 and (m["decoder-frame-drop-count"] or 0) == 0, {"vo_drops": m["frame-drop-count"], "dec_drops": m["decoder-frame-drop-count"], "delayed": m["vo-delayed-frame-count"], "mistimed": m["mistimed-frame-count"]})
    rec("play: A/V sync within 40 ms", m["avsync"] is not None and abs(m["avsync"]) < 0.04, m["avsync"])
    rec("play: display fps detected", (m["display-fps"] or 0) > 20, {"display": m["display-fps"], "container": m["container-fps"], "size": [m["width"], m["height"]]})
    rec("play: audio output live", bool(m["ao"]) and m["ao"] not in ("[]", "null"), m["ao"])
    # pause / seek / resume-write
    p0 = m["time-pos"]; key("Space", 1.5); m1 = mpv_read(); rec("pause: Space pauses (time-pos stops)", m1["pause"] is True, {"pause": m1["pause"]})
    key("Space", 1.0); key("Right", 1.5); m2 = mpv_read(); rec("seek: Right while playing = +30 s", m2["time-pos"] is not None and m2["time-pos"] > (p0 or 0) + 20, {"before": p0, "after": m2["time-pos"]})
    do(action="seek", secs=200); time.sleep(2.5); do(action="stop"); time.sleep(1.0); w = status()["window"]
    rec("stop: Back/stop returns to rails", not w["playing"] and w["zone"] in ("rails", "top"), w["zone"])
    st = q("SELECT resume_sec,duration_sec,play_count FROM state WHERE uid=?", v["uid"])
    rec("resume: state row written with position", bool(st) and (st[0]["resume_sec"] or 0) > 30, st[0] if st else None)
    do(action="detail", uid=v["uid"]); time.sleep(0.8); d = status()["window"]["detail"]; shot("04_detail_resume")
    rec("resume: detail reopens same uid", bool(d) and d.get("uid") == v["uid"], d)

    # 4. favourites toggle via keyboard path (detailBtn 2)
    do(action="set", zone="detail", detailBtn=2); key("Return", 0.8); f1 = q("SELECT favorite FROM state WHERE uid=?", v["uid"])
    rec("favorite: toggles on", bool(f1) and f1[0]["favorite"] == 1, f1)
    key("Return", 0.8); f2 = q("SELECT favorite FROM state WHERE uid=?", v["uid"]); rec("favorite: toggles off", bool(f2) and f2[0]["favorite"] == 0, f2); key("Escape")

    # 5. one verified title from EVERY source through backend.play + telemetry
    for src in ("pd", "nas", "toontown", "chan83"):
        rows = q("SELECT uid,title FROM items WHERE source=? AND verified=1 ORDER BY RANDOM() LIMIT 1", src)
        if not rows: rec(f"play {src}: no verified item to test", False, "0 verified rows"); continue
        it = rows[0]; do(action="play", uid=it["uid"]); time.sleep(9); m = mpv_read(); s = status()
        ok = s["window"]["playing"] and m["time-pos"] is not None and m["time-pos"] > 2
        rec(f"play {src}: {it['title'][:40]}", ok, {"hwdec": m["hwdec-current"], "codec": m["video-codec"], "size": [m["width"], m["height"]], "fps": m["container-fps"], "drops": m["frame-drop-count"], "avsync": m["avsync"], "cache_s": m["demuxer-cache-duration"], "toasts": s["toasts"][-1:]}); shot(f"05_play_{src}")
        do(action="stop"); time.sleep(1.0)

    # 6. unverified item -> Play button must be "Find playable", not Play
    u = q("SELECT uid,title FROM items WHERE verified=0 AND source='pd' LIMIT 1")
    if u:
        do(action="detail", uid=u[0]["uid"]); time.sleep(0.8); d = status()["window"]["detail"]
        rec("unverified: detail reports verified=false (button = Find playable)", bool(d) and d.get("verified") is False, d); shot("06_unverified"); key("Escape")

    # 7. mouse path: click a poster, click Play
    do(action="home"); do(action="set", zone="top", topIdx=0, railIdx=0, colIdx=0); time.sleep(0.8)
    # rail row 2 (Public Domain) posters sit ~y 0.60; first poster ~x 0.09 at 1080p layout
    do(action="click", x=0.09, y=0.62); time.sleep(1.2); w = status()["window"]
    rec("mouse: poster click opens detail", w["zone"] == "detail" and bool(w["detail"]), {"zone": w["zone"], "detail": w["detail"]}); shot("07_mouse_detail")
    if w["zone"] == "detail" and w["detail"] and w["detail"].get("verified"):
        do(action="click", x=0.135, y=0.735); time.sleep(8); s = status(); m = mpv_read()
        rec("mouse: Play button starts playback", s["window"]["playing"] and (m["time-pos"] or 0) > 1, {"uid": s["window"]["current_uid"], "time-pos": m["time-pos"], "toasts": s["toasts"][-2:]}); shot("07_mouse_playing"); do(action="stop"); time.sleep(1)
    else:
        rec("mouse: Play button starts playback", False, "detail not open or item unverified - check click coordinates in 07_mouse_detail.jpg")
    do(action="home"); do(action="set", zone="top", topIdx=0)

    # 8. Dreamy from the terminal (same agent the UI uses)
    try:
        out = subprocess.run([sys.executable, "-m", "dreamreels", "dreamy", "find", "me", "an", "Alfred", "Hitchcock", "episode"], capture_output=True, text=True, timeout=90, cwd="/opt/dreamreels").stdout
        j = json.loads(out[out.index("{"):]) if "{" in out else {}
        btns = [b for b in (j.get("buttons") or j.get("results") or []) if isinstance(b, dict)]
        rec("dreamy: returns playable buttons for a title query", len(btns) > 0, {"buttons": len(btns), "first": (btns[0].get("title") if btns else None), "reply": (j.get("text") or j.get("reply") or "")[:100]})
    except Exception as e: rec("dreamy: terminal query", False, repr(e))

    # 9. observatory itself
    lg = get("/log?n=5").decode(); rec("observatory: log tail readable", "dreamreels.player" in lg, lg.splitlines()[-1][:100] if lg else "")
    sysf = status()["system"]; rec("system: versions read live", bool(sysf.get("mpv")) and bool(sysf.get("ffmpeg")), {k: sysf.get(k) for k in ("mpv", "ffmpeg", "yt_dlp", "vaapi", "scenegraph")})

    # contact sheet
    try:
        sel = shots[:12]; n = len(sel); cols = 4; rows = (n + cols - 1) // cols
        inputs = sum((["-i", p] for p in sel), []); layout = "|".join(f"{(i%cols)*480}_{(i//cols)*270}" for i in range(n))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", f"{''.join(f'[{i}:v]scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2[v{i}];' for i in range(n))}{''.join(f'[v{i}]' for i in range(n))}xstack=inputs={n}:layout={layout}[o]", "-map", "[o]", "-q:v", "7", os.path.join(a.out, "contact_sheet.jpg")])
    except Exception as e: print("contact sheet failed", e)
    fails = [r for r in R if not r["ok"]]
    md = ["# DreamReels QA drive - " + time.strftime("%Y-%m-%d %H:%M:%S %Z"), "", f"**{len(R) - len(fails)} PASS / {len(fails)} FAIL**", "", "| result | step | measured |", "|---|---|---|"]
    md += [f"| {'PASS' if r['ok'] else 'FAIL'} | {r['step']} | `{json.dumps(r['detail'], default=str)[:220]}` |" for r in R]
    open(os.path.join(a.out, "report.md"), "w").write("\n".join(md)); json.dump(R, open(os.path.join(a.out, "report.json"), "w"), indent=1, default=str)
    print(f"\n{len(R) - len(fails)} PASS / {len(fails)} FAIL  -> {a.out}/report.md"); return len(fails)

if __name__ == "__main__":
    sys.exit(main())
