"""Dreamy - the DreamReels mascot. A friendly film-reel character drawn as pure SVG with five poses.
Deterministic, theme-tinted, no external assets, no emoji. Same drawing rules as the badge: one path
per shape, numeric tokens never concatenated (Sep 5 lesson)."""
from __future__ import annotations

POSES = ("idle", "think", "point", "celebrate", "oops")

def dreamy_svg(pose: str = "idle", accent: str = "#E11D48", accent2: str = "#60A5FA", ink: str = "#0B0F17", size: int = 360) -> str:
    pose = pose if pose in POSES else "idle"
    body = "#F5F7FA"; cheek = accent; reel = ink
    # eyes
    if pose == "think":
        eyes = '<ellipse cx="146" cy="132" rx="9" ry="12" fill="#0B0F17"/><ellipse cx="214" cy="128" rx="9" ry="12" fill="#0B0F17"/><path d="M128 108 q18 -10 36 -2" stroke="#0B0F17" stroke-width="6" fill="none" stroke-linecap="round"/>'
        mouth = '<path d="M164 172 q16 -6 32 4" stroke="#0B0F17" stroke-width="6" fill="none" stroke-linecap="round"/>'
    elif pose == "celebrate":
        eyes = '<path d="M134 128 q12 -14 24 0" stroke="#0B0F17" stroke-width="7" fill="none" stroke-linecap="round"/><path d="M202 128 q12 -14 24 0" stroke="#0B0F17" stroke-width="7" fill="none" stroke-linecap="round"/>'
        mouth = '<path d="M150 166 q30 34 60 0" stroke="#0B0F17" stroke-width="6" fill="#0B0F17" stroke-linejoin="round"/>'
    elif pose == "oops":
        eyes = '<circle cx="146" cy="132" r="13" fill="#0B0F17"/><circle cx="214" cy="132" r="13" fill="#0B0F17"/><circle cx="150" cy="127" r="4" fill="#fff"/><circle cx="218" cy="127" r="4" fill="#fff"/>'
        mouth = '<ellipse cx="180" cy="176" rx="12" ry="9" fill="#0B0F17"/>'
    else:
        eyes = '<circle cx="146" cy="132" r="11" fill="#0B0F17"/><circle cx="214" cy="132" r="11" fill="#0B0F17"/><circle cx="150" cy="128" r="3.5" fill="#fff"/><circle cx="218" cy="128" r="3.5" fill="#fff"/>'
        mouth = '<path d="M156 168 q24 22 48 0" stroke="#0B0F17" stroke-width="6" fill="none" stroke-linecap="round"/>'
    # arms
    if pose == "point":
        arms = f'<path d="M112 236 q-40 10 -52 46" stroke="{body}" stroke-width="22" fill="none" stroke-linecap="round"/><path d="M248 236 q60 -30 88 -66" stroke="{body}" stroke-width="22" fill="none" stroke-linecap="round"/><circle cx="338" cy="166" r="16" fill="{body}"/>'
    elif pose == "celebrate":
        arms = f'<path d="M112 236 q-46 -26 -52 -80" stroke="{body}" stroke-width="22" fill="none" stroke-linecap="round"/><path d="M248 236 q46 -26 52 -80" stroke="{body}" stroke-width="22" fill="none" stroke-linecap="round"/><circle cx="60" cy="152" r="16" fill="{body}"/><circle cx="300" cy="152" r="16" fill="{body}"/>'
    elif pose == "think":
        arms = f'<path d="M112 236 q-40 10 -52 46" stroke="{body}" stroke-width="22" fill="none" stroke-linecap="round"/><path d="M248 236 q10 -40 -30 -56" stroke="{body}" stroke-width="22" fill="none" stroke-linecap="round"/><circle cx="214" cy="178" r="15" fill="{body}"/>'
    elif pose == "oops":
        arms = f'<path d="M112 236 q-20 -50 20 -90" stroke="{body}" stroke-width="22" fill="none" stroke-linecap="round"/><path d="M248 236 q20 -50 -20 -90" stroke="{body}" stroke-width="22" fill="none" stroke-linecap="round"/>'
    else:
        arms = f'<path d="M112 236 q-40 10 -52 46" stroke="{body}" stroke-width="22" fill="none" stroke-linecap="round"/><path d="M248 236 q40 10 52 46" stroke="{body}" stroke-width="22" fill="none" stroke-linecap="round"/><circle cx="60" cy="286" r="16" fill="{body}"/><circle cx="300" cy="286" r="16" fill="{body}"/>'
    sprockets = "".join(f'<circle cx="{180 + 92 * __import__("math").cos(a):.1f}" cy="{140 + 92 * __import__("math").sin(a):.1f}" r="9" fill="{body}"/>' for a in [i * 3.14159 / 4 for i in range(8)])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 360" width="{size}" height="{size}" role="img" aria-label="Dreamy, the DreamReels mascot">
<title>Dreamy</title>
<ellipse cx="180" cy="336" rx="96" ry="12" fill="{ink}" opacity="0.25"/>
<rect x="118" y="212" width="124" height="112" rx="52" fill="{body}"/>
<rect x="150" y="238" width="60" height="44" rx="12" fill="{accent2}" opacity="0.9"/>
<rect x="158" y="246" width="44" height="28" rx="6" fill="{ink}"/>
<path d="M164 260 l12 -7 v14 z" fill="{body}"/>
{arms}
<circle cx="180" cy="140" r="112" fill="{reel}"/>
<circle cx="180" cy="140" r="98" fill="{body}"/>
<circle cx="180" cy="140" r="86" fill="{reel}" opacity="0.06"/>
{sprockets}
<circle cx="180" cy="140" r="14" fill="{ink}" opacity="0.15"/>
<circle cx="132" cy="160" r="12" fill="{cheek}" opacity="0.55"/><circle cx="228" cy="160" r="12" fill="{cheek}" opacity="0.55"/>
{eyes}
{mouth}
</svg>'''
