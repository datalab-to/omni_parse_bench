"""Draw the README's two charts, headline against latency and headline against price, as
docs/assets/latency.svg and docs/assets/cost.svg.

    python scripts/charts.py

POINTS holds each plotted system: its headline (the README's results table), its median seconds per page
and its price per 1,000 pages. Update it with the table, then run this again.
"""

from __future__ import annotations

import math
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"

# (name, headline, median seconds per page, USD per 1,000 pages, kind, timing)
# kind: "datalab", "test" (used in creating and verifying tests; drawn hollow) or "other".
# timing: "html" (median of successful, unretried HTML calls) or "page" (the full page: HTML plus layout when
# requested, failures and retries included).
POINTS = [
    ("Gemini 4 Argon", 95.99, 23.3, 49.88, "other", "page"),
    ("Gemini 4 Carbon", 95.67, 28.9, 58.73, "other", "page"),
    ("Datalab accurate", 94.69, 9.0, 7.50, "datalab", "html"),
    ("Datalab balanced", 93.68, 7.2, 3.00, "datalab", "html"),
    ("Gemini 3.8 Flash", 92.54, 21.1, 37.09, "test", "html"),
    ("GPT-6.1 Sol", 91.50, 18.5, 30.95, "other", "page"),
    ("Reducto", 91.09, 6.0, 10.00, "other", "html"),
    ("LlamaParse", 90.77, 32.95, 56.26, "other", "html"),
    ("Claude Opus 5.5", 90.00, 18.5, 68.45, "test", "page"),
    ("Mistral OCR", 89.88, 2.9, 4.00, "other", "html"),
    ("Claude Sonnet 5.5", 88.89, 12.2, 34.29, "test", "html"),
    ("GPT-5.6 Sol", 87.89, 29.2, 94.51, "other", "html"),
    ("Extend", 83.44, 12.7, 33.74, "other", "html"),
    ("Azure", 83.44, 2.4, 5.00, "other", "html"),
]

W, H = 760, 497
LEFT, RIGHT, TOP, BOTTOM = 64, 610, 92, 412
Y0, Y1 = 80, 100
BLUE, INK, MUTED, FAINT, GRID, BG = "#001dbe", "#3a3d44", "#595e66", "#9a9fa7", "#e9ebf0", "#f9fafd"

STYLE = """<style>@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&amp;family=Geist+Mono:wght@400;500&amp;display=swap');
/* Datalab design system -- tokens from svelte/src/styles/datalab-system.css, converted from
   oklch to hex so the figures render identically outside a browser. The system is light-only;
   this guard stops a viewer's auto dark mode inverting them on its own. */
:root{color-scheme:only light}
text{font-family:Geist,ui-sans-serif,system-ui,sans-serif;fill:#0f1217}
.h2{font-weight:500;font-size:18px;letter-spacing:-.09px;font-feature-settings:"ss01" 1}
.cap{font-size:13px;fill:#595e66}
.nm{font-family:"Geist Mono",ui-monospace,"SF Mono",Menlo,monospace;font-size:12.5px;fill:#3a3d44}
.num{font-family:"Geist Mono",ui-monospace,"SF Mono",Menlo,monospace;font-size:12px;fill:#3a3d44;
  font-feature-settings:"tnum" 1}
.halo{paint-order:stroke;stroke:#f9fafd;stroke-width:5px;stroke-linejoin:round}
</style>"""


def y(headline: float) -> float:
    return BOTTOM - (headline - Y0) / (Y1 - Y0) * (BOTTOM - TOP)


def chart(title: str, caption: str, xlabel: str, xs: list[tuple[float, str]], x, value) -> str:
    """One chart: gridlines, ticks `xs` (value, label), the points at x(value(point)), their frontier and
    labels."""
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'font-size="15" role="img" '
        f'aria-label="{title}">',
        STYLE,
        f'<rect width="{W}" height="{H}" fill="{BG}" />',
        f'<text class="h2" x="24" y="38">{title}</text>',
        f'<text class="cap" x="24" y="60">{caption}</text>',
    ]
    for h in range(Y0, Y1 + 1, 5):
        out += [
            f'<line x1="{LEFT}" x2="{RIGHT}" y1="{y(h):.1f}" y2="{y(h):.1f}" stroke="{GRID}" />',
            f'<text class="num" x="{LEFT - 8}" y="{y(h) + 4:.1f}" text-anchor="end">{h}</text>',
        ]
    for v, label in xs:
        out += [
            f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{TOP}" y2="{BOTTOM}" stroke="{GRID}" />',
            f'<text class="num" x="{x(v):.1f}" y="{BOTTOM + 18}" text-anchor="middle">{label}</text>',
        ]
    out += [
        f'<text class="cap" x="{(LEFT + RIGHT) / 2:.0f}" y="452" text-anchor="middle">{xlabel}</text>',
        '<text class="cap" transform="translate(20 252) rotate(-90)" text-anchor="middle">headline</text>',
    ]
    # The frontier: the best headline at each value or less, as a staircase out to the right edge.
    best, stair = -1.0, []
    for p in sorted(POINTS, key=lambda p: (value(p), -p[1])):
        if p[1] > best:
            px = x(value(p))
            if stair:
                stair.append((px, stair[-1][1]))
            stair.append((px, y(p[1])))
            best = p[1]
    stair.append((RIGHT, stair[-1][1]))
    pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in stair)
    out.append(
        f'<polyline points="{pts}" fill="none" stroke="{MUTED}" stroke-width="1.5" stroke-dasharray="4 3" />'
    )
    boxes = [(x(value(p)) - 6, y(p[1]) - 6, x(value(p)) + 6, y(p[1]) + 6) for p in POINTS]
    # Note: the frontier's segments too, so no label sits on the dashed line.
    boxes += [
        (min(a[0], b[0]) - 2, min(a[1], b[1]) - 2, max(a[0], b[0]) + 2, max(a[1], b[1]) + 2)
        for a, b in zip(stair, stair[1:], strict=False)
    ]
    for p in sorted(POINTS, key=lambda p: -p[1]):
        name, headline, kind = p[0], p[1], p[4]
        cx, cy = x(value(p)), y(headline)
        label = name + ("*" if kind == "test" else "")
        cls, colour = ("cap", FAINT) if kind == "test" else ("nm", BLUE if kind == "datalab" else INK)
        width = len(label) * (6.6 if cls == "cap" else 7.6)
        # Note: the first spot, of right, left, above and below, that overlaps no point and no label
        # placed before.
        for dx, dy, anchor in (
            (9, 4, "start"),
            (-9, 4, "end"),
            (9, -9, "start"),
            (9, 16, "start"),
            (-9, -9, "end"),
            (-9, 16, "end"),
        ):
            lx = cx + dx if anchor == "start" else cx + dx - width
            box = (lx, cy + dy - 11, lx + width, cy + dy + 3)
            if (
                box[0] >= LEFT + 2
                and box[2] <= W - 4
                and not any(
                    box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in boxes
                )
            ):
                break
        boxes.append(box)
        dot = (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.5" fill="{BG}" stroke="{FAINT}" stroke-width="1.5" />'
            if kind == "test"
            else f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{colour}" />'
        )
        style = f' style="fill:{colour}"' if colour != INK else ""
        out.append(
            f'<g data-model="{name}" data-headline="{headline}">'
            f"<title>{name}: headline {headline:.2f}</title>{dot}"
            f'<text class="{cls} halo" x="{cx + dx:.1f}" y="{cy + dy:.1f}" text-anchor="{anchor}"{style}>'
            f"{label}</text></g>"
        )
    out.append(
        '<text class="cap" x="24" y="486">* Used in creating and verifying at least some tests.</text>'
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    lat = lambda s: LEFT + s / 35 * (RIGHT - LEFT)
    (ASSETS / "latency.svg").write_text(
        chart(
            "Headline against latency",
            "Median seconds per page",
            "median seconds per page",
            [(v, str(v)) for v in range(0, 36, 5)],
            lat,
            lambda p: p[2],
        )
    )
    cost = lambda c: LEFT + math.log10(c) / 2 * (RIGHT - LEFT)
    (ASSETS / "cost.svg").write_text(
        chart(
            "Headline against cost",
            "Price per 1,000 pages",
            "dollars per 1,000 pages, log scale",
            [(v, str(v)) for v in (1, 2, 5, 10, 20, 50, 100)],
            cost,
            lambda p: p[3],
        )
    )


if __name__ == "__main__":
    main()
