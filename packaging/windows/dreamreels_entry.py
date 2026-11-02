"""PyInstaller entry point. Must stay a top-level script with an ABSOLUTE import: freezing the package's own
__main__.py fails at start with 'attempted relative import with no known parent package'."""
import os, sys

def _smoke(out_path: str) -> int:
    """CI self-check for the windowed exe (it has no console, so stdout is not usable).
    Writes one line per check to out_path and exits non-zero if any check fails."""
    lines, ok = [], True
    def check(name, good, note=""):
        nonlocal ok; ok = ok and bool(good); lines.append(("OK   " if good else "FAIL ") + name + (f"  {note}" if note else ""))
    try:
        from dreamreels import __version__; check("version", __version__.startswith("2."), f"dreamreels {__version__}")
        from dreamreels.core import paths
        qml = paths.REPO_ROOT / "dreamreels" / "ui" / "qml" / "Main.qml"
        check("bundled QML", qml.is_file(), str(qml)); check("bundled assets", (paths.ASSETS / "app" / "dreamreels.ico").is_file(), str(paths.ASSETS))
        check("lane seeds", (paths.REPO_ROOT / "dreamreels" / "data" / "chan83_seed.json").is_file())
        from dreamreels.player import mpv_widget
        check("libmpv loads", mpv_widget.mpv is not None, mpv_widget.MPV_IMPORT_ERROR or getattr(mpv_widget.mpv, "__version__", ""))
        import dreamreels.player.run, dreamreels.wizard.run, dreamreels.wizard.win_shortcuts  # noqa: F401
        check("player + wizard import", True)
    except Exception as e:
        check("import", False, repr(e))
    with open(out_path, "w", encoding="utf-8") as f: f.write("\n".join(lines) + "\n")
    return 0 if ok else 1

if __name__ == "__main__":
    if os.environ.get("DREAMREELS_SMOKE_OUT"):
        sys.exit(_smoke(os.environ["DREAMREELS_SMOKE_OUT"]))
    from dreamreels.__main__ import main
    if len(sys.argv) == 1:      # double-clicked: open the player (it shows the wizard on first run)
        sys.argv.append("player")
    sys.exit(main())
