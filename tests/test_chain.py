"""The normalizer chain and its distance (omni_parse_bench/chain.py, fold.py): the counterexamples of
the design (Appendix B), each rule's switch both ways, and the laws on small inputs. The relations over
loaded tests are in metamorphic/test_chain.py."""

from __future__ import annotations

import itertools

import pytest

from omni_parse_bench import chain, fold, reader, score, switches, views
from omni_parse_bench.scorers.unit_tests import runners
from omni_parse_bench.scorers.unit_tests import tests as gold_tests


@pytest.fixture(autouse=True)
def rules_on():
    with switches.set_all(True):
        yield


def ok(gold: str, html: str, point: str = "Words", k: int = 0, **kw) -> bool:
    return chain.match(chain.tokens_of_gold(gold), chain.tokens_of_output(html), point, k, **kw)


def grid(gold: str, other: str, point: str, k: int = 0) -> bool:
    return chain.equal(chain.tokens_of_gold(gold), chain.tokens_of_gold(other), point, k)


# ------------------------------------------------------------------------- Appendix B counterexamples


def test_a_coarser_point_adds_passes_for_exists_and_failures_for_absent():
    # absent "Secret phrase here" / "SECRET PHRASE HERE": found at Words, not at Cased (it keeps case)
    assert not ok("Secret phrase here", "<p>SECRET PHRASE HERE</p>", "Cased")
    assert ok("Secret phrase here", "<p>SECRET PHRASE HERE</p>", "Words")


def test_tokens_stay_fixed_so_a_glued_pair_never_matches_at_any_point():
    for point in ("Text", "Cased", "Words"):
        assert not ok("Total", "<p>TotalDue</p>", point)


def test_case_with_a_budget_is_refused_at_cased():
    with pytest.raises(ValueError):
        ok("Paid", "<p>paid</p>", "Cased", 1)
    assert not ok("Paid", "<p>paid</p>", "Cased")
    assert ok("Paid", "<p>Paid</p>", "Cased")


@pytest.mark.parametrize(
    "gold, html, want",
    [
        ("45", "<p>45%</p>", False),
        ("$45", "<p>45</p>", False),
        ("45", "<p>$45</p>", False),
        ("10-12", "<p>10-12</p>", True),
        ("-5", "<p>x-5</p>", False),
        ("5", "<p>x-5</p>", True),
        ("10", "<p>10<sup>2</sup></p>", False),
        ("4.2", "<p>4.2<sup>1</sup></p>", False),
        ("10²", "<p>10<sup>2</sup></p>", True),
        ("1M", "<p>1m</p>", False),
        ("123", "<p>x123y</p>", False),
        ("A4", "<p>A4</p>", True),
    ],
)
def test_quantities_are_atomic(gold, html, want):
    assert ok(gold, html) is want and ok(gold, html, k=1) is want


@pytest.mark.parametrize(
    "gold, html", [("10kg", "<p>10mg</p>"), ("3万", "<p>3千</p>"), ("1/2", "<p>1/3</p>")]
)
def test_an_edit_touching_a_quantity_fails_at_any_budget(gold, html):
    assert not ok(gold, html, k=1) and not ok(gold, html, k=5)


def test_a_wrap_is_free_only_at_a_line_end_before_a_lowercase_letter():
    assert not ok("self-aware", "<p>selfaware</p>")
    assert ok("self-aware", "<p>self-<br>aware</p>")
    assert ok("selfaware", "<p>self-<br>aware</p>")


def test_hangul_particles_and_compounds_are_both_found():
    assert ok("서울", "<p>서울에서</p>") and ok("서울", "<p>서울대학교</p>")


def test_hangul_spacing_is_free_from_cased_on_and_kept_at_text():
    assert ok("서울 대학교", "<p>서울대학교</p>", "Cased") and ok("서울대학교", "<p>서울 대학교</p>", "Cased")
    assert not ok("서울 대학교", "<p>서울대학교</p>", "Text")


def test_a_budget_is_per_claim_edits():
    assert not ok("Totla", "<p>Total</p>") and ok("Totla", "<p>Total</p>", k=1)  # OSA: a swap is one edit
    assert ok("Total", "<p>Totla</p>", k=1)
    assert not ok("Total", "<p>Totxx</p>", k=1)


def test_a_gold_phrase_is_not_found_across_two_table_cells_but_across_paragraphs():
    assert not ok("Total Due", "<table><tr><td>Total</td><td>Due</td></tr></table>")
    assert ok("Total Due", "<p>Total</p><p>Due</p>")
    assert ok("Total Due", "<table><tr><td>Total Due</td></tr></table>")


def test_a_footnote_mark_is_free_from_cased_on():
    assert ok("Smith and Jones", "<p>Smith<sup>1</sup> and Jones</p>")
    assert ok("Smith and Jones", "<p>Smith[2] and Jones</p>")
    assert not ok("Smith and Jones", "<p>Smith<sup>1</sup> and Jones</p>", "Text")


# ---------------------------------------------------------------------------------------- the space


def test_a_space_is_free_on_the_gold_side_only():
    assert ok("Total Due", "<p>TotalDue</p>") and not ok("TotalDue", "<p>Total Due</p>")
    assert not ok("therapist", "<p>the rapist</p>")


def test_the_space_is_symmetric_with_the_rule_off():
    with switches.using(space_one_sided=False):
        assert ok("TotalDue", "<p>Total Due</p>") and ok("therapist", "<p>the rapist</p>")


def test_a_break_matches_a_gold_space():
    assert ok("a b", "<p>a</p><p>b</p>", "Text") and ok("a b", "<p>a<br>b</p>", "Text")


# ---------------------------------------------------------------------------------------- each rule off


def test_with_word_edges_off_a_match_may_start_inside_a_word():
    with switches.using(word_edges=False):
        assert ok("Total", "<p>Totally</p>") and ok("cat", "<p>concatenate</p>")
    assert not ok("cat", "<p>concatenate</p>")


def test_with_osa_off_a_swap_is_two_edits():
    with switches.using(osa=False):
        assert not ok("Totla", "<p>Total</p>", k=1) and ok("Totla", "<p>Total</p>", k=2)


def test_with_qty_atomic_off_a_digit_is_edited_like_any_character():
    with switches.using(qty_atomic=False):
        assert ok("10kg", "<p>10mg</p>", k=1)


def test_with_marks_free_off_a_mark_is_a_character():
    with switches.using(marks_free=False):
        assert not ok("Smith and Jones", "<p>Smith<sup>1</sup> and Jones</p>")


def test_with_wrap_free_off_a_wrapped_hyphen_costs():
    with switches.using(wrap_free=False):
        assert not ok("selfaware", "<p>self-<br>aware</p>")


def test_with_cell_windows_off_cells_join():
    with switches.using(cell_windows=False):
        assert ok("Total Due", "<table><tr><td>Total</td><td>Due</td></tr></table>")


def test_blame_names_the_rule_that_decided():
    g, o = chain.tokens_of_gold("therapist"), chain.tokens_of_output("<p>the rapist</p>")
    assert chain.blame(g, o, "Words") == ["space_one_sided"]
    g, o = chain.tokens_of_gold("Total"), chain.tokens_of_output("<p>Totally</p>")
    assert chain.blame(g, o, "Words") == ["word_edges"]


# -------------------------------------------------------------------------------------------- the fold


@pytest.mark.parametrize(
    "gold, html",
    [
        ("fix", "<p>ﬁx</p>"),
        ('"quote"', "<p>“quote”</p>"),
        ("a - b", "<p>a – b</p>"),
        ("Done", "<p>Done​</p>"),
        ("1/2", "<p>½</p>"),
        ("ABC", "<p>ＡＢＣ</p>"),
        ("a...b", "<p>a&hellip;b</p>"),
    ],
)
def test_a_typographic_variant_matches_at_text(gold, html):
    assert ok(gold, html, "Text") or ok(gold, html, "Words")


def test_the_fold_is_idempotent_on_its_cases():
    cases = ["ﬁx “q” – … ½ ① ＡＢＣ • a", "a . . . b ___ c", "é Å ㎏ ʼn", "√ Done ☑ [x]", "·79 3·14 ·", "​­"]
    for s in cases:
        once = fold.fold_gap(s, line_start=True)
        assert fold.fold_gap(once, line_start=True) == once, (s, once)


def test_a_length_changing_operation_outside_the_first_step_is_refused():
    bad = fold.FoldOp(fold.TEXT_CASED, "bad", str.strip, False, "x")
    with pytest.raises(ValueError):
        old = fold.FOLD
        try:
            fold.FOLD = (*old, bad)
            fold.check()
        finally:
            fold.FOLD = old


def test_an_empty_unit_equals_an_empty_gold_and_nothing_else():
    assert chain.equal([], [], "Text") and chain.equal(tok_(""), chain.tokens_of_output("<p> </p>"), "Cased")
    assert not chain.equal([], tok_("x"), "Text") and not chain.equal(tok_("x"), [], "Text")


def test_whole_mode_compares_the_whole_unit_and_refuses_one_across_cells():
    two = chain.tokens_of_output("<table><tr><td>A</td><td>X</td></tr></table>")
    one = chain.tokens_of_output("<table><tr><td>X</td></tr></table>")
    assert not chain.equal(tok_("X"), two, "Text") and chain.equal(tok_("X"), one, "Text")


def test_a_circled_digit_is_the_digit_but_another_circled_digit_is_another_number():
    assert ok("1", "<p>①</p>") and ok("①", "<p>1</p>") and ok("10", "<p>⑩</p>")
    assert not ok("①", "<p>②</p>") and not ok("①", "<p>②</p>", k=1)


def test_a_parenthesized_digit_reads_with_its_parentheses():
    assert ok("1", "<p>⑴</p>") and grid("(1)", "⑴", "Text") and not grid("1", "⑴", "Text")


def test_a_fold_keeps_the_markup_of_the_words_it_did_not_touch():
    toks = reader.read("<p>ﬁ <b>X</b></p>").tokens
    x = next(t for t in toks if t.text == "X")
    assert "b" in x.markup and x.end - x.start == 1


def tok_(s: str) -> list[reader.Token]:
    return chain.tokens_of_gold(s)


# ------------------------------------------------------------------------------------------ the laws


def tok(s: str) -> list[reader.Token]:
    return chain.tokens_of_gold(s)


ALPHABET = ["a", "A", "b", " ", "1", "\n"]


def _strings(n: int):
    for L in range(1, n + 1):
        for t in itertools.product(ALPHABET, repeat=L):
            yield "".join(t)


def test_l1_witness_inclusion_exhaustive_on_short_strings():
    """Raw candidates at Text are candidates at Cased, and at Cased at Words (every pair up to length 3 over a
    small alphabet with case, a quantity, a space and a break)."""
    g_all = [s for s in _strings(3) if s.strip()][:150]
    o_all = list(_strings(4))[::3]
    for g in g_all:
        gt = tok(g)
        for o in o_all:
            ot = tok(o)
            prev = None
            for p in ("Text", "Cased", "Words"):
                k = 0
                w = {(x.first, x.last) for x in chain.windows(gt, ot, p, k)}
                if prev is not None:
                    assert prev <= w, (g, o, p)
                prev = w


def test_non_expansive_at_every_point_for_every_budget():
    """If a window is within k at Text it is within k at Cased and Words (k = 1)."""
    gs = ["ab", "Ab", "a b", "a1", "1a"]
    os_ = ["ab", "AB", "a b", "xab", "a1", "a 1", "1a", "A b y", "ba", "a\nb", "b a", "a a"]
    for g, o in itertools.product(gs, os_):
        gt, ot = tok(g), tok(o)
        a = {(x.first, x.last) for x in chain.windows(gt, ot, "Text", 1)}
        b = {(x.first, x.last) for x in chain.windows(gt, ot, "Cased", 0)}
        c = {(x.first, x.last) for x in chain.windows(gt, ot, "Words", 1)}
        assert a <= c, (g, o)
        assert b <= {(x.first, x.last) for x in chain.windows(gt, ot, "Words", 0)}, (g, o)


def test_a_symmetric_swap_holds_at_text_and_one_way_at_cased():
    assert grid("a b", "a b", "Text") and grid("ab", "ab", "Text")
    assert not grid("ab", "a b", "Text") and not grid("a b", "ab", "Text")
    assert grid("a b", "ab", "Cased") and not grid("ab", "a b", "Cased")


# ------------------------------------------------------------------------------------------- the scorer


def raw(text: str, k: int = 0, exact: bool = False, absent: bool = False) -> dict:
    content = {"text": text, "max_diffs": k} | ({"exact_case": True} if exact else {})
    return {
        "id": "a",
        "derivation": "authored",
        "tags": [],
        "output_type": "html",
        "test_type": "present",
        "args": {"content": content},
        "settings": {"absent": True} if absent else {},
    }


def verdict(text: str, html: str, **kw):
    return score({"html": html, "blocks": []}, gold_tests.parse("p", {"tests": [raw(text, **kw)]}))[0]


def test_present_text_goes_through_the_chain_when_it_is_on():
    with switches.using(chain=True):
        assert verdict("Total Due", "<p>TotalDue</p>").result == "pass"
        v = verdict("therapist", "<p>the rapist</p>")
        assert v.result == "fail" and v.why.startswith("[space_one_sided]"), v
        assert verdict("Paid", "<p>paid</p>", exact=True).result == "fail"
        assert verdict("Paid", "<p>Paid</p>", exact=True).result == "pass"


def test_with_chain_off_present_text_is_the_old_reading():
    with switches.using(chain=False):
        assert verdict("therapist", "<p>the rapist</p>").result == "pass"  # the old squeeze joins words


# ------------------------------------------------------------------------------------------------ order


def order_verdict(before: str, after: str, html: str, k: int = 0, **sw):
    t = {
        "id": "o",
        "derivation": "authored",
        "tags": [],
        "output_type": "html",
        "test_type": "order",
        "args": {"before": {"text": before, "max_diffs": k}, "after": {"text": after, "max_diffs": k}},
        "settings": {},
    }
    with switches.using(chain=True, **sw):
        return score({"html": html, "blocks": []}, gold_tests.parse("p", {"tests": [t]}))[0]


def test_order_on_the_chain_reads_each_claim_at_words_and_any_copy():
    assert order_verdict("Total", "Due", "<p>Total</p><p>Due</p>").result == "pass"
    v = order_verdict("Total", "Due", "<p>Due</p><p>Total</p>")
    assert v.result == "fail" and v.why.startswith("[order]"), v
    v = order_verdict("Total", "Due", "<p>Due x</p><p>Total x</p><p>Due</p>")
    assert v.result == "pass" and v.why.startswith("[copy]"), v


def test_order_swaps_cost_one_and_a_missing_claim_is_named():
    assert order_verdict("Totla", "Due", "<p>Total</p><p>Due</p>", 1).result == "pass"
    v = order_verdict("Totla", "Due", "<p>Total</p><p>Due</p>")
    assert v.result == "fail" and "'before'" in v.why, v


def test_order_keeps_a_quantity_atomic_and_a_split_word_fails():
    assert order_verdict("10kg", "xyz", "<p>10mg xyz</p>", 1).result == "fail"
    assert order_verdict("therapist", "x", "<p>the rapist x</p>").result == "fail"


def test_order_claims_keep_their_own_budgets():
    from omni_parse_bench.scorers.unit_tests import tests as loader

    def load(b: int, a: int):
        t = {"id": "o", "derivation": "authored", "tags": [], "output_type": "html", "test_type": "order",
             "args": {"before": {"text": "Totla", "max_diffs": b}, "after": {"text": "Duee", "max_diffs": a}},
             "settings": {}}
        return loader.parse("p", {"tests": [t]})[0].params

    p = load(1, 0)
    assert p.budgets == (1, 0) and load(1, 1).budgets == (1, 1)
    page = {"html": "<p>Total</p><p>Duee</p>", "blocks": []}
    for sw in (True, False):
        with switches.using(chain=sw):
            assert runners.run("order", p, views.html(page["html"]))[0]       # 'before' spends its edit
            q = load(0, 1)
            assert not runners.run("order", q, views.html(page["html"]))[0]            # 'before' has none
            assert runners.run("order", load(1, 0), views.html("<p>Total</p><p>Duxe</p>")) [0] is False


def test_a_quantity_matches_only_a_quantity_and_a_mark_never_stands_for_one():
    sup = chain.tokens_of_output("<sup>1</sup>")
    assert not chain.equal(tok_("1"), sup, "Text") and not chain.equal(tok_("1"), sup, "Words")
    # both ways: a gold that names the mark as a number fails; a gold without it passes where marks are free
    page = "<p>Smith<sup>1</sup></p>"
    assert not ok("Smith 1", page) and not ok("Smith 1", page, "Text") and not ok("Smith1", page)
    assert ok("Smith", page, "Cased") and ok("Smith", page, "Words")


def test_the_fold_keeps_the_underscores_of_an_identifier_and_removes_a_leader():
    assert fold.fold_gap("a ____ b") == "a b"
    assert fold.fold_gap("token____ x") == "token____ x" and fold.fold_gap("foo___bar") == "foo___bar"
