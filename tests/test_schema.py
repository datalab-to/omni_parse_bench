# ruff: noqa: E501
"""The contract's table (schema.py), its quantifiers (quantifiers.py) and the gate they give an empty output."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import pytest

from omni_parse_bench import vocab
from omni_parse_bench.scorers.unit_tests import quantifiers as q
from omni_parse_bench.scorers.unit_tests import runners, schema, tests

DOC = Path(__file__).resolve().parent.parent / "docs" / "scoring" / "schema.md"


class W(NamedTuple):
    lo: int
    hi: int


def test_every_test_type_has_a_row_and_the_vocabulary_agrees():
    assert set(schema.TYPES) == set(runners.TYPES) == set(vocab.READS) == set(vocab.FAMILIES)
    for r in schema.ROWS:
        assert vocab.READS[r.type] == r.reads and vocab.FAMILIES[r.type] == r.family


def test_the_loader_reads_its_roles_from_the_table():
    assert tests.ARG_ROLES == schema.roles() and tests.REQUIRED == schema.required()


def test_the_gate_of_an_empty_output_is_the_tables():
    negative = {r.type for r in schema.ROWS if r.gate == schema.BLANK}
    assert negative == {"present", "no_excess_repeats", "layout_absent"}
    assert schema.SCHEMA["present.absent"].gate == schema.BLANK and schema.SCHEMA["present"].gate == schema.FAIL
    assert schema.SCHEMA["repeat"].gate == schema.COUNTED == schema.SCHEMA["page_near_empty"].gate
    assert runners.negative(runners.NoExcessRepeats(runners.Text("x", 0)))
    assert not runners.negative(runners.Repeat(runners.Text("x", 0), 1))


def test_the_page_shows_the_table():
    assert DOC.read_text(encoding="utf-8").count(schema.render()) == 1, (
        "docs/scoring/schema.md differs from schema.render(); regenerate its table"
    )


def test_a_selection_keeps_the_leftmost_longest_and_drops_overlaps():
    cands = [W(0, 1), W(0, 3), W(3, 4), W(5, 6), W(2, 5)]
    assert [tuple(c) for c in q.select(cands)] == [(0, 3), (3, 4), (5, 6)]


def test_a_selection_reads_positions_so_a_shared_space_overlaps():
    # two windows whose content is disjoint but that both cover the space between them are one candidate
    assert [tuple(c) for c in q.select([W(0, 3), W(2, 5)])] == [(0, 3)]
    assert [tuple(c) for c in q.select([W(0, 2), W(2, 4)])] == [(0, 2), (2, 4)]


def test_the_quantifiers():
    assert q.exists([W(0, 1)]) and not q.exists([])
    assert q.not_exists([]) and not q.not_exists([W(0, 1)])
    assert q.unique([W(0, 1), W(0, 1)]) and not q.unique([W(0, 1), W(1, 2)]) and not q.unique([])
    assert q.count([W(0, 1), W(1, 2)], 2) and not q.count([W(0, 1), W(1, 2)], 3) and q.count([], 0)
    assert q.count([W(0, 1)], 1, 3) and not q.count([W(0, 1), W(1, 2), W(2, 3), W(3, 4)], 1, 3)
    assert q.every([1, 2], lambda a: a > 0) and not q.every([], lambda a: True) and not q.every([1, 0], lambda a: a)
    assert q.locator_and_not([W(0, 1)], []) and not q.locator_and_not([], []) and not q.locator_and_not([W(0, 1)], [W(1, 2)])


@pytest.mark.parametrize("row", schema.ROWS, ids=lambda r: r.name)
def test_a_row_is_well_formed(row):
    assert row.quantifier in schema.QUANTIFIERS and row.gate in schema.GATES
    assert set(row.required) <= set(row.roles)


def test_the_label_order_is_list_and_form_below_text_only():
    le = schema.label_le
    assert le("list", "text") and le("form", "text") and le("text", "text") and le("list", "list")
    assert not le("text", "list") and not le("caption", "text") and not le("footnote", "text")
    assert not le("list", "form") and not le("heading", "text")
    assert runners.AS_TEXT == schema.below("text")


def test_layout_absent_reads_the_label_order_when_the_switch_is_on():
    from omni_parse_bench import switches
    from omni_parse_bench.views import Block

    blocks = [Block("list", (0.0, 0.0, 1.0, 1.0), "a list")]
    t = runners.LayoutAbsent(("text",))
    with switches.using(label_order=False):
        assert runners.layout_absent(t, blocks)[0]
    with switches.using(label_order=True):
        assert not runners.layout_absent(t, blocks)[0]
        assert runners.layout_absent(runners.LayoutAbsent(("form",)), blocks)[0]


def _order(i: str, before: str, after: str):
    return tests.parse("p", {"tests": [{
        "id": i, "derivation": "authored", "tags": [], "output_type": "html", "test_type": "order",
        "args": {"before": {"text": before, "max_diffs": 0}, "after": {"text": after, "max_diffs": 0}},
        "settings": {}}]})[0]


def test_the_order_lint_flags_a_pair_that_can_pass_on_unrelated_copies():
    ts = [_order("same", "Total Due", "total due"), _order("inside", "Total", "Total Due"),
          _order("ok", "Total Due", "Signature"), _order("twice", "Total", "Signature")]
    flagged = dict(tests.order_lint(ts))
    assert set(flagged) == {"same", "inside"}
    assert {i for i, _ in tests.order_lint(ts, "Total and Total then Signature")} == {"same", "inside", "twice"}


def test_a_table_cell_with_a_shape_is_a_for_all_row():
    plain = runners.TableCell(runners.Text("x", 0), {}, 0, (), None, (), {})
    shaped = plain._replace(shapes={"right": "empty"})
    assert schema.variant("table_cell", plain).quantifier == schema.EXISTS
    assert schema.variant("table_cell", shaped).quantifier == schema.ALL


def test_a_negative_format_test_is_a_locator_and_a_claim():
    from omni_parse_bench import switches, views

    t = runners.Format(None, "Total", None, 0, (), ("bold",))
    plain, bold = views.html("<p>Total due</p>"), views.html("<p><b>Total</b> due</p>")
    absent_target = views.html("<p>Nothing here</p>")
    with switches.using(format_locator=False):
        assert not runners.format_mark(t, plain)[0]          # no marks anywhere: nothing shows one could be
    with switches.using(format_locator=True):
        assert runners.format_mark(t, plain)[0]              # the target is there and carries no bold
        assert not runners.format_mark(t, bold)[0]           # the claim has a witness
        assert not runners.format_mark(t, absent_target)[0]  # the locator has none
        assert not runners.format_mark(t, views.html(""))[0]
