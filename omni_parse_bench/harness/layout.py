"""A vendor's layout blocks as the `blocks` output: `{label, bbox, text}`, boxes from 0 to 1.

Every vendor names its block types its own way. Each adapter states how its types map onto
`views.LABELS` in a table, and `label` looks a type up in it: a type the table doesn't have fails
the page, so a new type is decided by a person rather than guessed. The label is what a
`layout_kind` test grades (docs/providers.md has every vendor's table).

`guess` is for a vendor with no fixed set of types, an LLM, whose types are free text.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from . import errors

FIGURE = re.compile(r"fig|pic|image|graphic|photo|chart|drawing|diagram|logo", re.I)
TABLE = re.compile(r"table", re.I)
FORM = re.compile(r"form|key.?value", re.I)


def label(labels: Mapping[str, str], vendor_type: str) -> str:
    """A vendor's block type as one of views.LABELS, from the adapter's table."""
    if vendor_type not in labels:
        raise errors.VendorError(f"block type {vendor_type!r} isn't in the adapter's LABELS: decide its "
                                 f"label and add it (docs/providers.md)", status=200)
    return labels[vendor_type]


# Note: tried in order, so a "table caption" is a caption, a "running title" page furniture, and a
# "section header" a heading.
GUESSES = (("caption", re.compile(r"caption|legend", re.I)), ("footnote", re.compile(r"foot.?note", re.I)),
           ("page_furniture",
            re.compile(r"page.?(?:header|footer|number)|running|furniture|^(?:header|footer)$", re.I)),
           ("heading", re.compile(r"title|heading|section.?head", re.I)),
           ("list", re.compile(r"list", re.I)), ("equation", re.compile(r"equation|formula|math", re.I)),
           ("code", re.compile(r"code", re.I)), ("figure", FIGURE), ("form", FORM), ("table", TABLE))


def guess(vendor_type: str) -> str:
    """A free-text block type as one of views.LABELS, by the words in it (GUESSES, in order)."""
    return next((k for k, r in GUESSES if r.search(vendor_type)), "text")


def block(label: str, box: Sequence[float], frame: Sequence[float], text: str) -> dict:
    """One block, its box `[x0, y0, x1, y1]` divided by the frame `(width, height)` and clamped."""
    w, h = frame
    scale = (w, h, w, h)
    bbox = [min(1.0, max(0.0, float(x) / n)) for x, n in zip(box, scale, strict=True)]
    return {"label": label, "bbox": bbox, "text": text}
