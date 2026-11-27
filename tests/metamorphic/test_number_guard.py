# ruff: noqa: E501
"""Relations of the number guard (M121 to M125): an edit budget never pays for a digit or a minus sign, in
`present`, `order` and `table_cell`, and still pays for every other edit."""
from __future__ import annotations

import html as _html
import unicodedata

from hypothesis import given
from hypothesis import strategies as st

from metamorphic.common import CELL_DIGIT, HOLDS, ORDER_DIGIT, answer_page, passes, relation
from omni_parse_bench.scorers.unit_tests import runners

BUDGETS = [0, 1, 2, 3]


def text_test(s: str, md: int) -> runners.Present:
    return runners.Present(runners.Text(s, md))


def order_test(before: str, after: str, md: int) -> runners.Order:
    return runners.Order(before, after, md)


def cell_test(cell: str, md: int, **relations) -> runners.TableCell:
    return runners.TableCell(cell, relations, md)


def one_digit_changed(page: str, k: int) -> str:
    """`page` with its k-th digit of text (a digit in a tag or a character reference is not counted) another digit (of any script, the new one an ASCII digit)."""
    inside, places = False, []     # inside a tag or a character reference (`&#x27;`)
    for i, c in enumerate(page):
        inside = c in "<&" or (inside and c not in ">;")
        if c.isdigit() and not inside:
            places.append(i)
    i = places[k % len(places)]
    return page[:i] + str((unicodedata.digit(page[i]) + 1) % 10) + page[i + 1:]


@relation(HOLDS, pool="order digit")
@given(st.sampled_from(ORDER_DIGIT), st.integers(0, 100))
def test_changing_one_digit_of_an_order_string_fails_the_test(t, k):
    """An `order` test with a digit in one of its strings passes on the page that writes them and fails when any
    one digit of the page is another digit, at every budget. [M121]
    Why it matters for a score: a budget is for a misread letter, not a misread figure; `present` already keeps
    its numbers exact (digits-exact), and `order` read `1982` for `1983` at one edit before this."""
    # Given an order test with a digit; the page that writes it passes
    page = answer_page(t.params)
    assert passes(t.params, page)
    # When one digit of the page is changed; Then it fails
    assert not passes(t.params, one_digit_changed(page, k)), one_digit_changed(page, k)


@relation(HOLDS, pool="table_cell digit")
@given(st.sampled_from(CELL_DIGIT), st.integers(0, 100))
def test_changing_one_digit_of_a_table_cell_test_fails_the_test(t, k):
    """A `table_cell` test with a digit in its cell, a neighbor, a heading, a section or a row group passes on the
    table that writes them and fails when any one digit of that table is another digit, at every budget. [M122]
    Why it matters for a score: the cell match is a similarity ratio that let a digit slip at one edit (`1,240`
    read `1,420`); a number is now exact, as in `present`."""
    page = answer_page(t.params)
    assert passes(t.params, page)
    assert not passes(t.params, one_digit_changed(page, k)), one_digit_changed(page, k)


# A gold and what it reads as in each type: a figure with a sign, and a figure that holds a hyphen.
SIGNED = [("net -5 total", "net 5 total", "net -5 total"), ("temp −5 C", "temp 5 C", "temp −5 C"),
          ("x = -12.5 kg", "x = 12.5 kg", "x = –12.5 kg"), ("(-5) margin", "(5) margin", "(-5) margin"),
          ("loss -$1,234 ok", "loss $1,234 ok", "loss −$1,234 ok")]
UNSIGNED = [("table 2026-11-26 ok", "table 2026 11-26 ok"), ("see A-12 and B-7", "see A12 and B-7"),
            ("pages 1-2 here", "pages 1 2 here"), ("COVID-19 cases", "COVID19 cases")]


def verdicts(gold: str, page: str, md: int) -> list[bool]:
    """Whether the page passes, for each of the three types, the test of the gold with `md` edits."""
    cell, escaped = f"<table><tr><td>{_html.escape(page)}</td></tr></table>", _html.escape(page)
    return [passes(text_test(gold, md), f"<p>{escaped}</p>"),
            passes(order_test(gold, "zzzz", md), f"<p>{escaped}</p><p>zzzz</p>"),
            passes(cell_test(gold, md), cell)]


@relation(HOLDS, domain="5 golds with a minus sign (`-` before a number or a currency symbol, after a space, a bracket or the start, `−`, "
                        "an en dash) x 4 budgets x 3 test types: the sign lost, added, or written as `−` or an en dash")
def test_a_lost_or_added_minus_sign_fails_at_any_budget():
    """A minus sign directly before a number, after white space, a bracket or the start of the string, must be
    written and cannot be added: in `present`, `order` and `table_cell`, a test whose gold has `-5` fails on `5`,
    a test whose gold has `5` fails on `-5`, and `-`, `−` and the en dash are one sign, at budgets 0 to 3. [M123]
    Why it matters for a score: a minus is not a letter; `present` passed `-5` on `5` at one edit (69% of
    sign edits on the published tests), and `order` and `table_cell` more.
    Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0): minus added or lost."""
    for gold, lost, same in SIGNED:
        for md in BUDGETS:
            # Given the gold; Then the page that writes it, the sign in another spelling, passes in all three
            assert all(verdicts(gold, gold, md)), (gold, md)
            assert all(verdicts(gold, same, md)), (gold, same, md)
            # And the sign lost fails in all three, and the sign added to the unsigned gold fails too
            assert not any(verdicts(gold, lost, md)), (gold, lost, md)
            assert not any(verdicts(lost, gold, md)), (lost, gold, md)


@relation(HOLDS, domain="4 golds with a hyphen in a date, an id, a range or a name x budget 1 to 3 x 3 test types: the "
                        "hyphen dropped or made a space, and the same with a digit changed")
def test_a_hyphen_between_figures_or_after_a_letter_is_not_a_sign():
    """A hyphen after a letter or a digit (`2026-11-26`, `A-12`, `1-2`, `COVID-19`) is a hyphen, not a minus
    sign: dropping it or making it a space costs an edit, which a budget of one pays, in `present`, `order` and `table_cell`; and the
    same page with a digit changed still fails. [M124]
    Why it matters for a score: the sign rule must not turn dates, ids and ranges into signed numbers; its cost
    is that a minus written after a letter (`x-5`) reads as a hyphen too.
    Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0): hyphenated ids and dates beside signs."""
    for gold, dropped in UNSIGNED:
        for md in (1, 2, 3):
            assert all(verdicts(gold, dropped, md)), (gold, dropped, md)
            digit = one_digit_changed(dropped, 0)
            assert not any(verdicts(gold, digit, md)), (gold, digit, md)
        assert not any(verdicts(gold, dropped, 0)), (gold, dropped)


@relation(HOLDS, domain="4 golds with a figure and words x budgets 1 to 3 x 3 test types: one letter changed, one letter "
                        "dropped, or a letter changed with a digit changed")
def test_a_letter_edit_within_the_budget_keeps_the_verdict_and_a_digit_edit_does_not():
    """A gold with a figure passes on the page with one letter changed or dropped, in `present`, `order` and
    `table_cell`, when the budget allows one edit, and fails on that page with a digit of the figure also
    changed. [M125]
    Why it matters for a score: the guard takes digits and signs out of the budget and nothing else; a misread
    letter is still what a budget pays for. Credit: ParseBench-2 (arXiv 2611.17400, A.2, CC BY 4.0): typos
    beside numbers."""
    for gold in ["Total due 1,240 units", "ratio of 3.5 to 12 cells", "year 1982 report", "dose -4.8 mg daily"]:
        letter = next(i for i, c in enumerate(gold) if c.isalpha())
        edits = [gold[:letter] + ("z" if gold[letter] != "z" else "y") + gold[letter + 1:], gold[:letter] + gold[letter + 1:]]
        for md in (1, 2, 3):
            for edited in edits:
                assert all(verdicts(gold, edited, md)), (gold, edited, md)
                digit = one_digit_changed(edited, 0)
                assert not any(verdicts(gold, digit, md)), (gold, digit, md)


SEPARATORS = [("rate 1.2 per", "rate 1,2 per"), ("rate 1,2 per", "rate 1.2 per"), ("rate 1.2 per", "rate 12 per"),
              ("rate 12 per", "rate 1.2 per"), ("rate 1.2 per", "rate 1 2 per"), ("rate 1.25 per", "rate 12.5 per"),
              ("sum 1,240 here", "sum 1.240 here"), ("sum 1,240 here", "sum 1240 here"), ("area .5 ha", "area 5 ha"),
              ("area 5 ha", "area .5 ha")]


@relation(HOLDS, domain="10 golds and pages that differ in one separator inside a number (`.` for `,`, dropped, "
                        "inserted, replaced by a space, moved, a leading point) x 4 budgets x 3 test types")
def test_a_budget_never_pays_for_a_separator_inside_a_number():
    """A number's `.` or `,` between its digits (and a leading `.`) is part of the number: a gold passes on the
    page that writes it, and fails when the page replaces, drops, inserts or moves one separator, at budgets 0
    to 3, in `present`, `order` and `table_cell`; `1,240` is not `1240`, as in `present`'s digit rule. [M180]
    Why it matters for a score: `1.2` read as `1,2` (a different quantity) cost one edit, which a budget paid.
    Credit: found in review of this change."""
    for gold, page in SEPARATORS:
        for md in BUDGETS:
            assert all(verdicts(gold, gold, md)), (gold, md)
            assert not any(verdicts(gold, page, md)), (gold, page, md)


PLUS = [("dose +1.55 mg", "dose 1.55 mg"), ("dose ±0.3 mg", "dose 0.3 mg"), ("(+5) and", "(5) and"),
        ("x = +5 ok", "x = 5 ok"), ("net +$5 total", "net $5 total")]


@relation(HOLDS, domain="5 golds with a `+` or `±` sign x 4 budgets x 3 test types: the sign lost, or added to the "
                        "unsigned gold")
def test_a_lost_or_added_plus_or_plus_minus_sign_fails_at_any_budget():
    """A `+` or `±` directly before a number, after white space, a bracket or the start of the string (not after
    a letter or a digit: `1+1`), must be written and cannot be added, at budgets 0 to 3, in `present`, `order`
    and `table_cell`. [M181]
    Why it matters for a score: dropping a plus sign (`+1.55` read `1.55`) is a misreading, as a lost minus is."""
    for gold, lost in PLUS:
        for md in BUDGETS:
            assert all(verdicts(gold, gold, md)), (gold, md)
            assert not any(verdicts(gold, lost, md)), (gold, lost, md)
            assert not any(verdicts(lost, gold, md)), (lost, gold, md)


COMMA = [("CI (1.13, 3.99) here", "CI (1.13,3.99) here"), ("on 12, 19 November 2012", "on 12,19 November 2012"),
         ("[-100, -60, 80,10]", "[-100, -60, 80, 10]")]


@relation(HOLDS, domain="3 golds with a comma between numbers (a CI, a date list, a list) x 2 directions x budgets 1 to 3 "
                        "x 3 test types: the space after the comma added or dropped; and `1,240` for `1240` or `1, 240`, `1.2` for `1, 2` or `1,2`")
def test_a_space_after_a_comma_between_numbers_is_free_but_a_dropped_comma_is_not():
    """A space added or dropped after a comma between two numbers (`(1.13, 3.99)` and `(1.13,3.99)`) keeps the
    verdict in `present`, `order` and `table_cell`, in both directions; a comma replaced or dropped (`1,240` for
    `1240` or `1, 240`, `1.2` for `1,2`) fails at budgets 1 to 3. [M182]
    Why it matters for a score: the digits and the numbers are the same, only the white space moved; the number
    guard must not turn that into a number change."""
    for gold, page in COMMA:
        for md in (1, 2, 3):
            assert all(verdicts(gold, page, md)), (gold, page, md)
            assert all(verdicts(page, gold, md)), (page, gold, md)
    for gold, page in [("sum 1,240 here", "sum 1240 here"), ("sum 1,240 here", "sum 1, 240 here"),
                      ("rate 1.2 per", "rate 1, 2 per"), ("rate 1.2 per", "rate 1,2 per"), ("rate 1,2 per", "rate 1.2 per")]:
        for md in (1, 2, 3):
            assert not any(verdicts(gold, page, md)), (gold, page, md)


LISTS = [("meet C&MS Items 630,", "meet C&MS Items 630, 632, 633 and"), ("A 630", "A 630, 632"),
         ("pages 5 and 7", "pages 5 and 7, 9"), ("Items 630, 632", "see Items 630, 632, 633")]


@relation(HOLDS, domain="4 golds that stop at a number of a list x budgets 0 to 3 x `present` and `order`: the page "
                        "prints the list on, with more numbers after a comma and a space")
def test_a_gold_that_stops_inside_a_list_of_numbers_passes():
    """A gold that ends at a number of a list (`Items 630,`, `pages 5 and 7`) passes on a page that prints the list
    on (`Items 630, 632, 633`), in `present` and `order`, at budgets 0 to 3: a comma and a space end a number. [M183]
    Why it matters for a score: a number guard that joined a list into one number would fail faithful pages."""
    for gold, page in LISTS:
        for md in BUDGETS:
            escaped = _html.escape(page)
            assert passes(text_test(gold, md), f"<p>{escaped}</p>"), (gold, page, md)
            assert passes(order_test(gold, "zzzz", md), f"<p>{escaped}</p><p>zzzz</p>"), (gold, page, md)
