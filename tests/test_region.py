"""The closed region on the chain (`region` switch, runners._chain_verbatim): anchors at token edges, pairing,
the region compared as a whole at Text. What it keeps of the old reading and what it changes."""

from __future__ import annotations

import pytest

from omni_parse_bench import switches, views
from omni_parse_bench.scorers.unit_tests import runners as R

S, E = "Date of birth:", "Place of birth:"


@pytest.fixture(autouse=True)
def on():
    with switches.set_all(True):
        yield


def v(html: str, start=S, end=E, content=None, k: int = 0):
    return R.verbatim(R.Verbatim(start, end, content, k), views.html(html))


def form(value: str) -> str:
    return f"<p>{S} {value}</p><p>{E} Paris</p>"


def test_a_blank_region_passes_and_anything_in_it_fails():
    assert v(form("")) == (True, "")
    ok, why = v(form("N/A"))
    assert not ok and why.startswith(f"between {S!r} and {E!r} holds "), why


def test_the_content_is_compared_as_a_whole_with_case_kept():
    assert v(form("1 May"), content="1 May")[0]
    assert not v(form("1 may"), content="1 May")[0]
    assert not v(form("1 May 1985"), content="1 May")[0]
    assert v(form("1 Mya"), content="1 May", k=1)[0]


def test_a_region_runs_across_table_cells():
    page = f"<table><tr><td>{S}</td><td>1 May</td></tr><tr><td>{E}</td><td>x</td></tr></table>"
    assert v(page, content="1 May")[0]
    assert not v(page, content="1")[0]


def test_every_copy_of_the_start_is_judged():
    page = f"<p>{S} 1 May</p><p>{E} x</p><p>{S}</p><p>{E} y</p>"
    ok, why = v(page, content="1 May")
    assert not ok and why.startswith("copy 2 of 2: ")


def test_an_anchor_opened_again_before_its_end_is_unclosed():
    ok, why = v(f"<p>{S} {S} 1 May</p><p>{E} x</p>", content="1 May")
    assert not ok and "opened again" in why


def test_a_missing_end_fails_and_no_end_runs_to_the_page_end():
    assert not v(f"<p>{S} 1 May</p>", content="1 May")[0]
    assert v(f"<p>{S} 1 May</p>", end=None, content="1 May")[0]
    assert v("<p>Draft</p><p>Results</p>", start=None, end="Results", content="Draft")[0]


def test_a_start_inside_a_longer_end_belongs_to_the_end():
    page = "<p>Table 3</p><p>Rows</p><p>Table 3 (continued)</p>"
    assert v(page, start="Table 3", end="Table 3 (continued)", content="Rows")[0]


def test_a_number_is_atomic_in_the_region():
    assert not v(form("10mg"), content="10kg", k=1)[0]
    assert not v(form("1,5"), content="1.5", k=1)[0]


def test_what_a_region_does_not_compare():
    assert v(form("__/__/____"), content="__/__/____")[0]
    assert v(form("//"), content="__/__/____")[0]
    assert v("<p>Items: • Rent ‣ Fuel</p>", start=None, end=None, content="Items: Rent Fuel")[0]
    assert v(form("<img alt='12/03/1985'>"))[0]
    assert v(form("<math></math><ol><li></li></ol><input type=hidden value=1985>"))[0]


def test_a_footnote_mark_is_kept_at_text_and_never_equals_a_number():
    page = "<p>Abstract</p><p>We study parsing.<sup>1</sup></p><p>Introduction</p>"
    for gold in ("We study parsing.1", "We study parsing. 1", "We study parsing."):
        assert not v(page, "Abstract", "Introduction", gold)[0], gold
    assert not v("<p>Smith<sup>1</sup></p>", None, None, "Smith 1")[0]
    assert not v("<p>Smith<sup>1</sup></p>", None, None, "Smith1")[0]


def test_each_exemption_is_a_switch():
    with switches.using(region_underscore=False):
        assert not v(form("//"), content="__/__/____")[0]
    with switches.using(region_bullet=False):
        assert not v("<p>Items: • Rent</p>", start=None, end=None, content="Items: Rent")[0]
    assert v("<p>Items: • Rent</p>", start=None, end=None, content="Items: Rent")[0]


def test_a_wrapped_hyphen_is_free_in_the_region():
    assert v("<p>re-<br>sign</p>", None, None, "resign")[0]
    assert v("<p>re-<br>sign</p>", None, None, "re-sign")[0]
    assert not v("<p>re sign</p>", None, None, "resign")[0]


def test_with_the_switch_off_the_old_region_reading_stands():
    with switches.using(region=False):
        assert v(form("1 may"), content="1 May")[0]       # the old region read case folded
    assert not v(form("1 may"), content="1 May")[0]


def test_a_long_underscore_line_is_the_folds_and_an_identifier_is_kept():
    # three or more underscores that touch no word are a leader: the Text fold removes them, so the region
    # switch cannot see them (it decides runs of one or two); an identifier's underscores stay text
    for sw in (False, True):
        with switches.using(region_underscore=sw):
            assert v(form("____ hi"), content="hi")[0]
            assert not v(form("token____"), content="token")[0]
            assert not v(form("foo___bar"), content="foo bar")[0]
            assert v(form("foo___bar"), content="foo___bar")[0]


def test_the_underscore_switch_decides_a_short_run_that_touches_no_word():
    page = form("__ hi")
    with switches.using(region_underscore=True):
        assert v(page, content="hi")[0]
    with switches.using(region_underscore=False):
        assert not v(page, content="hi")[0]
