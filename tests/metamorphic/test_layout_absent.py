# ruff: noqa: E501
"""Relations of `layout_absent` tests (M174 to M177): a block of a forbidden kind added anywhere fails the test;
a block of an allowed kind added, or a block relabeled within the allowed kinds, keeps the verdict; order,
boxes and text never change it; and on the loaded layout tests' own blocks the verdict is exactly whether the
block's label is forbidden."""
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from metamorphic.common import HOLDS, LAYOUT, relation
from omni_parse_bench import views
from omni_parse_bench.scorers.unit_tests import runners

KINDS = [k for k in views.LABELS if k != "text"]     # what a test may forbid
BLANK = ("heading", "table", "caption", "equation", "footnote", "list", "code")

COORD = st.floats(0, 1, allow_nan=False)


@st.composite
def a_box(draw):
    x0, x1 = sorted((draw(COORD), draw(COORD)))
    y0, y1 = sorted((draw(COORD), draw(COORD)))
    return (x0, y0, x1, y1)


@st.composite
def a_test(draw):
    """A kinds set (the blank-page set, or any non-empty set of labels other than text) and the labels it
    allows."""
    kinds = draw(st.one_of(st.just(BLANK), st.lists(st.sampled_from(KINDS), min_size=1, unique=True).map(tuple)))
    return runners.LayoutAbsent(kinds), [k for k in views.LABELS if k not in kinds]


def blocks_of(labels, boxes, texts=None) -> tuple[views.Block, ...]:
    raw = [{"label": b, "bbox": list(box), "text": (texts or [""] * len(labels))[i]}
           for i, (b, box) in enumerate(zip(labels, boxes, strict=True))]
    return views.blocks(raw)


def passes(t, blocks) -> bool:
    return runners.layout_absent(t, blocks)[0]


@relation(HOLDS, domain="random kinds sets (the blank-page set, or any set of labels but text) x 0 to 6 blocks "
                        "of allowed labels x a forbidden block of any label in the set, any box, at any place in "
                        "the list")
@given(a_test(), st.data())
def test_a_forbidden_block_added_anywhere_fails(test, data):
    """A block list of allowed labels passes; the same list with one block of a forbidden label added, at any
    position, with any box (a whole page or a sliver) and any text, fails. [M174]
    Why it matters for a score: an invented heading, table or equation on a blank page is caught wherever and
    however small the system draws it."""
    t, allowed = test
    labels = data.draw(st.lists(st.sampled_from(allowed), max_size=6)) if allowed else []
    boxes = data.draw(st.lists(a_box(), min_size=len(labels), max_size=len(labels)))
    assert passes(t, blocks_of(labels, boxes))
    i = data.draw(st.integers(0, len(labels)))
    bad = data.draw(st.sampled_from(t.kinds))
    labels2, boxes2 = [*labels[:i], bad, *labels[i:]], [*boxes[:i], data.draw(a_box()), *boxes[i:]]
    assert not passes(t, blocks_of(labels2, boxes2)), (t.kinds, labels2)


@relation(HOLDS, domain="random kinds sets x 0 to 6 blocks of any label x an allowed block added at any place, "
                        "or an allowed block relabeled to another allowed label")
@given(a_test(), st.data())
def test_an_allowed_block_added_or_relabeled_within_the_allowed_kinds_keeps_the_verdict(test, data):
    """For any block list, passing or failing, adding a block whose label the test allows, at any position, or
    relabelling a block from one allowed label to another, keeps the verdict. [M175]
    Why it matters for a score: what the test allows (text, a folio as page furniture, a stain as a figure)
    never costs, and how a system splits or names it among the allowed kinds is free."""
    t, allowed = test
    labels = data.draw(st.lists(st.sampled_from(views.LABELS), max_size=6))
    boxes = data.draw(st.lists(a_box(), min_size=len(labels), max_size=len(labels)))
    before = passes(t, blocks_of(labels, boxes))
    if allowed:
        i = data.draw(st.integers(0, len(labels)))
        labels2 = [*labels[:i], data.draw(st.sampled_from(allowed)), *labels[i:]]
        boxes2 = [*boxes[:i], data.draw(a_box()), *boxes[i:]]
        assert passes(t, blocks_of(labels2, boxes2)) is before, (t.kinds, labels2)
        mine = [j for j, b in enumerate(labels) if b in allowed]
        if mine:
            j = data.draw(st.sampled_from(mine))
            labels3 = [*labels[:j], data.draw(st.sampled_from(allowed)), *labels[j + 1:]]
            assert passes(t, blocks_of(labels3, boxes)) is before, (t.kinds, labels3)


@relation(HOLDS, domain="random kinds sets x 0 to 6 blocks of any label x their order shuffled, every box "
                        "replaced, every text replaced")
@given(a_test(), st.data(), st.randoms(use_true_random=False))
def test_order_boxes_and_text_do_not_change_the_verdict(test, data, rnd):
    """Shuffling the blocks, replacing every box, or replacing every block's text keeps the verdict. [M176]
    Why it matters for a score: the test reads labels only, so a system's reading order, geometry and
    transcription never move it."""
    t, _ = test
    labels = data.draw(st.lists(st.sampled_from(views.LABELS), max_size=6))
    boxes = data.draw(st.lists(a_box(), min_size=len(labels), max_size=len(labels)))
    before = passes(t, blocks_of(labels, boxes))
    order = list(range(len(labels)))
    rnd.shuffle(order)
    assert passes(t, blocks_of([labels[i] for i in order], [boxes[i] for i in order])) is before
    new_boxes = data.draw(st.lists(a_box(), min_size=len(labels), max_size=len(labels)))
    assert passes(t, blocks_of(labels, new_boxes)) is before
    texts = data.draw(st.lists(st.text(max_size=20), min_size=len(labels), max_size=len(labels)))
    assert passes(t, blocks_of(labels, boxes, texts)) is before


@relation(HOLDS, domain="every loaded layout_kind test's own block (its label, its place's box, its text) x 3 "
                        "kinds sets (the blank-page set, its own label, every label but its own and text)",
          pool="layout")
def test_on_each_loaded_layout_block_the_verdict_is_whether_its_label_is_forbidden():
    """Each loaded layout_kind test's answer, one block with the test's label over its place, passes a
    layout_absent test exactly when that label is not forbidden: under the blank-page set, under a set of its
    own label alone, and under a set of every other label but text. [M177]
    Why it matters for a score: on the dataset's own labels and places, the verdict is the label check and
    nothing else."""
    bad, n = [], 0
    for lt in LAYOUT:
        xs = lt.params.content.place
        box = (min(b[0] for b in xs), min(b[1] for b in xs), max(b[2] for b in xs), max(b[3] for b in xs))
        blocks = blocks_of([lt.params.kind], [box], [lt.params.content.text])
        others = tuple(k for k in KINDS if k != lt.params.kind)
        for kinds in {BLANK, (lt.params.kind,) if lt.params.kind != "text" else BLANK, others}:
            n += 1
            if passes(runners.LayoutAbsent(kinds), blocks) is (lt.params.kind in kinds):
                bad.append((lt.id, lt.params.kind, kinds))
    assert n, "no loaded layout_kind test"
    assert not bad, f"{len(bad)} of {n} cases break, e.g. {bad[:5]}"
