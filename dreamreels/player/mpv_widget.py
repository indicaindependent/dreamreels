"""
Embedded mpv render object for DreamReels (v1 technique, proven on GNOME Wayland + Intel UHD 770).
Renders libmpv INTO the QML scene via QQuickFramebufferObject + the mpv render API,
so video and QML controls share ONE window (fixes the black-screen / two-window bug
under mutter/Wayland). Industry-standard Qt+mpv integration.
"""
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtQuick import QQuickFramebufferObject
import mpv


def _get_proc_address(_, name):
    # Resolve GL function pointers for libmpv's OpenGL render backend
    from PySide6.QtGui import QOpenGLContext
    ctx = QOpenGLContext.currentContext()
    if ctx is None:
        return 0
    # bytes -> address int
    if isinstance(name, bytes):
        name = name.decode("utf-8")
    return int(ctx.getProcAddress(name.encode("utf-8")))


class MpvRenderer(QQuickFramebufferObject.Renderer):
    def __init__(self, obj):
        super().__init__()
        self._obj = obj
        self._ctx = None

    def createFramebufferObject(self, size):
        # (re)create the render context once we have a GL context
        if self._ctx is None:
            self._ctx = mpv.MpvRenderContext(
                self._obj.mpv,
                "opengl",
                opengl_init_params={"get_proc_address": mpv.MpvGlGetProcAddressFn(_get_proc_address)},
            )
            self._ctx.update_cb = self._obj.on_update
        return super().createFramebufferObject(size)

    def render(self):
        if self._ctx is None:
            return
        fbo = self.framebufferObject()
        self._ctx.render(
            flip_y=True,
            opengl_fbo={"w": fbo.width(), "h": fbo.height(), "fbo": fbo.handle()},
        )


class MpvObject(QQuickFramebufferObject):
    onUpdate = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMirrorVertically(True)
        # the actual mpv player — vo=libmpv so it renders through our FBO, not its own window
        from ..core.tools import ytdlp_path
        _yt = ytdlp_path()
        self.mpv = mpv.MPV(
            vo="libmpv",
            hwdec="auto-safe",
            ytdl=bool(_yt),  # YouTube lane: mpv resolves via the NEWEST yt-dlp on the machine (stale binaries 403)
            **({"script_opts": f"ytdl_hook-ytdl_path={_yt}"} if _yt else {}),
            user_agent="DreamReels/2.0 (+github.com/indicaindependent/dreamreels)",
            keep_open="no",
            cache="yes",
            demuxer_max_bytes="150MiB",
            input_default_bindings=False,
            osc=False,
        )
        self.onUpdate.connect(self.update, Qt.QueuedConnection)

    def on_update(self, ctx=None):
        # called from mpv's render thread -> hop to GUI thread to schedule a repaint
        self.onUpdate.emit()

    def createRenderer(self):
        return MpvRenderer(self)
