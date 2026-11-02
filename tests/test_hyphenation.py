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


def test_order_and_repeat_keep_their_existing_rules():
    # An unrelated hyphen must not activate new order behavior.
    t = R.Order("ab", "cd", 0)
    assert not R.order(t, views.html("cd ab c d"))[0]
    assert not R.order(t, views.html("cd ab c d X- য"))[0]
    # Continuation tolerance is deliberately confined to text presence.
    assert not R.order(R.Order("মানুহৰ", "শেষ", 0), views.html("মানু- হৰ শেষ"))[0]
    assert R.repeat(R.Repeat("মানুহৰ", 0), views.html("অঁমানু- হৰ"))[0]


def test_fallback_requires_a_continuation_inside_the_match():
    assert not hyphenation.matches("foo", "foo X- য")
    assert not hyphenation.matches("foo", "X- foo")
    assert not hyphenation.matches("foo", "foo- x")
    assert not hyphenation.matches("মানুহৰ", "মানুহৰ X- য")
    assert hyphenation.matches("মানুহৰ", "İ মানু- হৰ")


def test_mixed_hyphen_interpretations_follow_the_presence_policy():
    # J = joined, W = wrapping evidence, H = a required unspaced hyphen.
    forms = {"J": "", "W": "- ", "H": "-"}
    for left, right in itertools.product(itertools.product(forms, repeat=3), repeat=2):
        gold = "অ" + "".join(forms[x] + "ক" for x in left) + "শেষ"
        pred = "অ" + "".join(forms[x] + "ক" for x in right) + "শেষ"
        compatible = all({a, b} != {"J", "H"} for a, b in zip(left, right, strict=True))
        assert present(gold, pred) == compatible, (left, right)


def test_adversarial_optional_hyphens_finish_without_backtracking():
    code = """
from omni_parse_bench.scorers.unit_tests import hyphenation
for n in (24, 100, 500):
    assert not hyphenation.matches(('অ- ' * n) + 'অz', ('অ ' * n) + 'অy')
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=5)
