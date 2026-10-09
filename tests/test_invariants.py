"""What must hold for every test, whatever its content: on tests/fixtures/invariants/, and on the
published dataset when OPB_DATASET is set to its root.

    empty      an empty output (html "", blocks []) passes no test;
    answer     a test's own answer written as the output (`answer`) passes it; and
    determined scoring a page twice, caches cleared, gives the same verdicts.

    OPB_DATASET=~/parse_bench/dataset-v2 pytest tests/test_invariants.py
"""
from __future__ import annotations

import html as _html
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from omni_parse_bench import equations, gold, metric, runners, tables, views

FIXTURE = Path(__file__).parent / "fixtures" / "invariants"
DATASET = Path(os.environ.get("OPB_DATASET", "")).expanduser()
EMPTY = {"html": "", "blocks": []}


def fixture_tests() -> tuple[gold.Test, ...]:
    return tuple(t for f in sorted((FIXTURE / "gold").glob("*.json")) for t in gold.read(f))


@pytest.fixture(scope="module", params=["fixture", "dataset"])
def tests(request) -> tuple[gold.Test, ...]:
    if request.param == "fixture": return fixture_tests()
    if not (DATASET / gold.MANIFEST).exists(): pytest.skip("set OPB_DATASET to a dataset root")
    return gold.load(DATASET)[1]


def answer(t: gold.Test) -> dict[str, Any]:
    """The output that writes exactly what `t` asks for, and nothing else."""
    p, e = t.params, _html.escape
    match p:
        case runners.Present(content=runners.Text(text=x)): html = f"<p>{e(x)}</p>"
        case runners.Present(content=runners.Number(number=x)): html = f"<p>{e(x)}</p>"
        case runners.Present(content=runners.Latex(latex=x)): html = f"<p>$${e(x)}$$</p>"
        case runners.Order(): html = f"<p>{e(p.before)}</p><p>{e(p.after)}</p>"
        case runners.Repeat(): html = "".join(f"<p>{e(p.text)}</p>" for _ in range(p.expected_count))
        case runners.TableCell(): html = table(p)
        case runners.LayoutKind():
            xs = p.content.place
            box = [min(b[0] for b in xs), min(b[1] for b in xs), max(b[2] for b in xs), max(b[3] for b in xs)]
            return {"blocks": [{"label": p.kind, "bbox": box, "text": p.content.text}]}
        case _: raise AssertionError(p)
    return {"html": html}


def table(p: runners.TableCell) -> str:
    """A table holding the cell where its args put it.

    Columns: an empty first column (so no row reads as a section label), the row groups, the
    left_heading (a <th>), left, the cell, right. Rows: each heading (a <th> over the cell), the
    top_heading (a <th>), the section (one cell across the table), up, the cell's row, down."""
    r = p.relations
    cols = ["", *p.row_groups, r.get("left_heading"), r.get("left"), p.cell, r.get("right")]
    width, at = len(cols), len(cols) - 2

    def row(cells: Sequence[str | None], th: Sequence[int] = ()) -> str:
        tag = lambda j: "th" if j in th else "td"  # noqa: E731
        return "<tr>" + "".join(f"<{tag(j)}>{_html.escape(x or '')}</{tag(j)}>"
                                for j, x in enumerate(cells)) + "</tr>"

    over = lambda x: row([None] * at + [x, None], th=(at,))  # noqa: E731
    rows = [over(h) for h in p.headings]
    if "top_heading" in r: rows.append(over(r["top_heading"]))
    if p.section: rows.append(f"<tr><td colspan='{width}'>{_html.escape(p.section)}</td></tr>")
    if "up" in r: rows.append(row([None] * at + [r["up"], None]))
    rows.append(row(cols, th=(len(p.row_groups) + 1,) if "left_heading" in r else ()))
    if "down" in r: rows.append(row([None] * at + [r["down"], None]))
    return "<table>" + "".join(rows) + "</table>"


def failures(tests: Sequence[gold.Test], outputs, want: str) -> list[str]:
    """The tests whose verdict on `outputs(t)` isn't `want`, with why."""
    out = []
    for t in tests:
        [v] = metric.score(outputs(t), [t])
        if v.result != want: out.append(f"{t.id}: {v.result} ({v.why[:100]})")
    return out


def test_an_empty_output_passes_no_test(tests):
    bad = failures(tests, lambda t: EMPTY, "fail")
    assert not bad, f"{len(bad)} tests pass on an empty output, e.g. {bad[:5]}"


def test_each_tests_own_answer_passes_it(tests):
    bad = failures(tests, answer, "pass")
    assert not bad, f"{len(bad)} tests fail on their own answer, e.g. {bad[:5]}"


def test_scoring_is_deterministic(tests):
    for page, ts in gold.by_page(tests).items():
        outputs = {"html": "".join(answer(t).get("html", "") for t in ts),
                   "blocks": [b for t in ts for b in answer(t).get("blocks", [])]}
        first = metric.score(outputs, ts)
        tables.parse.cache_clear()
        equations.symbols.cache_clear()
        assert metric.score(outputs, ts) == first, page


@pytest.mark.parametrize("change", [
    {"section": "Age"}, {"headings": ("Controls", "No. (%)")}, {"row_groups": ("Male",)},
    {"relations": {"up": "12 (15.0)"}}, {"relations": {"left": ">60 y"}},
])
def test_the_table_builder_puts_each_arg_where_the_runner_looks(change):
    [t] = [t for t in fixture_tests() if t.id == "fx_table_everything"]
    other = t.params._replace(**{k: t.params.relations | v if k == "relations" else v
                                 for k, v in change.items()})
    assert not runners.table_cell(t.params, views.html(table(other)))[0]
