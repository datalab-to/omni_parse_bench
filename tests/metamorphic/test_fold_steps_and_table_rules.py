# ruff: noqa: E501
"""Relations of the fold steps no relation checked, of table_cell's `section`, `row_groups`, `left_heading` and
floor ratio, and of layout_kind's list-or-form-as-text rule (M126 to M137)."""
from __future__ import annotations

import string

from hypothesis import given
from hypothesis import strategies as st

from metamorphic.common import HOLDS, escaped, passes, relation
from omni_parse_bench import views
from omni_parse_bench.scorers.unit_tests import runners

# ------------------------------------------------------------------------------------- fold steps


def text_test(s: str, max_diffs: int = 0) -> runners.Present:
    return runners.Present(runners.Text(s, max_diffs))


def reads(gold: str, page: str, max_diffs: int = 0) -> bool:
    """Whether a text test of `gold` passes on a page whose one paragraph is `page`."""
    return passes(text_test(gold, max_diffs), f"<p>{escaped(page)}</p>")


NUMBERS = ["1,240", "12", "7.5", "3,000.25"]
SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
LETTERS = st.text(string.ascii_lowercase, min_size=2, max_size=5)


@relation(HOLDS, domain="4 numbers x 10 superscript digits, a text test and a number test, the digit set apart "
                        "and the digit glued")
def test_a_superscript_digit_after_a_digit_is_set_apart_from_it():
    """A superscript digit right after a digit is not part of the number: a text test or a number test for
    `1,240` passes on `1,240¹`, a text test for the number with the digit glued on (`1,2401`) fails on it, and
    one for the number, a space and the digit passes. [M126]
    Why it matters for a score: a footnote marker set as a superscript after a figure (`1,240¹`) must not turn
    the figure into another one (`1,2401`), nor hide the figure it follows."""
    for n in NUMBERS:
        for sup in SUPERSCRIPTS:
            digit = str(SUPERSCRIPTS.index(sup))
            page = f"{n}{sup}"
            # Given a number followed by a superscript digit; When the number is asked for; Then it is found
            assert reads(n, page), (n, sup)
            assert passes(runners.Present(runners.Number(n)), f"<p>{page}</p>"), (n, sup)
            # And the number, a space and the digit is found, but the digits glued are not
            assert reads(f"{n} {digit}", page), (n, sup)
            assert not reads(f"{n}{digit}", page), (n, sup)
            # And the other way: a test written with the superscript passes on the spaced page, not the glued one
            assert reads(page, f"{n} {digit}"), (n, sup)
            assert not reads(page, f"{n}{digit}"), (n, sup)


WRITTEN = ["​", "‍", "­", "⁠", "‎", "‪", "⁦", "﻿", "", ""]


@relation(HOLDS, domain="3 words x every position x 10 invisible or private-use characters, 4 visible ones "
                        "put there instead, and the Arabic number sign")
def test_invisible_and_private_use_characters_inside_a_word_change_no_text_verdict():
    """A zero-width space or joiner, a soft hyphen, a word joiner, a bidi control, a byte-order mark or a
    private-use character put anywhere inside a word leaves a `present` text test for the word passing; a
    visible character put in the same place fails it; the visible number signs that are format characters (the
    Arabic `\u0600`) are kept, so a test that has one fails on a page without it. [M127]
    Why it matters for a score: a text layer carries these characters unseen; a reader sees the word whole.
    Credit: the documented rule 'private-use characters and format characters ... removed' (internals.md)."""
    for word in ["Acme", "Total due", "Müller"]:
        for i in range(1, len(word)):
            if word[i - 1] == " " or word[i] == " ":
                continue
            # Given a word and an invisible character put inside it; When the word is asked for; Then it is found
            for hidden in WRITTEN:
                assert reads(word, word[:i] + hidden + word[i:]), (word, i, hidden)
                assert reads(word[:i] + hidden + word[i:], word), (word, i, hidden)    # and the other way
            # But a visible character in its place fails
            for shown in ["|", "x", "9", "~"]:
                assert not reads(word, word[:i] + shown + word[i:]), (word, i, shown)
    # And a visible format character (the Arabic number sign, which draws under its digits) is kept: a test
    # that has it fails on a page without it, and passes on a page with it
    assert reads("\u0600123", "\u0600123")
    assert not reads("\u0600123", "123")


SINGLE = ["‘", "’", "‚", "‛", "ʼ", "`", "´", "′", "ꞌ", "Ꞌ", "ˈ"]
DOUBLE = ["“", "”", "„", "‟", "«", "»", "″"]


@relation(HOLDS, domain="11 single (the acute accent only inside a word; the saltillo and the IPA stress mark included) and 7 double quote glyphs x 2 words x both directions, TeX's two-glyph "
                        "quotes, and the two families set against each other")
def test_quote_glyphs_of_a_family_read_as_one_quote():
    """A `present` text test with an ASCII `'` or `"` passes on a page that writes any glyph of its family
    (curly, low, reversed, prime, grave, saltillo, the IPA stress mark, and the acute accent between two letters, for `'`; guillemets and the
    double prime for `"`), and a test written with the glyph passes on the ASCII page; two of the single quotes in a row (`''`,
    ``` `` ```) read as the double quote; the single and the double family do not read as each other. [M128]
    Why it matters for a score: a system may print typographic quotes where the gold has plain ones, or the
    reverse; it is graded on the words."""
    for word in ["don't", "ship"]:
        # Note: a `´` after a letter is a spacing accent, and a quote only between two letters (`don´t`)
        for glyph in [g for g in SINGLE if "'" in word or g != "\u00b4"]:
            quoted = word.replace("'", glyph) if "'" in word else f"{glyph}{word}{glyph}"
            plain = word if "'" in word else f"'{word}'"
            assert reads(plain, quoted), (glyph, word)
            assert reads(quoted, plain), (glyph, word)
        for glyph in DOUBLE:
            assert reads(f'"{word}"', f"{glyph}{word}{glyph}"), (glyph, word)
            assert reads(f"{glyph}{word}{glyph}", f'"{word}"'), (glyph, word)
    # Given TeX's double quote, written with two single quotes or two grave accents
    for page in ["``ship''", "''ship''", "`'ship'`", "‘’ship‘’"]:
        # Then it is read as a double quote
        assert reads('"ship"', page), page
        assert reads(page, '"ship"'), page    # and the other way
    # But a single quote is not a double quote, and the families do not read as each other
    assert not reads('"ship"', "'ship'")
    assert not reads("``ship''", "'ship'")
    assert not reads("'ship'", '"ship"')
    assert not reads("‘ship’", "“ship”")


ARROWS = {"→": "⇒➡⟶↦➔➜⇨", "←": "⇐⬅⟵↤",
          "↑": "⇑⬆↥", "↓": "⇓⬇↧"}


@relation(HOLDS, domain="4 arrow directions x 3 to 7 members of each family x both directions, and the four "
                        "directions set against each other")
def test_arrow_glyphs_of_a_family_read_as_one_arrow():
    """A `present` text test with a plain arrow (`→ ← ↑ ↓`) passes on a page that writes another arrow of its
    family (double, heavy, long, white, mapsto), and the other way round; an arrow of another direction does
    not read as it. [M129]
    Why it matters for a score: a table or a flow chart is drawn with whatever arrow the font offers; the
    gold and the system need not agree on its weight."""
    for plain, members in ARROWS.items():
        for member in members:
            # Given a plain arrow and a member of its family; Then each reads as the other
            assert reads(f"a {plain} b", f"a {member} b"), (plain, member)
            assert reads(f"a {member} b", f"a {plain} b"), (plain, member)
            # But no other direction does
            for other in ARROWS.keys() - {plain}:
                assert not reads(f"a {plain} b", f"a {other} b"), (plain, other)


FULL_WIDTH = {"。": ".", "、": ",", "，": ",", "．": ".", "：": ":", "；": ";", "！": "!", "？": "?", "（": "(",
              "）": ")", "％": "%", "＝": "="}


@relation(HOLDS, domain="12 full-width marks x 3 words x both directions, and each against another ASCII mark")
def test_full_width_punctuation_reads_as_its_ascii_mark():
    """A `present` text test with an ASCII mark (`. , : ; ! ? ( ) % =`) passes on a page that writes its
    full-width or ideographic form (`。 、 ， ． ： ； ！ ？ （ ） ％ ＝`), and the other way round; a different ASCII
    mark fails. [M130]
    Why it matters for a score: a Chinese or Japanese page, or a system that sets Latin text in a CJK font,
    writes these marks; the gold is graded on the same characters."""
    for wide, ascii_ in FULL_WIDTH.items():
        other = "?" if ascii_ != "?" else "!"
        for a, b in [("abc", "def"), ("12", "34"), ("x", "y")]:
            # Given a mark in its two forms between two words; Then each reads as the other
            assert reads(f"{a}{ascii_}{b}", f"{a}{wide}{b}"), (wide, a, b)
            assert reads(f"{a}{wide}{b}", f"{a}{ascii_}{b}"), (wide, a, b)
            # But another mark does not
            assert not reads(f"{a}{other}{b}", f"{a}{wide}{b}"), (wide, a, b)


@relation(HOLDS, domain="4 raised-decimal pages, and 5 pages where the dot separates or multiplies (3) or is a CJK dot "
                        "between digits (2), both directions")
def test_a_raised_decimal_point_reads_as_a_point_and_other_middle_dots_stay():
    """A middle dot or bullet operator that starts a decimal (`·79`, `p<·05`) or follows a digit and precedes
    one (`3·14`) reads as a decimal point, so a text test with `.79`, `p<.05` or `3.14` passes on it and the
    other way round; one after a letter or a closing bracket (`A·1`, `(a)·1`) is a separator and stays, so the
    test with a point fails; so does a Japanese `・` between two digits (`3・11`). [M131]
    Why it matters for a score: a scan prints a decimal point raised, and a text layer keeps the raised dot;
    a product or a list separator written with the same glyph is not a decimal."""
    for point, raised in [(".79", "·79"), ("p<.05", "p<·05"), ("3.14", "3·14"), ("x = .5", "x = ∙5")]:
        # Given a decimal written with a point and with a raised dot; Then each reads as the other
        assert reads(point, raised), (point, raised)
        assert reads(raised, point), (point, raised)
    # But a middle dot after a letter or a closing bracket, or a CJK dot between digits, is no point
    for point, kept in [("A.1", "A·1"), ("(a).1", "(a)·1"), ("x).2", "x)·2"), ("3.11", "3・11"),
                        ("3.11", "3･11")]:
        assert not reads(point, kept), (point, kept)
        assert not reads(kept, point), (point, kept)


LEADER_ITEMS = [".", "-", "=", "*"]


@relation(HOLDS, domain="4 characters (`.`, `-`, `=`, `*`) x runs of 1 to 5, written solid or with spaces "
                        "between, between two words")
def test_a_run_of_three_dots_dashes_equals_or_stars_is_a_leader_and_a_shorter_one_is_text():
    """Between two words, a run of three or more dots, dashes, `=` or `*` (solid, or with spaces between its
    items) reads as one space, so a text test for the two words with one space passes; a run of one or two
    is text, so that test fails and the test that writes the run passes. [M132]
    Why it matters for a score: a table of contents or a form is ruled with leaders, and two dots or a
    double dash are punctuation. The minimum of 3 is where the two meet (the one for `_` is M22a's)."""
    for item in LEADER_ITEMS:
        for n in range(1, 6):
            for joiner in ["", " "]:
                run = joiner.join(item * n) if joiner else item * n
                page = f"a {run} b"
                # Given two words with a run of n items between them
                if n >= 3:
                    # Then three or more read as one space
                    assert reads("a b", page), (item, n, joiner)
                    assert reads(page, "a b"), (item, n, joiner)    # and a gold with the leader, on a space
                else:
                    # But fewer stay text: the two words alone fail, the run as written passes
                    assert not reads("a b", page), (item, n, joiner)
                    assert not reads(page, "a b"), (item, n, joiner)    # and a gold with the run, on a space
                    assert reads(page, page), (item, n, joiner)


# ----------------------------------------------------------------------------------- table_cell


def cell_test(cell, relations=None, max_diffs=0, headings=(), section=None, row_groups=()):
    return runners.TableCell(cell, relations or {}, max_diffs, tuple(headings), section, tuple(row_groups))


def cell_passes(params, page: str) -> bool:
    return passes(params, page)


def rows_html(rows: list[list[str]]) -> str:
    """A table from rows of ready-made cell tags."""
    return "<table>" + "".join(f"<tr>{''.join(r)}</tr>" for r in rows) + "</table>"


def td(text: str, **attrs) -> str:
    return f"<td{''.join(f' {k}={v}' for k, v in attrs.items())}>{escaped(text)}</td>"


def th(text: str) -> str:
    return f"<th>{escaped(text)}</th>"


LABELS = st.lists(st.text(string.ascii_uppercase, min_size=4, max_size=6), min_size=3, max_size=3, unique=True)
LABELS4 = st.lists(st.text(string.ascii_uppercase, min_size=4, max_size=6), min_size=4, max_size=4, unique=True)
VALUES = st.lists(st.integers(100, 999).map(str), min_size=4, max_size=4, unique=True)


@relation(HOLDS, domain="3 distinct labels and 4 values: 2 section rows over 2 body rows each, 3 ways to "
                        "write a section row, every body cell; and a row-spanning cell, not in the first column")
def test_a_section_is_the_nearest_section_row_above_the_cell():
    """In a table of section rows each followed by body rows, a body cell's `section` is the nearest section
    row above it: its test passes for that row's label and fails for another section's; moving a body row
    across a section row flips both verdicts; a section row written once across the table, once in the first
    cell beside blank ones, or in every cell reads the same (a test naming the label of an earlier row written in
    every cell is read as that row, M120); two section rows in a row are read together; a
    row-spanning cell to the left is a section for the rows it spans; and the first cell of the cell's own row is a
    section too. [M133]
    Why it matters for a score: tables of the dataset group their rows under printed section labels; a
    system that lays out one group's rows under another's section must fail."""
    def build(first, second, a_rows, b_rows, style):
        def section(label):
            return {"merged": [td(label, colspan=2)], "blank": [td(label), td("")],
                    "repeated": [td(label), td(label)]}[style]
        body = lambda rs: [[td(f"r{v}"), td(v)] for v in rs]  # noqa: E731
        return rows_html([[th("Item"), th("Value")], section(first), *body(a_rows), section(second),
                          *body(b_rows)])

    @given(LABELS, VALUES)
    def check(labels, values):
        first, second, wrong = labels
        a_rows, b_rows = values[:2], values[2:]
        for style in ["merged", "blank", "repeated"]:
            page = build(first, second, a_rows, b_rows, style)
            for v in a_rows:
                # Given a body row under the first section; Then its cell has that section and not the second
                assert cell_passes(cell_test(v, section=first), page), (style, v)
                assert not cell_passes(cell_test(v, section=second), page), (style, v)
                assert not cell_passes(cell_test(v, section=wrong), page), (style, v)
            for v in b_rows:
                assert cell_passes(cell_test(v, section=second), page), (style, v)
                # Note: a row that repeats the label a test names is that section row (M120), so the
                # earlier repeated row of the first label reads for a test that names it
                assert style == "repeated" or not cell_passes(cell_test(v, section=first), page), (style, v)
                # And body rows between the two section rows end the run: the two labels are not read together
                assert not cell_passes(cell_test(v, section=f"{first} {second}"), page), (style, v)
            # When the last row of the first group is moved under the second section; Then its verdicts flip
            moved = build(first, second, a_rows[:1], [a_rows[1], *b_rows], style)
            assert cell_passes(cell_test(a_rows[1], section=second), moved), style
            assert style == "repeated" or not cell_passes(cell_test(a_rows[1], section=first), moved), style
    check()
    # Given two section rows in a row; Then both read together, the nearer one alone, the farther one not alone
    page = rows_html([[td("Cohort", colspan=2)], [td("Males", colspan=2)], [td("row"), td("5")]])
    assert cell_passes(cell_test("5", section="Males"), page)
    assert cell_passes(cell_test("5", section="Cohort Males"), page)
    assert not cell_passes(cell_test("5", section="Cohort"), page)
    # And a row-spanning cell to the left, not in the first column, is a section for the rows it spans only
    page = rows_html([[td("Alpha"), td("Group", rowspan=2), td("x"), td("1")], [td("Beta"), td("y"), td("2")],
                      [td("Gamma"), td("Plain"), td("z"), td("3")]])
    for v in ("1", "2"):
        assert cell_passes(cell_test(v, section="Group"), page), v
        assert not cell_passes(cell_test(v, section="Plain"), page), v
    assert not cell_passes(cell_test("3", section="Group"), page)
    assert not cell_passes(cell_test("3", section="Plain"), page)   # a cell that spans no rows is no section
    # And a section above no row at all, or the first cell of the cell's own row, is its own case
    assert not cell_passes(cell_test("5", section="Cohort"), rows_html([[td("row"), td("5")]]))
    assert cell_passes(cell_test("5", section="row"), rows_html([[td("row"), td("5")]]))
    assert not cell_passes(cell_test("5", section="other"), rows_html([[td("row"), td("5")]]))


GROUPS = st.lists(st.text(string.ascii_uppercase, min_size=4, max_size=6), min_size=3, max_size=3, unique=True)


@relation(HOLDS, domain="3 distinct group labels, rows under 2 nested groups, a group written as a "
                        "rowspan or once above blank cells, every body cell, 6 gold lists")
def test_row_groups_are_the_cells_to_the_left_that_span_the_cells_rows_in_order():
    """A body cell's `row_groups` test passes when its gold groups are, in the order they stand, among the
    cells to the left of the cell in its rows (a subsequence of them, so the outer group alone also passes),
    and fails for the groups of another block, for an unrelated label and for the order reversed; a group
    written once above blank cells instead of as a rowspan reads the same. [M134]
    Why it matters for a score: grouped rows (a country, then its cities) are the dataset's way to say which
    block a figure belongs to; a system that merges the blocks or loses the nesting must fail."""
    @given(GROUPS)
    def check(labels):
        outer, one, two = labels
        for style in ["rowspan", "blank"]:
            # Given an outer group over two inner groups of two rows each
            rows = []
            for k, inner in enumerate([one, one, two, two]):
                row = []
                if k == 0:
                    row.append(td(outer, rowspan=4) if style == "rowspan" else td(outer))
                elif style == "blank":
                    row.append(td(""))
                if k in (0, 2):
                    row.append(td(inner, rowspan=2) if style == "rowspan" else td(inner))
                elif style == "blank":
                    row.append(td(""))
                rows.append([*row, td(f"x{k}"), td(str(10 + k))])
            page = rows_html(rows)
            for k, inner in enumerate([one, one, two, two]):
                v = str(10 + k)
                other = two if inner == one else one
                # Then the cell's groups pass in order, as a subsequence, and fail for the other block, an
                # unrelated label and the reverse
                assert cell_passes(cell_test(v, row_groups=[outer, inner]), page), (style, k)
                assert cell_passes(cell_test(v, row_groups=[inner]), page), (style, k)
                assert cell_passes(cell_test(v, row_groups=[outer]), page), (style, k)
                assert not cell_passes(cell_test(v, row_groups=[outer, other]), page), (style, k)
                assert not cell_passes(cell_test(v, row_groups=[inner, outer]), page), (style, k)
                assert not cell_passes(cell_test(v, row_groups=["NOSUCHGROUP"]), page), (style, k)
    check()


@relation(HOLDS, domain="4 distinct row labels, rows of 2 to 4 columns, the label a `<th>` or a `<td>`, every "
                        "cell right of the label, and two `<th>` in a row")
def test_a_cells_left_heading_is_the_label_of_its_own_row():
    """A cell's `left_heading` is the heading cell found walking left in the cell's own row (the first cell of
    the row when the walk meets no `<th>`, any `<th>` of the row to its left when it does): the test passes for its row's
    label, at any distance from the label, and fails for the label of another row; swapping the labels of two
    rows flips both verdicts; and in `top_heading`, the cells of a `<thead>` are headings of their column. [M135]
    Why it matters for a score: row labels are what a reader reads a figure against; a figure under another
    row's label is a wrong figure."""
    @given(LABELS4, VALUES, st.integers(2, 4), st.booleans())
    def check(labels, values, width, header):
        def page(order):
            rows = []
            for lab, v in zip(order, values, strict=True):
                label = th(lab) if header else td(lab)
                rows.append([label, *[td(f"{v}{j}") for j in range(width - 1)]])
            return rows_html(rows)

        for j in range(width - 1):
            for i, (lab, v) in enumerate(zip(labels, values, strict=True)):
                target = f"{v}{j}"
                assert cell_passes(cell_test(target, {"left_heading": lab}), page(labels)), (i, j)
                for k, wrong in enumerate(labels):
                    if k != i:
                        assert not cell_passes(cell_test(target, {"left_heading": wrong}), page(labels)), (i, j, k)
            # When two rows swap their labels; Then each cell's verdicts for the two labels flip
            swapped = [labels[1], labels[0], *labels[2:]]
            t0 = f"{values[0]}{j}"
            assert cell_passes(cell_test(t0, {"left_heading": labels[1]}), page(swapped))
            assert not cell_passes(cell_test(t0, {"left_heading": labels[0]}), page(swapped))
    check()
    # And a column's headings include the cells of a `<thead>`, `<td>` or `<th>`, which the walk to the edge
    # would not reach: only the top row of a table without one is read
    head = "<thead><tr><td>Group</td><td>Group</td></tr><tr><td>Name</td><td>Head</td></tr></thead>"
    for page, expected in [(f"<table>{head}<tr><td>Row</td><td>5</td></tr></table>", True),
                           (f"<table>{head[7:-8]}<tr><td>Row</td><td>5</td></tr></table>", False)]:
        assert cell_passes(cell_test("5", {"top_heading": "Head"}), page) == expected
        assert cell_passes(cell_test("5", {"top_heading": "Group"}), page)
        assert not cell_passes(cell_test("5", {"top_heading": "Row"}), page)
    # And with two headings in a row, each is a heading of the cell; a `<td>` beside a `<th>` is not
    page = rows_html([[th("Group"), th("Name"), td("5")]])
    assert cell_passes(cell_test("5", {"left_heading": "Name"}), page)
    assert cell_passes(cell_test("5", {"left_heading": "Group"}), page)
    page = rows_html([[th("Group"), td("Name"), td("5")]])
    assert cell_passes(cell_test("5", {"left_heading": "Group"}), page)
    assert not cell_passes(cell_test("5", {"left_heading": "Name"}), page)


FLOOR_GOLD = ["abcd", "abcdef", "abcdefgh", "abcdefghij"]


@relation(HOLDS, domain="4 golds of 4 to 10 distinct letters x every number of substitutions up to the whole "
                        "cell x 4 edit budgets (0, half, the whole length, three times it)")
def test_a_cell_never_matches_below_a_ratio_of_one_half_whatever_the_edit_budget():
    """A `table_cell` test with a gold cell of n characters and any edit budget matches a cell with j characters
    substituted when j is within the budget and at most n/2, and never when j is more than n/2, however large
    the budget; raising the budget past n/2 changes no verdict. [M136]
    Why it matters for a score: a test that allows many edits must not match an unrelated cell (docs/scoring/
    table_cell.md: 'A cell never matches below a ratio of 0.5')."""
    for gold in FLOOR_GOLD:
        n = len(gold)
        for j in range(n + 1):
            page = rows_html([[td("9" * j + gold[j:])]])
            verdicts = {}
            for budget in [0, n // 2, n, 3 * n]:
                verdicts[budget] = cell_passes(cell_test(gold, max_diffs=budget), page)
                # Then it matches when j is within the budget and at most n/2
                assert verdicts[budget] == (j <= budget and 2 * j <= n), (gold, j, budget)
            # And the verdict stops changing once the budget reaches n/2
            assert verdicts[n // 2] <= verdicts[n] == verdicts[3 * n], (gold, j)


# ----------------------------------------------------------------------------------------- layout


@relation(HOLDS, domain="all 11 x 11 pairs of a block's label and a test's kind, the block alone on the page, "
                        "and the same with a larger block of another label around it")
def test_a_list_or_form_block_is_text_for_a_text_test_and_nothing_else_is():
    """A layout_kind test of kind `text` passes when the block that holds its place is labeled `text`, `list`
    or `form`; every other kind passes only on its own label, so a `list` or `form` block fails a test for any
    other kind and a `text` block fails a `list` or `form` test. [M137]
    Why it matters for a score: vendors differ in whether they give a list item or a form field a block of its
    own; the dataset asks only that a line of text is not a heading or a table, and nothing else is forgiven."""
    place = (0.2, 0.2, 0.6, 0.25)
    for label in views.LABELS:
        for kind in views.LABELS:
            # Given a block of this label over the place; When a test of this kind reads it
            test = runners.LayoutKind(runners.Text("x", 0, (place,)), kind)
            ok, _ = runners.layout_kind(test, [views.Block(label, place, "")])
            # Then it passes on its own label, and for `text` also on a list or form
            assert ok == (label == kind or (kind == "text" and label in ("list", "form"))), (label, kind)
            # And it holds when a larger block of another label surrounds it
            big = views.Block("figure" if label != "figure" else "table", (0, 0, 1, 1), "")
            assert runners.layout_kind(test, [big, views.Block(label, place, "")])[0] == ok, (label, kind)
