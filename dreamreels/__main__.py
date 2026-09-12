"""CLI entry. No config -> wizard. Subcommands are explicit so forkers can script them."""
from __future__ import annotations
import argparse, sys
from . import __version__, GITHUB_URL
from .core import config as cfgmod, db, log as logmod

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dreamreels", description=f"DreamReels {__version__}  {GITHUB_URL}")
    ap.add_argument("--version", action="version", version=f"dreamreels {__version__}")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("doctor", help="measure the environment and print what is missing")
    sub.add_parser("wizard", help="run Dreamy setup")
    sub.add_parser("player", help="start the player")
    sub.add_parser("migrate-db", help="create/upgrade the database")
    b = sub.add_parser("badge", help="write the IIM badge SVG"); b.add_argument("out")
    sub.add_parser("config", help="print effective config")
    sub.add_parser("build", help="run the Build step from a terminal (same code the wizard runs)")
    g = sub.add_parser("grow", help="run the library grower"); g.add_argument("--discover", action="store_true"); g.add_argument("--work", type=int, default=0); g.add_argument("--limit", type=int, default=40); g.add_argument("--status", action="store_true")
    m = sub.add_parser("import-v1", help="import a DreamReel v1 library"); m.add_argument("--db", default="/opt/dreamreel/dreamreel.db")
    v = sub.add_parser("verify-url", help="decode-proof one URL"); v.add_argument("url")
    d = sub.add_parser("dreamy", help="ask Dreamy from the terminal"); d.add_argument("text", nargs="+")
    sub.add_parser("apply", help="root half of setup (sudo)")
    a, rest = ap.parse_known_args(argv)
    log = logmod.setup()
    if a.cmd == "migrate-db":
        print(f"schema v{db.migrate()} at {db.DB_FILE}"); return 0
    if a.cmd == "badge":
        from .badge.iim import badge_svg
        open(a.out, "w").write(badge_svg()); print(a.out); return 0
    if a.cmd == "build":
        from .wizard.build import run_build; cfg = cfgmod.load(); r = run_build(cfg, log=print, launch_player=not getattr(a, "no_player", False)); return 0 if r["ok"] else 2
    if a.cmd == "grow":
        from . import grower; cfg = cfgmod.load(); db.migrate()
        if a.discover: print("seeded", grower.discover(cfg, a.limit))
        if a.work: print("worked", grower.work(cfg, a.work))
        print(grower.status()); return 0
    if a.cmd == "import-v1":
        from .migrate.from_v1 import run as imp; print(imp(a.db)); return 0
    if a.cmd == "doctor":
        from .doctor import run as doc; return doc()
    if a.cmd == "apply":
        from .apply import main as ap_main; return ap_main(rest)
    if a.cmd == "dreamy":
        from .dreamy import agent; import json as _j; cfg = cfgmod.load(); db.migrate(); print(_j.dumps(agent.ask(cfg, " ".join(a.text)), indent=1, ensure_ascii=False)); return 0
    if a.cmd == "verify-url":
        from .sources.archive_org import verify_decode; print(verify_decode(a.url)); return 0
    if a.cmd == "config":
        print(cfgmod.dumps(cfgmod.load())); return 0
    cfg = cfgmod.load()
    if a.cmd == "wizard" or (a.cmd is None and not cfg["meta"]["setup_complete"]):
        from .wizard import run as wizard_run
        return wizard_run.main(cfg, rest)
    from .player import run as player_run
    return player_run.main(cfg, rest)

if __name__ == "__main__":
    sys.exit(main())
