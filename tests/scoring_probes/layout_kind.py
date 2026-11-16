# ruff: noqa: E501
"""Cases for docs/scoring/layout_kind.md. The line's place is `cases.PLACE`, [0.2, 0.2, 0.6, 0.25]."""
from cases import layout, table

LINE = (0.2, 0.2, 0.6, 0.25)
PAGE = (0, 0, 1, 1)

TABLES = [
    table(
        "layout-rules",
        layout("lay-match", "I", "a block on the line, right label", "text", [("text", LINE)]),
        layout("lay-list-is-text", "I", "a list or form block passes a text test", "text", [("list", LINE)]),
        layout("lay-smallest", "I", "the smallest block that covers half wins", "heading", [("text", PAGE), ("heading", LINE)]),
        layout("lay-half", "I", "a block covering half the place", "text", [("heading", (0.2, 0.2, 0.4, 0.25)), ("text", (0.4, 0.2, 0.6, 0.25))]),
        layout("lay-page-block", "B", "one block over the whole page", "table", [("table", PAGE)]),
        layout("lay-text-unread", "B", "the block's text is not read", "text", [("text", LINE)], text="unrelated words"),
        layout("lay-tie", "B", "equal areas: the first listed wins", "heading", [("heading", LINE), ("text", LINE)]),
        layout("lay-wrong-label", "P", "another label", "text", [("caption", LINE)], why=True),
        layout("lay-heading-list", "P", "a list block for a heading", "heading", [("list", LINE)]),
        layout("lay-small-wrong", "P", "a smaller block with another label inside", "text", [("text", PAGE), ("heading", LINE)]),
        layout("lay-too-little", "P", "a block covering 40% of the place", "text", [("text", (0.2, 0.2, 0.36, 0.25))], why=True),
        layout("lay-none", "P", "no blocks", "text", [], why=True),
    ),
]
