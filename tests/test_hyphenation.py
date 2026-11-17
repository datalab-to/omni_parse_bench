"""Continuation tolerance without discarding a compound's hyphen."""
import itertools
import subprocess
import sys

import pytest

from omni_parse_bench import normalize, views
from omni_parse_bench.scorers.unit_tests import hyphenation, runners as R


def present(gold, prediction):
    return R.found(R.Text(gold, 0), views.html(prediction))[0]


@pytest.mark.parametrize("joined, split", [
    ("মানুহৰ", "মানু- হৰ"),
    ("পঢ়িবলৈ", "পঢ়ি-\nবলৈ"),
    ("नमस्कार", "नम- स्कार"),
    ("মানুহৰ", "মানু‐ হৰ"),
    ("মানুহৰ", "মানু‑ হৰ"),
    ("caféine", "cafe\u0301- ine"),
])
def test_continuations_on_either_side(joined, split):
    assert present(joined, split)
    assert present(split, joined)


def test_mixed_interpretations_in_one_match():
    assert present("নিত্য-নৈমিত্তিক মানুহৰ পঢ়িবলৈ",
                   "নিত্য-\nনৈমিত্তিক মানু- হৰ পঢ়ি- বলৈ")
    assert present("মানু- হৰ পঢ়িবলৈ", "মানুহৰ পঢ়ি- বলৈ")


def test_spaced_hyphen_is_optional_on_the_gold_side_too():
    # Gold may carry a line-end hyphen, as the existing Latin rule already allows.
    assert present("মানু- হৰ", "মানুহৰ")
    assert present("well- known method", "wellknown method")
    assert present("well- known method", "well known method")


@pytest.mark.parametrize("hyphen", ["-", "‐", "‑"])
@pytest.mark.parametrize("space", [" ", "\n"])
def test_latin_wrapped_compounds_keep_both_readings(hyphen, space):
    wrapped = f"well{hyphen}{space}known method"
    for gold in ("well-known method", "wellknown method"):
        assert present(gold, wrapped)
        assert present(wrapped, gold)
    assert not present("well-known method", "wellknown method")
    assert not present("wellknown method", "well-known method")


def test_latin_mixed_hyphen_interpretations_in_one_match():
    gold = "well-known developers use state-of-the-art methods"
    wrapped = "well- known develop- ers use state- of-the- art methods"
    assert present(gold, wrapped)
    assert present(wrapped, gold)


def test_a_compound_in_capitals_keeps_both_readings():
    # Fold joins a line-end hyphen between two words in capitals, as in lower case; so the hyphen stays
    # optional there, as in lower case, and a heading in capitals still matches the compound.
    for wrapped in ("SELF- AWARE", "self- aware"):
        assert present("self-aware", wrapped) and present("selfaware", wrapped)
        assert present(wrapped, "self-aware") and present(wrapped, "selfaware")
    # A capital after a word in mixed case keeps the hyphen: the compound, not the joined word.
    assert present("self-aware", "Self- Aware") and not present("selfaware", "Self- Aware")


def test_published_korean_compound_regression():
    gold = "있다. T점수가 40점 이하를 낮은 점수라고 본다. 나는 남성성-여성성인 척도 5번이"
    assert present(gold, gold.replace("성-여", "성-\n여"))
    assert not present(gold, gold.replace("성-여", "성여"))


@pytest.mark.parametrize("gold, pred", [
    ("মানুহৰ", "মানু-হৰ"),              # no whitespace evidence
    ("নিত্য-নৈমিত্তিক", "নিত্যনৈমিত্তিক"),
    ("মানুহৰ", "মানু— হৰ"),             # dash, not a wrapping hyphen
    ("মানুহৰ", "মানু– হৰ"),
    ("মানুহৰ", "মানু− হৰ"),
    ("caféIne", "cafe\u0301- Ine"),     # uppercase continuation
    ("caféǅine", "cafe\u0301- ǅine"),   # titlecase continuation
    ("\u0301হৰ", "\u0301- হৰ"),        # unattached combining mark
    ("মানুহৰ", "মানু- বৰ"),             # no extra fuzzy edit allowance
])
def test_no_new_exemption_for_other_differences(gold, pred):
    assert not present(gold, pred)


def test_fold_itself_still_preserves_uncased_breaks():
    assert normalize.fold("পঢ়ি- বলৈ") == "পঢ়ি- বলৈ"
    assert normalize.fold("well- known develop-\ners") == "wellknown developers"


def test_order_and_repeat_keep_their_existing_rules():
    # An unrelated hyphen must not activate new order behavior.
    t = R.Order("ab", "cd", 0)
    assert not R.order(t, views.html("cd ab c d"))[0]
    assert not R.order(t, views.html("cd ab c d X- য"))[0]
    assert R.repeat(R.Repeat("মানুহৰ", 0), views.html("অঁমানু- হৰ"))[0]


def runs(t, page):
    return {R.Order: R.order, R.Repeat: R.repeat, R.TableCell: R.table_cell}[type(t)](t, views.html(page))[0]


@pytest.mark.parametrize("t, page", [
    (R.Order("self-aware", "tail", 0), "<p>self- aware</p><p>tail</p>"),
    (R.Order("self- aware", "tail", 0), "<p>self-aware</p><p>tail</p>"),
    (R.Order("head", "self-aware", 0), "<p>head</p><p>self-<br>aware</p>"),
    (R.Order("মানুহৰ", "শেষ", 0), "মানু- হৰ শেষ"),
    (R.Repeat("self-aware", 1), "<p>self- aware</p>"),
    (R.Repeat("self- aware", 1), "<p>self-aware</p>"),
    (R.TableCell("self-aware", {}, 0), "<table><tr><td>self- aware</td></tr></table>"),
    (R.TableCell("self- aware", {}, 0), "<table><tr><td>self-aware</td></tr></table>"),
    (R.TableCell("x", {"right": "self-aware"}, 0), "<table><tr><td>x</td><td>self- aware</td></tr></table>"),
    (R.TableCell("x", {"top_heading": "Primary- Revision"}, 0),
     "<table><tr><th>PRIMARY- REVISION</th></tr><tr><td>x</td></tr></table>"),
    (R.TableCell("x", {}, 0, headings=("self-aware",)),
     "<table><tr><th>self- aware</th></tr><tr><td>x</td></tr></table>"),
])
def test_order_repeat_and_table_cell_read_a_broken_compound_either_way(t, page):
    # As present does: a hyphen a line broke after, on the page or in the gold, read kept or dropped.
    assert runs(t, page)


def test_the_hyphen_fallback_never_fails_headings_the_plain_reading_matches():
    # A cell that takes several headings through a broken hyphen must not leave one to a later cell that the
    # plain reading would have matched: the plain reading is tried first.
    t = R.TableCell("x", {}, 0, headings=("self-", "aware", "Total"))
    page = ("<table><tr><th>self-<br>self-aware</th></tr><tr><th>aware Total</th></tr>"
            "<tr><td>x</td></tr></table>")
    assert runs(t, page)


@pytest.mark.parametrize("t, page", [
    (R.Order("tail", "self-aware", 0), "<p>self- aware</p><p>tail</p>"),       # still in order only
    (R.Order("self-aware", "tail", 0), "<p>self-awre</p><p>tail</p>"),         # no edits to spend
    (R.Repeat("self-aware", 1), "<p>xself- aware</p>"),                        # still whole words
    (R.TableCell("self-aware", {}, 0), "<table><tr><td>self- aware x</td></tr></table>"),   # the whole cell
    (R.TableCell("self-aware", {}, 0), "<table><tr><td>selfaware</td></tr></table>"),       # unspaced
])
def test_the_hyphen_fallback_adds_no_other_way_to_pass(t, page):
    assert not runs(t, page)


@pytest.mark.parametrize("count, passes", [(1, True), (2, True), (3, False)])
def test_repeat_counts_a_word_written_whole_and_broken_as_two_copies(count, passes):
    # The main count sees the whole copy (1); the fallback reads both, each once (2), never more. With 1 the
    # main count passes, as it did: the fallback only adds a way to pass.
    page = "<p>self-aware</p><p>self- aware</p>"
    assert runs(R.Repeat("self-aware", count), page) is passes
    assert runs(R.Repeat("self-aware", 2), "<p>self- aware</p><p>self- aware</p>")
    assert not runs(R.Repeat("self-aware", 2), "<p>self- aware</p>")


def test_fallback_requires_a_continuation_inside_the_match():
    assert not hyphenation.matches("foo", "foo X- য")
    assert not hyphenation.matches("foo", "X- foo")
    assert not hyphenation.matches("foo", "foo- x")
    assert not hyphenation.matches("foo-", "foo- x")
    assert not hyphenation.matches("-foo", "x- foo")
    assert not hyphenation.matches("মানুহৰ", "মানুহৰ X- য")
    assert hyphenation.matches("মানুহৰ", "İ মানু- হৰ")


@pytest.mark.parametrize("gold, page, passes", [
    ("self-aware 40", "self-aware 400", False),
    ("self-aware 40", "self-aware 40 0", True),
    ("self-aware 40", "self-aware 40.", True),
    ("12 self-aware", "112 self-aware", False),
    ("12 self-aware", "1 12 self-aware", True),
])
def test_a_wrapped_compound_keeps_the_digit_edge(gold, page, passes):
    # Unbroken and wrapped across a line, the same verdict: an exact match cut out of a longer number fails.
    assert present(gold, page) is passes
    assert present(gold, page.replace("-", "- ", 1)) is passes


@pytest.mark.parametrize("first, letter, last", [("অ", "ক", "শেষ"), ("a", "b", "end")])
def test_mixed_hyphen_interpretations_follow_the_presence_policy(first, letter, last):
    # J = joined, W = wrapping evidence, H = a required unspaced hyphen.
    forms = {"J": "", "W": "- ", "H": "-"}
    for left, right in itertools.product(itertools.product(forms, repeat=3), repeat=2):
        gold = first + "".join(forms[x] + letter for x in left) + last
        pred = first + "".join(forms[x] + letter for x in right) + last
        compatible = all({a, b} != {"J", "H"} for a, b in zip(left, right, strict=True))
        assert present(gold, pred) == compatible, (left, right)


def test_adversarial_optional_hyphens_finish_without_backtracking():
    code = """
from omni_parse_bench.scorers.unit_tests import hyphenation
for n in (24, 100, 500):
    assert not hyphenation.matches(('অ- ' * n) + 'অz', ('অ ' * n) + 'অy')
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=5)
