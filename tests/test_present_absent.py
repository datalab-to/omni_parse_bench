# ruff: noqa: E501
"""`present` with `{"absent": true}`: what a gold file may say, and the verdicts it gives on outputs that leave a known wrong reading out
or write it, near or exact, anywhere (docs/scoring/present-absent.md)."""
from __future__ import annotations

import pytest

from omni_parse_bench import score, views
from omni_parse_bench.scorers.unit_tests import runners as R
from omni_parse_bench.scorers.unit_tests import tests as gold

H = "Johnathan Quincy Smithers"     # 25 characters after fold, over the floor of 20


def gold_of(content, settings=None) -> tuple[gold.Test, ...]:
    return gold.parse("p", {"tests": [{"id": "a", "test_type": "present", "output_type": "html",
                                       "derivation": "rendered_source", "tags": [], "args": {"content": content},
                                       "settings": {"absent": True} if settings is None else settings}]})


def verdict(html: str, text: str = H, md: int = 3) -> tuple[bool, str]:
    r = score({"html": html}, gold_of({"text": text, "max_diffs": md}))[0]
    return r.result == "pass", r.why


# ------------------------------------------------------------------------------------------- the loader


def test_the_loader_takes_a_text_arg():
    [t] = gold_of({"text": H, "max_diffs": 5})
    assert t.params == R.Present(R.Text(H, 5), absent=True)
    assert gold.arg_kinds("present", t.args) == ("text",)


@pytest.mark.parametrize("content, settings, why", [
    ({"text": H, "max_diffs": 7}, None, "at most 6"),
    ({"text": "Johnathan Smithers", "max_diffs": 0}, None, "at least 20"),
    ({"text": "J. Q. Smithers  ....", "max_diffs": 0}, None, "at least 20"),
    ({"text": H, "max_diffs": 0, "exact_case": True}, None, "exact_case"),
    ({"text": H, "max_diffs": 0, "place": [[0, 0, 1, 1]]}, None, "place"),
    ({"number": "4417123456789113"}, None, "text arg"),
    ({"text": H, "max_diffs": 0}, {"absent": True, "blank_after": True}, "settings"),
    ({"text": H, "max_diffs": 0}, {"absent": "yes"}, "settings"),
])
def test_the_loader_refuses_what_is_not_a_specific_reading_or_a_text_arg(content, settings, why):
    with pytest.raises(ValueError, match=why):
        gold_of(content, settings)


def test_the_loader_needs_content():
    with pytest.raises(ValueError, match="needs args"):
        gold.parse("p", {"tests": [{"id": "a", "test_type": "present", "output_type": "html",
                                    "derivation": "rendered_source", "tags": [], "args": {}, "settings": {}}]})


# ------------------------------------------------------------------------------------------- verdicts


PAGES = [
    "<p>x</p>", "<p>Patient name:</p>", "<p>Patient name: ████</p>", "<p>Patient name: [REDACTED]</p>",
    f"<p>Patient name: {H}</p>", "<p>Patient name: Jonathan Quincy Smithers</p>", "<p>Patient name: John Smith</p>",
    f"<p>{H.upper().replace(' ', '')}</p>", f"<table><tr><td>{H}</td></tr></table>",
    "<p>Johnathan</p><p>Quincy Smithers</p>", "<p>Johnathan Quincy Smith-</p><p>ers</p>", f"<p>x</p><p>{H}</p><p>{H}</p>",
]


@pytest.mark.parametrize("html", PAGES)
@pytest.mark.parametrize("md", [0, 3, 6])
def test_absent_is_not_present_on_a_page_without_images(html, md):
    present = R.present(R.Present(R.Text(H, md)), views.html(html))[0]
    assert verdict(html, md=md)[0] is not present


@pytest.mark.parametrize("html", [f"<img alt='{H}'>", f"<p>x</p><img src='a.png' alt=\"Patient: {H}\" />",
                                  f"![{H}](a.png)", f"<figure><img alt='{H}'><figcaption>Fig. 1</figcaption></figure>"])
def test_an_image_description_is_not_read_though_present_reads_it(html):
    assert R.present(R.Present(R.Text(H, 3)), views.html(html))[0]
    assert verdict(html + "<p>Fig. 1</p>") == (True, "")
    # Note: an image alone is an output with nothing to read: it fails like an empty one (tests/test_empty_gate.py)
    if "<p>" not in html and "<figcaption>" not in html:
        assert verdict(html)[1].startswith("no output")
    # Note: the same reading in the visible text beside the image still fails
    assert not verdict(html + f"<p>{H}</p>")[0]


def test_an_image_is_left_out_whole_not_its_neighbors():
    v = views.html(f"<p>Before</p><img alt='{H}'><p>{H}</p>")
    assert R._visible(v).seen == R._visible(v).text
    assert H in R._visible(v).text


@pytest.mark.parametrize("html", [f"<p>Patient name: {H}</p>", "<p>Patient name: Jonathan Quincy Smithers</p>",
                                  f"<table><tr><td>Patient name:</td><td>{H}</td></tr></table>",
                                  f"<p>{H.upper()}</p>", f"<ul><li>{H}</li></ul>"])
def test_the_reading_fails_wherever_the_visible_text_holds_it(html):
    assert verdict(html) == (False, "'Johnathan Quincy Smithers' found, a reading the page does not print")


@pytest.mark.parametrize("html", ["<p>Patient name:</p>", "<p>Patient name: ████</p>", "<p>Patient name: John Smith</p>",
                                  "<p>Johnathan</p><p>Signed by Quincy Smithers</p>"])
def test_what_is_not_the_reading_passes(html):
    assert verdict(html) == (True, "")


def test_numbers_are_exact_at_any_budget():
    acct = "Account number 4417 1234 5678 9113"
    assert not verdict(f"<p>{acct}</p>", acct, 2)[0]
    assert verdict("<p>Account number 4417 1234 5678 9112</p>", acct, 2)[0]
    assert not verdict("<p>Acount numbr 4417 1234 5678 9113</p>", acct, 2)[0]


def test_the_budget_reaches_a_near_copy_and_no_further():
    assert not verdict("<p>Jonathan Quincy Smither</p>", md=3)[0]     # 2 edits
    assert verdict("<p>Jonathan Quincy Smither</p>", md=1)[0]
    assert verdict("<p>Jon Quincy Smithers</p>", md=3)[0]              # 6 edits


def test_a_collision_check_finds_the_reading_in_any_order_the_page_admits():
    sign = R.Text("North station opens Tuesday", 3)
    assert R.absent_collisions(["Opens Tuesday\nNorth station", "North station\nOpens Tuesday"], sign) == [1]
    assert R.absent_collisions(["Opens Tuesday\nNorth station"], sign) == []
    # Note: it runs the test's own search: glued words, a line hyphen and the budget count
    assert R.absent_collisions(["NorthStationOpensTuesday", "North sta-\ntion opens Tuesday",
                                "Nort station opens Tusday"], sign) == [0, 1, 2]
