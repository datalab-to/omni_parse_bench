"""One page's tests run against its outputs: a verdict per test (`score`). Each output is read once into its
view (`views`), and each test runs on its output's view (`runners`). A test fails when it fails, or when its
output is missing or malformed. A test that raises on a well-formed output is a bug of the scorer's: it fails
with the reason `scorer error: ...` and is logged at ERROR with its id, so one bad test never ends a grade
run (set `OPB_RAISE_SCORER_ERRORS=1`, as the test suite does, to raise it instead).
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, NamedTuple

from omni_parse_bench import views

from . import runners
from . import tests as _tests

log = logging.getLogger("omni_parse_bench.scorer")
SCORER_ERROR = "scorer error: "  # the start of the reason of a test that raised
Result = Literal["pass", "fail"]


VIEWS: dict[str, Callable[[Any], Any]] = {
    "html": views.html,
    "blocks": views.blocks,
}


class Verdict(NamedTuple):
    id: str
    result: Result
    why: str


def score(pred: Mapping[str, Any], gold: Sequence[_tests.Test]) -> list[Verdict]:
    """One verdict per test of `gold`, the page's tests. `pred` maps an output type to its value, or to None
    when it errored. A test whose output is missing fails."""
    blank = None    # whether the page's gold says it is blank (a page_near_empty test), read when needed
    built: dict[str, Any] = {}   # output type -> its view, or the Verdict its tests all get
    out = []
    for t in gold:
        if pred.get(t.output_type) is None:
            out.append(Verdict(t.id, "fail", f"no {t.output_type} output"))
            continue
        if t.output_type not in built:
            built[t.output_type] = _view(t.output_type, pred[t.output_type])
        if isinstance(v := built[t.output_type], Verdict):
            out.append(v._replace(id=t.id))
            continue
        if blank is None:
            blank = any(g.test_type == "page_near_empty" for g in gold)
        try:
            passed, why = runners.run(t.test_type, t.params, v, blank)
        except Exception as e:
            e.add_note(f"while running test {t.id} ({t.test_type}) of page {t.page_id}")
            if os.environ.get("OPB_RAISE_SCORER_ERRORS"):
                raise
            log.error("scorer error on test %s (%s) of page %s: %r", t.id, t.test_type, t.page_id, e)
            out.append(Verdict(t.id, "fail", f"{SCORER_ERROR}{type(e).__name__}: {e}"))
            continue
        out.append(Verdict(t.id, "pass" if passed else "fail", why))
    return out


def _view(output_type: str, value: Any) -> Any:
    """The output's view; or, when it is of the wrong shape (the provider's fault), the `fail` each of its
    tests gets. Building it raising otherwise is a bug of ours, raised."""
    try:
        return VIEWS[output_type](value)
    except views.MalformedOutput as e:
        return Verdict("", "fail", f"malformed {output_type} output: {e}")
