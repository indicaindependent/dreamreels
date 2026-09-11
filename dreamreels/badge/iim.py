"""Dynamic IIM badge: 'Created with Creative Clarity'. Deterministic from the install id -
accent hue, guilloche ring phase and dot pattern differ per install, text and mark never do.
Pure SVG, no emoji, no external assets. Renders identically in QML Image and in a browser."""
from __future__ import annotations
import math
from .. import BADGE_TEXT, GITHUB_URL, __version__
from ..core.ids import badge_seed

def _hsl(h: float, s: float, l: float) -> str:
    return f"hsl({h:.0f} {s:.0f}% {l:.0f}%)"

def badge_svg(seed: int | None = None, width: int = 420) -> str:
    seed = badge_seed() if seed is None else seed
    hue = seed % 360
    hue2 = (hue + 150 + (seed >> 8) % 60) % 360
    phase = (seed >> 16) % 360
    dots = 18 + (seed >> 20) % 10
    h = round(width * 0.31)
    r = h * 0.36
    cx, cy = h * 0.5, h * 0.5
    ring = []
    for i in range(dots):
        a = math.radians(phase + i * 360 / dots)
        ring.append(f'<circle cx="{cx + r*math.cos(a):.1f}" cy="{cy + r*math.sin(a):.1f}" r="{h*0.022:.1f}" fill="{_hsl(hue2,70,62)}" opacity="{0.35 + 0.65*((i*7)%dots)/dots:.2f}"/>')
    acc, acc2 = _hsl(hue, 78, 58), _hsl(hue2, 70, 62)
    fs1, fs2, fs3 = h * 0.185, h * 0.13, h * 0.11
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h}" viewBox="0 0 {width} {h}" role="img" aria-label="{BADGE_TEXT}">
<title>{BADGE_TEXT} - Indica Independent Media</title>
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{acc}"/><stop offset="1" stop-color="{acc2}"/></linearGradient></defs>
<rect x="0.5" y="0.5" width="{width-1}" height="{h-1}" rx="{h*0.18:.1f}" fill="#0f1117" stroke="url(#g)" stroke-width="1.5"/>
<g>{''.join(ring)}<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r*0.62:.1f}" fill="none" stroke="url(#g)" stroke-width="{h*0.05:.1f}"/>
<path d="M{cx-r*0.28:.1f} {cy:.1f} l{r*0.22:.1f} {r*0.22:.1f} l{r*0.36:.1f} -{r*0.44:.1f}" fill="none" stroke="#f5f7fa" stroke-width="{h*0.05:.1f}" stroke-linecap="round" stroke-linejoin="round"/></g>
<text x="{h*1.05:.0f}" y="{h*0.42:.0f}" font-family="Inter, Outfit, DejaVu Sans, sans-serif" font-weight="700" font-size="{fs1:.0f}" fill="#f5f7fa">{BADGE_TEXT}</text>
<text x="{h*1.05:.0f}" y="{h*0.66:.0f}" font-family="Inter, DejaVu Sans, sans-serif" font-weight="500" font-size="{fs2:.0f}" fill="{acc}">INDICA INDEPENDENT MEDIA</text>
<text x="{h*1.05:.0f}" y="{h*0.87:.0f}" font-family="Inter, DejaVu Sans, sans-serif" font-weight="400" font-size="{fs3:.0f}" fill="#9aa3b2">DreamReels {__version__} · {GITHUB_URL.replace('https://','')}</text>
</svg>'''
