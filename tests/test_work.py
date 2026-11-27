"""The worst-case inputs stay inside fixed work bounds. Counts are deterministic (no clock), so a regression
to quadratic work fails here on any machine; `work.BOUNDS` only logs, it never changes a verdict."""

import logging

import pytest

from omni_parse_bench import chain, switches, work

CASES = {
    "full-width bars": "<p>" + "｜ " * 8000 + "</p>",
    "fraction chain": "<p>" + "1/" * 20000 + "1</p>",
    "repeated words": "<p>" + "lorem ipsum dolor sit amet " * 4000 + "</p>",
    "one symbol per cluster": "<p>" + "§" * 100000 + "</p>",
}


@pytest.mark.parametrize("name", CASES)
def test_reader_and_search_work_is_linear_in_the_input(name, caplog):
    html = CASES[name]
    with switches.set_all(True), caplog.at_level(logging.WARNING, logger="omni_parse_bench.work"):
        work.reset()
        toks = chain.tokens_of_output(html)
        read = work.snapshot()
        gold = chain.tokens_of_gold("dolor sit amet lorem ipsum")
        work.reset()
        chain.windows(gold, toks, chain.WORDS, 2)
        search = work.snapshot()
    chars = len(html)
    assert read.get("diff_cells", 0) <= 100 * chars
    assert read.get("emit_runs", 0) <= 2 * chars
    assert search.get("search_states", 0) <= 40 * chars
    assert not caplog.records, [r.getMessage() for r in caplog.records]


def test_a_search_over_its_bound_is_logged_not_changed(caplog):
    with caplog.at_level(logging.WARNING, logger="omni_parse_bench.work"):
        assert work.check_search(10, 10, 10**9)
        assert not work.check_search(10, 10, 5)
    assert any("search work over its bound" in r.getMessage() for r in caplog.records)
