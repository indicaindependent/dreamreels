"""
Embedded mpv render object for DreamReels (v1 technique, proven on GNOME Wayland + Intel UHD 770).
Renders libmpv INTO the QML scene via QQuickFramebufferObject + the mpv render API,
so video and QML controls share ONE window (fixes the black-screen / two-window bug
under mutter/Wayland). Industry-standard Qt+mpv integration.
"""
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtQuick import QQuickFramebufferObject
import mpv, logging
log = logging.getLogger("dreamreels.player")


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
            try:
                self._ctx = mpv.MpvRenderContext(
                    self._obj.mpv,
                    "opengl",
                    opengl_init_params={"get_proc_address": mpv.MpvGlGetProcAddressFn(_get_proc_address)},
                )
                self._ctx.update_cb = self._obj.on_update
                log.info("mpv render context created (%dx%d)", size.width(), size.height())
            except Exception as e:
                log.error("mpv render context FAILED: %s - video will not draw", e)
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
        # Sep-2026 playback tuning for an Intel iGPU under the libmpv render API. Each option is applied on its
        # own and logged, so an option this libmpv build rejects is a log line, never a dead player.
        tuned = {
            "hwdec": "auto-safe",                 # VA-API on Intel (iHD); measured live as hwdec-current in the observatory
            "hwdec-codecs": "all",                # let AV1/VP9/HEVC/H.264 all take the hardware path
            "vd-lavc-dr": "yes",                  # direct rendering into GPU-visible buffers
            "scale": "ewa_lanczossharp",          # high-quality upscaler for 480p/576p public-domain film
            "cscale": "ewa_lanczossharp",
            "dscale": "mitchell",
            "deband": "yes",                      # old telecine/VHS-era masters band badly
            "deband-iterations": "2",
            "dither-depth": "auto",
            "video-sync": "display-resample",     # lock to the TV refresh, resample audio
            "interpolation": "yes",
            "tscale": "oversample",               # cheap, artefact-free frame timing (no soap-opera blend)
            "demuxer-readahead-secs": "90",
            "cache-secs": "120",
            "stream-buffer-size": "4MiB",
            "audio-channels": "auto-safe",
            "audio-pitch-correction": "yes",
            "ytdl-format": "bestvideo[height<=2160]+bestaudio/best",
        }
        applied, rejected = [], []
        for k, v in tuned.items():
            try: self.mpv[k] = v; applied.append(k)
            except Exception as e: rejected.append(f"{k}={v} ({e.__class__.__name__})")
        log.info("mpv tuning applied: %s", ", ".join(applied))
        if rejected: log.warning("mpv tuning REJECTED by this libmpv: %s", "; ".join(rejected))
        self.onUpdate.connect(self.update, Qt.QueuedConnection)
        log.info("libmpv %s ready (vo=libmpv, ytdl=%s)", getattr(mpv, "MPV_VERSION", "?"), bool(_yt))
        @self.mpv.event_callback("end-file")
        def _end(ev):
            try: d = ev.as_dict() if hasattr(ev, "as_dict") else {}
            except Exception: d = {}
            log.info("mpv end-file: %s", {k: (v.decode() if isinstance(v, bytes) else v) for k, v in (d.get("event") or d).items()} if isinstance(d, dict) else d)
        @self.mpv.event_callback("file-loaded")
        def _loaded(ev): log.info("mpv file-loaded")
        @self.mpv.property_observer("video-format")
        def _vf(_n, v): log.info("mpv video-format -> %s", v)

    def on_update(self, ctx=None):
        # called from mpv's render thread -> hop to GUI thread to schedule a repaint
        self.onUpdate.emit()

    def createRenderer(self):
        return MpvRenderer(self)
