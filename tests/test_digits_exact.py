"""A present text test with edits to spend keeps its numbers exact: each maximal run of digits is one token
that an edit may not touch (`runners._numbers_kept`). Checked on the documented cases, against a brute-force
reference, for monotonicity in the budget, and for speed."""
from __future__ import annotations

import re
import time

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from omni_parse_bench import normalize, views
from omni_parse_bench.scorers.unit_tests import runners as R


def passes(gold: str, page: str, k: int) -> bool:
    return R.found(R.Text(gold, k), views.html(f"<p>{page}</p>"))[0]


@pytest.mark.parametrize("gold, page, k, want", [
    ("Total: 41", "Total: 41", 1, True),
    ("Total: 41", "Total: 40", 1, False),         # a number differs
    ("Total: 41", "Total: 40", 3, False),         # at any budget
    ("Total: 41", "Total: 400", 1, False),
    ("Total: 41", "Totel: 41", 1, True),          # a letter edit is within the budget
    ("Total: 41", "Totel: 41", 2, True),
    ("Total: 41", "Total: 4 1", 1, False),        # a number split by a space
    ("Total: 41", "Total: 4 1", 3, False),
    ("Total: 41", "Total 4.1", 3, False),         # split by a dot
    ("Total 41", "Tota1 41", 1, False),           # a number added
    ("Total 41", "Tota1 41", 3, False),
    ("Figure 3", "Figure 3 2019 data", 0, True),  # what follows the stretch is outside it
    ("Figure 3", "Figure 3 2019 data", 1, True),
    ("Figure 3", "Figure 3 2019 data", 3, True),
    ("Pages 1 to 2", "Pages 12", 3, False),       # two numbers joined
    ("1,000", "1000", 1, False),
    ("1000", "1,000", 1, False),
    ("3.", "๓.", 1, False),                       # another script's digit is another number
    ("3 x", "３ x", 1, True),                      # full width folds to ASCII first
    ("ab 12", "ab 12", 1, True),
    ("Total 41", "41 Total", 2, False),           # the letters must still be within budget
    ("price 1", "price 1,000 and price 2", 1, False),   # a glued copy and a changed number: two stretches
    ("total 4", "total 4.5 and total 7", 1, False),
    ("total 4", "total 4.5 and totl 4", 1, True),
])
def test_the_documented_consequences(gold, page, k, want):
    assert passes(gold, page, k) is want


@pytest.mark.parametrize("gold, page", [
    ("Totl: 41", "Total: 41"),                    # a deleted letter
    ("Total: 41", "Totl: 41"),                    # an inserted letter
    ("Total 41 kg", "Total 41 kgs"),
])
def test_letter_edits_pass_in_both_directions(gold, page):
    assert passes(gold, page, 1) and passes(page, gold, 1)


@pytest.mark.parametrize("gold, page", [
    ("Total: 41", "Total: 40"), ("Total: 41", "Total: 4 1"), ("Total: 41", "Total: 4.1"),
    ("1,000", "1000"), ("Pages 1 to 2", "Pages 12"), ("Tota 41", "Tota1 41"),
])
def test_number_edits_fail_in_both_directions(gold, page):
    assert not passes(gold, page, 2) and not passes(page, gold, 2)


def test_no_digit_keeps_todays_verdicts():
    # A gold without a digit never reaches the rule: the verdict is `_contains`'s.
    assert passes("Totl", "Total 400", 1)
    assert passes("Total due", "TotalDue 41", 0)


@pytest.mark.parametrize("gold, page, want", [
    ("Total: 41", "Total: 41", True),
    ("Total: 41", "Total:41", True),              # spacing between a word and a number stays free
    ("Total: 41", "Total: 40", False),
    ("21", "2 1 2", False),                       # the squeezed retry never joins two numbers
    ("11", "2ab 1 1 bb", False),
    ("305357", "3 0 5 3 5 7", False),
    ("40", "400 4 0", False),
    ("1 2", "12", False),
    ("12", "1<sup>2</sup>", False),               # an exponent is not part of the number
])
def test_with_no_budget_numbers_are_exact_too(gold, page, want):
    assert passes(gold, page, 0) is want
    assert passes(gold, page, 1) is want          # and k = 1 agrees: no fail-to-pass from k = 0 to 1


@pytest.mark.parametrize("gold, page, want", [
    ("1½", "1 1/2", True), ("1 1/2", "1½", True),   # the whole number stays apart from the numerator
    ("1½", "11/2", False), ("11/2", "1½", False),
    ("1½", "1/2", False),
    ("¾", "3/4", True), ("3/4", "¾", True),
    ("10½\" pitch", "10 1/2\" pitch", True),
])
def test_a_vulgar_fraction_after_a_digit_is_a_number_of_its_own(gold, page, want):
    assert normalize.fold("1½") == "1 1/2" and normalize.fold("½") == "1/2"
    assert passes(gold, page, 0) is want


def test_the_failure_says_a_number_differs():
    ok, why = R.found(R.Text("Total: 41", 1), views.html("<p>Total: 40</p>"))
    assert not ok and why == ("'Total: 41' not found with its numbers exact (a number differs, or one was "
                              "added, split or joined)")


def test_the_retries_keep_numbers_exact():
    # Footnote markers dropped
    assert passes("Smith and Jones 41", "Smith[1] and Jones 41", 1)
    assert not passes("Smith and Jones 41", "Smith[1] and Jones 4 1", 1)
    # A word broken at a line end
    assert passes("Developers have 41", "Develop- ers have 41", 1)
    assert not passes("Developers have 41", "Develop- ers have 4 1", 1)
    assert not passes("Developers have 4 1", "Develop- ers have 41", 1)
    # Squeezed: spacing between words is free, between two numbers it is not
    assert passes("Total 41 kg", "Total41kg", 1)
    assert not passes("1 2 kg", "12 kg", 1)


def test_a_private_use_character_on_the_page_is_not_a_number():
    assert not passes("Total 41", "Total \U000F0001", 1)
    assert R._tokens("a 41", "a \U000F0001 41")[1][2] == "�"


# ------------------------------------------------------------------------------------- reference

ALPHABET = "ab12 .,"
NUMBER = "\U000F0000"


def encoded(gold: str, page: str) -> tuple[str, str]:
    """Both strings with each distinct number (digit runs joined by a `.`, or a `,` before one to three
    digits; a leading `.` after a space or bracket) made one private-use character of its own."""
    codes: dict[str, str] = {}

    def encode(s: str) -> str:
        return re.sub(r"(?:(?<![^ \t\n\xa0(\[{<>=:;|/±+-])\.(?=\d))?\d+(?:\.\d+|, ?\d{1,3}(?!\d))*",
                      lambda m: codes.setdefault(m[0].replace(" ", ""), chr(ord(NUMBER) + len(codes))), s)
    return encode(gold), encode(page)


def distance(s: str, t: str, k: int) -> int:
    """The optimal string alignment distance from `s` to `t`, an edit that touches a number costing k + 1."""
    def number(c: str) -> bool:
        return c >= NUMBER

    def one(c: str) -> int:
        return k + 1 if number(c) else 1
    d = [[0] * (len(t) + 1) for _ in range(len(s) + 1)]
    for i in range(1, len(s) + 1):
        d[i][0] = d[i - 1][0] + one(s[i - 1])
    for j in range(1, len(t) + 1):
        d[0][j] = d[0][j - 1] + one(t[j - 1])
    for i in range(1, len(s) + 1):
        for j in range(1, len(t) + 1):
            a, b = s[i - 1], t[j - 1]
            d[i][j] = min(d[i - 1][j] + one(a), d[i][j - 1] + one(b),
                          d[i - 1][j - 1] + (0 if a == b else max(one(a), one(b))))
            if (i > 1 and j > 1 and a == t[j - 2] and s[i - 2] == b and a != b
                    and not number(a) and not number(b)):
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def reference(gold: str, page: str, k: int) -> bool:
    """The rule by brute force: every stretch of the page between token boundaries, spaced and squeezed, once
    exact copies cut out of a longer number are blanked out (`_unglue`, the digit edge `_contains` keeps)."""
    def within(want: str, hay: str) -> bool:
        return any(distance(want, hay[a:b], k) <= k
                   for a in range(len(hay) + 1) for b in range(a, len(hay) + 1))
    if not gold.replace(" ", ""):
        return False
    want, hay = encoded(gold, R._unglued_both(gold, page))
    return within(want, hay) or within(want.replace(" ", ""), hay.replace(" ", ""))


def same(s: str) -> str:
    return s


@given(st.text(ALPHABET, min_size=1, max_size=7), st.text(ALPHABET, max_size=12), st.integers(0, 3))
def test_the_rule_agrees_with_brute_force(gold, page, k):
    assert R._numbers_kept(gold, page, k, same, same) is reference(gold, page, k)


@st.composite
def near_copies(draw) -> tuple[str, str, int]:
    """A gold, a page that holds it with k edits (an adjacent swap most likely) between other text, and k."""
    gold = draw(st.text(ALPHABET, min_size=2, max_size=8))
    out, k = list(gold), draw(st.integers(0, 3))
    for _ in range(k):
        i = draw(st.integers(0, len(out) - 1))
        match draw(st.sampled_from("ttsid")):
            case "s": out[i] = draw(st.sampled_from(ALPHABET))
            case "i": out.insert(i, draw(st.sampled_from(ALPHABET)))
            case "d" if len(out) > 1: del out[i]
            case "t" if i + 1 < len(out): out[i], out[i + 1] = out[i + 1], out[i]
    return gold, draw(st.text(ALPHABET, max_size=3)) + "".join(out) + draw(st.text(ALPHABET, max_size=3)), k


@example(("xabcx", "xbacx", 1))
@example(("1ab 2", "1ba 2", 1))
@example(("a1b", "1ab", 2))
@example(("11a1a", "11aa1", 1))     # a number swapped with a letter is an edit that touches a number
@given(near_copies())
def test_the_rule_agrees_with_brute_force_on_near_copies(copy):
    gold, page, k = copy
    for budget in {max(k - 1, 0), k}:
        assert R._numbers_kept(gold, page, budget, same, same) is reference(gold, page, budget)


@example("21", "2 1 2", 0)
@example("11", "2ab 1 1 bb", 0)
@given(st.text(ALPHABET, min_size=1, max_size=8), st.text(ALPHABET, max_size=16), st.integers(0, 3))
def test_a_pass_at_one_budget_passes_at_the_next(gold, page, k):
    if passes(gold, page, k):
        assert passes(gold, page, k + 1)
    if R._numbers_kept(gold, page, k, same, same):
        assert R._numbers_kept(gold, page, k + 1, same, same)


@given(st.text(ALPHABET, min_size=1, max_size=8), st.text(ALPHABET, max_size=16), st.integers(1, 3))
def test_the_rule_never_passes_what_plain_edits_fail(gold, page, k):
    # Why the prefilter is sound: the rule's costs are never below plain edits', so it only turns passes
    # into fails.
    if R._numbers_kept(gold, page, k, same, same):
        assert (R._edits_scan(gold, page) <= k
                or R._edits_scan(gold.replace(" ", ""), page.replace(" ", "")) <= k)


# ------------------------------------------------------------------------------------- speed
# Note: the worst shapes for the rule are pages that `_contains` passes and the rule fails everywhere, with
# every number of the gold on the page (else `_tokens` ends it at once). Each runs in well under a second;
# the bounds are generous so a slow machine never fails them.

def seconds(gold: str, page: str, k: int) -> tuple[float, bool]:
    v = views.html(f"<p>{page}</p>")
    start = time.perf_counter()
    ok = R.found(R.Text(gold, k), v)[0]
    return time.perf_counter() - start, ok


@pytest.mark.parametrize("last, want", [("Total due 41.5 0 50", False), ("Totl due 41.50", True)])
def test_many_near_copies_of_a_short_gold_stay_fast(last, want):
    page = " ".join(["Total due 41.5 0 50"] * 2999 + [last])     # each copy splits a number
    took, ok = seconds("Total due 41.50", page, 2)
    assert ok is want and took < 10, took


@pytest.mark.parametrize("good", [False, True])
def test_a_long_digit_dense_gold_on_a_long_page_stays_fast(good):
    numbers = [f"{i * 37 % 1000:03d}" for i in range(100)]
    gold = " ".join(numbers)                                        # 399 characters, 100 numbers
    split = " ".join(numbers[:-1] + [numbers[-1][:2] + " " + numbers[-1][2:]])
    copies = [split] * 49 + [gold.replace(" ", "/", 30) if good else split]   # 30 edits, numbers kept
    page = numbers[-1] + " " + " ".join(copies)                     # about 20,000 characters
    took, ok = seconds(gold, page, 40)
    assert ok is good and took < 10, took
