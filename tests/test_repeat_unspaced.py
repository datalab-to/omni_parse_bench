"""`repeat` counts a copy beside a letter of a script written without spaces."""
from __future__ import annotations

import pytest

from omni_parse_bench import views
from omni_parse_bench.scorers.unit_tests import runners


def verdict(text: str, n: int, page: str) -> bool:
    return runners.repeat(runners.Repeat(runners.Text(text, 0), n), views.html(page))[0]


FAITHFUL = "<p>LCR meter 4284A</p><p>LCRメータ4284A</p>"       # an English line, its Japanese line
DUPLICATED = "<p>LCR meter 4284A</p><p>LCR meter 4284A</p><p>LCRメータ4284A</p>"


def test_katakana_glued_to_a_model_number_does_not_hide_the_copy():
    assert verdict("4284A", 2, FAITHFUL)


def test_an_output_that_duplicates_the_english_line_counts_three_and_fails():
    assert not verdict("4284A", 2, DUPLICATED)
    assert verdict("4284A", 3, DUPLICATED)


def test_a_line_that_starts_with_the_same_chinese_words_counts_each_line():
    page = "".join(f"<p>一年里的第{c}季</p>" for c in "一二三")
    assert verdict("一年里的第", 3, page)
    assert not verdict("一年里的第", 2, page)


@pytest.mark.parametrize("neighbor", ["ก", "ក", "か", "한", "မ", "ཀ", "ກ"])
def test_each_unspaced_script_is_an_edge(neighbor):
    assert verdict("4284A", 1, f"<p>{neighbor}4284A{neighbor}</p>")


@pytest.mark.parametrize("neighbor", ["x", "Я", "Ω", "א", "ع", "क", "7", "Ա", "ა"])
def test_a_letter_or_digit_of_a_spaced_script_still_glues(neighbor):
    assert not verdict("4284A", 1, f"<p>{neighbor}4284A</p>")
    assert not verdict("4284A", 1, f"<p>4284A{neighbor}</p>")
