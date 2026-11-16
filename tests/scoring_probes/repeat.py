# ruff: noqa: E501
"""Cases for docs/scoring/repeat.md."""
from cases import repeat, table

TABLES = [
    table(
        "repeat-rules",
        repeat("rep-pass", "I", "two copies, two expected", "Total", 2, "<p>Total</p><p>Total</p>"),
        repeat("rep-case", "I", "letter case", "Total", 1, "TOTAL"),
        repeat("rep-spacing", "I", "spacing inside the line", "Total Due", 1, "To tal Due"),
        repeat("rep-cell", "I", "a copy in a table cell", "Total", 1, "<table><tr><td>Total</td></tr></table>"),
        repeat("rep-alt-ignored", "I", "an image description is not a copy", "Total", 1, "<p>Total</p><img alt='Total'>"),
        repeat("rep-line-hyphen", "I", "a word broken at a line end", "developers", 1, "develop- ers"),
        repeat("rep-blocks-glue", "B", "two blocks read as one line", "Total Due", 1, "<p>Total</p><p>Due</p>"),
        repeat("rep-underscore", "B", "an underscore, hyphen or full stop is an edge", "Total", 1, "Total_x"),
        repeat("rep-sign", "B", "an added sign", "4.8", 1, "-4.8"),
        repeat("rep-missing", "P", "a missing copy", "Total", 2, "Total", why=True),
        repeat("rep-extra", "P", "an extra copy", "Total", 2, "<p>Total</p><p>Total</p><p>Total</p>", why=True),
        repeat("rep-longer-word", "P", "only inside a longer word", "Total", 1, "Totals"),
        repeat("rep-digit", "P", "a digit glued on", "Total", 1, "Total1"),
        repeat("rep-typo", "P", "a changed character", "Total", 1, "Tota1"),
        repeat("rep-alt-only", "P", "only in an image description", "Total", 1, "<img alt='Total'>"),
        repeat("rep-overlap", "P", "copies that overlap", "aa", 1, "aaaa"),
        repeat("rep-compound", "P", "hyphenated compound broken at a line end", "self-aware", 1, "self- aware"),
    ),
]
