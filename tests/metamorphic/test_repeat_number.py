"""Relations of repeat tests with a number arg: the count is exact (M34a), a number written with other
separators or with a digit glued on is no copy (M34b, M34c), what `present` ignores around a number leaves the
count alone (M34d), a decimal is no copy where more of its digits follow (M34e) or with a zero added or
dropped (M34f), a group of digits is not counted across a cell, paragraph or space (M34g), a copy `repeat`
counts is one `present` finds (M35), and the same holds for the loaded tests (M34a)."""
from __future__ import annotations

import random

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from metamorphic.test_numbers import one_digit_glued, one_separator_changed

from metamorphic.common import HOLDS, REPEAT_NUMBER, escaped, more_evidence, passes, relation
from omni_parse_bench import views
from omni_parse_bench.scorers.unit_tests import runners

FILLER = ["foo", "bar", "baz"]


@st.composite
def numbers(draw):
    """A number gold that loads: 1 to 8 digits whole, grouped by `,`, `.`, a space or not, perhaps a decimal
    part, a sign (-, a true minus or an en dash), a currency sign, parentheses and a percent sign."""
    whole = str(draw(st.integers(1, 10**7)))
    sep = draw(st.sampled_from([",", ".", " ", ""]))
    frac = draw(st.sampled_from(["", ".5", ",25", ".125", ".0472"]))
    groups = [whole[max(0, i - 3):i] for i in range(len(whole), 0, -3)][::-1]
    sign = draw(st.sampled_from(["", "-", "\u2212", "\u2013"]))
    cur = draw(st.sampled_from(["", "", "$", "\u20ac"]))
    body = f"{sign}{cur}{sep.join(groups)}{frac}{draw(st.sampled_from(['', '%']))}"
    gold = f"({body})" if draw(st.booleans()) and not sign else body
    assume(runners.number(gold) is not None and frac[:1] != sep)
    return gold


def page(items: list[str], rnd: random.Random) -> str:
    """The items and three filler words, each in a paragraph of its own, shuffled."""
    items = [*items, *(rnd.choice(FILLER) for _ in range(3))]
    rnd.shuffle(items)
    return "".join(f"<p>{escaped(x)}</p>" for x in items)


@relation(HOLDS)
@given(numbers(), st.integers(1, 4), st.randoms(use_true_random=False))
def test_a_number_repeat_test_needs_exactly_its_count(gold, n, rnd):
    """A repeat test of a number, n copies expected, passes on a page with its number written n times, and
    fails with n + 1 or n - 1 copies. [M34a]
    Why it matters for a score: the count of a repeated number (a total, a dose, a value in several cells)
    is what a merged or invented cell changes; M5 states the same for text."""
    # Given a repeat test of n for a number; When the page writes it n times, among filler; Then it passes
    r = runners.Repeat(runners.Number(gold), n)
    assert passes(r, page([gold] * n, rnd))
    # When it writes it n + 1 or n - 1 times; Then it fails
    assert not passes(r, page([gold] * (n + 1), rnd))
    assert not passes(r, page([gold] * (n - 1), rnd))


@relation(HOLDS)
@given(numbers(), st.integers(1, 3), st.integers(1, 3), st.data(), st.randoms(use_true_random=False))
def test_a_number_written_with_other_separators_is_not_a_copy(gold, k, j, data, rnd):
    """A repeat test of a number, k copies expected, passes on a page with k copies as written and j more
    written with one separator (`,`, `.` or a space) dropped, swapped or added between two digits, and fails
    when it expects k + j (`1,240` does not count `1240`, `1.240`, `1 240` or `1,2,40`). [M34b]
    Why it matters for a score: a model that reprints a figure with other punctuation has not copied it."""
    # Given k copies as written; When j others are written with a changed separator; Then only the k count
    assume(one_separator_changed(gold))     # a single digit has no separator to change
    others = data.draw(st.lists(st.sampled_from(one_separator_changed(gold)), min_size=j, max_size=j))
    pg = page([gold] * k + others, rnd)
    assert passes(runners.Repeat(runners.Number(gold), k), pg), (gold, others)
    assert not passes(runners.Repeat(runners.Number(gold), k + j), pg), (gold, others)


@relation(HOLDS)
@given(numbers(), st.integers(1, 3), st.integers(1, 3), st.data(), st.randoms(use_true_random=False))
def test_a_number_with_a_digit_glued_on_is_not_a_copy(gold, k, j, data, rnd):
    """A repeat test of a number, k copies expected, passes on a page with k copies and j more with a digit
    glued before or after the number's digits, and fails when it expects k + j (`1,240` does not count
    `91,240` or `1,2409`). [M34c]
    Why it matters for a score: a figure with a digit added or run into its neighbour is another figure."""
    # Given k copies; When j others have a digit glued on; Then only the k count
    others = data.draw(st.lists(st.sampled_from(one_digit_glued(gold)), min_size=j, max_size=j))
    pg = page([gold] * k + others, rnd)
    assert passes(runners.Repeat(runners.Number(gold), k), pg), (gold, others)
    assert not passes(runners.Repeat(runners.Number(gold), k + j), pg), (gold, others)


@relation(HOLDS)
@given(st.integers(1, 999), st.integers(1, 9999), st.integers(1, 3), st.randoms(use_true_random=False))
def test_a_decimal_with_a_trailing_zero_added_or_dropped_is_not_a_copy(whole, frac, k, rnd):
    """A repeat test of a decimal number (`8.455`, `0.50`), k copies expected, passes on a page with k copies
    and others with a zero added to or dropped from the end of its decimals (`8.455` has `8.4550` and
    `8.45500`, `0.50` has `0.500` and `0.5`), and fails when it expects one more. [M34f]
    Why it matters for a score: precision is part of a figure; `8.4550` is not `8.455`, so a model that
    normalises its decimals has not copied them."""
    # Given a decimal with k copies; When others have a zero added to, or dropped from, its decimals
    digits = str(frac).rstrip("0") or "1"
    gold = f"{whole}.{digits}0" if rnd.random() < .5 else f"{whole}.{digits}"
    assume(runners.number(gold) is not None)
    others = [f"{gold}0", f"{gold[:-1]}" if gold.endswith("0") else f"{gold}00"]
    assume(all(o.rstrip(".") != gold and not o.endswith(".") for o in others))
    pg = page([gold] * k + others, rnd)
    # Then only the k copies count
    assert passes(runners.Repeat(runners.Number(gold), k), pg), (gold, others)
    assert not passes(runners.Repeat(runners.Number(gold), k + 1), pg), (gold, others)


WRAPS = ["{}", "({})", "${}", "€{}", "{}.", "{},", "{}, then", "see {}", "{}. Next", " {} "]


@relation(HOLDS)
@given(numbers(), st.lists(st.sampled_from(WRAPS), min_size=1, max_size=4), st.randoms(use_true_random=False))
def test_what_present_ignores_around_a_number_leaves_the_count_alone(gold, wraps, rnd):
    """A repeat test of a number passes on a page with as many copies as it expects, each written plain, in
    parentheses, after a currency sign, before a full stop or a comma, or in a sentence, and fails with one
    more. [M34d]
    Why it matters for a score: a copy in a sentence or a cell with a currency sign or parentheses is a copy
    (`present` finds it there), and counting it differently would let a test pass where `present` fails."""
    # Given a repeat test of n; When each copy is written in one of the wrappings; Then it passes
    n = len(wraps)
    items = [w.format(gold) for w in wraps]
    r = runners.Repeat(runners.Number(gold), n)
    assert passes(r, page(items, rnd)), items
    # When one copy more is written; Then it fails
    assert not passes(r, page([*items, gold], rnd)), items


@relation(HOLDS)
@given(st.tuples(st.integers(1, 999), st.integers(1, 99)).map(lambda x: f"{x[0]}.{x[1]}"),
       st.integers(1, 3), st.sampled_from(".,"), st.integers(0, 9), st.randoms(use_true_random=False))
def test_a_decimal_followed_by_a_point_and_a_digit_is_not_a_copy(gold, k, sep, d, rnd):
    """A repeat test of a decimal number (`12.5`), k copies expected, passes on a page with k copies and
    others where `.` or `,` and one or two digits follow it at once (`12.5.7`, `12.5,77`), and fails when it
    expects one more. [M34e]
    Why it matters for a score: as for M20, '12.5' cut out of '12.5.7' is a different number."""
    # Given k copies, some with clean tails (`12.5.`, `12.5, then`); When others have a point or comma, digits
    r = runners.Repeat(runners.Number(gold), k)
    tails = ([".", ", then", ""] * 2)[:k]
    pg = page([f"{gold}{t}" for t in tails] + [f"{gold}{sep}{d}", f"{gold}{sep}{d}{d}"], rnd)
    # Then only the k copies count
    assert passes(r, pg), pg
    assert not passes(runners.Repeat(runners.Number(gold), k + 1), pg), pg


@pytest.mark.skipif(not REPEAT_NUMBER, reason="no number-repeat test in this set of tests")
@more_evidence(pool="repeat number")
@given(st.sampled_from(REPEAT_NUMBER or [None]), st.randoms(use_true_random=False))
def test_a_loaded_number_repeat_test_needs_exactly_its_count(t, rnd):
    """The same holds for each loaded repeat test with a number and its own number and count. [M34a]
    Why it matters for a score: as for M34a, on the numbers the tests really hold."""
    # Given a loaded repeat test with a number; When its number is written exactly its count of times, or one
    # more or fewer
    # Then it passes, then fails twice
    p = t.params
    n, c = p.content.number, p.expected_count
    assert passes(p, page([n] * c, rnd))
    assert not passes(p, page([n] * (c + 1), rnd))
    assert not passes(p, page([n] * (c - 1), rnd))


@relation(HOLDS)
@given(st.integers(1, 999), st.integers(100, 999), st.randoms(use_true_random=False))
def test_a_group_of_digits_is_not_counted_across_a_cell_a_paragraph_or_a_space(a, g, rnd):
    """A repeat test of a number of three digits, one copy expected, passes on a page holding it in a cell of
    its own after a cell of another number (`12 | 500`), and when another copy continues a group of digits
    across a space (`Total 12 500`, `1 000 000`) the page holds one copy fewer; a test of a number grouped
    by a space (`12 500`) fails on a page that writes its groups in two cells or paragraphs. [M34g]
    Why it matters for a score: a space groups digits, and a block break is a space to the text view: without
    this a repeated figure would be counted inside a longer one, or across two cells that merely sit side by
    side."""
    assume(a != g)
    gold = str(g)
    # Given the number in a cell of its own beside another: one copy
    cells = f"<table><tr><td>{a}</td><td>{gold}</td></tr></table>"
    assert passes(runners.Repeat(runners.Number(gold), 1), cells)
    # When a copy of it continues a group on its line ("Total 12 500") and another stands alone, one counts
    pg = f"<p>Total {a} {gold}</p><p>Fee {gold}</p>"
    assert passes(runners.Repeat(runners.Number(gold), 1), pg), pg
    assert not passes(runners.Repeat(runners.Number(gold), 2), pg), pg
    # When a number grouped by a space is written in two cells or two paragraphs; Then it is not found
    grouped = f"{a} {gold}"
    assert not passes(runners.Repeat(runners.Number(grouped), 1), f"<p>{a}</p><p>{gold}</p>")
    assert not passes(runners.Repeat(runners.Number(grouped), 1), cells)
    assert not passes(runners.Repeat(runners.Number(grouped), 1), f"<p>{a}<br>{gold}</p>")
    # And written on one line it is found
    assert passes(runners.Repeat(runners.Number(grouped), 1), f"<p>{grouped}</p>")


NUMBER_TOKENS = ["1,240", "12", "500", "12 500", "$1,240", "(4.8)", "-4.8", "4.8%", "1 000", "10", "5,5", "x",
                 "see", "1.240", "1240", "<sup>2</sup>", "[1]", "<br>", "</p><p>", "&nbsp;"]


@relation(HOLDS)
@given(st.sampled_from(["1,240", "12", "500", "12 500", "4.8", "-4.8", "1 000", "10", "1240"]),
       st.lists(st.sampled_from(NUMBER_TOKENS), max_size=10))
def test_a_number_repeat_copy_is_one_present_finds(gold, tokens):
    """A number that a repeat test counts at least once on a page is found by a present test for it: repeat is
    never more lenient than present (it also leaves out the digits of a footnote mark or a list, and counts
    line by line). [M35]
    Why it matters for a score: a page cannot pass a count of one for a number that a presence test fails."""
    # Given a page of numbers, marks and breaks; When repeat finds a copy; Then present finds it too
    page_html = "<p>" + " ".join(tokens) + "</p>"
    if runners._number_copies(gold, views.html(page_html)):
        assert passes(runners.Present(runners.Number(gold)), page_html), page_html
