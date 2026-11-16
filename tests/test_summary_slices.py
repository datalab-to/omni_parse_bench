"""The summary's effective documents, and its marker for keys that select the same tests."""

import subprocess
import sys

import pytest

from omni_parse_bench import pooling
from omni_parse_bench.scorers import unit_tests
from omni_parse_bench.scorers.unit_tests import unit_tests as scorer


def line(test_id, *, document="d", page=None, suite="s", tags=(), derivation="authored", ok=True,
         test_type="present"):
    """A test line, as `lines` writes it, for `summarize`."""
    return {"page_id": page or document, "document": document, "suite": suite, "test_id": test_id,
            "test_type": test_type, "derivation": derivation, "tags": list(tags),
            "result": "pass" if ok else "fail",
            "args": {"content": {"text": test_id, "max_diffs": 0}}}


def test_effective_documents_on_small_known_examples():
    assert pooling.effective_documents([4, 4, 4]) == 3
    assert pooling.effective_documents([3, 1]) == pytest.approx(1.6)
    assert pooling.effective_documents([]) == 0


def test_every_entry_has_effective_documents_equal_to_documents_for_equal_documents():
    xs = [line(f"t{i}", document=f"d{i // 2}", tags=["a"]) for i in range(8)]     # 4 documents of 2 tests
    s = unit_tests.summarize(xs)
    for entry in (s["families"]["text"], s["per_tag"]["a"], s["per_suite"]["s"],
                  s["per_test_type"]["present"], s["per_derivation"]["authored"], s["per_arg_kind"]["text"]):
        assert (entry["documents"], entry["effective_documents"]) == (4, 4.0), entry


def test_effective_documents_is_smaller_for_skewed_documents_and_sums_a_documents_pages():
    xs = [line("a1", document="d1", page="p1"), line("a2", document="d1", page="p2"),
          line("a3", document="d1", page="p2"), line("b1", document="d2")]
    got = unit_tests.summarize(xs)["families"]["text"]
    assert got["documents"] == 2
    assert got["effective_documents"] == 1.6     # d1 holds 3 tests, d2 holds 1: 16 / 10


def test_a_summary_keeps_its_scores_next_to_the_new_keys():
    xs = [line("a", ok=True, tags=["x"]), line("b", ok=False, tags=["x"])]
    s = unit_tests.summarize(xs)
    assert s["score"] == 0.5 and s["families"]["text"]["score"] == 0.5 and s["per_tag"]["x"]["score"] == 0.5


def test_keys_with_identical_tests_are_twins_and_entries_without_twins_have_no_marker():
    xs = [line("a", tags=["rus", "Cyrl"]), line("b", tags=["rus", "Cyrl"], ok=False),
          line("c", tags=["lone"])]
    tags = unit_tests.summarize(xs)["per_tag"]
    assert tags["rus"]["same_tests_as"] == ["Cyrl"] and tags["Cyrl"]["same_tests_as"] == ["rus"]
    assert "same_tests_as" not in tags["lone"]


def test_equal_counts_with_different_tests_are_not_twins():
    xs = [line("a", tags=["x"]), line("b", tags=["y"])]       # one test each, different ids
    tags = unit_tests.summarize(xs)["per_tag"]
    assert (tags["x"]["tests"], tags["x"]["score"]) == (tags["y"]["tests"], tags["y"]["score"])
    assert "same_tests_as" not in tags["x"] and "same_tests_as" not in tags["y"]


def test_three_way_twins_list_the_other_two_sorted():
    xs = [line("a", tags=["c", "a", "b"]), line("b", tags=["a", "b", "c"])]
    tags = unit_tests.summarize(xs)["per_tag"]
    assert tags["a"]["same_tests_as"] == ["b", "c"] and tags["c"]["same_tests_as"] == ["a", "b"]


def test_arg_kinds_can_be_twins_and_families_never_carry_the_marker():
    mixed = {"x": {"latex": "x"}, "y": {"number": "1"}}          # one test, counted under number and latex
    xs = [{**line("a"), "args": mixed}, line("b")]
    s = unit_tests.summarize(xs)
    assert s["per_arg_kind"]["number"]["same_tests_as"] == ["latex"]
    assert s["per_arg_kind"]["latex"]["same_tests_as"] == ["number"]
    assert "same_tests_as" not in s["per_arg_kind"]["text"]
    assert all("same_tests_as" not in e for e in s["families"].values())


def score_line(document, suite, count_by_key, ids_by_key, page_ids=None):
    """A score line for `summarize` with `{kind: {key: (tests, passed)}}` and digests `ids_by_key`."""
    c = {kind: {k: {"tests": t, "passed": p, **({"ids": ids_by_key[kind][k]} if kind in ids_by_key else {})}
                for k, (t, p) in ks.items()} for kind, ks in count_by_key.items()}
    tests = sum(t for t, _ in count_by_key["per_family"].values())
    return {"id": document, "row": {"document": document, "suite": suite}, "tests": tests,
            "passed": sum(p for _, p in count_by_key["per_family"].values()),
            **({"ids": page_ids} if page_ids is not None else {}), **c}


def test_suites_and_derivations_twin_by_digest_across_score_lines():
    counts = {"per_family": {"text": (2, 1)}, "per_derivation": {"A": (2, 1), "B": (2, 1)},
              "per_tag": {}, "per_test_type": {}, "per_arg_kind": {}}
    ids = {"per_family": {"text": 5}, "per_derivation": {"A": 7, "B": 7}, "per_tag": {}, "per_test_type": {},
           "per_arg_kind": {}}
    s = scorer._summary([score_line("d", "s", counts, ids, page_ids=5)])
    assert s["per_derivation"]["A"]["same_tests_as"] == ["B"]
    ids["per_derivation"]["B"] = 8
    s = scorer._summary([score_line("d", "s", counts, ids, page_ids=5)])
    assert "same_tests_as" not in s["per_derivation"]["A"]
    # two suites holding one page each, with the same digest and count, are twins
    a, b = (score_line(d, su, counts, ids, page_ids=9) for d, su in (("d1", "s1"), ("d2", "s2")))
    s = scorer._summary([a, b])
    assert s["per_suite"]["s1"]["same_tests_as"] == ["s2"]


def test_lines_graded_before_the_digest_make_no_twins_and_do_not_crash():
    counts = {"per_family": {"text": (1, 1)}, "per_tag": {"x": (1, 1), "y": (1, 1)}, "per_test_type": {},
              "per_arg_kind": {}, "per_derivation": {}}
    ids = {"per_family": {"text": 5}, "per_tag": {"x": 3, "y": 3}}
    new = score_line("d1", "s", counts, ids, page_ids=5)
    old = score_line("d2", "s", counts, {}, page_ids=None)
    assert "same_tests_as" in scorer._summary([new])["per_tag"]["x"]
    for pages in ([old], [new, old], [old, new]):
        s = scorer._summary(pages)
        assert "same_tests_as" not in s["per_tag"]["x"] and "same_tests_as" not in s["per_suite"]["s"]
        assert s["per_tag"]["x"]["tests"] == len(pages)


def test_a_key_held_by_old_pages_is_not_a_twin_of_a_key_new_pages_hold():
    both = {"per_family": {"text": (2, 2)}, "per_tag": {"x": (1, 1), "y": (1, 1)}, "per_test_type": {},
            "per_arg_kind": {}, "per_derivation": {}}
    only_x = {"per_family": {"text": (1, 1)}, "per_tag": {"x": (1, 1)}, "per_test_type": {},
              "per_arg_kind": {}, "per_derivation": {}}
    new = score_line("d1", "s", both, {"per_family": {"text": 1}, "per_tag": {"x": 6, "y": 6}}, page_ids=1)
    old = score_line("d2", "s", only_x, {}, page_ids=None)
    s = scorer._summary([new, old])
    assert "same_tests_as" not in s["per_tag"]["y"] and "same_tests_as" not in s["per_tag"]["x"]


def test_the_digest_does_not_depend_on_the_order_of_tests_or_pages_and_is_stable():
    ids = [f"test-{i}" for i in range(50)]
    assert scorer._ids(ids) == scorer._ids(reversed(ids)) == scorer._ids(sorted(ids))
    assert scorer._ids(["a"]) != scorer._ids(["b"]) and scorer._ids([]) == 0
    xs = [line(f"t{i}", document=f"d{i}", tags=["x", "y"]) for i in range(6)]
    a = unit_tests.summarize(xs)
    b = unit_tests.summarize(list(reversed(xs)))
    assert a == b and a["per_tag"]["x"]["same_tests_as"] == ["y"]
    # blake2b, not hash(): the same value in another interpreter with another hash seed
    code = ("from omni_parse_bench.scorers.unit_tests import unit_tests as u; print(u._ids(['a', 'b', 'c']))")
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                           env={"PYTHONHASHSEED": str(seed), "PATH": ""}).stdout for seed in (1, 2)}
    assert outs == {f"{scorer._ids(['a', 'b', 'c'])}\n"}


def test_a_scored_page_carries_digests_that_summarize_reads_alike(tmp_path):
    from tests.test_scorer import PAGE, TESTS   # the scorer tests' own page
    sc = scorer.UnitTests().score({"html": "<p>alpha beta</p>"}, TESTS)
    ln = {"id": "p", "row": scorer.UnitTests().row_fields(PAGE), **sc.result}
    via_scores = scorer.UnitTests().summarize([ln])
    via_tests = unit_tests.summarize(unit_tests.lines(unit_tests.score({"html": "<p>alpha beta</p>"}, TESTS),
                                                      TESTS, PAGE))
    assert via_scores == via_tests
