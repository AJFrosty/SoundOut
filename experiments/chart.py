"""Draw the comparison as an SVG, by hand.

No plotting library: the repository already asks for numpy, sounddevice and cryptography,
and a chart drawn once a weekend is not worth a fourth dependency. SVG is text.
"""

import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

WIDTH, HEIGHT = 840, 470
LEFT, RIGHT, TOP, BOTTOM = 66, 210, 58, 54

INK = "#0E1A26"
LINE = "#22384B"
TEXT = "#E8EDF2"
MUTED = "#8AA3B8"

COLOURS = {
    "nothing": "#E8705A",
    "courier": "#C9A227",
    "cellular": "#5B8DEF",
    "soundout": "#F6A623",
    "perfect": "#2E7D74",
}

LABELS = {
    "nothing": "No communications",
    "courier": "A runner every 6 h",
    "cellular": "Phones, back at 48 h",
    "soundout": "SoundOut",
    "perfect": "A perfect link",
}


def write_chart(lines, methods, hours, path="docs/comparison.svg"):
    plot_w = WIDTH - LEFT - RIGHT
    plot_h = HEIGHT - TOP - BOTTOM
    top_hours = max(max(line) for line in lines.values()) * 1.05

    def x(hour):
        return LEFT + hour / hours * plot_w

    def y(value):
        return TOP + plot_h - value / top_hours * plot_h

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" font-family="system-ui,-apple-system,sans-serif">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{INK}"/>',
        f'<text x="{LEFT}" y="26" fill="{TEXT}" font-size="15" font-weight="600">'
        f'How old is the information the base is acting on?</text>',
        f'<text x="{LEFT}" y="45" fill="{MUTED}" font-size="11.5">'
        f'Mean age of the freshest report per shelter, 12 shelters across 30 km. '
        f'Lower is better.</text>',
    ]

    for step in range(0, int(top_hours) + 12, 12):
        if step > top_hours:
            break
        out.append(f'<line x1="{LEFT}" y1="{y(step):.1f}" x2="{LEFT + plot_w}" '
                   f'y2="{y(step):.1f}" stroke="{LINE}" stroke-width="1"/>')
        out.append(f'<text x="{LEFT - 10}" y="{y(step) + 4:.1f}" fill="{MUTED}" '
                   f'font-size="11" text-anchor="end">{step} h</text>')

    for hour in range(0, hours + 1, 12):
        out.append(f'<text x="{x(hour):.1f}" y="{TOP + plot_h + 20}" fill="{MUTED}" '
                   f'font-size="11" text-anchor="middle">{hour}</text>')

    out.append(f'<text x="{LEFT + plot_w / 2:.0f}" y="{HEIGHT - 14}" fill="{MUTED}" '
               f'font-size="11.5" text-anchor="middle">hours after the storm</text>')

    # the line you cannot do worse than: knowing nothing newer than the storm itself
    out.append(f'<line x1="{x(0):.1f}" y1="{y(0):.1f}" x2="{x(top_hours):.1f}" '
               f'y2="{y(top_hours):.1f}" stroke="{MUTED}" stroke-width="1" '
               f'stroke-dasharray="3 4" opacity=".55"/>')

    for name in methods:
        points = " ".join(
            f"{x(minute / 60):.1f},{y(lines[name][minute]):.1f}"
            for minute in range(0, hours * 60, 10)
        )
        thick = 3.2 if name == "soundout" else 1.9
        out.append(f'<polyline points="{points}" fill="none" stroke="{COLOURS[name]}" '
                   f'stroke-width="{thick}" stroke-linejoin="round"/>')

    legend_x = LEFT + plot_w + 26
    out.append(f'<text x="{legend_x}" y="{TOP + 4}" fill="{MUTED}" font-size="10.5" '
               f'letter-spacing="0.08em">AT 24 HOURS</text>')

    for index, name in enumerate(sorted(methods, key=lambda m: lines[m][24 * 60])):
        row = TOP + 28 + index * 42
        out.append(f'<rect x="{legend_x}" y="{row - 8}" width="13" height="3.5" '
                   f'rx="1.75" fill="{COLOURS[name]}"/>')
        out.append(f'<text x="{legend_x + 21}" y="{row - 3}" fill="{TEXT}" '
                   f'font-size="12">{LABELS[name]}</text>')
        out.append(f'<text x="{legend_x + 21}" y="{row + 13}" fill="{MUTED}" '
                   f'font-size="11.5">{lines[name][24 * 60]:.1f} h old</text>')

    out.append(f'<text x="{legend_x}" y="{HEIGHT - 54}" fill="{MUTED}" font-size="10.5">'
               f'dashed: knowing nothing</text>')
    out.append("</svg>")

    destination = _Path(__file__).resolve().parents[1] / path
    destination.write_text("\n".join(out), encoding="utf-8")
    print(f"\n\nwrote {path}")
