# ruff: noqa: E501
"""Cases for docs/scoring/order.md."""
from cases import order, table

TABLES = [
    table(
        "order-rules",
        order("ord-pass", "I", "in order, in two blocks", "Alpha", "Beta", "<p>Alpha</p><p>Beta</p>"),
        order("ord-fold", "I", "case and spacing", "Alpha", "Beta", "<p>ALPHA</p><p>b e t a</p>"),
        order("ord-leaders", "I", "leaders", "Alpha", "Beta", "<p>Alpha ......</p><p>Beta</p>"),
        order("ord-line-hyphen", "I", "a word broken at a line end", "developers", "Beta", "<p>develop- ers</p><p>Beta</p>"),
        order("ord-any-pair", "B", "any pair in order decides", "Alpha", "Beta", "<p>Beta</p><p>Alpha</p><p>Beta</p>"),
        order("ord-glued", "B", "no word edge", "Alpha", "Beta", "AlphaBeta"),
        order("ord-overlap", "B", "the two may overlap", "Alpha Beta", "Beta", "Alpha Beta"),
        order("ord-alt", "B", "an image description has a place in the order", "Alpha", "Beta", "<img alt='Alpha'><p>Beta</p>"),
        order("ord-reversed", "P", "reversed", "Alpha", "Beta", "<p>Beta</p><p>Alpha</p>", why=True),
        order("ord-missing", "P", "one string missing", "Alpha", "Beta", "<p>Beta</p>", why=True),
        order("ord-same-start", "P", "both start at the same place", "Alpha", "Alpha Beta", "Alpha Beta"),
        order("ord-table", "P", "table cells in the other order", "Alpha", "Beta", "<table><tr><td>Beta</td><td>Alpha</td></tr></table>"),
        order("ord-transposition", "P", "two letters swapped is 2 edits here", "Alpha", "Beta", "<p>Alhpa</p><p>Beta</p>", md=1),
        order("ord-transposition-2", "I", "the same with 2 edits", "Alpha", "Beta", "<p>Alhpa</p><p>Beta</p>", md=2),
        order("ord-digit-edge", "P", "a digit continues a number", "Total: 40", "ZZZ", "<p>Total: 400</p><p>ZZZ</p>", why=True),
        order("ord-compound", "P", "hyphenated compound broken at a line end", "self-aware", "ZZZ", "<p>self- aware</p><p>ZZZ</p>"),
        order("ord-case-hyphen", "P", "a capital before a line-end hyphen", "R- M", "ZZZ", "<p>r- m</p><p>ZZZ</p>"),
    ),
]
