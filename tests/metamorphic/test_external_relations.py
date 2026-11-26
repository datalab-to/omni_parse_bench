# ruff: noqa: E501
"""Relations taken from an external catalogue: the perturbations of ParseBench-2 (arXiv 2611.17400, Appendix A.2,
CC BY 4.0), whose benign variations must keep a verdict and whose error types must flip it (M104 to M120).
The scorer's authors did not write the list: they read it and stated, for each perturbation that applies to OPB,
what its documented rules say. Where OPB's rules differ from ParseBench-2's severity, the relation states the
OPB rule."""
from __future__ import annotations

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from metamorphic.common import HOLDS, LIMITATION, deviation, escaped, more_evidence, passes, relation
from omni_parse_bench import markdown, views
from omni_parse_bench.scorers.unit_tests import runners
from omni_parse_bench.scorers.unit_tests.runners import _area as area
from omni_parse_bench.scorers.unit_tests.runners import _intersection as intersection


def text_test(s: str, max_diffs: int = 0) -> runners.Present:
    return runners.Present(runners.Text(s, max_diffs))


def number_test(s: str) -> runners.Present:
    return runners.Present(runners.Number(s))


def md_passes(params, md: str) -> bool:
    return passes(params, markdown.to_html(md))


# ------------------------------------------------------------------ 3. Markdown dialects (ParseBench-2 A.2)

# Each group writes one page in several markdown dialects; the text of every spelling is the same.
DIALECTS = {
    "headings": ["# Annual Report\n\nthe body", "Annual Report\n=============\n\nthe body",
                 "# Annual Report #\n\nthe body", "## Annual Report ##\n\nthe body"],
    "emphasis": ["a **bold** and *slanted* word", "a __bold__ and _slanted_ word",
                 "a <b>bold</b> and <i>slanted</i> word", "a ***bold*** and *slanted* word"],
    "page fence": ["the body text", "```\nthe body text\n```", "```markdown\nthe body text\n```",
                   "```markdown\nthe body text"],
    "one bullet": ["* the item", "- the item", "+ the item", "• the item"],
    "one number": ["1. the item", "1) the item"],
}
GOLDS = {"headings": ("Annual Report", "the body", "Annual Report the body"),
         "emphasis": ("a bold and slanted word", "bold", "slanted word"),
         "page fence": ("the body text", "body", "the body text"),
         "one bullet": ("the item", "item", "the"),
         "one number": ("the item", "item", "the")}


@relation(HOLDS, domain="5 groups of 2 to 4 spellings of one page x 3 golds of each, and each gold with one letter "
                        "changed (ParseBench-2 A.2: setext and closing-# headings, __bold__ and _italic_, bullet "
                        "glyphs, 1) numbering, a fence around the page)")
def test_equivalent_markdown_dialects_give_the_same_text_verdicts():
    """A page written in another markdown dialect (setext, ATX or closing-# headings, `__bold__` or `**bold**`,
    `*`, `-`, `+` or `•` for one bullet, `1.` or `1)` for one numbered item, a fence around the page) passes the
    same `present` text tests, and fails the same one-letter-changed ones. [M104]
    Why it matters for a score: a system is graded on what it wrote, not on the markdown dialect it chose;
    credit to ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0) for the perturbations."""
    # Given each group's spellings and its golds
    for group, spellings in DIALECTS.items():
        for gold in GOLDS[group]:
            changed = gold[:-1] + ("x" if gold[-1] != "x" else "y")
            # When each spelling is converted; Then the gold passes and its changed form fails on all of them
            for md in spellings:
                assert md_passes(text_test(gold), md), (group, gold, md)
                assert not md_passes(text_test(changed), md), (group, changed, md)


@relation(HOLDS, domain="4 bullet dialects and 3 numbered ones, over a two-item list, a gold across the items and a gold of one item")
def test_list_markers_are_page_text_across_items():
    """A gold that spans two list items reads the second item's marker: `- `, `* `, `+ ` and `1)` are page text
    (the converter escapes them), a `•` at the start of a line is dropped by fold, and an ordered list's
    numbers are read as written (`1. 1.` is not `1. 2.`). A gold of one item passes in every dialect. [M105]
    Why it matters for a score: this is where OPB's documented rules differ from the dialect invariance
    ParseBench-2 expects (markdown.py: 'the marker is page text'); a converter that does not number a
    list the way its gold does changes the verdicts of a gold across items.
    Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0)."""
    # Given a two-item list in each dialect
    across = text_test("one two")
    # Then `•` lists pass a gold across items, and `-`, `*`, `+` lists do not (the marker is text)
    assert md_passes(across, "• one\n• two")
    for marker in "-*+":
        assert not md_passes(across, f"{marker} one\n{marker} two"), marker
        assert md_passes(text_test(f"one {marker} two"), f"{marker} one\n{marker} two"), marker
    # And numbered items read their numbers as written
    for source, gold in [("1. one\n2. two", "1. one 2. two"), ("1. one\n1. two", "1. one 1. two"),
                         ("1) one\n2) two", "1) one 2) two")]:
        assert md_passes(text_test(gold), source), (source, gold)
    assert not md_passes(text_test("1. one 2. two"), "1. one\n1. two")
    assert not md_passes(across, "1. one\n2. two")
    # But a gold of one item passes in every dialect
    for source in ["- one\n- two", "1. one\n1. two", "1) one\n2) two", "• one\n• two"]:
        assert md_passes(text_test("one"), source) and md_passes(text_test("two"), source), source


# ------------------------------------------------------------------------------ 4. The squeeze retry

WORDS = ["Total Due", "hello world", "the quick brown fox", "Nom de famille"]


def spaced(s: str) -> str:
    """`s` with a space between every two characters (a box per character)."""
    return " ".join(s.replace(" ", ""))


@relation(HOLDS, domain="4 letter-edged golds x 5 respacings (spaces dropped, doubled, put inside every word, between every "
                        "character) x each gold with one letter changed")
def test_a_text_test_passes_with_spaces_dropped_or_inserted_inside_words():
    """A `present` text test passes on its text with the spaces between its words removed, doubled, or with a
    space put between every character, and fails on the same page with one letter changed: the retry on squeezed
    strings. [M106]
    Why it matters for a score: a text run together or a box-per-character field is read as the text it is;
    nothing but the squeeze retry (README, 'squeezed') makes these pass. Credit: ParseBench-2
    (arXiv 2611.17400, A.2, CC BY 4.0): words split or joined, box-per-character fields."""
    for gold in WORDS:
        changed = gold[:-1] + ("x" if gold[-1] != "x" else "y")
        # Given the gold; When its spacing is changed; Then it passes, and the changed text fails
        for page in [gold, gold.replace(" ", ""), gold.replace(" ", "  "), spaced(gold),
                     gold.replace(" ", " ")]:
            assert passes(text_test(gold), f"<p>{escaped(page)}</p>"), (gold, page)
            changed_page = page[:-1] + ("x" if page[-1] != "x" else "y")
            assert not passes(text_test(gold), f"<p>{escaped(changed_page)}</p>"), (gold, changed_page)
        assert not passes(text_test(changed), f"<p>{escaped(gold)}</p>")


@relation(HOLDS, domain="digit-edged text golds and number golds x spacing inside a group of digits")
def test_spaces_inside_a_group_of_digits_still_fail_a_number_or_digit_edged_test():
    """The squeeze retry does not rejoin digits: a number test fails on its digits spaced inside a group
    (`1,2 40`, `4 2`), and a text test with a digit at its edge fails when a space is put into the digits it
    starts or ends with (`12 500` on `1 2500`, `123` on `1 23`), while a letter-edged text test passes with
    its letters spaced. [M107]
    Why it matters for a score: a figure split by a space is two numbers; present-number.md (case num-split) and
    present-text.md (the digit edge) say so. Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0)."""
    for gold, page in [("1,240", "1,2 40"), ("42", "4 2"), ("1 240", "1240"), ("1240", "1 240")]:
        assert not passes(number_test(gold), f"<p>{page}</p>"), (gold, page)
        assert passes(number_test(gold), f"<p>{gold}</p>"), gold
    for gold, page in [("12 500", "1 2500"), ("123", "1 23"), ("Total 123", "Total 1 23")]:
        assert not passes(text_test(gold), f"<p>{page}</p>"), (gold, page)
        assert passes(text_test(gold), f"<p>{gold}</p>"), gold
    assert passes(text_test("1st"), "<p>1 st</p>")      # a digit then letters: the squeeze applies


# -------------------------------------------------------------------------- 5. Typography and compatibility

EQUIVALENT = [("it's", "it’s"), ("it's", "it‘s"), ('"hi"', "“hi”"), ("a-b", "a–b"),
              ("a-b", "a—b"), ("a-b", "a−b"), ("final", "ﬁnal"), ("office", "oﬃce"),
              ("a b", "a b"), ("a b", "a b"), ("a, b", "a， b"), ("a(b)", "a（b）"),
              ("a:b", "a：b"), ("12", "１２"), ("A", "Ａ"), ("a...b", "a…b"),
              ("m2", "m²"), ("5 µ", "5 μ"), ("2.3", "2·3")]
NOT_FOLDED = [("3 x 4", "3 × 4"), ("5 u", "5 µ"), ("5 u", "5 μ"), ("Apple", "Аpple"),
              ("e", "е"), ("a", "а"), ("o", "о"), ("A", "Α"), ("→", "->"), ("x", "×")]


@relation(HOLDS, domain=f"{len(EQUIVALENT)} pairs: curly quotes, dashes, ligatures, no-break and thin spaces, "
                        "full-width punctuation and letters and digits, ellipsis, superscript, micro and mu, "
                        "middle dot; both orders, and each with a letter changed")
def test_typographic_variants_give_the_same_text_verdict():
    """A text test passes whichever of two typographic spellings the gold and the page use (curly or straight
    quotes, en or em dash or minus for a hyphen, ligatures, no-break or thin spaces, full-width punctuation,
    letters and digits, the ellipsis, a superscript digit, micro and mu, a raised decimal point) and fails when
    the page's text is also changed. [M108]
    Why it matters for a score: a system is not penalized for typography the text does not hold; the
    fold (NFKC and the quote, dash and dot families) is the only reason these pass.
    Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0): typographic characters."""
    for a, b in EQUIVALENT:
        for gold, page in ((a, b), (b, a)):
            assert passes(text_test(gold), f"<p>x {escaped(page)} y</p>"), (gold, page)
            assert not passes(text_test(gold), f"<p>x {escaped(page[:-1])}q y</p>"), (gold, page)


@relation(HOLDS, domain=f"{len(NOT_FOLDED)} look-alike pairs (x and ×, u and µ or μ, Latin and Cyrillic "
                        "or Greek letters, an arrow and ->), both orders")
def test_look_alikes_that_are_different_characters_fail():
    """Characters that look alike but are not compatibility forms are not folded: `×` is not `x`, `µ` and
    `μ` are not `u`, a Cyrillic or Greek capital is not the Latin one, `→` is not `->`. A text test fails on
    them, in both orders. [M109]
    Why it matters for a score: the fold is deliberately narrow; a wrong-script letter is a wrong
    letter, so a system is not credited for a look-alike. Credit: ParseBench-2 (arXiv 2611.17400, A.2,
    CC BY 4.0): typographic look-alikes."""
    for a, b in NOT_FOLDED:
        assert not passes(text_test(a), f"<p>7 {escaped(b)} 7</p>"), (a, b)
        assert not passes(text_test(b), f"<p>7 {escaped(a)} 7</p>"), (b, a)
        assert passes(text_test(a), f"<p>7 {escaped(a)} 7</p>")


# -------------------------------------------------------------------- 6. Sign, percent, currency of a number

@relation(HOLDS, domain="4 golds with a sign, a percent, both or neither x the page as written, with a sign lost, "
                        "added or a percent lost, and a sign written as a minus sign or an en dash")
def test_a_number_loses_its_sign_or_percent_only_by_failing():
    """A number test passes on its number, its minus written as `−` or `–`, and an added percent sign or a
    space before `%`, and fails with its sign lost, a sign added, or its percent lost. [M110]
    Why it matters for a score: a dropped minus or percent sign is a wrong figure; present-number.md says so
    (cases num-sign-lost, num-sign-added, num-percent-lost). Credit: ParseBench-2 (arXiv 2611.17400, A.2,
    CC BY 4.0): minus added, % dropped."""
    for gold, passing, failing in [
            ("-4.8%", ["-4.8%", "−4.8%", "–4.8%", "-4.8 %"], ["4.8%", "-4.8", "4.8"]),
            ("4.8%", ["4.8%", "4.8 %"], ["4.8", "-4.8%", "-4.8"]),
            ("-4.8", ["-4.8", "−4.8", "-4.8%"], ["4.8", "(4.8)", "4.8%"]),
            ("4.8", ["4.8", "4.8%", "(4.8)", "$4.8"], ["-4.8", "−4.8", "-4.8%"])]:
        for page in passing:
            assert passes(number_test(gold), f"<p>{escaped(page)}</p>"), (gold, page)
        for page in failing:
            assert not passes(number_test(gold), f"<p>{escaped(page)}</p>"), (gold, page)


@relation(HOLDS, domain="3 negative golds x 3 ways to write a negative in parentheses, and 3 positive golds x the same")
def test_parentheses_never_make_a_number_negative():
    """Parentheses around a number are ignored: a gold `4.8` passes on `(4.8)`, and a gold `-4.8` fails on
    `(4.8)`, `($4.8)` and `(4.8%)`: an accounting negative is not read as one. [M111]
    Why it matters for a score: present-number.md (cases num-parens, num-parens-negative); a page that writes
    a loss as (4.8) is not credited for -4.8, and one that writes a gain in parentheses still is.
    Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0): accounting negatives."""
    for gold in ["-4.8", "-1,240.00", "-12"]:
        digits = gold[1:]
        for page in [f"({digits})", f"(${digits})", f"({digits}%)"]:
            assert not passes(number_test(gold), f"<p>{page}</p>"), (gold, page)
        assert passes(number_test(gold), f"<p>-{digits}</p>")
    for gold in ["4.8", "1,240.00", "12"]:
        for page in [f"({gold})", f"({gold}%)", f"(${gold})"]:
            assert passes(number_test(gold), f"<p>{page}</p>"), (gold, page)
        assert not passes(number_test(gold), f"<p>-{gold}</p>"), gold


@relation(HOLDS, domain="5 currency signs and codes x 3 golds, a trailing .00 added or dropped, on number and text tests")
def test_a_currency_sign_is_free_and_a_changed_decimal_part_fails():
    """A number test passes with any currency sign before it (`$`, `€`, `£`, `¥`, `₹`) and fails when `.00` is
    added to a whole gold or dropped from a gold that has it, and so does a text test of the same digits
    (their digit edge). [M112]
    Why it matters for a score: a currency is not part of the figure, but decimals are (cases num-currency,
    num-decimals-extra, num-decimals-lost). Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0): currency
    moved or added, .00 added."""
    for sign in ["$", "€", "£", "¥", "₹"]:
        for gold in ["1,240.00", "5", "1,240"]:
            assert passes(number_test(gold), f"<p>{sign}{gold}</p>"), (sign, gold)
    for gold, page in [("5", "5.00"), ("1,240", "1,240.00"), ("1,240.00", "1,240"), ("1,240.00", "1,240.0")]:
        assert not passes(number_test(gold), f"<p>{page}</p>"), (gold, page)
        if gold in ("5", "1,240.00"):
            assert not passes(text_test(gold), f"<p>{page}</p>"), (gold, page)


# ---------------------------------------------------------------------------------- 7b-d. Table transforms

def td_table(rows) -> str:
    return "<table>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>"


def cell_passes(cell, relations, page, **kwargs) -> bool:
    return passes(runners.TableCell(cell, relations, 0, **kwargs), page)


GRID = st.tuples(st.integers(2, 4), st.integers(1, 3), st.integers(0, 4))


@relation(HOLDS, domain="grids of 2 to 4 rows and 1 to 3 columns of distinct cells x a row inserted at every position, "
                        "every up and down test of every cell")
@given(GRID)
def test_an_inserted_row_flips_exactly_the_tests_across_it(shape):
    """Inserting a row of new cells between rows flips exactly the `down` test of the cells above it and the
    `up` test of the cells below it (the two sides of the insertion), and no other up or down test of the table.
    [M113]
    Why it matters for a score: a row an extractor invents splits two neighbours; tests across the join must
    fail and every other test must keep its verdict. Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0):
    row inserted."""
    rows, cols, where = shape
    where = min(where, rows)
    grid = [[f"r{r}c{c}" for c in range(cols)] for r in range(rows)]
    page = grid[:where] + [[f"new{c}" for c in range(cols)]] + grid[where:]
    # Given each up and down test of the original table: it passes
    for r in range(rows):
        for c in range(cols):
            for side, other in (("up", r - 1), ("down", r + 1)):
                if not 0 <= other < rows:
                    continue
                assert cell_passes(grid[r][c], {side: grid[other][c]}, td_table(grid))
                # When a row is inserted; Then it fails exactly when the new row lies between the two
                between = where == (r if side == "up" else r + 1)
                assert cell_passes(grid[r][c], {side: grid[other][c]}, td_table(page)) is (not between), (r, c, side)


@relation(HOLDS, domain="tables of 2 to 4 rows and 2 to 4 columns of distinct cells with every row and column headed "
                        "by a `<th>`, every cell and both heading directions")
@given(st.integers(2, 4), st.integers(2, 4))
def test_transposing_a_table_swaps_left_and_top_heading_verdicts(rows, cols):
    """A cell's `top_heading` test passes on a table exactly when its `left_heading` test (the same text) passes on
    the table's transpose, and the reverse; a wrong heading fails in both. [M114]
    Why it matters for a score: a table written with its rows and columns exchanged is the same data read the
    other way; the heading walks are mirror images. Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0):
    transposed table."""
    top = [f"col{c}" for c in range(cols)]
    left = [f"row{r}" for r in range(rows)]
    body = [[f"v{r}x{c}" for c in range(cols)] for r in range(rows)]

    def table(rows_of_cells, header_rows, header_cols) -> str:
        return "<table>" + "".join(
            "<tr>" + "".join(f"<th>{x}</th>" if i < header_rows or j < header_cols else f"<td>{x}</td>"
                             for j, x in enumerate(row)) + "</tr>" for i, row in enumerate(rows_of_cells)) + "</table>"

    original = [["corner", *top]] + [[left[r], *body[r]] for r in range(rows)]
    transposed = [list(x) for x in zip(*original, strict=True)]
    for r in range(rows):
        for c in range(cols):
            cell = body[r][c]
            # Given the cell with its column and row headings; Then they hold, and swap on the transpose
            assert cell_passes(cell, {"top_heading": top[c], "left_heading": left[r]}, table(original, 1, 1))
            assert cell_passes(cell, {"top_heading": left[r], "left_heading": top[c]}, table(transposed, 1, 1))
            wrong = top[(c + 1) % cols]
            assert not cell_passes(cell, {"top_heading": wrong}, table(original, 1, 1))
            assert not cell_passes(cell, {"left_heading": wrong}, table(transposed, 1, 1))
            assert not cell_passes(cell, {"left_heading": left[r]}, table(transposed, 1, 1))
            wrong_row = left[(r + 1) % rows]
            assert not cell_passes(cell, {"left_heading": wrong_row}, table(original, 1, 1))
            assert not cell_passes(cell, {"top_heading": wrong_row}, table(transposed, 1, 1))


SPANS = [
    # (cell, kwargs, spanned page, the same with the spanned cell written in each position it covers)
    ("6", {"headings": ("Group", "B")},
     "<table><tr><th colspan=2>Group</th></tr><tr><th>A</th><th>B</th></tr><tr><td>5</td><td>6</td></tr></table>",
     "<table><tr><th>Group</th><th>Group</th></tr><tr><th>A</th><th>B</th></tr><tr><td>5</td><td>6</td></tr></table>"),
    ("6", {"row_groups": ("Male",)},
     "<table><tr><td rowspan=2>Male</td><td>5</td></tr><tr><td>6</td></tr></table>",
     "<table><tr><td>Male</td><td>5</td></tr><tr><td>Male</td><td>6</td></tr></table>"),
]
SECTION = ("6", {"section": "Cohort 1"},
           "<table><tr><th>A</th><th>B</th></tr><tr><td colspan=2>Cohort 1</td></tr><tr><td>5</td><td>6</td></tr></table>",
           "<table><tr><th>A</th><th>B</th></tr><tr><td>Cohort 1</td><td>Cohort 1</td></tr><tr><td>5</td><td>6</td></tr></table>")


@relation(HOLDS, domain=f"{len(SPANS)} tables: a merged heading and a row-spanning group; each written "
                        "merged and with the cell repeated in every position it covers; the right and a wrong label")
def test_repeating_a_spanned_cell_keeps_heading_and_row_group_verdicts():
    """Writing a merged cell (`colspan`, `rowspan`) as a copy in each cell it covers keeps the verdict of a
    `headings` or `row_groups` arg of a `table_cell` test, for the right label and for a wrong one.
    [M115]
    Why it matters for a score: a converter may or may not merge cells; table_cell.md promises that a merged
    heading and a repeated one both count. Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0): merged
    cells repeated."""
    for cell, args, merged, repeated in SPANS:
        key, value = next(iter(args.items()))
        wrong = ("Other",) if isinstance(value, tuple) and key != "headings" else \
            ("Other", value[-1]) if isinstance(value, tuple) else "Other"
        # Given the merged page and its repeated form; Then the right label passes and a wrong one fails on both
        for page in (merged, repeated):
            assert cell_passes(cell, {}, page, **args), (key, page)
            assert not cell_passes(cell, {}, page, **{key: wrong}), (key, page)


@relation(LIMITATION, domain="a section row written as one cell across the table, and as its label in every cell; "
                             "the right label and a wrong one")
@deviation("M120")
def test_repeating_a_section_row_cell_keeps_the_section_verdict():
    """Writing a section row's label in every cell it covers, instead of once across the table, keeps the
    `section` verdict of a `table_cell` test. [M120]
    Why it matters for a score: a converter that repeats a spanned section label in each column is not read as
    having a section row: a section row is one label in the first column, so the cell has no section
    (tables.py: 'a row of one label, in its first column'). Credit: ParseBench-2 (arXiv 2611.17400, A.2,
    CC BY 4.0): merged cells repeated, group labels."""
    cell, args, _, repeated = SECTION
    assert cell_passes(cell, {}, repeated, **args), repeated


@more_evidence()
def test_the_section_controls_of_a_repeated_section_row_hold():
    """The controls of M120 hold: a section label written once across the table passes, and a wrong section fails
    on that page and on the one that repeats the label in every cell. [M120]
    Why it matters for a score: M120 stops at its first failing assertion; these show that only the repeated
    label's positive verdict is what deviates."""
    cell, args, merged, repeated = SECTION
    assert cell_passes(cell, {}, merged, **args), merged
    for page in (merged, repeated):
        assert not cell_passes(cell, {}, page, section="Other"), page


# -------------------------------------------------------------------------- 8. Paragraph-break invariance

SENTENCES = ["the quick brown fox jumps over the lazy dog", "Total Due 5 on receipt",
             "alpha beta gamma delta epsilon"]


@relation(HOLDS, domain="3 sentences x every word boundary x a paragraph, a `<br>`, a newline or a space; 3 golds "
                        "across or inside the break, a present test, an order test, and each changed")
def test_splitting_or_joining_paragraphs_keeps_present_and_order_verdicts():
    """A page split into two paragraphs at a word boundary, or the two joined, gives the same `present` and
    `order` verdicts for a gold across or inside the break, and the same failures for a changed gold: a block
    break reads as a space. [M116]
    Why it matters for a score: whether a system wraps a sentence in one paragraph or several, or ends each printed
    line with a paragraph, must not change a verdict; only a leader run or a hyphen reads the break (M117).
    Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0): paragraphs run together, hard line breaks."""
    for sentence in SENTENCES:
        words = sentence.split()
        for i in range(1, len(words)):
            first, second = " ".join(words[:i]), " ".join(words[i:])
            pages = [f"<p>{sentence}</p>", f"<p>{first}</p><p>{second}</p>", f"<p>{first}<br>{second}</p>",
                     f"<p>{first}\n{second}</p>", f"<div>{first}</div><div>{second}</div>"]
            for page in pages:
                assert passes(text_test(sentence), page), (sentence, page)
                assert passes(text_test(words[i - 1] + " " + words[i]), page), (sentence, page)
                assert not passes(text_test(words[i - 1] + "x " + words[i]), page), (sentence, page)
                assert runners.order(runners.Order(words[0], words[-1], 0), views.html(page))[0], (sentence, page)
                assert not runners.order(runners.Order(words[-1], words[0], 0), views.html(page))[0], (sentence, page)


@relation(HOLDS, domain="a gold of 2 words x a paragraph break, a space or nothing between its copies, 1 or 2 "
                        "expected copies; a space-grouped number repeat across the break; a leader run and a line-end hyphen "
                        "across the break")
def test_a_paragraph_break_changes_repeat_and_present_only_by_edges_leaders_and_hyphens():
    """A block break is a space except in four places: `repeat` counts the copies of a line in
    `<p>the cat</p><p>the cat</p>` and `<p>the cat the cat</p>` alike (2), and changes only when the copies are
    glued with no space (`the catthe cat` is a longer word: 1 or 0 copies); a leader run stops at the break
    (`<p>a _</p><p>__</p><p>b</p>` does not read as `a b`); and a hyphen at the end of a block joins the next
    block, as it does across a `<br>`; and a `repeat` test with a number reads line by line, so `12 500` is one
    copy in `<p>12 500</p>` and none across `<p>12</p><p>500</p>`. [M117]
    Why it matters for a score: these are the only places where a paragraph break and a space differ; the
    documented rules (internals.md: the text view, the hyphen rule, the leader rule; repeat.md) say so.
    Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0): paragraphs run together."""
    cat = runners.Text("the cat", 0)

    def copies(n: int, page: str) -> bool:
        return runners.repeat(runners.Repeat(cat, n), views.html(page))[0]

    # Given two copies of a line; Then a break or a space between them keeps the count of 2
    assert copies(2, "<p>the cat</p><p>the cat</p>") and copies(2, "<p>the cat the cat</p>")
    assert not copies(1, "<p>the cat</p><p>the cat</p>") and not copies(1, "<p>the cat the cat</p>")
    # And a copy split across the break is one copy, as it is when written in one paragraph
    assert copies(1, "<p>the</p><p>cat</p>") and copies(1, "<p>the cat</p>")
    # But copies glued with no space are not whole words
    assert not copies(2, "<p>the catthe cat</p>") and not copies(1, "<p>the catthe cat</p>")
    # A number repeat reads line by line: a block break splits a space-grouped number
    number = runners.Number("12 500")
    def number_copies(page: str) -> bool:
        return runners.repeat(runners.Repeat(number, 1), views.html(page))[0]
    assert number_copies("<p>12 500</p>") and not number_copies("<p>12</p><p>500</p>")
    # A leader run stops at a break and not at a space; a hyphen joins across it
    assert not passes(text_test("a b"), "<p>a _</p><p>__</p><p>b</p>")
    assert passes(text_test("a b"), "<p>a _ __ b</p>")
    assert passes(text_test("developers"), "<p>develop-</p><p>ers</p>") and passes(text_test("developers"), "<p>develop-<br>ers</p>")


# ------------------------------------------------------------------------------- 9. Layout partial overlap

PLACE = [(0.0, 0.0, 0.5, 0.5)]
BOX = st.tuples(*[st.integers(0, 64).map(lambda k: k / 64)] * 4).map(
    lambda b: (min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])))
LABEL = st.sampled_from(views.LABELS)


def cover(place, box) -> float:
    return sum(area(intersection(p, box)) for p in place) / sum(area(p) for p in place)


def layout_verdict(kind, blocks) -> bool:
    test = runners.LayoutKind(runners.Text("x", 0, tuple(PLACE)), kind)
    return runners.layout_kind(test, [views.Block(label, box, "") for label, box in blocks])[0]


@relation(HOLDS, domain="a place, 0 to 4 blocks on a 1/64 grid, one added block covering under half of the place, "
                        "any label, any size, and each kind")
@given(st.lists(st.tuples(LABEL, BOX), max_size=4), LABEL, BOX, LABEL)
def test_a_block_covering_under_half_of_a_place_changes_no_layout_verdict(blocks, label, box, kind):
    """Adding a block that covers less than half of a layout_kind test's place, of any label and any size, leaves
    the verdict unchanged. [M118]
    Why it matters for a score: a junk or neighbouring box that only grazes a place does not take it from the
    block that holds it. Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0): junk boxes, loose boxes."""
    # Given blocks and a block covering under half the place (on the grid, the fraction is exact)
    assume(cover(PLACE, box) < 0.5)
    # When it is added; Then the verdict is the same
    assert layout_verdict(kind, [*blocks, (label, box)]) == layout_verdict(kind, blocks)
    assert layout_verdict(kind, [(label, box), *blocks]) == layout_verdict(kind, blocks)


@settings(suppress_health_check=[HealthCheck.filter_too_much])
@relation(HOLDS, domain="a place, 0 to 4 blocks on a 1/64 grid, one added block covering half or more of the place and "
                        "smaller than every block that holds it, any label, each kind")
@given(st.lists(st.tuples(LABEL, BOX), max_size=4), LABEL, BOX, LABEL)
def test_a_smaller_block_covering_half_of_a_place_becomes_its_holder(blocks, label, box, kind):
    """Adding a block that covers half or more of the place and is smaller than every block already covering
    half of it makes that block the holder: the verdict is whether its label is the test's kind (`text` also
    reads a list or form). [M119]
    Why it matters for a score: the smallest block over a place is the most specific one (lay-small-wrong); a
    vendor's tight box inside a large one decides the label. Credit: ParseBench-2 (arXiv 2611.17400, A.2,
    CC BY 4.0): a second box over a matched line, table plus tight cell boxes."""
    # Given a block covering at least half the place and smaller than every block that covers half of it
    assume(cover(PLACE, box) >= 0.5)
    assume(all(area(b) > area(box) * (1 + 1e-6) for _, b in blocks if cover(PLACE, b) >= 0.5))
    # When it is added; Then the verdict is its label's
    want = label in runners.AS_TEXT if kind == "text" else label == kind
    assert layout_verdict(kind, [*blocks, (label, box)]) is want
