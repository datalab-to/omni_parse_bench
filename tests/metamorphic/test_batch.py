"""Relation of scoring tests in a batch (M19)."""
from __future__ import annotations

from hypothesis import assume, given
from hypothesis import strategies as st
from test_invariants import answer

from metamorphic.common import CELL, HOLDS, NUMBER, ORDER, REPEAT, REPEAT_NUMBER, TEXT, relation
from omni_parse_bench import views
from omni_parse_bench.scorers import unit_tests as scorer
from omni_parse_bench.scorers.unit_tests import runners


@relation(HOLDS, pool="batch")
@given(st.lists(st.sampled_from([*TEXT, *NUMBER, *ORDER, *REPEAT, *REPEAT_NUMBER, *CELL]), min_size=1,
                max_size=6, unique_by=lambda t: t.id), st.randoms(use_true_random=False))
def test_a_tests_verdict_does_not_depend_on_the_tests_scored_with_it(chosen, rnd):
    """On one page holding the answers of 1-6 text, number, order, repeat (of text or a number) or table_cell
    tests (latex and layout_kind tests are not drawn), every test passes; and each gets the same verdict, and
    the same (empty) reason, scored alone on that page, in the batch, or with the batch's list order
    shuffled. [M19]
    Why it matters for a score: a page's tests are scored together; when all pass, none passes only because of
    the others or their order."""
    # Given one output holding the answers of a few tests side by side (a number is asked by one test at most:
    # a repeat of it and another test of it would count each other's copies)
    numbers = [t.params.content.number for t in chosen
               if isinstance(t.params, (runners.Present, runners.Repeat))
               and isinstance(t.params.content, runners.Number)]
    assume(len(numbers) == len(set(numbers)))
    # (and no repeat test's number is counted more often on the whole page than that test expects)
    page = views.html("".join(answer(t)["html"] for t in chosen))
    assume(all(runners._number_copies(t.params.content.number, page) == t.params.expected_count
               for t in chosen if isinstance(t.params, runners.Repeat)
               and isinstance(t.params.content, runners.Number)))
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
