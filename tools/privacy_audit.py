"""Scan a DreamReels tree for private details before you publish a fork.
    python3 tools/privacy_audit.py [path] [--extra word ...]
Exit 0 = clean, 1 = hits (each printed as file:line: match). Patterns cover private IPs, MAC addresses, emails,
tokens/keys that look real, home paths and SMB shares. Add your own hostnames/usernames with --extra.
Run it once against a file you planted on purpose, so you know it can say no."""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path

PATTERNS = {
    "private IPv4": r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b",
    "MAC address": r"\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b",
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "home path": r"(?:/home/[a-z_][a-z0-9_-]*/|C:\\\\?Users\\\\?[A-Za-z0-9_.-]+)",
    "SMB share": r"(?:smb|cifs)://[^\s\"']+",
    "key-like secret": r"(?i)(?:api[_-]?key|token|secret|password)\s*[=:]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']",
    "bearer/JWT": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.",
}
ALLOW = [r"/home/dreamreels/", r"127\.0\.0\.1", r"user@example\.com", r"noreply@github\.com"]
SKIP_DIRS = {".git", "__pycache__", "dist", "build", ".venv", "venv"}
TEXT_EXT = {".py", ".qml", ".js", ".json", ".md", ".toml", ".txt", ".sh", ".yml", ".yaml", ".spec", ".cfg", ".ini", ".svg", ""}


def scan(root: Path, extra: list[str]) -> list[str]:
    pats = {k: re.compile(v) for k, v in PATTERNS.items()}
    for w in extra:
        pats[f"extra:{w}"] = re.compile(re.escape(w), re.I)
    allow = [re.compile(a) for a in ALLOW]
    hits = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.parts) or p.suffix.lower() not in TEXT_EXT:
            continue
        if p.name == "privacy_audit.py":   # its own pattern table would match itself
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for name, rx in pats.items():
                for m in rx.finditer(line):
                    if any(a.search(m.group(0)) for a in allow):
                        continue
                    hits.append(f"{p.relative_to(root)}:{n}: [{name}] {m.group(0)[:80]}")
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--extra", nargs="*", default=[])
    a = ap.parse_args(argv)
    hits = scan(Path(a.path), a.extra)
    for h in hits:
        print(h)
    print(f"{len(hits)} hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
