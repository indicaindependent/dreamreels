"""Gamepad -> navigation signals. Any evdev pad with a south button and a hat/stick works
(DualSense, Xbox, 8BitDo...). evdev is optional; without it the bridge is inert."""
from __future__ import annotations
import threading, time
from PySide6.QtCore import QObject, Signal

class GamepadBridge(QObject):
    navUp=Signal(); navDown=Signal(); navLeft=Signal(); navRight=Signal()
    select=Signal(); back=Signal(); playPause=Signal(); info=Signal(); home=Signal()
    railPrev=Signal(); railNext=Signal(); seekFwd=Signal(); seekBack=Signal(); dreamy=Signal()
    connectedChanged=Signal(bool)
    def __init__(self, enabled: bool = True):
        super().__init__(); self._stop = False; self.connected = False
        if enabled:
            threading.Thread(target=self._loop, daemon=True, name="gamepad").start()
    def _find(self):
        try:
            from evdev import list_devices, InputDevice, ecodes
        except Exception:
            return None
        for path in list_devices():
            try:
                d = InputDevice(path); n = (d.name or "").lower(); caps = d.capabilities()
                if any(x in n for x in ("motion", "touchpad", "headset", "keyboard", "mouse")): continue
                keys = caps.get(ecodes.EV_KEY, []); axes = [a for a, _ in caps.get(ecodes.EV_ABS, [])]
                if ecodes.BTN_SOUTH in keys and (ecodes.ABS_HAT0X in axes or ecodes.ABS_X in axes):
                    return d
            except Exception: continue
        return None
    def _loop(self):
        try:
            from evdev import ecodes
        except Exception:
            return
        while not self._stop:
            dev = self._find()
            if not dev: time.sleep(2.0); continue
            self.connected = True; self.connectedChanged.emit(True)
            lastx = lasty = 0
            try:
                for ev in dev.read_loop():
                    if self._stop: break
                    if ev.type == ecodes.EV_KEY and ev.value == 1:
                        b = ev.code
                        if b == ecodes.BTN_SOUTH: self.select.emit()
                        elif b == ecodes.BTN_EAST: self.back.emit()
                        elif b == ecodes.BTN_WEST: self.playPause.emit()
                        elif b == ecodes.BTN_NORTH: self.info.emit()
                        elif b == ecodes.BTN_TL: self.railPrev.emit()
                        elif b == ecodes.BTN_TR: self.railNext.emit()
                        elif b == ecodes.BTN_TL2: self.seekBack.emit()
                        elif b == ecodes.BTN_TR2: self.seekFwd.emit()
                        elif b == ecodes.BTN_MODE: self.home.emit()
                        elif b == ecodes.BTN_START: self.info.emit()
                        elif b in (getattr(ecodes, "BTN_SELECT", -1), getattr(ecodes, "BTN_THUMBL", -2)): self.dreamy.emit()
                    elif ev.type == ecodes.EV_ABS:
                        if ev.code == ecodes.ABS_HAT0X:
                            if ev.value < 0: self.navLeft.emit()
                            elif ev.value > 0: self.navRight.emit()
                        elif ev.code == ecodes.ABS_HAT0Y:
                            if ev.value < 0: self.navUp.emit()
                            elif ev.value > 0: self.navDown.emit()
                        elif ev.code in (ecodes.ABS_X, ecodes.ABS_Y):
                            ai = dev.absinfo(ev.code); mid = (ai.min + ai.max) / 2; span = (ai.max - ai.min) / 2 or 1
                            v = (ev.value - mid) / span
                            if ev.code == ecodes.ABS_X:
                                if abs(v) > 0.7 and lastx == 0: (self.navRight if v > 0 else self.navLeft).emit(); lastx = 1
                                elif abs(v) < 0.3: lastx = 0
                            else:
                                if abs(v) > 0.7 and lasty == 0: (self.navDown if v > 0 else self.navUp).emit(); lasty = 1
                                elif abs(v) < 0.3: lasty = 0
            except OSError:
                pass
            self.connected = False; self.connectedChanged.emit(False); time.sleep(1.5)
