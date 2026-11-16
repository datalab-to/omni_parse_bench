# ruff: noqa: E501
"""Cases for docs/scoring/page_near_empty.md."""
from cases import near_empty, table

TABLES = [
    table(
        "near-empty-rules",
        near_empty("ne-blank", "I", "a page with no text", 0, ""),
        near_empty("ne-spaces", "I", "spaces and line breaks are not counted", 0, "<p> </p><p>\n</p><br>"),
        near_empty("ne-alt", "I", "an image description is not counted", 0, "<p></p><img alt='stamp'>"),
        near_empty("ne-folio", "I", "a page number within the limit", 2, "<p>12</p>"),
        near_empty("ne-spacing", "I", "spaces inside the text do not count", 2, "<p>1 2</p>"),
        near_empty("ne-image-only", "B", "an image is not read, however much it shows", 0, "<img src='scan.png'>"),
        near_empty("ne-one-over", "P", "one character over the limit", 2, "<p>123</p>", why=True),
        near_empty("ne-invisible", "I", "an invisible format character (a zero-width space, a byte-order mark, a soft hyphen)", 0, "<p>\u200b\ufeff\u00ad</p>"),
        near_empty("ne-empty-math", "I", "an empty math element", 0, "<math></math>"),
        near_empty("ne-empty-item", "I", "an `<li>` holding only white space", 0, "<ol><li></li></ol>"),
        near_empty("ne-hidden-input", "I", "a hidden input", 0, "<input type=hidden value=v>"),
        near_empty("ne-item-number", "P", "a list item is text, with its number", 0, "<ol><li>x</li></ol>", why=True),
        near_empty("ne-text", "P", "a transcribed line", 0, "Total due", why=True),
        near_empty("ne-cell", "P", "text in a table cell", 0, "<table><tr><td>5</td></tr></table>", why=True),
    ),
]
