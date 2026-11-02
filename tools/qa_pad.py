#!/usr/bin/env python3
"""Phase A acceptance: a virtual gamepad presses the D-pad N times; the player's log must show one NAVACK per press.
Usage: qa_pad.py [--n 200] [--gap-ms 70] [--log PATH]. Exit 0 only on 0 dropped. Runs as a user in group input."""
import argparse, time, re, sys, os
from evdev import UInput, ecodes as e, AbsInfo
ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=200); ap.add_argument("--gap-ms", type=int, default=70)
ap.add_argument("--log", default="/home/dreamreels/.local/state/dreamreels/logs/player.log"); a = ap.parse_args()
caps = {e.EV_KEY: [e.BTN_SOUTH, e.BTN_EAST, e.BTN_WEST, e.BTN_NORTH, e.BTN_TL, e.BTN_TR, e.BTN_MODE, e.BTN_START],
        e.EV_ABS: [(e.ABS_HAT0X, AbsInfo(0, -1, 1, 0, 0, 0)), (e.ABS_HAT0Y, AbsInfo(0, -1, 1, 0, 0, 0)),
                   (e.ABS_X, AbsInfo(128, 0, 255, 0, 15, 0)), (e.ABS_Y, AbsInfo(128, 0, 255, 0, 15, 0))]}
ui = UInput(caps, name="DreamReels QA Pad", vendor=0x1209, product=0x0001)
print("virtual pad created:", ui.device.path); time.sleep(3.0)  # give the bridge's 2 s rescan time to attach
start = os.path.getsize(a.log)
t0 = time.monotonic(); presses = []
for i in range(a.n):
    code = e.ABS_HAT0X if i % 2 == 0 else e.ABS_HAT0X
    val = 1 if (i // 2) % 2 == 0 else -1          # alternate right/left in pairs so focus never pins at an edge
    ui.write(e.EV_ABS, code, val); ui.syn(); presses.append(time.monotonic())
    time.sleep(0.03); ui.write(e.EV_ABS, code, 0); ui.syn()   # release before the 380 ms repeat threshold
    time.sleep(max(0, a.gap_ms / 1000 - 0.03))
time.sleep(1.5); ui.close()
with open(a.log, "rb") as f: f.seek(start); tail = f.read().decode("utf-8", "replace")
pad = [int(m) for m in re.findall(r"PAD nav(?:Left|Right) t=(\d+)", tail)]
ack = [int(m) for m in re.findall(r"NAVACK \S+ t=(\d+)", tail)]
lat = [b - p for p, b in zip(pad, ack)] if len(ack) == len(pad) else []
lat_s = sorted(lat); p95 = lat_s[int(0.95 * (len(lat_s) - 1))] if lat_s else None
print(f"presses={a.n} PAD_emitted={len(pad)} NAVACK={len(ack)} dropped={a.n - len(ack)} latency_ms median={lat_s[len(lat_s)//2] if lat_s else None} p95={p95} max={lat_s[-1] if lat_s else None}")
print("attached line present:", "PAD attached DreamReels QA Pad" in tail)
sys.exit(0 if len(ack) == a.n and len(pad) == a.n else 1)
