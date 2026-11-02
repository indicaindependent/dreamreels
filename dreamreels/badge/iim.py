"""IIM credit badge: 'Created with Creative Clarity' (Indica Independent Media).
v2.1.0 (Nov 1 2026): redesigned as a small pill (monogram tile + one line of words). The player and wizard draw the pill
natively in QML (components/BadgeCorner.qml); this SVG version is for the README, the project page and the QR fallback.
Accent hue is deterministic from the install id, so every install's pill is tinted slightly differently; the words never change.
Pure SVG, no emoji, no external assets, letters drawn as strokes (no font needed for the mark)."""
from __future__ import annotations
from .. import BADGE_TEXT, __version__
from ..core.ids import badge_seed

def _hsl(h: float, s: float, l: float) -> str:
    return f"hsl({h:.0f} {s:.0f}% {l:.0f}%)"

def iim_mark_svg(a: str = "#E11D48", b: str = "#60A5FA", size: int = 48) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 48 48">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient></defs>'
            '<rect x="1" y="1" width="46" height="46" rx="12" fill="url(#g)"/>'
            '<g fill="none" stroke="#ffffff" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M11.5 15v18"/><path d="M19 15v18"/><path d="M26.5 33V15l5.75 10.5L38 15v18"/></g></svg>')

def badge_svg(seed: int | None = None, height: int = 56) -> str:
    seed = badge_seed() if seed is None else seed
    hue = seed % 360; hue2 = (hue + 150 + (seed >> 8) % 60) % 360
    a, b = _hsl(hue, 78, 58), _hsl(hue2, 70, 62)
    h = height; tile = h * 0.64; pad = (h - tile) / 2; fs = h * 0.34
    text_w = len(BADGE_TEXT) * fs * 0.6          # generous estimate for DejaVu/Inter at this weight, so nothing clips
    w = round(h * 0.28 + tile + h * 0.24 + text_w + h * 0.42)
    mark = iim_mark_svg(a, b).split('>', 1)[1].rsplit('</svg>', 1)[0]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{BADGE_TEXT}">'
            f'<title>{BADGE_TEXT} - Indica Independent Media - DreamReels {__version__}</title>'
            f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{h / 2:.1f}" fill="#151B26" stroke="#ffffff" stroke-opacity="0.12"/>'
            f'<g transform="translate({h * 0.28:.1f} {pad:.1f}) scale({tile / 48:.4f})">{mark}</g>'
            f'<text x="{h * 0.28 + tile + h * 0.24:.1f}" y="{h * 0.5 + fs * 0.36:.1f}" font-family="Inter, Outfit, DejaVu Sans, sans-serif" '
            f'font-weight="600" font-size="{fs:.1f}" fill="#C9D1DC">{BADGE_TEXT}</text></svg>')
