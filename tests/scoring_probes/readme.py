# ruff: noqa: E501
"""Cases for docs/scoring/README.md: how verdicts become scores."""
from cases import reading, table

from omni_parse_bench.scorers import unit_tests as U

DOC = {"tests": [
    {"id": "a", "test_type": "present", "output_type": "html", "derivation": "authored", "tags": [],
     "args": {"content": {"text": "Hello", "max_diffs": 0}}, "settings": {}},
    {"id": "b", "test_type": "table_cell", "output_type": "html", "derivation": "authored", "tags": [],
     "args": {"cell": {"text": "5", "max_diffs": 0}}, "settings": {}},
    {"id": "c", "test_type": "layout_kind", "output_type": "blocks", "derivation": "authored", "tags": [],
     "args": {"content": {"text": "x", "max_diffs": 0, "place": [[0.1, 0.1, 0.5, 0.2]]}}, "settings": {"kind": "text"}},
]}
TESTS = U.tests.parse("page", DOC)


def verdicts(pred) -> str:
    return "; ".join(f"{v.result}: {v.why.split(':')[0]}" if v.why else v.result for v in U.score(pred, TESTS))


def summary(results: dict[str, list[bool]]) -> str:
    """A summary's headline and family scores, for test types each with these results."""
    lines = [{"page_id": f"p{i}", "document": f"d{i}", "test_type": tt, "result": "pass" if ok else "fail"}
             for tt, oks in results.items() for i, ok in enumerate(oks)]
    s = U.unit_tests.summarize(lines)
    fams = ", ".join(f"{k} {v['score']:.2f}" for k, v in s["families"].items())
    return f"headline {s['score']:.2f} ({fams})"


TABLES = [
    table(
        "readme-scoring",
        reading("score-headline", "the headline is the mean of the family scores",
                "text 3 of 4 passed, tables 0 of 1, layout 1 of 1", "headline 0.58 (text 0.75, tables 0.00, layout 1.00)",
                lambda: summary({"present": [True, True, True, False], "table_cell": [False], "layout_kind": [True]})),
        reading("score-subset", "a run without a family averages the families it has",
                "text 1 of 2 passed, layout 1 of 1", "headline 0.75 (text 0.50, layout 1.00)",
                lambda: summary({"present": [True, False], "layout_kind": [True]})),
        reading("score-missing-output", "an output the system did not give fails the tests that read it",
                "html only, for a text, a table and a layout test", "pass; fail: no tables found; fail: no blocks output",
                lambda: verdicts({"html": "<p>Hello</p>"})),
        reading("score-malformed", "an output of the wrong shape fails the tests that read it",
                "html that is not a string, no blocks", "fail: malformed html output; fail: malformed html output; fail: no blocks output",
                lambda: verdicts({"html": 5})),
        reading("score-failed-page", "a failed page (refused, crashed, wrong shape) fails every test",
                "the same three tests", "fail: no html output; fail: no html output; fail: no blocks output",
                lambda: "; ".join(f"{d['result']}: {d['why']}" for d in U.UnitTests().score_failure(TESTS).details)),
    ),
]
