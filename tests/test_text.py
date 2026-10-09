"""markdown.to_html, views.text and normalize.fold: the rules each module's docstring lists."""
from __future__ import annotations

import re

import pytest

from omni_parse_bench import markdown, normalize, views


def test_unclosed_fence_is_not_a_code_block():
    h = markdown.to_html("```markdown\n# Title\n\nBody text\n")
    assert "<h1>" in h and "<pre>" not in h


def test_front_matter_is_dropped():
    assert "primary_language" not in markdown.to_html("---\nprimary_language: en\n---\n\nReal text\n")


def test_raw_table_survives_blank_lines_and_indentation():
    h = markdown.to_html("<table>\n  <tr><td>a</td></tr>\n\n    <tr><td>b</td></tr>\n</table>\n")
    assert h.count("<td>") == 2


def test_list_markers_stay_in_the_text():
    assert "29." in views.text(markdown.to_html("29. Valstybinių švenčių\n"))
    assert "- Hoces" in views.text(markdown.to_html("- Hoces probati jedan?\n"))


def test_math_braces_survive_conversion():
    assert r"$\{x\}_1$" in markdown.to_html(r"Intro $\{x\}_1$ end")


@pytest.mark.parametrize("row, cells", [
    ("| Net | ($26.9) | $2.5 | ($27.8) |", ["Net", "($26.9)", "$2.5", "($27.8)"]),
    ("| Total | **$24,468** | **$1,200** |", ["Total", "$24,468", "$1,200"]),
    ("| $x_1$ | $y$ |", ["$x_1$", "$y$"]),
    ("| Loss | $f = (f_i)|_{|\\mathcal{B}|}$ |", ["Loss", "$f = (f_i)|_{|\\mathcal{B}|}$"]),
])
def test_dollar_amounts_in_a_pipe_table_stay_in_their_cells(row, cells):
    h = markdown.to_html(f"| a | b | c | d |\n|---|---|---|---|\n{row}\n")
    got = [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<td>(.*?)</td>", h, re.S)]
    assert [c for c in got if c] == cells


def test_math_with_a_pipe_outside_a_table_is_held_whole():
    assert "$3 - 2|x| < 2$" in markdown.to_html("The set $3 - 2|x| < 2$ is open\n")
    block = "$$\n\\text{O} \\\\\n| \\quad | \\\\\n$$"
    assert block in markdown.to_html(f"Before\n\n{block}\n\nAfter\n")


def test_math_element_reads_as_text():
    assert "$Q(1)^2$" in views.text("<p>Let <math>Q(1)^2</math> hold</p>")


def test_form_value_reads_as_text():
    assert "ZQX184001TOKEN" in views.text('<input type="text" value="ZQX184001TOKEN"/>')


def test_controls_read_as_ballot_boxes():
    v = views.text('<input type="checkbox"/> CDI <input type="checkbox" checked/> CDD')
    assert views.UNCHECKED in v and views.CHECKED in v


def test_image_alt_is_text():
    assert "Figure 13: caption" in views.text('<img src="x.png" alt="Figure 13: caption"/>')


def test_doctype_is_not_text():
    assert views.text("<!DOCTYPE html>\n<html><body><p>6</p></body></html>").strip().startswith("6")


def test_less_than_sign_is_not_a_tag():
    assert "0.05" in views.text("<p>P < 0.05 and the rest of the page</p>")


def test_seen_view_leaves_out_image_alt_text():
    v = views.html('<p>A caption</p><img src="x.png" alt="a chart of sales"/>')
    assert "a chart of sales" in v.text and "a chart of sales" not in v.seen and "A caption" in v.seen


@pytest.mark.parametrize("a, b", [
    ("Ethnic & Racial", "ethnic &amp; racial"),
    ("PAGE 1 — café", "page 1 - café"),
    ("match。", "match."),
    ("\u21e8 Post-deal", "\u21d2 post-deal"),
    ("As much as I always could........ 0", "as much as i always could 0"),
    (r"$c_{\text{MC}}$ (g L$^{-1}$)", "cmc (g l-1)"),
    ("the Mann-Whitney $U$ test", "the Mann-Whitney U test"),
    (r"into $\mathrm { Q }$ systems", "into Q systems"),
    (r"at $x _ { k } ( t _ { 0 } )$ we", "at xk(t0) we"),
    ("the develop-\ners of", "the developers of"),
    ("the effi- cient detector", "the efficient detector"),
    (r"$$2 . 5 5 \pm 0 . 5 1$$", "2.55±0.51"),
    ("$$4 0$$ patients", "40 patients"),
    ("the develop\u2010\ners of", "the developers of"),
    (r"$x\ y$", "x y"),
    (r"$$\mathrm{mg} \ \mathrm{kg}$$", "mg kg"),
    (r"$\operatorname{arg\,max} x$", "arg max x"),
    (r"$\text{a {b} c}$", "a b c"),
    ("\u2018\u2018quoted\u2019\u2019", '"quoted"'),
    ("Cuo\u00b4 and Mu\u00a8ller", "Cu\u00f3 and M\u00fcller"),
    ("it\u00b4s", "it's"),
    ("<math>T = 20.3, p &lt; 0.0001</math>", "T = 20.3, p < 0.0001"),
    ("$T = 20.3$, $p < 0.0001$", "T = 20.3, p < 0.0001"),
])
def test_fold_equates_both_sides(a, b):
    assert normalize.fold(views.text(a)) == normalize.fold(views.text(b))


def test_fold_leaves_money_alone():
    assert "$1,000.01" in normalize.fold("b $1,000.01 to $2,000.00")
    # prose between two "$" with one LaTeX-like character in it isn't math
    form = "Amount enclosed $____ Date paid ____ Balance $"
    assert normalize.fold(form) == "amount enclosed $ date paid balance $"


def test_a_line_end_dash_isnt_a_hyphen():
    assert normalize.fold("north\u2014\nsouth") != normalize.fold("northsouth")


def test_a_line_end_hyphen_before_a_capital_stays():
    assert normalize.fold("well-\nKnown") != normalize.fold("wellKnown")


def test_math_keeps_the_space_after_a_command_and_in_text():
    assert normalize.fold(r"$\alpha b$") == "αb"
    assert "is the" in normalize.fold(r"$\text{is the}$")


def test_squeeze_joins_superscripts():
    assert normalize.squeeze("Probiotic 1") == normalize.squeeze("Probiotic1")


def test_a_documents_head_and_title_are_not_page_text():
    html = "<html><head><title>Report</title><meta charset='utf-8'></head><body><p>Report</p></body></html>"
    assert views.text(html).split() == ["Report"]


@pytest.mark.parametrize("a, b", [
    ("Ac​me", "Acme"),
    ("Ac⁠me", "Acme"),
    ("Ac᠎me", "Acme"),
    ("؜Acme﻿", "Acme"),
    ("in­tegral", "integral"),
])
def test_fold_drops_every_invisible_format_character(a, b):
    assert normalize.fold(a) == normalize.fold(b)


def test_fold_keeps_the_printed_number_signs():
    assert "؀" in normalize.fold("؀١٢")
    assert normalize.fold("۝12") != normalize.fold("12")


def test_a_superscript_never_joins_the_number_before_it():
    assert normalize.fold(views.text("1,240<sup>1</sup>")) == normalize.fold("1,240¹") == "1,240 1"
    # text still finds a superscript written inline, by squeeze
    assert normalize.squeeze(views.text("x<sup>2</sup>")) == normalize.squeeze("x2")


def test_a_rule_opening_the_page_is_not_front_matter():
    v = views.text(markdown.to_html("---\n\nIntro paragraph.\n\nSecond paragraph.\n\n---\n\n3\n"))
    assert "Intro paragraph." in v and "Second paragraph." in v


@pytest.mark.parametrize("md, kept", [
    ("Text\n\n```python\ndef __init__(self, *args):\n    x = a*b*c\n# a comment\n```\n\nAfter\n",
     "def __init__(self, *args):\n    x = a*b*c\n# a comment"),
    ("```\ncode *x*\n```\n\nmore text\n", "code *x*"),
    ("```markdown\n# Title\n\n```python\nx = a*b\n```\n\nEnd\n```", "x = a*b"),
])
def test_a_fenced_listing_in_the_page_stays_code(md, kept):
    assert kept in views.text(markdown.to_html(md))


def test_a_fence_around_the_page_is_removed():
    h = markdown.to_html("```markdown\n# Title\n\nBody\n```")
    assert "<h1>" in h and "<pre>" not in h


@pytest.mark.parametrize("md, text", [
    (r"Revenue \$5 and costs \$6 here", "Revenue $5 and costs $6 here"),
    ("| a | b |\n|---|---|\n| \\$5 | \\$6 |", "$5"),
])
def test_an_escaped_dollar_is_a_price(md, text):
    v = views.text(markdown.to_html(md))
    assert text in v and "\\" not in v


def test_an_address_in_brackets_is_text():
    line = "Sherry Tenison <tw@example.com>"
    assert line in views.text(markdown.to_html(line))


def test_no_escape_is_left_inside_a_raw_html_block():
    assert "\\" not in views.text(markdown.to_html("<p>\n29. Item one\n- dash item\n</p>\n"))


def test_a_reference_list_is_text():
    assert "[1]: https://doi.org/10.1000/xyz" in views.text(
        markdown.to_html("References\n\n[1]: https://doi.org/10.1000/xyz\n\nEnd."))
