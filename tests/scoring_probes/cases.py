"""The cases behind the scoring reference (docs/scoring): each row of a rules table there is one `Case`.

A case runs one test (or one reading of the text) on a small output and states what it expects. `render.py`
runs every case, records the results in `observed.txt`, and writes each table into its page between marker
comments; `tests/test_scoring_reference.py` checks that the claims hold, that the record and the pages are up
to date, and that every case cited in the pages exists.

An output with no tag is run as `<p>output</p>`; the page shows it bare.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from omni_parse_bench import normalize, views
from omni_parse_bench.scorers.unit_tests import runners as R

Run = Callable[[], tuple[str, str]]     # -> (result, detail): ("pass" | "fail", why), or (a reading, "")
MARKS = {"I": "pass", "B": "pass", "P": "fail"}


@dataclass(frozen=True)
class Case:
    label: str
    rule: str       # the difference or rule, in plain words (markdown)
    gold: str       # as shown in the page (markdown)
    output: str     # as shown in the page (markdown); "" for a reading
    expect: str     # "pass" / "fail" for a verdict, the expected text for a reading
    run: Run
    mark: str = ""  # I, B or P for a verdict
    why: bool = False   # show the why of a failure in the page


@dataclass(frozen=True)
class Table:
    id: str
    kind: str       # "verdict" or "reading"
    cases: tuple[Case, ...]


def table(id: str, *cases: Case) -> Table:
    kinds = {"reading" if c.mark == "" else "verdict" for c in cases}
    assert len(kinds) == 1, f"table {id} mixes verdicts and readings"
    return Table(id, kinds.pop(), cases)


# ----------------------------------------------------------------------------------------------- display


def code(s: str) -> str:
    """`s` as inline code inside a markdown table cell."""
    s = s.replace("|", "\\|").replace("\n", "\\n")
    fence = "``" if "`" in s else "`"
    pad = " " if s.startswith("`") or s.endswith("`") else ""
    return f"{fence}{pad}{s}{pad}{fence}" if s else '`""`'


def html(out: str) -> str:
    return out if "<" in out or out == "" else f"<p>{out}</p>"


def _v(mark: tuple[bool, str]) -> tuple[str, str]:
    ok, why = mark
    return ("pass" if ok else "fail", why)


def _md(gold: str, md: int) -> str:
    return code(gold) + (f" (md {md})" if md else "")


def verdict(label: str, mark: str, rule: str, gold: str, output: str, run: Run, *, show: str | None = None,
            why: bool = False) -> Case:
    assert mark in MARKS, mark
    return Case(label, rule, gold, show if show is not None else code(output), MARKS[mark], run, mark, why)


# ----------------------------------------------------------------------------------------------- test types


def text(label, mark, rule, gold, out, md=0, **kw) -> Case:
    """`present` with a text arg."""
    return verdict(label, mark, rule, _md(gold, md), out,
                   lambda: _v(R.found(R.Text(gold, md), views.html(html(out)))), **kw)


def number(label, mark, rule, gold, out, **kw) -> Case:
    """`present` with a number arg."""
    return verdict(label, mark, rule, code(gold), out,
                   lambda: _v(R.found(R.Number(gold), views.html(html(out)))), **kw)


def latex(label, mark, rule, gold, out, **kw) -> Case:
    """`present` with a latex arg."""
    return verdict(label, mark, rule, code(gold), out,
                   lambda: _v(R.found(R.Latex(gold), views.html(html(out)))), **kw)


def order(label, mark, rule, before, after, out, md=0, **kw) -> Case:
    gold = f"{code(before)} before {code(after)}" + (f" (md {md})" if md else "")
    return verdict(label, mark, rule, gold, out,
                   lambda: _v(R.order(R.Order(before, after, md), views.html(html(out)))), **kw)


def repeat(label, mark, rule, gold, count, out, **kw) -> Case:
    return verdict(label, mark, rule, f"{code(gold)} ×{count}", out,
                   lambda: _v(R.repeat(R.Repeat(gold, count), views.html(html(out)))), **kw)


def near_empty(label, mark, rule, max_chars, out, **kw) -> Case:
    return verdict(label, mark, rule, f"at most {max_chars}", out,
                   lambda: _v(R.page_near_empty(R.PageNearEmpty(max_chars), views.html(html(out)))), **kw)


def cell(label, mark, rule, gold, out, md=0, headings=(), section=None, row_groups=(), **rel) -> Case:
    """`table_cell`; `out` is html, or a fixture name (`cell_fixture`) with optional replacements."""
    kw = {k: rel.pop(k) for k in ("show", "why") if k in rel}
    shown = [_md(gold, md)] + [f"{k} {code(v)}" for k, v in rel.items()]
    shown += [f"headings {' > '.join(code(h) for h in headings)}"] if headings else []
    shown += [f"section {code(section)}"] if section else []
    shown += [f"row groups {' > '.join(code(g) for g in row_groups)}"] if row_groups else []
    t = R.TableCell(gold, rel, md, tuple(headings), section, tuple(row_groups))
    return verdict(label, mark, rule, ", ".join(shown), out,
                   lambda: _v(R.table_cell(t, views.html(out))), **kw)


PLACE = ((0.2, 0.2, 0.6, 0.25),)


def layout(label, mark, rule, kind, blocks: Sequence[tuple[str, tuple[float, ...]]], text: str = "",
           **kw) -> Case:
    """`layout_kind` for a line whose place is `PLACE`; `blocks` are (label, bbox)."""
    raw = [{"label": b, "bbox": list(box), "text": text} for b, box in blocks]
    shown = "; ".join(f"{b} {list(box)}" for b, box in blocks) or "no blocks"
    t = R.LayoutKind(R.Text("x", 0, PLACE), kind)
    return verdict(label, mark, rule, code(kind), "", lambda: _v(R.layout_kind(t, views.blocks(raw))),
                   show=code(shown) if blocks else shown, **kw)


# ----------------------------------------------------------------------------------------------- readings


def reading(label: str, rule: str, shown: str, expect: str, run: Callable[[], str]) -> Case:
    return Case(label, rule, shown, "", expect, lambda: (run(), ""))


def folds(label: str, rule: str, out: str, expect: str, show: str | None = None) -> Case:
    """What an html output reads as after `fold` (the text every text test compares)."""
    return reading(label, rule, show if show is not None else code(out), expect,
                   lambda: normalize.fold(views.html(html(out)).text))


def gold_number(label: str, rule: str, gold: str, expect: str) -> Case:
    """How a gold number is read: its digits ("." the decimal point), or "refused" when it does not load."""
    def run() -> str:
        n = R.number(gold)
        return "refused" if n is None else ("-" if n.negative else "") + n.core + ("%" if n.percent else "")
    return reading(label, rule, code(gold), expect, run)


# ----------------------------------------------------------------------------------------------- rendering


def show_result(c: Case, result: str, detail: str) -> str:
    if c.mark == "":
        return code(result)
    return f"{result}: {code(detail)}" if c.why and result == "fail" else result


HEADERS = {"verdict": "| | difference | gold | output | verdict | case |\n|---|---|---|---|---|---|\n",
           "reading": "| rule | input | reads as | case |\n|---|---|---|---|\n"}


def render(t: Table, results: dict[str, tuple[str, str]]) -> str:
    rows = []
    for c in t.cases:
        r = show_result(c, *results[c.label])
        if t.kind == "verdict":
            rows.append(f"| {c.mark} | {c.rule} | {c.gold} | {c.output} | {r} | `{c.label}` |")
        else:
            rows.append(f"| {c.rule} | {c.gold} | {r} | `{c.label}` |")
    return HEADERS[t.kind] + "\n".join(rows) + "\n"


CITE = re.compile(r"\(cases? (`?[a-z0-9-]+`?(?:, `?[a-z0-9-]+`?)*)\)")


def cited(markdown: str) -> list[str]:
    """The case labels a page cites in prose, as `(case label)` or `(cases a, b)`."""
    return [x.strip(" `") for m in CITE.finditer(markdown) for x in m[1].split(",")]
