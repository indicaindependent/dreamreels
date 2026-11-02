"""Gamepad bridge, Phase A (Sep 12 2026). Everything runs on the GUI thread.

Why the rewrite: the previous bridge read evdev in a raw `threading.Thread` and called `.emit()` from it. PySide6 delivers
those slots in the EMITTING thread, so the QML handlers ran off the GUI thread - some landed, some were dropped, some
arrived late. That was the whole "D-pad moves twice, dies, comes back, lags" symptom; the DualSense over Bluetooth was fine.

Design:
  * QSocketNotifier on each evdev fd -> events are read inside the Qt event loop, no threads at all.
  * Every matching controller is attached at once (DualSense + a virtual QA pad can drive together).
  * Device pick: name-first. "DualSense Wireless Controller" (never its "Motion Sensors"/"Touchpad" siblings), any name in
    DR_PAD_NAMES, else any node with BTN_SOUTH + a HAT/stick whose name does not contain Motion/Touchpad/Keyboard/Mouse.
  * D-pad and left stick edge-detect, then HOLD-REPEAT (380 ms, then every 160 ms) so a held direction keeps moving.
  * Rescan every 2 s while nothing is attached; on OSError the device is dropped and the scan resumes (BT reconnects work).
  * Every emitted action is logged as `PAD <action> t=<ms>`; QML calls pad.ack(state) after it moves focus, logged as
    `NAVACK <state> t=<ms>` - the QA sweep counts and pairs these to prove 0 dropped and the latency.
"""
from __future__ import annotations
import os, time, logging
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QSocketNotifier, Property

log = logging.getLogger("dreamreels.player.pad")
_ms = lambda: int(time.monotonic() * 1000)

class GamepadBridge(QObject):
    navUp = Signal(); navDown = Signal(); navLeft = Signal(); navRight = Signal()
    select = Signal(); back = Signal(); playPause = Signal(); info = Signal(); home = Signal()
    railPrev = Signal(); railNext = Signal(); seekFwd = Signal(); seekBack = Signal(); dreamy = Signal()
    connectedChanged = Signal(bool)

    REPEAT_FIRST_MS = 380; REPEAT_MS = 160; DEADZONE = 0.6; RELEASE = 0.3

    def __init__(self, enabled: bool = True):
        super().__init__()
        self.connected = False; self._devs = {}   # path -> dict(dev, notifier, name)
        self._held = None      # ("navLeft"|...,) currently held direction for repeat
        self._rep = QTimer(self); self._rep.setSingleShot(True); self._rep.timeout.connect(self._repeat)
        self._scan = QTimer(self); self._scan.setInterval(2000); self._scan.timeout.connect(self._rescan)
        self._sticks = {}      # path -> {"x":0,"y":0}
        self._counts = {"emitted": 0, "acked": 0}
        if enabled:
            try:
                import evdev  # noqa
                self._rescan(); self._scan.start()
            except Exception as e:
                log.warning("evdev unavailable, pad disabled: %s", e)

    # ---- device discovery -------------------------------------------------------------------------
    def _wanted(self, dev) -> bool:
        from evdev import ecodes
        name = (dev.name or "").strip(); low = name.lower()
        if any(b in low for b in ("motion sensors", "touchpad", "keyboard", "mouse")): return False
        extra = [n.strip().lower() for n in os.environ.get("DR_PAD_NAMES", "DreamReels QA Pad").split(",") if n.strip()]
        if low == "dualsense wireless controller" or low in extra or low.startswith("wireless controller"): return True
        try:
            caps = dev.capabilities(); keys = set(caps.get(ecodes.EV_KEY, [])); axes = {a[0] if isinstance(a, tuple) else a for a in caps.get(ecodes.EV_ABS, [])}
            return ecodes.BTN_SOUTH in keys and (ecodes.ABS_HAT0X in axes or ecodes.ABS_X in axes)
        except Exception: return False

    def _rescan(self):
        try:
            import evdev
            paths = set(evdev.list_devices())
        except Exception: return
        for p in list(self._devs):
            if p not in paths: self._drop(p, "gone")
        for p in sorted(paths - set(self._devs)):
            try:
                dev = evdev.InputDevice(p)
                if not self._wanted(dev): dev.close(); continue
                os.set_blocking(dev.fd, False)
                n = QSocketNotifier(dev.fd, QSocketNotifier.Type.Read, self)
                n.activated.connect(lambda *_a, p=p: self._read(p))
                self._devs[p] = {"dev": dev, "notifier": n, "name": dev.name}; self._sticks[p] = {"x": 0, "y": 0}
                log.info("PAD attached %s (%s)", dev.name, p)
            except Exception as e:
                log.debug("pad open %s failed: %s", p, e)
        self._set_connected(bool(self._devs))

    def _drop(self, p, why):
        d = self._devs.pop(p, None); self._sticks.pop(p, None)
        if d:
            try: d["notifier"].setEnabled(False); d["dev"].close()
            except Exception: pass
            log.info("PAD detached %s (%s): %s", d["name"], p, why)
        if self._held: self._held = None; self._rep.stop()
        self._set_connected(bool(self._devs))

    def _set_connected(self, v):
        if v != self.connected: self.connected = v; self.connectedChanged.emit(v)

    # ---- events (GUI thread) ----------------------------------------------------------------------
    def _read(self, p):
        d = self._devs.get(p)
        if not d: return
        try:
            from evdev import ecodes
            for ev in d["dev"].read():
                if ev.type == ecodes.EV_KEY and ev.value == 1: self._button(ev.code)
                elif ev.type == ecodes.EV_ABS: self._axis(p, d["dev"], ev)
        except BlockingIOError: pass
        except OSError as e: self._drop(p, f"OSError {e}")

    def _button(self, b):
        from evdev import ecodes
        m = {ecodes.BTN_SOUTH: "select", ecodes.BTN_EAST: "back", ecodes.BTN_WEST: "playPause", ecodes.BTN_NORTH: "info",
             ecodes.BTN_TL: "railPrev", ecodes.BTN_TR: "railNext", ecodes.BTN_TL2: "seekBack", ecodes.BTN_TR2: "seekFwd",
             ecodes.BTN_MODE: "home", ecodes.BTN_START: "info", getattr(ecodes, "BTN_SELECT", -1): "dreamy", getattr(ecodes, "BTN_THUMBL", -2): "dreamy"}
        a = m.get(b)
        if a: self._fire(a)

    def _axis(self, p, dev, ev):
        from evdev import ecodes
        if ev.code == ecodes.ABS_HAT0X: self._dir("navLeft" if ev.value < 0 else "navRight" if ev.value > 0 else None)
        elif ev.code == ecodes.ABS_HAT0Y: self._dir("navUp" if ev.value < 0 else "navDown" if ev.value > 0 else None)
        elif ev.code in (ecodes.ABS_X, ecodes.ABS_Y):
            try: ai = dev.absinfo(ev.code)
            except Exception: return
            mid = (ai.min + ai.max) / 2; span = (ai.max - ai.min) / 2 or 1; v = (ev.value - mid) / span
            st = self._sticks.setdefault(p, {"x": 0, "y": 0}); k = "x" if ev.code == ecodes.ABS_X else "y"
            if abs(v) > self.DEADZONE and st[k] == 0:
                st[k] = 1 if v > 0 else -1
                self._dir(("navRight" if v > 0 else "navLeft") if k == "x" else ("navDown" if v > 0 else "navUp"))
            elif abs(v) < self.RELEASE and st[k] != 0:
                st[k] = 0; self._dir(None)

    def _dir(self, action):
        """Edge + hold-repeat. action=None is a release."""
        if action is None:
            self._held = None; self._rep.stop(); return
        self._held = action; self._fire(action); self._rep.start(self.REPEAT_FIRST_MS)

    def _repeat(self):
        if self._held: self._fire(self._held); self._rep.start(self.REPEAT_MS)

    def _fire(self, action):
        self._counts["emitted"] += 1
        log.info("PAD %s t=%d", action, _ms())
        getattr(self, action).emit()

    # ---- QML side -----------------------------------------------------------------------------------
    @Slot(str)
    def ack(self, state: str):
        """Called by Main.qml after nav() changed focus - the receipt the QA sweep pairs with PAD lines."""
        self._counts["acked"] += 1
        log.info("NAVACK %s t=%d", state, _ms())

    @Slot(result="QVariant")
    def stats(self): return {"connected": self.connected, "devices": [d["name"] for d in self._devs.values()], **self._counts}

    @Property(str, notify=connectedChanged)
    def deviceName(self): return ", ".join(d["name"] for d in self._devs.values())
