"""Config = one TOML file. Read with stdlib tomllib; written by a tiny serializer so we carry no writer dependency."""
from __future__ import annotations
import tomllib
from typing import Any
from .paths import CONFIG_FILE, ensure_dirs

DEFAULTS: dict[str, Any] = {
    "meta": {"version": 2, "setup_complete": False, "theme": "midnight", "input_mode": "all"},
    "sources": {"publicdomain": False, "chan83": False, "toontown": False, "nas": False, "youtube": False},
    "publicdomain": {"strict_pd": True, "decades": [], "genres": [], "people": []},
    "nas": {"mounts": [], "movie_dirs": [], "tv_dirs": [], "music_dirs": [], "keep_all": True},
    "youtube": {"channels": [], "api_key": ""},
    "tmdb": {"read_token": ""},
    "dreamy": {"brain": "auto", "ollama_url": "http://127.0.0.1:11434", "model": "qwen2.5:7b", "openai_base": "", "openai_key": ""},
    "grower": {"enabled": True, "max_rps": 1.0, "verify_concurrency": 2},
}

def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out

def load() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open("rb") as f:
            return _merge(DEFAULTS, tomllib.load(f))
    return _merge(DEFAULTS, {})

def _fmt(v: Any) -> str:
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return repr(v)
    if isinstance(v, str): return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list): return "[" + ", ".join(_fmt(x) for x in v) + "]"
    raise TypeError(f"unsupported TOML value: {type(v)}")

def dumps(cfg: dict[str, Any]) -> str:
    lines = []
    for section, body in cfg.items():
        if not isinstance(body, dict):
            raise TypeError("top-level config values must be tables")
        lines.append(f"[{section}]")
        for k, v in body.items():
            if isinstance(v, dict):
                raise TypeError("nested tables not supported in config")
            lines.append(f"{k} = {_fmt(v)}")
        lines.append("")
    return "\n".join(lines)

def save(cfg: dict[str, Any]) -> None:
    ensure_dirs()
    text = dumps(cfg)
    tomllib.loads(text)  # round-trip proof before we write
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(text)
    tmp.replace(CONFIG_FILE)
