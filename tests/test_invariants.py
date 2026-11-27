"""What must hold for every test, whatever its content: on tests/fixtures/invariants/, and on the
published dataset when OPB_DATASET is set to its root.

    empty      an empty output (html "", blocks []) passes no test except a page_near_empty test, or a region
               test with no anchors and no content, which it passes by definition;
    answer     a test's own answer written as the output (`answer`) passes it; and
    determined scoring a page twice, caches cleared, gives the same verdicts.

    OPB_DATASET=path/to/omni_parse_bench pytest tests/test_invariants.py
"""
from __future__ import annotations

import html as _html
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from omni_parse_bench import data, equations, tables, views
from omni_parse_bench.scorers import unit_tests as scorer
from omni_parse_bench.scorers.unit_tests import runners
from omni_parse_bench.scorers.unit_tests import tests as gold

FIXTURE = Path(__file__).parent / "fixtures" / "invariants"
DATASET = Path(os.environ.get("OPB_DATASET", "")).expanduser()
EMPTY = {"html": "", "blocks": []}
TAG = {"bold": "b", "italic": "i", "underline": "u", "strike": "s", "sup": "sup", "sub": "sub"}


def fixture_tests() -> tuple[gold.Test, ...]:
    return tuple(t for f in sorted((FIXTURE / "gold").glob("*.json")) for t in gold.read(f))


@pytest.fixture(scope="module", params=["fixture", "dataset"])
def tests(request) -> tuple[gold.Test, ...]:
    if request.param == "fixture": return fixture_tests()
    if not (DATASET / data.MANIFEST).exists(): pytest.skip("set OPB_DATASET to a dataset root")
    return scorer.check(data.read_manifest(DATASET)[1])


def answer(t: gold.Test) -> dict[str, Any]:
    """The output that writes exactly what `t` asks for, and nothing else."""
    p, e = t.params, _html.escape
    match p:
        case runners.Present(content=runners.Text(text=x)): html = f"<p>{e(x)}</p>"
        case runners.Present(content=runners.Number(number=x)): html = f"<p>{e(x)}</p>"
        case runners.Present(content=runners.Latex(latex=x)): html = f"<p>$${e(x)}$$</p>"
        case runners.Order(): html = f"<p>{e(p.before)}</p><p>{e(p.after)}</p>"
        case runners.Repeat(content=runners.Text(text=x) | runners.Number(number=x)):
            html = "".join(f"<p>{e(x)}</p>" for _ in range(p.expected_count))
        case runners.PageNearEmpty(): html = f"<p>{'x' * p.max_chars}</p>"     # as much as it allows
        case runners.Verbatim():
            html = "".join(f"<p>{e(x)}</p>" for x in (p.start, p.content, p.end) if x is not None)
        case runners.NoExcessRepeats(): html = f"<p>{e(p.content)}</p>"
        case runners.TableCell(): html = table(p)
        case runners.Format():
            span = e(p.span)
            for kind in p.marks:
                span = f"<{TAG[kind]}>{span}</{TAG[kind]}>"
            html = f"<p>{e(p.before or '')}{span}{e(p.after or '')}</p>"
            # Note: a negative test is only scored on an output that has a mark somewhere
            html += "" if p.marks else "<p><b>note</b></p>"
        case runners.LayoutKind():
            xs = p.content.place
            box = [min(b[0] for b in xs), min(b[1] for b in xs), max(b[2] for b in xs), max(b[3] for b in xs)]
            return {"blocks": [{"label": p.kind, "bbox": box, "text": p.content.text}]}
        case _: raise AssertionError(p)
    return {"html": html}


def table(p: runners.TableCell) -> str:
    """A table holding the cell where its args put it.

    Columns: an empty first column (so no row reads as a section label), the row groups, the
    left_heading (a <th>), left, the cell, right, right_heading (a <th>). Rows: each heading (a <th>
    over the cell), the top_heading (a <th>), the section (one cell across the table), up, the cell's row,
    down."""
    r = p.relations
    cols = ["", *p.row_groups, r.get("left_heading"), r.get("left"), p.cell, r.get("right"),
            r.get("right_heading")]
    width, at = len(cols), len(cols) - 3

    def row(cells: Sequence[str | None], th: Sequence[int] = ()) -> str:
        tag = lambda j: "th" if j in th else "td"  # noqa: E731
        return "<tr>" + "".join(f"<{tag(j)}>{_html.escape(x or '')}</{tag(j)}>"
                                for j, x in enumerate(cells)) + "</tr>"

    pad = [None] * (width - at - 1)
    over = lambda x: row([None] * at + [x, *pad], th=(at,))  # noqa: E731
    rows = [over(h) for h in p.headings]
    if "top_heading" in r: rows.append(over(r["top_heading"]))
    if p.section: rows.append(f"<tr><td colspan='{width}'>{_html.escape(p.section)}</td></tr>")
    if "up" in r: rows.append(row([None] * at + [r["up"], *pad]))
    th = ((len(p.row_groups) + 1,) if "left_heading" in r else ()) \
        + ((width - 1,) if "right_heading" in r else ())
    rows.append(row(cols, th=th))
    if "down" in r: rows.append(row([None] * at + [r["down"], *pad]))
    return "<table>" + "".join(rows) + "</table>"


def failures(tests: Sequence[gold.Test], outputs, want: str) -> list[str]:
    """The tests whose verdict on `outputs(t)` isn't `want`, with why."""
    out = []
    for t in tests:
        [v] = scorer.score(outputs(t), [t])
        if v.result != want: out.append(f"{t.id}: {v.result} ({v.why[:100]})")
    return out


def test_an_empty_output_passes_no_test(tests):
    # A page_near_empty test asks for a page with at most max_chars characters, so an empty output passes
    # it by definition; the next test checks that it fails one character over.
    # A verbatim test with no anchors and no content asks for an empty page too.
    asked = [t for t in tests if not isinstance(t.params, runners.PageNearEmpty)
             and t.params != runners.Verbatim(None, None, None, 0)]
    bad = failures(asked, lambda t: EMPTY, "fail")
    assert not bad, f"{len(bad)} tests pass on an empty output, e.g. {bad[:5]}"


def test_a_page_near_empty_test_passes_a_blank_page_and_fails_one_character_over_its_limit(tests):
    blank = [t for t in tests if isinstance(t.params, runners.PageNearEmpty)]
    assert not failures(blank, lambda t: EMPTY, "pass")
    over = lambda t: {"html": f"<p>{'x' * (t.params.max_chars + 1)}</p>"}  # noqa: E731
    bad = failures(blank, over, "fail")
    assert not bad, f"{len(bad)} page_near_empty tests pass a page over their limit, e.g. {bad[:5]}"


def test_a_blank_llm_reply_scores_as_an_empty_page(tests):
    # What the LLM adapter returns for a model's empty reply is an empty page: it passes the near-empty tests
    # and fails the rest.
    from omni_parse_bench.harness.providers import llm

    reply = {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]}
    html = llm.parse(reply, llm.contract.Request(frozenset({"html"}), {}))[0]["html"]
    assert html == ""
    out = {"html": html, "blocks": []}
    for t in tests:
        [v] = scorer.score(out, [t])
        assert v.result == ("pass" if isinstance(t.params, runners.PageNearEmpty) else "fail"), (t.id, v.why)


def test_each_tests_own_answer_passes_it(tests):
    bad = failures(tests, answer, "pass")
    assert not bad, f"{len(bad)} tests fail on their own answer, e.g. {bad[:5]}"


def test_scoring_is_deterministic(tests):
    for page, ts in gold.by_page(tests).items():
        outputs = {"html": "".join(answer(t).get("html", "") for t in ts),
                   "blocks": [b for t in ts for b in answer(t).get("blocks", [])]}
        first = scorer.score(outputs, ts)
        tables.parse.cache_clear()
        equations.symbols.cache_clear()
        assert scorer.score(outputs, ts) == first, page


@pytest.mark.parametrize("change", [
    {"section": "Age"}, {"headings": ("Controls", "No. (%)")}, {"row_groups": ("Male",)},
    {"relations": {"up": "12 (15.0)"}}, {"relations": {"left": ">60 y"}},
])
def test_the_table_builder_puts_each_arg_where_the_runner_looks(change):
    [t] = [t for t in fixture_tests() if t.id == "fx_table_everything"]
    other = t.params._replace(**{k: t.params.relations | v if k == "relations" else v
                                 for k, v in change.items()})
    assert not runners.table_cell(t.params, views.html(table(other)))[0]


def test_the_table_builder_puts_right_heading_at_the_end_of_the_row():
    p = runners.TableCell("1,240", {"left_heading": "Total", "right": "3", "right_heading": "Sum"}, 0)
    assert runners.table_cell(p, views.html(table(p)))[0]
    wrong = p._replace(relations=p.relations | {"right_heading": "Total"})
    assert not runners.table_cell(wrong, views.html(table(p)))[0]
