"""Relation of scoring tests in a batch (M19)."""
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from test_invariants import answer

from metamorphic.common import CELL, HOLDS, NUMBER, ORDER, REPEAT, TEXT, relation
from omni_parse_bench.scorers import unit_tests as scorer


@relation(HOLDS, pool="batch")
@given(st.lists(st.sampled_from([*TEXT, *NUMBER, *ORDER, *REPEAT, *CELL]), min_size=1, max_size=6,
                unique_by=lambda t: t.id), st.randoms(use_true_random=False))
def test_a_tests_verdict_does_not_depend_on_the_tests_scored_with_it(chosen, rnd):
    """On one page holding the answers of 1-6 text, number, order, repeat or table_cell tests (latex and
    layout_kind tests are not drawn), every test passes; and each gets the same verdict, and the same (empty)
    reason, scored alone on that page, in the batch, or with the batch's list order shuffled. [M19]
    Why it matters for a score: a page's tests are scored together; when all pass, none passes only because of
    the others or their order."""
    # Given one output holding the answers of a few tests side by side
    output = {"html": "".join(answer(t)["html"] for t in chosen)}
    shuffled = list(chosen)
    rnd.shuffle(shuffled)
    # When they are scored as a batch, as the batch shuffled, and one by one; Then every verdict is the same
    batch = {v.id: (v.result, v.why) for v in scorer.score(output, chosen)}
    assert all(result == "pass" for result, _ in batch.values()), batch    # so agreement is not all failures
    assert batch == {v.id: (v.result, v.why) for v in scorer.score(output, shuffled)}
    for t in chosen:
        [alone] = scorer.score(output, [t])
        assert (alone.result, alone.why) == batch[t.id], t.id
